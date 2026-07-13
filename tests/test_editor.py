from fastapi.testclient import TestClient

from furnisher.authoring import infer_connects, load_plan, plan_to_dict
from furnisher.authoring.editor import create_app
from furnisher.model import FloorPlan


def _two_room_json(**opening_overrides):
    opening = {"id": "d", "kind": "door", "room": "a", "edge": 1, "offset": 1.0, "width": 0.9}
    opening.update(opening_overrides)
    return {
        "name": "t",
        "rooms": [
            {"id": "a", "type": "living_room", "polygon": [[0, 0], [4, 0], [4, 3], [0, 3]]},
            {"id": "b", "type": "bedroom", "polygon": [[4, 0], [7, 0], [7, 3], [4, 3]]},
        ],
        "openings": [opening],
    }


def test_get_plan_missing_file_gives_empty_plan(tmp_path):
    client = TestClient(create_app(tmp_path / "new.yaml"))
    body = client.get("/api/plan").json()
    assert body["plan"]["rooms"] == []
    assert body["plan"]["name"] == "new"


def test_save_round_trip_with_inferred_connects(tmp_path):
    path = tmp_path / "plan.yaml"
    client = TestClient(create_app(path))
    body = client.post("/api/plan", json=_two_room_json()).json()
    assert body["saved"] is True
    assert body["issues"] == []
    assert body["plan"]["openings"][0]["connects"] == "b"

    saved = load_plan(path)
    assert saved.room("a").polygon == [(0, 0), (4, 0), (4, 3), (0, 3)]
    assert saved.openings[0].connects == "b"
    assert "rect:" in path.read_text(encoding="utf-8")  # sugar re-emitted


def test_save_rejects_schema_errors_without_writing(tmp_path):
    path = tmp_path / "plan.yaml"
    client = TestClient(create_app(path))
    bad = _two_room_json(width=-1)
    body = client.post("/api/plan", json=bad).json()
    assert body["saved"] is False
    assert body["issues"]
    assert not path.exists()


def test_validate_reports_geometry_issues_without_writing(tmp_path):
    path = tmp_path / "plan.yaml"
    client = TestClient(create_app(path))
    body = client.post("/api/validate", json=_two_room_json(offset=2.8)).json()
    assert any("does not fit" in issue for issue in body["issues"])
    assert not path.exists()


def test_render_endpoint_returns_svg(tmp_path):
    client = TestClient(create_app(tmp_path / "plan.yaml"))
    resp = client.post("/api/render", json=_two_room_json())
    assert resp.status_code == 200
    assert resp.text.startswith("<svg")


def test_render_empty_plan(tmp_path):
    client = TestClient(create_app(tmp_path / "plan.yaml"))
    resp = client.post("/api/render", json={"name": "x", "rooms": []})
    assert resp.status_code == 200
    assert "empty plan" in resp.text


def test_index_serves_editor(tmp_path):
    client = TestClient(create_app(tmp_path / "plan.yaml"))
    resp = client.get("/")
    assert "Furnisher" in resp.text


def test_infer_connects_exterior_door():
    plan = FloorPlan.model_validate(_two_room_json(edge=3))  # west wall: nothing beyond it
    infer_connects(plan)
    assert plan.openings[0].connects == "exterior"


def test_infer_connects_respects_explicit_value():
    plan = FloorPlan.model_validate(_two_room_json(connects="exterior"))
    infer_connects(plan)
    assert plan.openings[0].connects == "exterior"


def test_serializer_keeps_polygon_when_order_not_canonical():
    # Same rectangle but starting at a different corner: rect sugar would renumber the
    # edges that openings reference, so it must stay a polygon.
    plan = FloorPlan.model_validate(
        {
            "name": "t",
            "rooms": [{"id": "a", "type": "other", "polygon": [[4, 0], [4, 3], [0, 3], [0, 0]]}],
        }
    )
    data = plan_to_dict(plan)
    assert "polygon" in data["rooms"][0]
    assert "rect" not in data["rooms"][0]


def test_serializer_rect_has_no_float_noise():
    plan = FloorPlan.model_validate(
        {
            "name": "t",
            "rooms": [
                {
                    "id": "a",
                    "type": "other",
                    "polygon": [[4.0, -3.0], [10.55, -3.0], [10.55, -0.8], [4.0, -0.8]],
                }
            ],
        }
    )
    rect = plan_to_dict(plan)["rooms"][0]["rect"]
    assert rect == [4.0, -3.0, 6.55, 2.2]
