"""YAML plan loading with authoring sugar (docs/02).

Sugar desugared here, before schema validation:
- room `rect: [x, y, w, h]` instead of `polygon:` (emits a CCW rectangle)
- opening `offset_frac: 0..1` instead of `offset:` — the fraction of the edge at which the
  opening's *center* sits, so `offset_frac: 0.5` centers it on the edge
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import yaml

from furnisher.model import FloorPlan
from furnisher.model import geometry


class PlanLoadError(ValueError):
    pass


def load_plan(path: Path) -> FloorPlan:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise PlanLoadError(f"{path}: invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise PlanLoadError(f"{path}: expected a YAML mapping at the top level")
    return plan_from_dict(data)


def plan_from_dict(data: dict) -> FloorPlan:
    data = deepcopy(data)
    rooms = data.get("rooms") or []

    for room in rooms:
        rect = room.pop("rect", None)
        if rect is None:
            continue
        if "polygon" in room:
            raise PlanLoadError(
                f"room {room.get('id')!r}: give either 'rect' or 'polygon', not both"
            )
        if len(rect) != 4:
            raise PlanLoadError(f"room {room.get('id')!r}: 'rect' must be [x, y, w, h]")
        x, y, w, h = rect
        room["polygon"] = [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]

    polygons = {room.get("id"): room.get("polygon") for room in rooms}
    for op in data.get("openings") or []:
        frac = op.pop("offset_frac", None)
        if frac is None:
            continue
        if "offset" in op:
            raise PlanLoadError(
                f"opening {op.get('id')!r}: give either 'offset' or 'offset_frac', not both"
            )
        polygon = polygons.get(op.get("room"))
        if not polygon:
            raise PlanLoadError(
                f"opening {op.get('id')!r}: offset_frac needs a known room, got {op.get('room')!r}"
            )
        edge = op.get("edge")
        if not isinstance(edge, int) or not 0 <= edge < len(polygon):
            raise PlanLoadError(
                f"opening {op.get('id')!r}: offset_frac needs a valid 'edge' index, got {edge!r}"
            )
        length = geometry.edge_length(polygon, edge)
        op["offset"] = max(0.0, frac * length - op.get("width", 0.0) / 2.0)

    return FloorPlan.model_validate(data)
