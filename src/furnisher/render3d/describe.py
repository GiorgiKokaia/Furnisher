"""Programmatic layout -> spatial text for grounding image generation (docs/07).

The schematic SVG alone doesn't make the image model reproduce placements faithfully — it
tends to "reinterpret" the plan. These helpers translate the plan + placements into explicit
spatial language: the size of each wall and what opens onto it, and for every item which wall
it sits against, where it falls in the camera frame, and which way it faces. Fed into the
prompt this pins the composition far more tightly than "read the schematic".

Pure geometry, no LLM — deterministic and inspectable (the text is dumped next to each render).
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Sequence

from shapely.geometry import LineString
from shapely.geometry import Point as SPoint

from furnisher.layout import placement_polygon
from furnisher.model import FloorPlan, OpeningKind, Placement, geometry

Point = tuple[float, float]

AGAINST_WALL_M = 0.25  # a footprint within this of a wall is "against" it
Camera = tuple[Point, Point, str]  # (position, forward_unit, human description)


def _compass_of_normal(normal: Point) -> str:
    """Name the wall an interior normal points away from (normal points into the room)."""
    nx, ny = normal
    if abs(nx) > abs(ny):
        return "west" if nx > 0 else "east"
    return "south" if ny > 0 else "north"


def _compass_of_dir(d: Point) -> str:
    """Name the compass direction a heading vector points toward."""
    dx, dy = d
    if abs(dx) > abs(dy):
        return "east" if dx > 0 else "west"
    return "north" if dy > 0 else "south"


def _edge_normal(polygon: Sequence[Point], i: int) -> Point:
    a, b = geometry.edge(polygon, i)
    return geometry.left_normal(geometry.unit(a, b))


def room_camera(plan: FloorPlan, room_id: str) -> Camera:
    """Viewpoint for the room: standing just inside its first door, looking in.

    Matches the camera marker drawn by render_room_crop so the schematic and the text agree.
    Falls back to the room centroid looking north when the room has no door/passage.
    """
    room = plan.room(room_id)
    for op in plan.openings:
        if op.kind == OpeningKind.window:
            continue
        if op.room != room_id and op.connects != room_id:
            continue
        seg_a, seg_b = plan.opening_segment(op)
        n = geometry.left_normal(geometry.unit(seg_a, seg_b))
        if op.room != room_id:  # neighbour-owned opening: its interior normal points away from us
            n = (-n[0], -n[1])
        mid = ((seg_a[0] + seg_b[0]) / 2, (seg_a[1] + seg_b[1]) / 2)
        pos = (mid[0] + n[0] * 0.45, mid[1] + n[1] * 0.45)
        kind = "doorway" if op.kind == OpeningKind.door else "open passage"
        return (
            pos,
            n,
            (
                f"eye level, standing in the {kind} on the {_compass_of_normal(n)} wall, looking "
                "into the room"
            ),
        )
    return (
        geometry.centroid(room.polygon),
        (0.0, 1.0),
        ("eye level, from the room's entrance side looking toward the far wall"),
    )


def describe_walls(plan: FloorPlan, room_id: str) -> list[str]:
    """One line per wall: its length and every opening on it, in plain words."""
    room = plan.room(room_id)
    by_edge: dict[int, list[str]] = defaultdict(list)
    for op in plan.openings:
        if op.room != room_id and op.connects != room_id:
            continue
        seg_a, seg_b = plan.opening_segment(op)
        mid = ((seg_a[0] + seg_b[0]) / 2, (seg_a[1] + seg_b[1]) / 2)
        edge_i = min(
            range(len(room.polygon)),
            key=lambda i: LineString(geometry.edge(room.polygon, i)).distance(SPoint(mid)),
        )
        other = op.connects if op.room == room_id else op.room
        dest = (
            ""
            if other in (None, room_id)
            else (" to outside" if other == "exterior" else f" to the {other}")
        )
        if op.kind == OpeningKind.window:
            by_edge[edge_i].append(f"a window {op.width:.1f} m wide")
        elif op.kind == OpeningKind.door:
            by_edge[edge_i].append(f"a door{dest}")
        else:
            by_edge[edge_i].append(f"an open passage{dest}")

    lines = []
    for i in range(len(room.polygon)):
        wall = _compass_of_normal(_edge_normal(room.polygon, i)).capitalize()
        length = geometry.edge_length(room.polygon, i)
        ops = by_edge.get(i)
        detail = ", ".join(ops) if ops else "solid, no openings"
        lines.append(f"- {wall} wall ({length:.1f} m): {detail}.")
    return lines


def _position_phrase(room, poly) -> str:
    """Where an item sits relative to the walls: against a wall, in a corner, or free-standing."""
    near: list[str] = []
    for i in range(len(room.polygon)):
        if poly.distance(LineString(geometry.edge(room.polygon, i))) <= AGAINST_WALL_M:
            wall = _compass_of_normal(_edge_normal(room.polygon, i))
            if wall not in near:
                near.append(wall)
    if len(near) >= 2:
        order = {"north": 0, "south": 1, "east": 2, "west": 3}
        ns = [w for w in near if w in ("north", "south")]
        ew = [w for w in near if w in ("east", "west")]
        corner = "-".join(sorted(ns + ew, key=lambda w: order[w])) or "-".join(near[:2])
        return f"in the {corner} corner"
    if near:
        return f"against the {near[0]} wall"
    return "free-standing away from the walls, toward the centre of the room"


def describe_furniture(
    plan: FloorPlan, room_id: str, placements: list[Placement], catalog, camera: Camera
) -> list[str]:
    """One line per item, biggest first: wall position, camera framing, facing direction."""
    room = plan.room(room_id)
    cpos, fwd, _ = camera
    right = (fwd[1], -fwd[0])  # camera's right in world coords (y-up, looking along fwd)
    max_depth = (
        max((v[0] - cpos[0]) * fwd[0] + (v[1] - cpos[1]) * fwd[1] for v in room.polygon) or 1.0
    )

    room_placements = sorted(
        (p for p in placements if p.room == room_id),
        key=lambda p: catalog.get(p.item_ref).width_m * catalog.get(p.item_ref).depth_m,
        reverse=True,
    )
    lines = []
    for p in room_placements:
        item = catalog.get(p.item_ref)
        poly = placement_polygon(p, item)
        c = (poly.centroid.x, poly.centroid.y)

        d = (c[0] - cpos[0], c[1] - cpos[1])
        depth = d[0] * fwd[0] + d[1] * fwd[1]
        lateral = d[0] * right[0] + d[1] * right[1]
        if depth < 0.3:
            frame_x = "immediately to the viewer's " + ("right" if lateral > 0 else "left")
        else:
            angle = math.degrees(math.atan2(lateral, depth))
            frame_x = (
                "on the right of the frame"
                if angle > 18
                else "on the left of the frame"
                if angle < -18
                else "centred in the frame"
            )
        frac = max(depth, 0.0) / max_depth
        frame_z = (
            "in the foreground near the camera"
            if frac < 0.4
            else "on the far side of the room"
            if frac > 0.72
            else "in the mid-ground"
        )

        front = geometry.rotate((0.0, -1.0), p.rotation)
        to_cam = geometry.unit(c, cpos) if (cpos != c) else (0.0, 0.0)
        toward = front[0] * to_cam[0] + front[1] * to_cam[1]
        rel = (
            "front toward the camera"
            if toward > 0.5
            else "back to the camera"
            if toward < -0.5
            else "side-on to the camera"
        )

        lines.append(
            f"- {item.name} ({item.type_name}, "
            f"{item.width_m * 100:.0f}x{item.depth_m * 100:.0f} cm footprint, "
            f"{item.height_m * 100:.0f} cm tall): {_position_phrase(room, poly)}, "
            f"{frame_x}, {frame_z}, facing {_compass_of_dir(front)} ({rel})."
        )
    return lines


def describe_room_layout(
    plan: FloorPlan,
    room_id: str,
    placements: list[Placement],
    catalog,
    camera: Camera | None = None,
) -> str:
    """Full spatial brief for one room: dimensions, walls, camera, per-item placement."""
    if camera is None:
        camera = room_camera(plan, room_id)
    room = plan.room(room_id)
    xs = [p[0] for p in room.polygon]
    ys = [p[1] for p in room.polygon]
    parts = [
        f"Room footprint: {max(xs) - min(xs):.1f} m east-west by {max(ys) - min(ys):.1f} m "
        "north-south (north is up, east is right).",
        "Walls and openings:",
        *describe_walls(plan, room_id),
        "",
        "Furniture, placed exactly like this (reproduce each item's position, framing and "
        "facing — do not rearrange):",
        *describe_furniture(plan, room_id, placements, catalog, camera),
    ]
    return "\n".join(parts)


def describe_apartment_layout(plan: FloorPlan, placements: list[Placement], catalog) -> str:
    """Room arrangement (quadrant + connections) and per-room furniture for the dollhouse view."""
    rooms = plan.rooms
    xs = [x for r in rooms for x, _ in r.polygon]
    ys = [y for r in rooms for _, y in r.polygon]
    midx, midy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2

    conns: dict[str, set[str]] = defaultdict(set)
    for op in plan.openings:
        if op.connects and op.connects not in ("exterior", None):
            conns[op.room].add(op.connects)
            conns[op.connects].add(op.room)

    by_room: dict[str, list[str]] = defaultdict(list)
    for p in placements:
        by_room[p.room].append(catalog.get(p.item_ref).name)

    ordered = sorted(
        rooms, key=lambda r: (-geometry.centroid(r.polygon)[1], geometry.centroid(r.polygon)[0])
    )
    lines = ["Room arrangement (top-down, north up, east right):"]
    for room in ordered:
        cx, cy = geometry.centroid(room.polygon)
        rxs = [x for x, _ in room.polygon]
        rys = [y for _, y in room.polygon]
        quad = f"{'north' if cy >= midy else 'south'}-{'east' if cx >= midx else 'west'}"
        neigh = sorted(conns.get(room.id, ()))
        link = f"; connects to {', '.join(neigh)}" if neigh else ""
        lines.append(
            f"- {room.label()} ({max(rxs) - min(rxs):.1f}x{max(rys) - min(rys):.1f} m), "
            f"{quad} of the plan{link}."
        )
    lines.append(
        "Furniture per room — render EXACTLY these items in each room and nothing else. "
        "Rooms marked empty must be shown with no furniture:"
    )
    for room in ordered:
        items = by_room.get(room.id)
        lines.append(f"- {room.label()}: {', '.join(items) if items else 'EMPTY — no furniture'}.")
    return "\n".join(lines)
