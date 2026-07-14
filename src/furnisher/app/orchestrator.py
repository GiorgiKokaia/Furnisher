"""Orchestration (docs/08): wires project + catalog + agent + layout engine.
Owns the order things run in; contains no domain logic of its own.
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import quote

from furnisher.agent import DesignAgent, StyleProfile
from furnisher.catalog import Catalog
from furnisher.layout import MAX_FILL_RATIO, PlacementRequest, auto_place, validate
from furnisher.layout.rules import is_underlay
from furnisher.model import FloorPlan
from furnisher.render2d import RenderStyle, render_plan

# words to ignore when matching "replace the coffee table" against placed items
_STOPWORDS = {"the", "a", "an", "my", "our", "this", "that", "with", "for", "please", "item"}


def image_proxy_url(item) -> str | None:
    """Relative URL to the cache-backed image proxy for an item, or None if it has no image.

    Relative (no leading slash) so it resolves correctly both standalone (page at /) and when
    the furnish app is mounted under the hub (page at /furnish/)."""
    return f"api/item-image?id={quote(item.id, safe='')}" if item.image_urls else None


class Orchestrator:
    def __init__(self, project, catalog: Catalog, llm, on_progress=None):
        self.project = project
        self.catalog = catalog
        self.agent = DesignAgent(llm, catalog)
        self.on_progress = on_progress  # callable(str) for live status, e.g. streaming UIs
        self.pending_options = None  # {"room": str, "options": [RoomOption]}
        self.last_inspiration: list[str] = []  # filenames from the most recent inspiration pull

    def _progress(self, message: str) -> None:
        if self.on_progress is not None:
            try:
                self.on_progress(message)
            except Exception:  # a broken progress sink must never break the pipeline
                pass

    def _item_payload(self, item_ref: str) -> dict:
        item = self.catalog.get(item_ref)
        return {
            "id": item.id,
            "name": item.name,
            "type": item.type_name,
            "price": item.price,
            "currency": item.currency,
            "dims": f"{item.width_m * 100:.0f}×{item.depth_m * 100:.0f} cm",
            # served through our own cache-backed proxy (browser hotlinks to the IKEA CDN
            # fail intermittently); resolves relative to the page (standalone or under /furnish)
            "image": image_proxy_url(item),
        }

    def _mini_svg(self, room_id: str, placed: list) -> str:
        """A small standalone render of one room with the proposed furniture, for chat cards."""
        room = self.project.plan.room(room_id)
        mini = FloorPlan(
            name=room.label(),
            ceiling_height=self.project.plan.ceiling_height,
            rooms=[room],
            openings=[op for op in self.project.plan.openings if op.room == room_id],
        )
        return render_plan(
            mini,
            placements=placed,
            catalog=self.catalog,
            style=RenderStyle(scale=34, padding=0.25),
        )

    # --- queries ---
    def style(self) -> StyleProfile | None:
        raw = self.project.meta.get("style_profile")
        return StyleProfile.model_validate(raw) if raw else None

    def budget_remaining(self) -> float | None:
        budget = self.project.meta.get("budget")
        if budget is None:
            return None
        return budget - self.project.spent(self.catalog)

    def render_svg(self) -> Path:
        out = self.project.path / "renders" / "plan.svg"
        out.write_text(
            render_plan(
                self.project.plan, placements=self.project.placements, catalog=self.catalog
            ),
            encoding="utf-8",
        )
        return out

    def shopping_list(self) -> str:
        if not self.project.placements:
            return "nothing placed yet"
        lines = []
        total = 0.0
        for p in self.project.placements:
            item = self.catalog.get(p.item_ref)
            total += item.price
            lines.append(
                f"  {p.room:<12} {item.name} ({item.type_name}) — {item.price:.0f} {item.currency}"
            )
        lines.append(f"  total: {total:.0f} {self.project.meta.get('currency', 'EUR')}")
        return "\n".join(lines)

    # --- mutations (snapshot before, save + re-render after) ---
    def _mutated(self) -> None:
        self.project.save()
        self.render_svg()

    def set_budget(self, amount: float) -> str:
        self.project.snapshot()
        self.project.meta["budget"] = amount
        self._mutated()
        return f"budget set to {amount:.0f} {self.project.meta.get('currency', 'EUR')}"

    def _apply_style_from(self, images: list[Path], notes: str) -> str:
        style = self.agent.extract_style(images, notes)
        self.project.snapshot()
        self.project.meta["style_profile"] = style.model_dump()
        self._mutated()
        return f"style profile updated: {', '.join(style.style_tags) or '(no tags)'}"

    def add_inspiration(self, image: Path, notes: str = "") -> str:
        return self._apply_style_from([image] if image else [], notes or "(from images)")

    @staticmethod
    def _download_image(url: str) -> bytes:
        import httpx

        from furnisher.catalog.adapters.ikea import USER_AGENT

        resp = httpx.get(url, timeout=20, follow_redirects=True, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        return resp.content

    def inspire_from_ikea(self, query: str, notes: str = "") -> str:
        """Pull styled IKEA lifestyle photos for a query into inspiration/ and re-extract style."""
        provider = self.catalog.providers.get("ikea")
        if provider is None or not hasattr(provider, "inspiration_images"):
            return "the IKEA provider isn't available"
        photos = provider.inspiration_images(query)
        if not photos:
            return f"no inspiration photos found for {query!r}"
        dest = self.project.path / "inspiration"
        dest.mkdir(exist_ok=True)
        saved: list[Path] = []
        slug = "".join(c if c.isalnum() else "-" for c in query.lower()).strip("-")
        for n, photo in enumerate(photos):
            try:
                data = self._download_image(photo["url"])
            except Exception:
                continue
            path = dest / f"ikea-{slug}-{n}.jpg"
            path.write_bytes(data)
            saved.append(path)
        if not saved:
            return "could not download any inspiration photos"
        self.last_inspiration = [p.name for p in saved]
        reply = self._apply_style_from(saved, notes or f"IKEA lifestyle photos for: {query}")
        return f"pulled {len(saved)} IKEA photos into inspiration/ — {reply}"

    def _match_placement(self, target: str, room_id: str | None):
        """Best-matching current placement for a free-text description, or None if unclear."""
        candidates = [
            p for p in self.project.placements if room_id is None or p.room == room_id
        ]
        tokens = [t for t in re.findall(r"[a-z0-9]+", target.lower()) if t not in _STOPWORDS]
        if not candidates or not tokens:
            return None
        best, best_score = None, 0
        for p in candidates:
            item = self.catalog.get(p.item_ref)
            haystack = f"{p.id} {item.name} {item.type_name}".lower()
            score = sum(1 for t in tokens if t in haystack)
            if score > best_score:
                best, best_score = p, score
        return best if best_score > 0 else None

    def _placed_items_summary(self, room_id: str | None = None) -> str:
        rows = [
            f"{self.catalog.get(p.item_ref).name} ({self.catalog.get(p.item_ref).type_name})"
            f" in {p.room}"
            for p in self.project.placements
            if room_id is None or p.room == room_id
        ]
        return "; ".join(rows) if rows else "nothing placed yet"

    def replace_item(self, target: str, room_id: str | None, note: str = "") -> dict:
        """Swap one placed item for a different grounded catalog item, keeping its spot."""
        placement = self._match_placement(target, room_id)
        if placement is None:
            return {
                "reply": f"I couldn't tell which item you mean by {target!r}. "
                f"Currently placed: {self._placed_items_summary(room_id)}."
            }
        room_id = placement.room
        current = self.catalog.get(placement.item_ref)

        # budget available for the swap: what's left, plus what removing the old item frees up
        remaining = self.budget_remaining()
        swap_budget = remaining + current.price if remaining is not None else None

        self._progress(f"finding a replacement for {current.name}…")
        new_item = self.agent.propose_replacement(
            self.project.plan,
            room_id,
            current,
            note,
            swap_budget,
            self.project.meta.get("currency", "EUR"),
            on_progress=self._progress,
        )
        if new_item is None:
            return {"reply": f"couldn't find a suitable replacement for {current.name} — try "
                    "different wording or relax the constraint"}
        if new_item.id == current.id:
            return {"reply": f"{current.name} already looks like the best fit — kept it as is"}

        others = [p for p in self.project.placements if p.id != placement.id]
        # first try to keep the exact spot; fall back to re-placing the one item in the room
        trial = placement.model_copy(deep=True)
        trial.item_ref = new_item.id
        errors = [
            i
            for i in validate(self.project.plan, [*others, trial], self.catalog)
            if i.severity == "error" and placement.id in i.placements
        ]
        if errors:
            self._progress("fitting the new item…")
            placed, issues = auto_place(
                self.project.plan,
                room_id,
                [PlacementRequest(item=new_item, purpose=placement.id)],
                self.catalog,
                existing=others,
            )
            if not placed:
                msg = issues[0].message if issues else "no legal position"
                return {"reply": f"{new_item.name} doesn't fit where {current.name} was ({msg}) "
                        "— try a smaller replacement"}
            new_placement = placed[0]
        else:
            new_placement = trial

        self.project.snapshot()
        self.project.placements = [*others, new_placement]
        self._mutated()

        currency = self.project.meta.get("currency", "EUR")
        lines = [
            f"Replaced {current.name} with {new_item.name} "
            f"({new_item.type_name}, {new_item.price:.0f} {currency}) in {room_id} "
            f"-> {new_placement.position}.",
            f"  was: {current.name} at {current.price:.0f} {currency}",
        ]
        delta = new_item.price - current.price
        lines.append(f"  price change: {delta:+.0f} {currency}")
        rem = self.budget_remaining()
        if rem is not None:
            lines.append(f"  budget remaining: {rem:.0f} {currency}")
        return {"reply": "\n".join(lines), "placed": [self._item_payload(new_item.id)]}

    def clear_room(self, room_id: str) -> str:
        self.project.snapshot()
        before = len(self.project.placements)
        self.project.placements = [p for p in self.project.placements if p.room != room_id]
        self._mutated()
        return f"removed {before - len(self.project.placements)} items from {room_id!r}"

    def _resolve_room(self, room_id: str | None) -> str | None:
        """Which room an add/remove targets: the stated one, else the only furnished room,
        else the only room — otherwise None (caller asks the user)."""
        if room_id and any(r.id == room_id for r in self.project.plan.rooms):
            return room_id
        furnished = {p.room for p in self.project.placements}
        if len(furnished) == 1:
            return next(iter(furnished))
        if len(self.project.plan.rooms) == 1:
            return self.project.plan.rooms[0].id
        return None

    def add_item(self, target: str, room_id: str | None, note: str = "") -> dict:
        """Add a single grounded catalog item to a room, keeping everything already placed."""
        room_id = self._resolve_room(room_id)
        if room_id is None:
            rooms = ", ".join(r.id for r in self.project.plan.rooms)
            return {"reply": f"which room should I add that to? ({rooms})"}
        currency = self.project.meta.get("currency", "EUR")
        existing_names = [
            self.catalog.get(p.item_ref).name
            for p in self.project.placements
            if p.room == room_id
        ]
        item = self.agent.propose_addition(
            self.project.plan,
            room_id,
            target,
            note,
            self.budget_remaining(),
            currency,
            existing_names,
            on_progress=self._progress,
        )
        if item is None:
            return {"reply": f"couldn't find {target!r} in the catalog — try different wording"}
        self._progress(f"placing the {item.name}…")
        hint = "center" if is_underlay(item) else "wall"
        placed, issues = auto_place(
            self.project.plan,
            room_id,
            [PlacementRequest(item=item, purpose=item.type_name, hint=hint)],
            self.catalog,
            existing=self.project.placements,
            max_fill_ratio=MAX_FILL_RATIO,
        )
        if not placed:
            msg = issues[0].message if issues else "no legal spot"
            return {"reply": f"couldn't add {item.name} to {room_id}: {msg}"}
        self.project.snapshot()
        self.project.placements = self.project.placements + placed
        self._mutated()
        lines = [
            f"Added {item.name} ({item.type_name}, {item.price:.0f} {currency}) to {room_id} "
            f"-> {placed[0].position}."
        ]
        for issue in issues:
            lines.append(f"  ~ {issue.message}")
        rem = self.budget_remaining()
        if rem is not None:
            lines.append(f"  budget remaining: {rem:.0f} {currency}")
        return {"reply": "\n".join(lines), "placed": [self._item_payload(item.id)]}

    def remove_item(self, target: str, room_id: str | None) -> dict:
        """Remove one placed item matched by description; keep the rest of the room."""
        placement = self._match_placement(target, room_id)
        if placement is None:
            return {
                "reply": f"I couldn't tell which item you mean by {target!r}. "
                f"Currently placed: {self._placed_items_summary(room_id)}."
            }
        item = self.catalog.get(placement.item_ref)
        self.project.snapshot()
        self.project.placements = [p for p in self.project.placements if p.id != placement.id]
        self._mutated()
        return {"reply": f"Removed {item.name} ({item.type_name}) from {placement.room}."}

    def furnish_room(self, room_id: str, note: str = "") -> dict:
        """Step 1 of furnishing: agent researches and returns options; nothing is placed
        until the user picks one (choose_option)."""
        # budget for this room excludes items already in it — re-furnishing replaces them
        budget = self.project.meta.get("budget")
        room_budget = None
        if budget is not None:
            spent_elsewhere = sum(
                self.catalog.get(p.item_ref).price
                for p in self.project.placements
                if p.room != room_id
            )
            room_budget = budget - spent_elsewhere
        self._progress(f"designing options for {room_id}…")
        options, _reasoning = self.agent.propose_options(
            self.project.plan,
            room_id,
            self.style(),
            room_budget,
            self.project.meta.get("currency", "EUR"),
            note,
            on_progress=self._progress,
        )
        if not options:
            return {
                "reply": "the agent came back with no placeable items — "
                "try rephrasing or setting a budget"
            }
        # lay each option out now (deterministic) so the card can show a mini floor plan and
        # choosing reuses the exact placement it previewed
        self._progress("laying out the options…")
        kept_other_rooms = [p for p in self.project.placements if p.room != room_id]
        self.pending_options = {"room": room_id, "entries": []}
        payload = []
        for option in options:
            requests = [
                PlacementRequest(
                    item=self.catalog.get(p.item_id),
                    purpose=p.purpose,
                    hint=p.hint,
                    anchor=p.anchor,
                )
                for p in option.items
            ]
            placed, issues = auto_place(
                self.project.plan,
                room_id,
                requests,
                self.catalog,
                existing=kept_other_rooms,
                max_fill_ratio=MAX_FILL_RATIO,
            )
            self.pending_options["entries"].append(
                {"option": option, "placed": placed, "issues": issues}
            )
            items = [self._item_payload(p.item_id) for p in option.items]
            payload.append(
                {
                    "label": option.label,
                    "rationale": option.rationale,
                    "items": items,
                    "total": sum(i["price"] for i in items),
                    "currency": items[0]["currency"] if items else "",
                    "svg": self._mini_svg(room_id, placed) if placed else "",
                    "placed": len(placed),
                    "requested": len(option.items),
                }
            )
        lines = [f"I put together {len(options)} options for {room_id} — pick one:"]
        for n, option in enumerate(payload, start=1):
            names = ", ".join(i["name"] for i in option["items"])
            lines.append(
                f"  {n}. {option['label']} — {names} ({option['total']:.0f} {option['currency']})"
            )
        return {"reply": "\n".join(lines), "options": payload}

    def choose_option(self, index: int) -> dict:
        """Step 2: place the chosen option's items (reusing the layout previewed in step 1)."""
        if not self.pending_options:
            return {"reply": "no options pending — ask me to furnish a room first"}
        entries = self.pending_options["entries"]
        if not 0 <= index < len(entries):
            return {"reply": f"pick 1-{len(entries)}"}
        room_id = self.pending_options["room"]
        entry = entries[index]
        option, placed, issues = entry["option"], entry["placed"], entry["issues"]
        self.pending_options = None

        self._progress("placing the furniture…")
        kept_other_rooms = [p for p in self.project.placements if p.room != room_id]
        self.project.snapshot()
        self.project.placements = kept_other_rooms + placed
        self._mutated()

        lines = [f"{option.label} it is. " + (option.rationale.strip() or "")]
        for placement in placed:
            item = self.catalog.get(placement.item_ref)
            lines.append(
                # "->" not "→": Windows consoles are often cp1252 and choke on U+2192
                f"  + {item.name} ({item.type_name}, {item.price:.0f} {item.currency}) "
                f"-> {placement.room} at {placement.position}"
            )
        for issue in issues:
            lines.append(f"  ! {issue.message}")
        warnings = [
            i
            for i in validate(self.project.plan, self.project.placements, self.catalog)
            if i.severity == "warning"
        ]
        for warning in warnings:
            lines.append(f"  ~ {warning.message}")
        remaining = self.budget_remaining()
        if remaining is not None:
            lines.append(f"  budget remaining: {remaining:.0f} {self.project.meta['currency']}")
        return {
            "reply": "\n".join(lines),
            "placed": [self._item_payload(p.item_ref) for p in placed],
        }

    # --- free chat / routing ---
    def handle_message(self, message: str) -> dict:
        """Returns {"reply": str, "options": [...]?, "placed": [...]?}."""
        self.project.append_chat("user", message)
        stripped = message.strip()
        if self.pending_options and stripped.isdigit():
            result = self.choose_option(int(stripped) - 1)
        else:
            self._progress("understanding the request…")
            intent = self.agent.route(message, self.project.plan)
            if intent.action == "furnish_room" and intent.room_id:
                result = self.furnish_room(intent.room_id, intent.note)
            elif intent.action == "set_budget" and intent.budget is not None:
                result = {"reply": self.set_budget(intent.budget)}
            elif intent.action == "clear_room" and intent.room_id:
                result = {"reply": self.clear_room(intent.room_id)}
            elif intent.action == "add_item":
                result = self.add_item(intent.target, intent.room_id, intent.note)
            elif intent.action == "remove_item":
                result = self.remove_item(intent.target, intent.room_id)
            elif intent.action == "replace_item":
                result = self.replace_item(intent.target, intent.room_id, intent.note)
            else:
                context = (
                    f"You are a furnishing assistant for the apartment "
                    f"{self.project.meta['name']!r}. "
                    f"Rooms: {', '.join(r.id for r in self.project.plan.rooms)}. "
                    f"Current shopping list:\n{self.shopping_list()}\n"
                    "Answer briefly and concretely."
                )
                result = {"reply": self.agent.llm.complete(message, system=context)}
        self.project.append_chat("assistant", result["reply"])
        return result
