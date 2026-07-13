"""The design agent (docs/04): style extraction, room proposals grounded in catalog
search, and intent routing. Prompt logic lives here; the conversation loop lives in app/.

NB: no `from __future__ import annotations` in this file — it stringifies the tool
function's annotations, and google-genai's automatic function calling then fails with
"isinstance() arg 2 must be a type" when validating arguments.
"""

import logging
from pathlib import Path

from furnisher.agent.models import (
    Intent,
    ProposedItem,
    RoomOption,
    RoomOptions,
    StyleProfile,
)
from furnisher.catalog import Catalog, SearchFilters
from furnisher.model import FloorPlan

log = logging.getLogger(__name__)
PROMPTS = Path(__file__).parent / "prompts"


def _prompt(name: str) -> str:
    return (PROMPTS / f"{name}.md").read_text(encoding="utf-8")


def _room_summary(plan: FloorPlan, room_id: str) -> str:
    room = plan.room(room_id)
    xs = [p[0] for p in room.polygon]
    ys = [p[1] for p in room.polygon]
    openings = [
        f"{op.kind.value} {op.id} ({op.width:.1f} m wide)"
        for op in plan.openings
        if op.room == room_id or op.connects == room_id
    ]
    return (
        f"Room {room.id!r}, type {room.type.value}, "
        f"{max(xs) - min(xs):.1f} × {max(ys) - min(ys):.1f} m ({room.area():.1f} m²), "
        f"ceiling {room.ceiling_height or plan.ceiling_height:.1f} m. "
        f"Openings: {', '.join(openings) or 'none'}."
    )


class DesignAgent:
    def __init__(self, llm, catalog: Catalog):
        self.llm = llm
        self.catalog = catalog

    def extract_style(self, images: list[Path], notes: str) -> StyleProfile:
        content: list = [f"User notes: {notes or '(none)'}"]
        content.extend(images)
        return self.llm.complete_structured(content, StyleProfile, system=_prompt("style"))

    def route(self, message: str, plan: FloorPlan) -> Intent:
        rooms = ", ".join(f"{r.id!r} (type {r.type.value})" for r in plan.rooms)
        content = f"Rooms in the plan: {rooms}\n\nUser message: {message}"
        return self.llm.complete_structured(content, Intent, system=_prompt("route"))

    def propose_options(
        self,
        plan: FloorPlan,
        room_id: str,
        style: StyleProfile | None,
        budget_remaining: float | None,
        currency: str,
        note: str = "",
        on_progress=None,
    ) -> tuple[list[RoomOption], str]:
        """Returns (2-3 grounded furnishing options, the agent's free-text reasoning)."""
        seen_ids: set[str] = set()

        # NB: keep the signature free of `X | None` unions — google-genai's automatic
        # function calling chokes on them when validating arguments at call time.
        def search_catalog(query: str, max_price: float = 0) -> list[dict]:
            """Search real furniture. Returns id, name, type, width/depth/height in meters,
            and price. Propose only ids returned by this tool. Pass max_price=0 for no
            price limit."""
            if on_progress:
                on_progress(f"searching catalog: {query}")
            filters = SearchFilters(price_max=max_price if max_price > 0 else None)
            results = self.catalog.search(query, filters, limit=8)
            for item in results:
                seen_ids.add(item.id)
            return [
                {
                    "id": i.id,
                    "name": i.name,
                    "type": i.type_name,
                    "width_m": i.width_m,
                    "depth_m": i.depth_m,
                    "height_m": i.height_m,
                    "price": i.price,
                    "currency": i.currency,
                }
                for i in results
            ]

        parts = [_room_summary(plan, room_id)]
        if style is not None:
            parts.append(f"Style profile: {style.model_dump_json()}")
        if budget_remaining is not None:
            parts.append(f"Budget for this room: at most {budget_remaining:.0f} {currency}.")
        if note:
            parts.append(f"Extra constraints from the user: {note}")
        parts.append("Furnish this room now.")

        reasoning = self.llm.complete(
            "\n\n".join(parts), system=_prompt("proposal"), tools=[search_catalog]
        )
        if on_progress:
            on_progress("shaping the options…")

        draft = self.llm.complete_structured(
            "Convert this furnishing decision into the structured format (2-3 options). "
            "Use ONLY catalog ids that appear verbatim in the text:\n\n" + reasoning,
            RoomOptions,
        )

        # Grounding enforcement: drop anything the tool never returned / the catalog can't resolve
        options: list[RoomOption] = []
        for option in draft.options[:3]:
            items: list[ProposedItem] = []
            for proposed in option.items:
                if proposed.item_id not in seen_ids:
                    try:
                        self.catalog.get(proposed.item_id)
                    except KeyError:
                        log.warning("agent proposed unknown item %r — dropped", proposed.item_id)
                        continue
                items.append(proposed)
            if items:
                options.append(
                    RoomOption(
                        label=option.label or f"Option {len(options) + 1}",
                        items=items,
                        rationale=option.rationale,
                    )
                )
        return options, reasoning
