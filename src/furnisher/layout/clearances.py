"""Item-specific clearance rules, keyed by keywords in the item's type/name (docs/05).

Crude but effective: front_m is the free depth required in front of the item's front edge
(local -y at rotation 0). Items matching no rule get no clearance requirement.
"""

from __future__ import annotations

from furnisher.catalog.models import CatalogItem

# (keywords, required free depth in front, human label)
FRONT_CLEARANCES: list[tuple[tuple[str, ...], float]] = [
    (("wardrobe", "dresser", "drawer", "chest"), 0.9),  # doors/drawers must open
    (("bookcase", "bookshelf", "shelf", "cabinet"), 0.7),
    (("desk",), 0.7),  # room for the chair
    (("sofa", "armchair", "loveseat"), 0.3),  # a coffee table 0.3-0.5m away is *good* placement
    (("tv bench", "tv unit", "media"), 0.5),
    (("bed",), 0.6),  # access at the foot end
]

# chairs tuck under tables; requiring front clearance would only false-positive
_EXEMPT = ("dining chair", "office chair", "stool")


def front_clearance_m(item: CatalogItem) -> float | None:
    haystack = f"{item.type_name} {item.name}".lower()
    if any(word in haystack for word in _EXEMPT):
        return None
    for keywords, depth in FRONT_CLEARANCES:
        if any(word in haystack for word in keywords):
            return depth
    return None
