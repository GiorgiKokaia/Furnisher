from furnisher.model import FloorPlan


def _plan(**overrides) -> FloorPlan:
    base = {
        "rooms": [
            {"id": "a", "type": "living_room", "polygon": [[0, 0], [4, 0], [4, 3], [0, 3]]},
            {"id": "b", "type": "bedroom", "polygon": [[4, 0], [7, 0], [7, 3], [4, 3]]},
        ],
        "openings": [],
    }
    base.update(overrides)
    return FloorPlan.model_validate(base)


def test_fixtures_are_valid(studio, two_bedroom):
    assert studio.validate_plan() == []
    assert two_bedroom.validate_plan() == []


def test_json_round_trip(two_bedroom):
    again = FloorPlan.model_validate_json(two_bedroom.model_dump_json())
    assert again == two_bedroom


def test_area(studio):
    assert studio.room("main").area() == 20.0
    assert abs(studio.total_area() - (20.0 + 4.4 + 3.6)) < 1e-9


def test_clockwise_polygon_rejected():
    plan = _plan(
        rooms=[
            {"id": "cw", "type": "other", "polygon": [[0, 0], [0, 3], [4, 3], [4, 0]]},
        ]
    )
    errors = plan.validate_plan()
    assert len(errors) == 1
    assert "counter-clockwise" in errors[0]


def test_self_intersecting_polygon_rejected():
    plan = _plan(
        rooms=[
            {"id": "bow", "type": "other", "polygon": [[0, 0], [4, 3], [4, 0], [0, 3]]},
        ]
    )
    assert any("self-intersecting" in e for e in plan.validate_plan())


def test_opening_must_fit_on_edge():
    plan = _plan(
        openings=[
            {
                "id": "d",
                "kind": "door",
                "room": "a",
                "edge": 1,
                "offset": 2.5,
                "width": 1.0,
                "connects": "b",
            },
        ]
    )
    errors = plan.validate_plan()
    assert any("does not fit on edge" in e for e in errors)


def test_door_requires_connects():
    plan = _plan(
        openings=[
            {"id": "d", "kind": "door", "room": "a", "edge": 1, "offset": 1.0, "width": 0.9},
        ]
    )
    assert any("must declare 'connects'" in e for e in plan.validate_plan())


def test_door_between_non_adjacent_rooms_rejected():
    # Door on room a's *west* wall claiming to connect to room b in the east.
    plan = _plan(
        openings=[
            {
                "id": "d",
                "kind": "door",
                "room": "a",
                "edge": 3,
                "offset": 1.0,
                "width": 0.9,
                "connects": "b",
            },
        ]
    )
    assert any("not adjacent" in e for e in plan.validate_plan())


def test_adjacent_door_accepted():
    plan = _plan(
        openings=[
            {
                "id": "d",
                "kind": "door",
                "room": "a",
                "edge": 1,
                "offset": 1.0,
                "width": 0.9,
                "connects": "b",
                "swing": "inward_left",
            },
        ]
    )
    assert plan.validate_plan() == []


def test_duplicate_ids_rejected():
    plan = _plan(
        rooms=[
            {"id": "a", "type": "other", "polygon": [[0, 0], [4, 0], [4, 3], [0, 3]]},
            {"id": "a", "type": "other", "polygon": [[5, 0], [9, 0], [9, 3], [5, 3]]},
        ]
    )
    assert any("duplicate room id" in e for e in plan.validate_plan())


def test_opening_segment(studio):
    door = next(o for o in studio.openings if o.id == "door-main-bath")
    a, b = studio.opening_segment(door)
    # bathroom edge 3 runs (5,2.2)->(5,0); offset 0.6, width 0.8 -> y 1.6 down to 0.8
    assert a == (5.0, 2.2 - 0.6)
    assert abs(b[1] - 0.8) < 1e-9
