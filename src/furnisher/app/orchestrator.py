"""Orchestration (docs/08): wires project + catalog + agent + layout engine.
Owns the order things run in; contains no domain logic of its own.
"""

from __future__ import annotations

from pathlib import Path

from furnisher.agent import DesignAgent, StyleProfile
from furnisher.catalog import Catalog
from furnisher.layout import PlacementRequest, auto_place, validate
from furnisher.render2d import render_plan


class Orchestrator:
    def __init__(self, project, catalog: Catalog, llm):
        self.project = project
        self.catalog = catalog
        self.agent = DesignAgent(llm, catalog)

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
        reply = self._apply_style_from(saved, notes or f"IKEA lifestyle photos for: {query}")
        return f"pulled {len(saved)} IKEA photos into inspiration/ — {reply}"

    def clear_room(self, room_id: str) -> str:
        self.project.snapshot()
        before = len(self.project.placements)
        self.project.placements = [p for p in self.project.placements if p.room != room_id]
        self._mutated()
        return f"removed {before - len(self.project.placements)} items from {room_id!r}"

    def furnish_room(self, room_id: str, note: str = "") -> str:
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
        proposal, _reasoning = self.agent.propose_room(
            self.project.plan,
            room_id,
            self.style(),
            room_budget,
            self.project.meta.get("currency", "EUR"),
            note,
        )
        if not proposal.items:
            return "the agent came back with no placeable items — try rephrasing or a budget"

        requests = [
            PlacementRequest(
                item=self.catalog.get(p.item_id), purpose=p.purpose, hint=p.hint, anchor=p.anchor
            )
            for p in proposal.items
        ]
        existing = [p for p in self.project.placements if p.room != room_id]
        kept_other_rooms = existing
        placed, issues = auto_place(
            self.project.plan, room_id, requests, self.catalog, existing=kept_other_rooms
        )

        self.project.snapshot()
        self.project.placements = kept_other_rooms + placed
        self._mutated()

        lines = [proposal.rationale.strip() or "done."]
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
        return "\n".join(lines)

    # --- free chat / routing ---
    def handle_message(self, message: str) -> str:
        self.project.append_chat("user", message)
        intent = self.agent.route(message, self.project.plan)
        if intent.action == "furnish_room" and intent.room_id:
            reply = self.furnish_room(intent.room_id, intent.note)
        elif intent.action == "set_budget" and intent.budget is not None:
            reply = self.set_budget(intent.budget)
        elif intent.action == "clear_room" and intent.room_id:
            reply = self.clear_room(intent.room_id)
        else:
            context = (
                f"You are a furnishing assistant for the apartment {self.project.meta['name']!r}. "
                f"Rooms: {', '.join(r.id for r in self.project.plan.rooms)}. "
                f"Current shopping list:\n{self.shopping_list()}\n"
                "Answer briefly and concretely."
            )
            reply = self.agent.llm.complete(message, system=context)
        self.project.append_chat("assistant", reply)
        return reply
