"""Greedy auto-placement (docs/05): heuristics on top of validate(), nothing fancier
until proven necessary. Deterministic. Output always passes validate() with no errors —
items that can't be placed come back as LayoutIssues instead (the agent feeds on those).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from furnisher.catalog.models import CatalogItem
from furnisher.layout.validate import LayoutIssue, placement_polygon, validate
from furnisher.model import FloorPlan, Placement
from furnisher.model import geometry

WALL_GAP = 0.05
WALL_STEP = 0.25
_WALL_LOVERS = (
    "bed",
    "sofa",
    "wardrobe",
    "bookcase",
    "bookshelf",
    "shelf",
    "cabinet",
    "tv",
    "desk",
    "dresser",
    "chest",
)


@dataclass
class PlacementRequest:
    item: CatalogItem
    purpose: str  # short label, e.g. "sofa", "left nightstand"; becomes the placement id
    hint: str = "wall"  # "wall" | "center" | "free"
    anchor: str | None = None  # purpose of another request to place adjacent to


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "item"


def _is_wall_lover(item: CatalogItem) -> bool:
    haystack = f"{item.type_name} {item.name}".lower()
    return any(w in haystack for w in _WALL_LOVERS)


def _wall_candidates(plan: FloorPlan, room_id: str, item: CatalogItem):
    """Poses with the item's back against each wall, front facing the room."""
    polygon = plan.room(room_id).polygon
    w, d = item.footprint()
    for edge_i in range(len(polygon)):
        a, b = geometry.edge(polygon, edge_i)
        length = geometry.edge_length(polygon, edge_i)
        if length < w + 2 * WALL_GAP:
            continue
        u = geometry.unit(a, b)
        n = geometry.left_normal(u)  # interior side (CCW polygon)
        # rotation that makes local front (0,-1) face the interior normal
        rotation = round(math.degrees(math.atan2(n[0], -n[1])), 1) % 360
        t = w / 2 + WALL_GAP
        while t <= length - w / 2 - WALL_GAP + 1e-9:
            wall_point = geometry.point_along(a, b, t)
            center = (
                wall_point[0] + n[0] * (d / 2 + WALL_GAP),
                wall_point[1] + n[1] * (d / 2 + WALL_GAP),
            )
            yield center, rotation, "wall"
            t += WALL_STEP


def _center_candidates(plan: FloorPlan, room_id: str):
    cx, cy = geometry.centroid(plan.room(room_id).polygon)
    for dx in (0, -0.5, 0.5, -1.0, 1.0):
        for dy in (0, -0.5, 0.5, -1.0, 1.0):
            for rotation in (0, 90):
                yield (cx + dx, cy + dy), float(rotation), "center"


def _anchor_candidates(anchor: Placement, anchor_item: CatalogItem, item: CatalogItem):
    """Adjacent to the anchor on each of its four (rotated) sides, facing it."""
    ax, ay = anchor.position
    aw, ad = anchor_item.footprint()
    w, d = item.footprint()
    # sides in the anchor's local frame: (direction, anchor half-extent along it)
    sides = [((1, 0), aw / 2), ((-1, 0), aw / 2), ((0, 1), ad / 2), ((0, -1), ad / 2)]
    for local_dir, half in sides:
        direction = geometry.rotate(local_dir, anchor.rotation)
        offset = half + d / 2 + WALL_GAP
        center = (ax + direction[0] * offset, ay + direction[1] * offset)
        # face the anchor: local front (0,-1) maps to -direction
        rotation = round(math.degrees(math.atan2(-direction[0], direction[1])), 1) % 360
        yield center, rotation, "anchor"


def _min_distance(candidate_poly, others) -> float:
    if not others:
        return 1.5
    return min(candidate_poly.distance(o) for o in others)


def auto_place(
    plan: FloorPlan,
    room_id: str,
    requests: list[PlacementRequest],
    catalog,
    existing: list[Placement] | None = None,
) -> tuple[list[Placement], list[LayoutIssue]]:
    existing = list(existing or [])
    issues: list[LayoutIssue] = []
    placed: list[Placement] = []
    by_purpose: dict[str, tuple[Placement, CatalogItem]] = {}

    # anchored requests go after their anchors; otherwise big things first
    unanchored = sorted(
        (r for r in requests if not r.anchor),
        key=lambda r: r.item.width_m * r.item.depth_m,
        reverse=True,
    )
    anchored = sorted(
        (r for r in requests if r.anchor),
        key=lambda r: r.item.width_m * r.item.depth_m,
        reverse=True,
    )
    taken_ids = {p.id for p in existing}

    for request in unanchored + anchored:
        pid = _slug(request.purpose)
        while pid in taken_ids:
            pid += "-2"
        taken_ids.add(pid)

        candidates = []
        if request.anchor and request.anchor in by_purpose:
            anchor_placement, anchor_item = by_purpose[request.anchor]
            candidates.extend(_anchor_candidates(anchor_placement, anchor_item, request.item))
        if request.hint == "center":
            candidates.extend(_center_candidates(plan, room_id))
            candidates.extend(_wall_candidates(plan, room_id, request.item))
        else:
            candidates.extend(_wall_candidates(plan, room_id, request.item))
            candidates.extend(_center_candidates(plan, room_id))

        other_polys = [placement_polygon(p, catalog.get(p.item_ref)) for p in existing + placed]
        best = None
        for index, (center, rotation, kind) in enumerate(candidates):
            trial = Placement(
                id=pid,
                item_ref=request.item.id,
                room=room_id,
                position=(round(center[0], 3), round(center[1], 3)),
                rotation=rotation,
            )
            trial_issues = [
                i
                for i in validate(plan, existing + placed + [trial], catalog)
                if pid in i.placements
            ]
            if any(i.severity == "error" for i in trial_issues):
                continue
            score = 0.0
            if kind == "anchor":
                score += 4.0
            if kind == "wall" and _is_wall_lover(request.item):
                score += 2.0
            if kind == "center" and request.hint == "center":
                score += 1.5
            score -= sum(1.0 for i in trial_issues if i.severity == "warning")
            score += 0.3 * min(
                _min_distance(placement_polygon(trial, request.item), other_polys), 1.5
            )
            score -= index * 1e-4  # stable tie-break: earlier candidates win
            if best is None or score > best[0]:
                best = (score, trial)
        if best is None:
            issues.append(
                LayoutIssue(
                    "error",
                    f"could not place {request.purpose!r} ({request.item.name}, "
                    f"{request.item.width_m:.2f}×{request.item.depth_m:.2f} m) in {room_id!r} — "
                    "no position satisfies fit/door/overlap rules; try a smaller item",
                    [pid],
                )
            )
            continue
        placed.append(best[1])
        by_purpose[request.purpose] = (best[1], request.item)

    return placed, issues
