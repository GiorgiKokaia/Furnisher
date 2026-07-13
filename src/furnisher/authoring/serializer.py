"""Write a FloorPlan back to authoring YAML (docs/02).

Emits `rect` sugar only when the polygon is exactly the canonical rectangle the loader would
produce (same starting corner, CCW) — anything else would silently renumber edges and break the
openings that reference them.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from furnisher.model import FloorPlan


def _r(v: float) -> float:
    return round(v, 4)


def _as_rect(polygon: list[tuple[float, float]]) -> list[float] | None:
    if len(polygon) != 4:
        return None
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = polygon
    if not (y0 == y1 and x1 == x2 and y2 == y3 and x3 == x0):
        return None
    w, h = x1 - x0, y2 - y1
    if w <= 0 or h <= 0:
        return None
    # subtraction reintroduces float noise even on rounded vertices (10.55 - 4.0 -> 6.55000...01)
    return [x0, y0, _r(w), _r(h)]


def plan_to_dict(plan: FloorPlan) -> dict:
    data: dict = {
        "schema_version": plan.schema_version,
        "name": plan.name,
        "ceiling_height": _r(plan.ceiling_height),
        "rooms": [],
    }
    for room in plan.rooms:
        entry: dict = {"id": room.id, "type": room.type.value}
        polygon = [(_r(x), _r(y)) for x, y in room.polygon]
        rect = _as_rect(polygon)
        if rect is not None:
            entry["rect"] = rect
        else:
            entry["polygon"] = [[x, y] for x, y in polygon]
        if room.ceiling_height is not None:
            entry["ceiling_height"] = _r(room.ceiling_height)
        data["rooms"].append(entry)

    if plan.openings:
        data["openings"] = []
        for op in plan.openings:
            entry = {
                "id": op.id,
                "kind": op.kind.value,
                "room": op.room,
                "edge": op.edge,
                "offset": _r(op.offset),
                "width": _r(op.width),
            }
            if op.height != 2.0:
                entry["height"] = _r(op.height)
            if op.swing is not None:
                entry["swing"] = op.swing.value
            if op.connects is not None:
                entry["connects"] = op.connects
            if op.sill_height is not None:
                entry["sill_height"] = _r(op.sill_height)
            data["openings"].append(entry)
    return data


def save_plan(plan: FloorPlan, path: Path) -> None:
    text = yaml.safe_dump(plan_to_dict(plan), sort_keys=False, allow_unicode=True)
    path.write_text(text, encoding="utf-8")
