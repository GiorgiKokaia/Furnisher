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

    def __init__(self, plan: FloorPlan, style: RenderStyle, bounds=None):
        if bounds is not None:
            xs, ys = [bounds[0], bounds[2]], [bounds[1], bounds[3]]
        else:
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


def _dims_label(room) -> str:
    """Bounding-box dimensions + area; '≈' marks non-rectangular rooms where W × H is the bbox."""
    xs = [p[0] for p in room.polygon]
    ys = [p[1] for p in room.polygon]
    w, h = max(xs) - min(xs), max(ys) - min(ys)
    area = room.area()
    approx = "" if abs(area - w * h) < 1e-6 else "≈ "
    return f"{approx}{_fmt(w)} × {_fmt(h)} m · {area:.1f} m²"


def render_plan(
    plan: FloorPlan,
    style: RenderStyle | None = None,
    *,
    placements=None,
    catalog=None,
) -> str:
    """Empty plan, or furnished when `placements` (+ a catalog for item lookup) is given."""
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

    # Furniture footprints (scale-correct: real catalog dims + pose).
    if placements:
        if catalog is None:
            raise ValueError("rendering placements requires a catalog for item lookup")
        for p in placements:
            parts.extend(_render_placement(p, catalog, t, style))

    # Labels last, on top of everything. With furniture present, labels move to the room's
    # top-left corner so they don't sit on top of the pieces.
    for room in plan.rooms:
        if placements:
            xs = [p[0] for p in room.polygon]
            ys = [p[1] for p in room.polygon]
            lx, ly = t((min(xs) + 0.14, max(ys) - 0.12))
            parts.append(
                f'<text x="{_fmt(lx)}" y="{_fmt(ly + 10)}" fill="{style.label_color}" '
                f'font-size="11" font-weight="600">{html.escape(room.label())} '
                f'<tspan fill="{style.sublabel_color}" font-weight="400" font-size="10">'
                f"{_dims_label(room)}</tspan></text>"
            )
        else:
            cx, cy = t(geometry.centroid(room.polygon))
            parts.append(
                f'<text x="{_fmt(cx)}" y="{_fmt(cy)}" text-anchor="middle" '
                f'fill="{style.label_color}" font-size="14" font-weight="600">'
                f"{html.escape(room.label())}</text>"
            )
            parts.append(
                f'<text x="{_fmt(cx)}" y="{_fmt(cy + 16)}" text-anchor="middle" '
                f'fill="{style.sublabel_color}" font-size="11">{_dims_label(room)}</text>'
            )

    parts.append("</svg>")
    return "\n".join(parts)


_PLACEMENT_TINTS = [
    (("bed",), "#e6edf8"),
    (("sofa", "armchair", "loveseat"), "#f8efe2"),
    (("wardrobe", "dresser", "cabinet", "chest", "bookcase", "bookshelf", "shelf"), "#efe9e1"),
    (("table", "desk", "bench"), "#f7f4ec"),
    (("lamp", "light"), "#fdf3da"),
    (("chair", "stool"), "#f3f1ea"),
]


def _placement_fill(item) -> str:
    haystack = f"{item.type_name} {item.name}".lower()
    for keywords, color in _PLACEMENT_TINTS:
        if any(k in haystack for k in keywords):
            return color
    return "#fbf9f3"


def _render_placement(placement, catalog, t: _Transform, style: RenderStyle) -> list[str]:
    from furnisher.layout import placement_polygon  # shared pose math; no cycle (layout -> model)

    item = catalog.get(placement.item_ref)
    poly = placement_polygon(placement, item)
    pts = list(poly.exterior.coords)[:4]
    parts = [
        # thick round-join stroke fakes soft corners on the rotated rect
        f'<polygon points="{_points_attr(pts, t)}" fill="{_placement_fill(item)}" '
        'fill-opacity="0.94" stroke="#7a6a55" stroke-width="2" stroke-linejoin="round"/>'
    ]
    cx, cy = poly.centroid.x, poly.centroid.y
    # front tick: shows orientation (front = local -y at rotation 0)
    front = geometry.rotate((0, -1), placement.rotation)
    d = item.depth_m / 2
    tick_from = (cx + front[0] * d * 0.45, cy + front[1] * d * 0.45)
    tick_to = (cx + front[0] * d * 0.95, cy + front[1] * d * 0.95)
    parts.append(_polyline([tick_from, tick_to], t, "#b0a08a", 1.5))

    # labels only where they fit; rotate along tall narrow items; nothing on tiny ones
    min_x, min_y, max_x, max_y = poly.bounds
    ext_x = (max_x - min_x) * style.scale
    ext_y = (max_y - min_y) * style.scale
    if max(ext_x, ext_y) < 34:
        return parts
    sx, sy = t((cx, cy))
    transform = f' transform="rotate(-90 {_fmt(sx)} {_fmt(sy)})"' if ext_y > ext_x * 1.4 else ""
    parts.append(
        f'<text x="{_fmt(sx)}" y="{_fmt(sy)}" text-anchor="middle" fill="#5d5142" '
        f'font-size="9"{transform}>{html.escape(item.name)}</text>'
    )
    if min(ext_x, ext_y) >= 46:
        parts.append(
            f'<text x="{_fmt(sx)}" y="{_fmt(sy + 10)}" text-anchor="middle" fill="#9a8d78" '
            f'font-size="8"{transform}>{item.width_m * 100:.0f}×{item.depth_m * 100:.0f}</text>'
        )
    return parts


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
