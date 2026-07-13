"""Fill in plan fields that are derivable from geometry."""

from __future__ import annotations

from shapely.geometry import LineString

from furnisher.model import EXTERIOR, FloorPlan, OpeningKind
from furnisher.model.plan import WALL_ADJACENCY_TOL


def infer_connects(plan: FloorPlan) -> FloorPlan:
    """Fill missing door/passage `connects`: the room adjacent at the opening, else exterior.

    Mutates and returns the plan. Openings with broken geometry are left alone for
    validate_plan() to report.
    """
    for op in plan.openings:
        if op.kind not in (OpeningKind.door, OpeningKind.opening) or op.connects:
            continue
        try:
            polygon = plan.room(op.room).polygon
        except KeyError:
            continue
        if not 0 <= op.edge < len(polygon):
            continue
        segment = LineString(plan.opening_segment(op))
        probes = [segment.interpolate(t, normalized=True) for t in (0, 0.5, 1)]
        found = None
        for room in plan.rooms:
            if room.id == op.room:
                continue
            boundary = room.shapely_polygon().exterior
            if all(p.distance(boundary) <= WALL_ADJACENCY_TOL for p in probes):
                found = room.id
                break
        op.connects = found or EXTERIOR
    return plan
