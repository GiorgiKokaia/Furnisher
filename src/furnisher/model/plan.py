"""Canonical floor plan data model (docs/01). Everything else consumes this."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field
from shapely.geometry import LineString, Polygon as ShapelyPolygon

from furnisher.model import geometry
from furnisher.model.geometry import Point

# How far an opening's segment may sit from the connected room's boundary and still count as
# adjacent — covers wall thickness, which the schema doesn't model (docs/01).
WALL_ADJACENCY_TOL = 0.35

EXTERIOR = "exterior"


class RoomType(str, Enum):
    living_room = "living_room"
    bedroom = "bedroom"
    kitchen = "kitchen"
    bathroom = "bathroom"
    wc = "wc"
    hallway = "hallway"
    dining_room = "dining_room"
    office = "office"
    balcony = "balcony"
    storage = "storage"
    other = "other"


class OpeningKind(str, Enum):
    door = "door"
    window = "window"
    opening = "opening"  # doorless passage


class DoorSwing(str, Enum):
    inward_left = "inward_left"
    inward_right = "inward_right"
    outward_left = "outward_left"
    outward_right = "outward_right"
    sliding = "sliding"
    none = "none"


class Room(BaseModel):
    id: str
    type: RoomType = RoomType.other
    polygon: list[Point] = Field(min_length=3)
    ceiling_height: float | None = None

    def shapely_polygon(self) -> ShapelyPolygon:
        return ShapelyPolygon(self.polygon)

    def area(self) -> float:
        return abs(geometry.signed_area(self.polygon))

    def label(self) -> str:
        return self.id.replace("-", " ").replace("_", " ").title()


class Opening(BaseModel):
    id: str
    kind: OpeningKind
    room: str  # room whose polygon edge this opening sits on
    edge: int  # index into polygon edges: vertex i -> vertex (i+1) % n
    offset: float = Field(ge=0)  # meters from edge start to opening start
    width: float = Field(gt=0)
    height: float = 2.0
    swing: DoorSwing | None = None  # doors; inward = into `room`
    connects: str | None = None  # doors/passages: other room id or "exterior"
    sill_height: float | None = None  # windows; renderers default to 0.85


class Placement(BaseModel):
    id: str
    item_ref: str  # catalog item id, e.g. "ikea:00263850" (docs/03)
    room: str
    position: Point  # footprint center, meters
    rotation: float = 0.0  # CCW degrees; 0 = item width along +x
    note: str | None = None


class FloorPlan(BaseModel):
    schema_version: str = "0.1"
    name: str = "Untitled"
    ceiling_height: float = 2.6
    rooms: list[Room]
    openings: list[Opening] = Field(default_factory=list)

    def room(self, room_id: str) -> Room:
        for room in self.rooms:
            if room.id == room_id:
                return room
        raise KeyError(f"no room with id {room_id!r}")

    def opening_segment(self, opening: Opening) -> tuple[Point, Point]:
        """The opening's span on its wall edge, in world coordinates."""
        polygon = self.room(opening.room).polygon
        a, b = geometry.edge(polygon, opening.edge)
        return (
            geometry.point_along(a, b, opening.offset),
            geometry.point_along(a, b, opening.offset + opening.width),
        )

    def total_area(self) -> float:
        return sum(room.area() for room in self.rooms)

    def validate_plan(self) -> list[str]:
        """Geometric/semantic checks beyond field validation. Returns human-readable errors."""
        errors: list[str] = []
        room_ids = [room.id for room in self.rooms]

        for ids, what in ((room_ids, "room"), ([o.id for o in self.openings], "opening")):
            for dup in sorted({i for i in ids if ids.count(i) > 1}):
                errors.append(f"duplicate {what} id {dup!r}")

        for room in self.rooms:
            if not room.shapely_polygon().is_valid:
                errors.append(f"room {room.id!r}: polygon is self-intersecting or degenerate")
            elif not geometry.is_ccw(room.polygon):
                errors.append(
                    f"room {room.id!r}: polygon must be counter-clockwise "
                    "(reverse the vertex order)"
                )

        for i, room_a in enumerate(self.rooms):
            for room_b in self.rooms[i + 1 :]:
                poly_a, poly_b = room_a.shapely_polygon(), room_b.shapely_polygon()
                if not (poly_a.is_valid and poly_b.is_valid):
                    continue
                overlap = poly_a.intersection(poly_b).area
                if overlap > 1e-4:  # shared walls touch with zero area; anything more is overlap
                    errors.append(
                        f"rooms {room_a.id!r} and {room_b.id!r} overlap ({overlap:.2f} m²)"
                    )

        for op in self.openings:
            if op.room not in room_ids:
                errors.append(f"opening {op.id!r}: unknown room {op.room!r}")
                continue
            polygon = self.room(op.room).polygon
            if not 0 <= op.edge < len(polygon):
                errors.append(
                    f"opening {op.id!r}: edge index {op.edge} out of range "
                    f"(room {op.room!r} has {len(polygon)} edges)"
                )
                continue
            length = geometry.edge_length(polygon, op.edge)
            if op.offset + op.width > length + 1e-6:
                errors.append(
                    f"opening {op.id!r}: does not fit on edge {op.edge} of room {op.room!r} "
                    f"(edge is {length:.2f} m, offset+width is {op.offset + op.width:.2f} m)"
                )
                continue
            if op.kind in (OpeningKind.door, OpeningKind.opening):
                if not op.connects:
                    errors.append(
                        f"opening {op.id!r}: {op.kind.value} must declare 'connects' "
                        f"(a room id or {EXTERIOR!r})"
                    )
                elif op.connects != EXTERIOR:
                    if op.connects not in room_ids:
                        errors.append(f"opening {op.id!r}: unknown connects room {op.connects!r}")
                    elif op.connects == op.room:
                        errors.append(f"opening {op.id!r}: connects room to itself")
                    else:
                        # The whole opening must hug the connected room's boundary (within
                        # wall-thickness tolerance), not merely touch it at one point.
                        seg_a, seg_b = self.opening_segment(op)
                        segment = LineString([seg_a, seg_b])
                        boundary = self.room(op.connects).shapely_polygon().exterior
                        probes = [segment.interpolate(t, normalized=True) for t in (0, 0.5, 1)]
                        if any(p.distance(boundary) > WALL_ADJACENCY_TOL for p in probes):
                            errors.append(
                                f"opening {op.id!r}: rooms {op.room!r} and {op.connects!r} "
                                "are not adjacent at this opening"
                            )

        by_edge: dict[tuple[str, int], list[Opening]] = {}
        for op in self.openings:
            if op.room in room_ids and 0 <= op.edge < len(self.room(op.room).polygon):
                by_edge.setdefault((op.room, op.edge), []).append(op)
        for (room_id, edge), ops in by_edge.items():
            ops.sort(key=lambda o: o.offset)
            for prev, nxt in zip(ops, ops[1:]):
                if prev.offset + prev.width > nxt.offset + 1e-6:
                    errors.append(
                        f"openings {prev.id!r} and {nxt.id!r} overlap "
                        f"on edge {edge} of room {room_id!r}"
                    )
        return errors
