import pytest

from furnisher.catalog import Catalog
from furnisher.catalog.adapters.generic import GenericProvider
from furnisher.layout import validate
from furnisher.model import FloorPlan, Placement


@pytest.fixture(scope="module")
def catalog():
    return Catalog([GenericProvider()])


@pytest.fixture
def plan():
    # 5x4 living room with a door on the east wall (swings inward, hinge south) and a
    # window on the north wall.
    return FloorPlan.model_validate(
        {
            "name": "t",
            "rooms": [
                {"id": "room", "type": "living_room", "polygon": [[0, 0], [5, 0], [5, 4], [0, 4]]},
                {"id": "hall", "type": "hallway", "polygon": [[5, 0], [7, 0], [7, 4], [5, 4]]},
            ],
            "openings": [
                {
                    "id": "door",
                    "kind": "door",
                    "room": "room",
                    "edge": 1,
                    "offset": 0.5,
                    "width": 0.9,
                    "swing": "inward_left",
                    "connects": "hall",
                },
                {
                    "id": "window",
                    "kind": "window",
                    "room": "room",
                    "edge": 2,
                    "offset": 1.9,
                    "width": 1.2,
                    "sill_height": 0.85,
                },
            ],
        }
    )


def _place(item_ref, x, y, rotation=0.0, pid="p1", room="room"):
    return Placement(id=pid, item_ref=item_ref, room=room, position=(x, y), rotation=rotation)


def _errors(issues):
    return [i for i in issues if i.severity == "error"]


def _warnings(issues):
    return [i for i in issues if i.severity == "warning"]


def test_clean_layout(plan, catalog):
    # sofa back against the west wall, facing east (front = local -y; rot 90 CCW -> +x)
    issues = validate(plan, [_place("generic:loft-sofa-2", 0.55, 2.0, rotation=90)], catalog)
    assert issues == []


def test_item_outside_room(plan, catalog):
    issues = validate(plan, [_place("generic:loft-sofa-3", 4.5, 2.0)], catalog)
    assert any("does not fit inside room" in i.message for i in _errors(issues))


def test_overlapping_items(plan, catalog):
    issues = validate(
        plan,
        [
            _place("generic:loft-sofa-2", 2.0, 2.0, pid="a"),
            _place("generic:slab-coffee-table", 2.0, 2.0, pid="b"),
        ],
        catalog,
    )
    assert any("overlap" in i.message for i in _errors(issues))


def test_door_swing_blocked(plan, catalog):
    # coffee table inside the door's swing arc (door at east wall, y 0.5..1.4)
    issues = validate(plan, [_place("generic:slab-coffee-table", 4.4, 1.0)], catalog)
    assert any("swing" in i.message for i in _errors(issues))


def test_door_approach_blocked_from_other_room(plan, catalog):
    # wardrobe in the hallway right behind the door still blocks the approach
    issues = validate(
        plan, [_place("generic:keep-wardrobe-2d", 5.5, 1.0, rotation=90, room="hall")], catalog
    )
    assert any("approach" in i.message for i in _errors(issues))


def test_window_obstruction_warning(plan, catalog):
    # 2m wardrobe right under the window (sill 0.85)
    issues = validate(plan, [_place("generic:keep-wardrobe-2d", 2.5, 3.65)], catalog)
    assert not _errors(issues)
    assert any("obstructs window" in i.message for i in _warnings(issues))


def test_front_clearance_faces_wall(plan, catalog):
    # wardrobe facing straight into the west wall
    issues = validate(plan, [_place("generic:keep-wardrobe-2d", 0.5, 2.0, rotation=270)], catalog)
    assert any("faces a wall" in i.message for i in _warnings(issues))


def test_front_clearance_blocked_by_item(plan, catalog):
    # wardrobe against the south wall facing north, sofa parked right in front of it
    issues = validate(
        plan,
        [
            _place("generic:keep-wardrobe-2d", 2.5, 3.68, pid="w", rotation=0),
            _place("generic:loft-sofa-2", 2.5, 2.8, pid="s", rotation=180),
        ],
        catalog,
    )
    assert any("blocks access" in i.message for i in _warnings(issues))


def test_unknown_item_and_room(plan, catalog):
    issues = validate(
        plan,
        [
            _place("generic:no-such-thing", 1, 1, pid="a"),
            _place("generic:slab-coffee-table", 1, 1, pid="b", room="nope"),
        ],
        catalog,
    )
    msgs = [i.message for i in _errors(issues)]
    assert any("no generic catalog item" in m for m in msgs)
    assert any("unknown room" in m for m in msgs)
