"""2D floor plan SVG renderer (docs/06).

The y-flip between the world (y up) and SVG (y down) happens here and only here.
Wall thickness is painted (polygon stroke), not modeled — see docs/01.
"""

from __future__ import annotations

import html
from dataclasses import dataclass, field

from furnisher.model import DoorSwing, FloorPlan, Opening, OpeningKind, RoomType
from furnisher.model import geometry
from furnisher.model.geometry import Point

DEFAULT_ROOM_FILLS: dict[RoomType, str] = {
    RoomType.living_room: "#f3ecdd",
    RoomType.bedroom: "#e7ecf5",
    RoomType.kitchen: "#f0e4d7",
    RoomType.bathroom: "#ddeef0",
    RoomType.wc: "#ddeef0",
    RoomType.hallway: "#eeeae4",
    RoomType.dining_room: "#f3ecdd",
    RoomType.office: "#e9efe6",
    RoomType.balcony: "#e4efe0",
    RoomType.storage: "#e8e5e0",
    RoomType.other: "#ececec",
}


@dataclass
class RenderStyle:
    scale: float = 80.0  # px per meter
    padding: float = 0.8  # meters around the plan
    wall_thickness: float = 0.12  # meters, painted as stroke
    background: str = "#ffffff"
    wall_color: str = "#2f2a26"
    label_color: str = "#3a3a3a"
    sublabel_color: str = "#7a7a7a"
    window_fill: str = "#cfe3f2"
    window_stroke: str = "#5b87a8"
    door_color: str = "#8a6d3b"
    font_family: str = "'Segoe UI', system-ui, sans-serif"
    room_fills: dict[RoomType, str] = field(default_factory=lambda: dict(DEFAULT_ROOM_FILLS))


class _Transform:
    """World meters -> SVG pixels (y flipped)."""

    def __init__(self, plan: FloorPlan, style: RenderStyle):
        xs = [p[0] for room in plan.rooms for p in room.polygon]
        ys = [p[1] for room in plan.rooms for p in room.polygon]
        self.min_x, self.max_y = min(xs), max(ys)
        self.scale = style.scale
        self.pad = style.padding
        self.width_px = (max(xs) - min(xs) + 2 * style.padding) * style.scale
        self.height_px = (max(ys) - min(ys) + 2 * style.padding) * style.scale

    def __call__(self, p: Point) -> Point:
        return (
            (p[0] - self.min_x + self.pad) * self.scale,
            (self.max_y + self.pad - p[1]) * self.scale,
        )


def _fmt(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")


def _points_attr(points: list[Point], t: _Transform) -> str:
    return " ".join(f"{_fmt(x)},{_fmt(y)}" for x, y in (t(p) for p in points))


def _polyline(
    points: list[Point], t: _Transform, stroke: str, width_px: float, linecap: str = "round"
) -> str:
    return (
        f'<polyline points="{_points_attr(points, t)}" fill="none" stroke="{stroke}" '
        f'stroke-width="{_fmt(width_px)}" stroke-linecap="{linecap}"/>'
    )


def render_plan(plan: FloorPlan, style: RenderStyle | None = None) -> str:
    style = style or RenderStyle()
    if not plan.rooms:
        return (
            '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="200" '
            f'font-family="{style.font_family}">'
            f'<rect width="100%" height="100%" fill="{style.background}"/>'
            f'<text x="200" y="100" text-anchor="middle" fill="{style.sublabel_color}" '
            'font-size="14">empty plan — no rooms yet</text></svg>'
        )
    t = _Transform(plan, style)
    wall_px = style.wall_thickness * style.scale
    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{_fmt(t.width_px)}" '
        f'height="{_fmt(t.height_px)}" viewBox="0 0 {_fmt(t.width_px)} {_fmt(t.height_px)}" '
        f'font-family="{style.font_family}">',
        f'<rect width="100%" height="100%" fill="{style.background}"/>',
    ]

    # Room floors + walls (shared walls are painted twice; harmless).
    for room in plan.rooms:
        fill = style.room_fills.get(room.type, style.room_fills[RoomType.other])
        parts.append(
            f'<polygon points="{_points_attr(room.polygon, t)}" fill="{fill}" '
            f'stroke="{style.wall_color}" stroke-width="{_fmt(wall_px)}" '
            'stroke-linejoin="miter"/>'
        )

    # Openings: gap first (punch through the wall stroke), then the symbol.
    for op in plan.openings:
        parts.extend(_render_opening(plan, op, t, style, wall_px))

    # Labels last, on top of everything.
    for room in plan.rooms:
        cx, cy = t(geometry.centroid(room.polygon))
        parts.append(
            f'<text x="{_fmt(cx)}" y="{_fmt(cy)}" text-anchor="middle" '
            f'fill="{style.label_color}" font-size="14" font-weight="600">'
            f"{html.escape(room.label())}</text>"
        )
        parts.append(
            f'<text x="{_fmt(cx)}" y="{_fmt(cy + 16)}" text-anchor="middle" '
            f'fill="{style.sublabel_color}" font-size="11">{room.area():.1f} m²</text>'
        )

    parts.append("</svg>")
    return "\n".join(parts)


