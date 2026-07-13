"""Pure 2D geometry helpers.

World convention (docs/01): meters, x right, y up, room polygons CCW, angles CCW degrees.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

Point = tuple[float, float]


def signed_area(polygon: Sequence[Point]) -> float:
    """Shoelace area: positive for CCW polygons."""
    total = 0.0
    n = len(polygon)
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        total += x1 * y2 - x2 * y1
    return total / 2.0


def is_ccw(polygon: Sequence[Point]) -> bool:
    return signed_area(polygon) > 0


def edge(polygon: Sequence[Point], i: int) -> tuple[Point, Point]:
    """Edge i runs from vertex i to vertex (i+1) % n."""
    a = polygon[i]
    b = polygon[(i + 1) % len(polygon)]
    return (a[0], a[1]), (b[0], b[1])


def edge_length(polygon: Sequence[Point], i: int) -> float:
    a, b = edge(polygon, i)
    return math.hypot(b[0] - a[0], b[1] - a[1])


def point_along(a: Point, b: Point, dist: float) -> Point:
    """Point at `dist` meters from a toward b."""
    length = math.hypot(b[0] - a[0], b[1] - a[1])
    t = dist / length
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def unit(a: Point, b: Point) -> Point:
    length = math.hypot(b[0] - a[0], b[1] - a[1])
    return ((b[0] - a[0]) / length, (b[1] - a[1]) / length)


def left_normal(u: Point) -> Point:
    """For a CCW polygon, the left normal of an edge direction points into the room."""
    return (-u[1], u[0])


def rotate(v: Point, degrees: float) -> Point:
    rad = math.radians(degrees)
    c, s = math.cos(rad), math.sin(rad)
    return (v[0] * c - v[1] * s, v[0] * s + v[1] * c)


def centroid(polygon: Sequence[Point]) -> Point:
    """Area-weighted centroid; falls back to the vertex mean for degenerate polygons."""
    area = signed_area(polygon)
    if abs(area) < 1e-9:
        n = len(polygon)
        return (sum(p[0] for p in polygon) / n, sum(p[1] for p in polygon) / n)
    cx = cy = 0.0
    n = len(polygon)
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        cross = x1 * y2 - x2 * y1
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    return (cx / (6 * area), cy / (6 * area))
