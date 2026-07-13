"""Room-crop grounding render (docs/06 mode 3).

Consumer is a vision model, so clarity beats beauty: white floor, black walls, numbered
furniture footprints matching a returned legend, labeled doors/windows, a camera marker.
Returns (svg_text, legend_lines, camera_description).
"""

from __future__ import annotations

import html

from furnisher.layout import placement_polygon
from furnisher.model import FloorPlan, OpeningKind, Placement
from furnisher.model import geometry
from furnisher.render2d.svg import RenderStyle, _fmt, _points_attr, _polyline, _Transform

_CROP_PAD = 0.7  # meters around the room


def _wall_name(normal: tuple[float, float]) -> str:
    """The interior normal points away from the wall the opening sits in."""
    nx, ny = normal
    if abs(nx) > abs(ny):
        return "west" if nx > 0 else "east"
    return "south" if ny > 0 else "north"


def render_room_crop(
    plan: FloorPlan,
    room_id: str,
    placements: list[Placement],
    catalog,
) -> tuple[str, list[str], str]:
    room = plan.room(room_id)
    xs = [p[0] for p in room.polygon]
    ys = [p[1] for p in room.polygon]
    bounds = (min(xs) - _CROP_PAD, min(ys) - _CROP_PAD, max(xs) + _CROP_PAD, max(ys) + _CROP_PAD)

    style = RenderStyle(scale=110, padding=0.0, background="#ffffff", wall_color="#000000")
    t = _Transform(plan, style, bounds=bounds)
    wall_px = style.wall_thickness * style.scale

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{_fmt(t.width_px)}" '
        f'height="{_fmt(t.height_px)}" viewBox="0 0 {_fmt(t.width_px)} {_fmt(t.height_px)}" '
        'font-family="Arial, sans-serif">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<polygon points="{_points_attr(room.polygon, t)}" fill="#ffffff" '
        f'stroke="#000000" stroke-width="{_fmt(wall_px)}"/>',
    ]

    # openings on this room's walls, labeled in plain words
    camera_desc = "eye level, wide angle, from inside the room"
    camera_drawn = False
    for op in plan.openings:
        if op.room != room_id and op.connects != room_id:
            continue
        seg_a, seg_b = plan.opening_segment(op)
        u = geometry.unit(seg_a, seg_b)
        n = geometry.left_normal(u)
        if op.room != room_id:  # opening owned by the neighbor: its normal points away from us
            n = (-n[0], -n[1])
        mid = ((seg_a[0] + seg_b[0]) / 2, (seg_a[1] + seg_b[1]) / 2)
        wall = _wall_name(n)
        if op.kind == OpeningKind.window:
            parts.append(_polyline([seg_a, seg_b], t, "#2b7fd4", wall_px + 2, linecap="butt"))
            label = "window"
        else:
            parts.append(_polyline([seg_a, seg_b], t, "#ffffff", wall_px + 2, linecap="butt"))
            parts.append(_polyline([seg_a, seg_b], t, "#c48a3f", 4, linecap="butt"))
            label = "door" if op.kind == OpeningKind.door else "open passage"
            if not camera_drawn:  # camera looks in from the first door
                cam = (mid[0] + n[0] * 0.45, mid[1] + n[1] * 0.45)
                cx, cy = t(cam)
                parts.append(f'<circle cx="{_fmt(cx)}" cy="{_fmt(cy)}" r="9" fill="#d43f3f"/>')
                parts.append(
                    _polyline([cam, (cam[0] + n[0] * 0.6, cam[1] + n[1] * 0.6)], t, "#d43f3f", 3)
                )
                parts.append(
                    f'<text x="{_fmt(cx)}" y="{_fmt(cy - 14)}" text-anchor="middle" '
                    f'fill="#d43f3f" font-size="14" font-weight="bold">CAMERA</text>'
                )
                camera_desc = f"eye level from the {label} in the {wall} wall, wide angle"
                camera_drawn = True
        lx, ly = t((mid[0] + n[0] * 0.28, mid[1] + n[1] * 0.28))
        parts.append(
            f'<text x="{_fmt(lx)}" y="{_fmt(ly)}" text-anchor="middle" fill="#555" '
            f'font-size="13">{label} ({wall} wall)</text>'
        )

    # numbered furniture footprints, biggest first (matches photo attachment order)
    legend: list[str] = []
    room_placements = sorted(
        (p for p in placements if p.room == room_id),
        key=lambda p: catalog.get(p.item_ref).width_m * catalog.get(p.item_ref).depth_m,
        reverse=True,
    )
    for n_item, placement in enumerate(room_placements, start=1):
        item = catalog.get(placement.item_ref)
        poly = placement_polygon(placement, item)
        pts = list(poly.exterior.coords)[:4]
        parts.append(
            f'<polygon points="{_points_attr(pts, t)}" fill="#eeeeee" '
            'stroke="#333333" stroke-width="2.5"/>'
        )
        front = geometry.rotate((0, -1), placement.rotation)
        cx_w, cy_w = poly.centroid.x, poly.centroid.y
        tick_to = (cx_w + front[0] * item.depth_m * 0.48, cy_w + front[1] * item.depth_m * 0.48)
        parts.append(_polyline([(cx_w, cy_w), tick_to], t, "#333333", 2))
        sx, sy = t((cx_w, cy_w))
        parts.append(
            f'<text x="{_fmt(sx)}" y="{_fmt(sy + 8)}" text-anchor="middle" fill="#000" '
            f'font-size="24" font-weight="bold">{n_item}</text>'
        )
        legend.append(
            f"{n_item}. {item.name} — {item.type_name}, "
            f"{item.width_m * 100:.0f}×{item.depth_m * 100:.0f} cm footprint, "
            f"{item.height_m * 100:.0f} cm tall"
        )

    parts.append(
        f'<text x="12" y="24" fill="#000" font-size="16" font-weight="bold">'
        f"{html.escape(room.label())} — top-down plan, numbers = furniture legend</text>"
    )
    parts.append("</svg>")
    return "\n".join(parts), legend, camera_desc