def _render_opening(
    plan: FloorPlan, op: Opening, t: _Transform, style: RenderStyle, wall_px: float
) -> list[str]:
    seg_a, seg_b = plan.opening_segment(op)
    room = plan.room(op.room)
    fill = style.room_fills.get(room.type, style.room_fills[RoomType.other])
    parts: list[str] = []

    if op.kind == OpeningKind.window:
        # Windows sit in the wall: a light pane across the wall thickness.
        u = geometry.unit(seg_a, seg_b)
        n = geometry.left_normal(u)
        ht = style.wall_thickness / 2
        corners = [
            (seg_a[0] + n[0] * ht, seg_a[1] + n[1] * ht),
            (seg_b[0] + n[0] * ht, seg_b[1] + n[1] * ht),
            (seg_b[0] - n[0] * ht, seg_b[1] - n[1] * ht),
            (seg_a[0] - n[0] * ht, seg_a[1] - n[1] * ht),
        ]
        parts.append(
            f'<polygon points="{_points_attr(corners, t)}" fill="{style.window_fill}" '
            f'stroke="{style.window_stroke}" stroke-width="1.5"/>'
        )
        parts.append(_polyline([seg_a, seg_b], t, style.window_stroke, 1.0, linecap="butt"))
        return parts

    # Door or doorless passage: punch a gap through the wall stroke.
    parts.append(_polyline([seg_a, seg_b], t, fill, wall_px + 2, linecap="butt"))

    if op.kind == OpeningKind.door:
        swing = op.swing or DoorSwing.inward_left
        if swing in (DoorSwing.sliding, DoorSwing.none):
            parts.append(_polyline([seg_a, seg_b], t, style.door_color, 2.0))
            return parts

        u = geometry.unit(seg_a, seg_b)
        interior_n = geometry.left_normal(u)  # CCW polygon: left of edge direction is inside
        inward = swing.value.startswith("inward")
        hinge_left = swing.value.endswith("left")
        hinge = seg_a if hinge_left else seg_b
        jamb = seg_b if hinge_left else seg_a
        n_dir = interior_n if inward else (-interior_n[0], -interior_n[1])

        closed = (jamb[0] - hinge[0], jamb[1] - hinge[1])  # leaf lying along the wall
        cross = closed[0] * n_dir[1] - closed[1] * n_dir[0]
        sign = 1.0 if cross > 0 else -1.0
        arc = [
            (hinge[0] + v[0], hinge[1] + v[1])
            for v in (geometry.rotate(closed, sign * step) for step in range(0, 91, 10))
        ]
        leaf_end = arc[-1]
        parts.append(_polyline(arc, t, style.door_color, 1.2))
        parts.append(_polyline([hinge, leaf_end], t, style.door_color, 2.5))

    return parts
