import pytest

from furnisher.authoring import PlanLoadError, plan_from_dict


def test_rect_desugars_to_ccw_polygon():
    plan = plan_from_dict(
        {
            "rooms": [{"id": "r", "type": "other", "rect": [1, 2, 3, 4]}],
        }
    )
    assert plan.room("r").polygon == [(1, 2), (4, 2), (4, 6), (1, 6)]
    assert plan.validate_plan() == []


def test_rect_and_polygon_are_mutually_exclusive():
    with pytest.raises(PlanLoadError, match="not both"):
        plan_from_dict(
            {
                "rooms": [{"id": "r", "rect": [0, 0, 1, 1], "polygon": [[0, 0], [1, 0], [1, 1]]}],
            }
        )


def test_offset_frac_centers_opening():
    plan = plan_from_dict(
        {
            "rooms": [{"id": "r", "type": "other", "rect": [0, 0, 5, 4]}],
            "openings": [
                {
                    "id": "w",
                    "kind": "window",
                    "room": "r",
                    "edge": 0,
                    "offset_frac": 0.5,
                    "width": 1.8,
                },
            ],
        }
    )
    # bottom edge is 5 m long: center 2.5, so the opening starts at 2.5 - 0.9
    assert plan.openings[0].offset == pytest.approx(1.6)


def test_offset_frac_needs_known_room():
    with pytest.raises(PlanLoadError, match="known room"):
        plan_from_dict(
            {
                "rooms": [{"id": "r", "rect": [0, 0, 5, 4]}],
                "openings": [
                    {
                        "id": "w",
                        "kind": "window",
                        "room": "nope",
                        "edge": 0,
                        "offset_frac": 0.5,
                        "width": 1.0,
                    },
                ],
            }
        )


def test_offset_and_offset_frac_are_mutually_exclusive():
    with pytest.raises(PlanLoadError, match="not both"):
        plan_from_dict(
            {
                "rooms": [{"id": "r", "rect": [0, 0, 5, 4]}],
                "openings": [
                    {
                        "id": "w",
                        "kind": "window",
                        "room": "r",
                        "edge": 0,
                        "offset": 1.0,
                        "offset_frac": 0.5,
                        "width": 1.0,
                    },
                ],
            }
        )
