"""Layout validation (docs/05): cheap, pure, geometric. Called after every edit.

Rules v0:
- error: footprint not fully inside its room
- error: footprints overlap
- error: footprint blocks a door/passage (swing arc or approach corridor)
- warning: item taller than a window's sill sits against that window
- warning: required front clearance (docs/05 table) is blocked or faces a wall

Not yet implemented (docs/05): free-space connectivity via erosion. Auto-placement is M3.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations

from shapely.geometry import LineString, Polygon as ShapelyPolygon

from furnisher.catalog.models import CatalogItem
from furnisher.layout.clearances import front_clearance_m
from furnisher.layout.rules import is_underlay
from furnisher.model import DoorSwing, FloorPlan, Opening, OpeningKind, Placement
from furnisher.model import geometry

WALL_GAP_TOL = 0.02  # items may touch walls; allow tiny numeric slack
DOOR_CORRIDOR_M = 0.6  # free approach depth on both sides of a door/passage
WINDOW_PROXIMITY_M = 0.1


@dataclass
class LayoutIssue:
    severity: str  # "error" | "warning"
    message: str
    placements: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        return f"{self.severity.upper()}: {self.message}"


def placement_polygon(placement: Placement, item: CatalogItem) -> ShapelyPolygon:
    """The rotated footprint rectangle in world coordinates."""
    w, d = item.footprint()
    corners_local = [(-w / 2, -d / 2), (w / 2, -d / 2), (w / 2, d / 2), (-w / 2, d / 2)]
    px, py = placement.position
    corners = [
        (px + rx, py + ry)
        for rx, ry in (geometry.rotate(c, placement.rotation) for c in corners_local)
    ]
    return ShapelyPolygon(corners)


def front_zone_polygon(placement: Placement, item: CatalogItem, depth: float) -> ShapelyPolygon:
    """Rectangle of `depth` in front of the item (front = local -y at rotation 0)."""
    w, d = item.footprint()
    corners_local = [
        (-w / 2, -d / 2),
        (w / 2, -d / 2),
        (w / 2, -d / 2 - depth),
        (-w / 2, -d / 2 - depth),
    ]
    px, py = placement.position
    corners = [
        (px + rx, py + ry)
        for rx, ry in (geometry.rotate(c, placement.rotation) for c in corners_local)
    ]
    return ShapelyPolygon(corners)


def door_swing_polygon(plan: FloorPlan, op: Opening) -> ShapelyPolygon | None:
    """Quarter-circle swept by the door leaf (mirrors the renderer's arc math)."""
    swing = op.swing or DoorSwing.inward_left
    if swing in (DoorSwing.sliding, DoorSwing.none):
        return None
    seg_a, seg_b = plan.opening_segment(op)
    u = geometry.unit(seg_a, seg_b)
    interior_n = geometry.left_normal(u)  # CCW polygon: left of edge direction is inside op.room
    inward = swing.value.startswith("inward")
    hinge_left = swing.value.endswith("left")
    hinge = seg_a if hinge_left else seg_b
    jamb = seg_b if hinge_left else seg_a
    n_dir = interior_n if inward else (-interior_n[0], -interior_n[1])
    closed = (jamb[0] - hinge[0], jamb[1] - hinge[1])
    cross = closed[0] * n_dir[1] - closed[1] * n_dir[0]
    sign = 1.0 if cross > 0 else -1.0
    arc = [
        (hinge[0] + v[0], hinge[1] + v[1])
        for v in (geometry.rotate(closed, sign * step) for step in range(0, 91, 15))
    ]
    return ShapelyPolygon([hinge, *arc])


def corridor_polygon(plan: FloorPlan, op: Opening) -> ShapelyPolygon:
    """Approach corridor across the wall: the opening must stay walkable from both sides."""
    return LineString(plan.opening_segment(op)).buffer(DOOR_CORRIDOR_M, cap_style="flat")


def validate(plan: FloorPlan, placements: list[Placement], catalog) -> list[LayoutIssue]:
    """`catalog` is anything with .get(item_ref) -> CatalogItem (the Catalog facade)."""
    issues: list[LayoutIssue] = []
    footprints: dict[str, ShapelyPolygon] = {}
    items: dict[str, CatalogItem] = {}

    for p in placements:
        try:
            room = plan.room(p.room)
        except KeyError:
            issues.append(LayoutIssue("error", f"{p.id}: unknown room {p.room!r}", [p.id]))
            continue
        try:
            item = catalog.get(p.item_ref)
        except KeyError as exc:
            issues.append(LayoutIssue("error", f"{p.id}: {exc}", [p.id]))
            continue
        items[p.id] = item
        foot = placement_polygon(p, item)
        footprints[p.id] = foot

        room_poly = room.shapely_polygon().buffer(WALL_GAP_TOL)
        if not foot.within(room_poly):
            issues.append(
                LayoutIssue(
                    "error",
                    f"{p.id} ({item.name}) does not fit inside room {p.room!r} "
                    f"at {p.position} rot {p.rotation:g}°",
                    [p.id],
                )
            )

    # pairwise overlaps (rugs are underlays — furniture is *meant* to sit on top of them)
    placed = [p for p in placements if p.id in footprints]
    for a, b in combinations(placed, 2):
        if is_underlay(items[a.id]) or is_underlay(items[b.id]):
            continue
        inter = footprints[a.id].intersection(footprints[b.id]).area
        if inter > 1e-4:
            issues.append(
                LayoutIssue(
                    "error",
                    f"{a.id} ({items[a.id].name}) and {b.id} ({items[b.id].name}) "
                    f"overlap by {inter:.2f} m²",
                    [a.id, b.id],
                )
            )

    # doors and passages must stay usable
    for op in plan.openings:
        if op.kind == OpeningKind.window:
            continue
        zones: list[tuple[str, ShapelyPolygon | None]] = [
            ("swing", door_swing_polygon(plan, op) if op.kind == OpeningKind.door else None),
            ("approach", corridor_polygon(plan, op)),
        ]
        for zone_name, zone in zones:
            if zone is None:
                continue
            for p in placed:
                if is_underlay(items[p.id]):  # a flat rug under a door is fine to walk over
                    continue
                if footprints[p.id].intersection(zone).area > 1e-3:
                    issues.append(
                        LayoutIssue(
                            "error",
                            f"{p.id} ({items[p.id].name}) blocks the {zone_name} "
                            f"of {op.kind.value} {op.id!r}",
                            [p.id],
                        )
                    )

    # windows: warn when something tall sits right against them
    for op in plan.openings:
        if op.kind != OpeningKind.window:
            continue
        sill = op.sill_height if op.sill_height is not None else 0.85
        segment = LineString(plan.opening_segment(op))
        for p in placed:
            if items[p.id].height_m > sill and footprints[p.id].distance(segment) < (
                WINDOW_PROXIMITY_M
            ):
                issues.append(
                    LayoutIssue(
                        "warning",
                        f"{p.id} ({items[p.id].name}, {items[p.id].height_m:.2f} m tall) "
                        f"obstructs window {op.id!r} (sill {sill:.2f} m)",
                        [p.id],
                    )
                )

    # front clearances
    for p in placed:
        depth = front_clearance_m(items[p.id])
        if depth is None:
            continue
        zone = front_zone_polygon(p, items[p.id], depth)
        room_poly = plan.room(p.room).shapely_polygon().buffer(WALL_GAP_TOL)
        if not zone.within(room_poly):
            issues.append(
                LayoutIssue(
                    "warning",
                    f"{p.id} ({items[p.id].name}) needs {depth:.1f} m free in front "
                    "but faces a wall",
                    [p.id],
                )
            )
            continue
        for other in placed:
            if other.id != p.id and footprints[other.id].intersection(zone).area > 1e-3:
                issues.append(
                    LayoutIssue(
                        "warning",
                        f"{other.id} ({items[other.id].name}) blocks access to "
                        f"{p.id} ({items[p.id].name}) — needs {depth:.1f} m in front",
                        [p.id, other.id],
                    )
                )

    return issues
