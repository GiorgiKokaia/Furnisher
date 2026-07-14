"""Design rules (docs/05): item categorisation + preferred spatial relationships.

Two jobs, both keyed off crude keyword matching against an item's type/name:

- **Underlays** (rugs, mats): lie flat *under* other furniture, so overlaps with them are
  legal and they render beneath everything.
- **Anchoring**: which items want to sit in a specific spot relative to another —
  nightstands beside the head of the bed, a coffee table in front of the sofa, the desk
  chair in front of the desk, dining chairs around the table, a rug under the seating.

Deterministic; the layout engine (place.py) consumes these to build candidate poses and the
validator/renderer consume `is_underlay`.
"""

from __future__ import annotations

import math

from furnisher.catalog.models import CatalogItem
from furnisher.model import geometry

# category -> keywords (first match wins; order matters: specific categories before generic)
_CATEGORIES: list[tuple[str, tuple[str, ...]]] = [
    ("rug", ("rug", "carpet", "runner", "doormat")),
    ("nightstand", ("nightstand", "bedside")),  # before "bed" ("bedside" contains "bed")
    ("bed", ("bed",)),
    ("coffee_table", ("coffee table", "coffee-table")),
    ("dining_table", ("dining table", "kitchen table")),
    ("desk", ("desk",)),
    ("office_chair", ("office chair", "desk chair", "task chair")),
    ("sofa", ("sofa", "loveseat", "couch", "sectional", "settee")),
    ("armchair", ("armchair",)),
    ("tv", ("tv ", "tv-", "tv bench", "television", "media unit")),
    ("dining_chair", ("dining chair", "chair", "stool")),  # generic chair last
    ("wardrobe", ("wardrobe", "closet")),
    ("lamp", ("lamp", "light")),
]

# target category -> the category it anchors to (used when the agent didn't set an anchor)
ANCHOR_FOR: dict[str, str] = {
    "nightstand": "bed",
    "coffee_table": "sofa",
    "office_chair": "desk",
    "dining_chair": "dining_table",
    "rug": "sofa",
}


def category(item: CatalogItem) -> str:
    haystack = f"{item.type_name} {item.name}".lower()
    for name, keywords in _CATEGORIES:
        if any(k in haystack for k in keywords):
            return name
    return "other"


def is_underlay(item: CatalogItem) -> bool:
    """Rugs/mats lie flat under other furniture — overlaps with them are fine."""
    return category(item) == "rug"


def _face(direction: tuple[float, float]) -> float:
    """Rotation (deg) so the item's front (local -y) points opposite `direction` — i.e. the
    item at `anchor + direction` turns back to face the anchor."""
    return round(math.degrees(math.atan2(-direction[0], direction[1])), 1) % 360


def relation_candidates(anchor_placement, anchor_item: CatalogItem, item: CatalogItem):
    """Preferred poses for `item` given its design relationship to `anchor_item`.

    Yields (center, rotation_deg, "anchor_pref"). Empty when there's no special rule — the
    caller falls back to generic adjacency. Directions are in world space via the anchor's pose.
    """
    cat, acat = category(item), category(anchor_item)
    ax, ay = anchor_placement.position
    arot = anchor_placement.rotation
    aw, ad = anchor_item.footprint()
    w, d = item.footprint()
    gap = 0.05

    front = geometry.rotate((0.0, -1.0), arot)  # anchor's front (foot of bed, front of sofa)
    back = (-front[0], -front[1])  # toward the headboard / sofa back
    right = geometry.rotate((1.0, 0.0), arot)
    left = (-right[0], -right[1])

    def at(direction, distance, rotation):
        return ((ax + direction[0] * distance, ay + direction[1] * distance), rotation, "anchor_pref")

    if cat == "nightstand" and acat == "bed":
        toward_head = ad / 2 - d / 2  # align the nightstand's far edge with the headboard
        return [
            (
                (
                    ax + side[0] * (aw / 2 + w / 2 + gap) + back[0] * toward_head,
                    ay + side[1] * (aw / 2 + w / 2 + gap) + back[1] * toward_head,
                ),
                arot,
                "anchor_pref",
            )
            for side in (right, left)
        ]
    if cat == "coffee_table" and acat == "sofa":
        return [at(front, ad / 2 + 0.4 + d / 2, arot)]
    if cat == "rug" and acat == "sofa":
        # rug centred in front of the sofa, its near edge tucked slightly under the sofa
        return [at(front, ad / 2 + d / 2 - 0.35, arot)]
    if cat == "office_chair" and acat == "desk":
        return [at(front, ad / 2 + 0.1 + d / 2, _face(front))]
    if cat == "dining_chair" and acat == "dining_table":
        return [
            at(direction, half + 0.1 + d / 2, _face(direction))
            for direction, half in ((front, ad / 2), (back, ad / 2), (right, aw / 2), (left, aw / 2))
        ]
    return []
