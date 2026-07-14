import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from furnisher.agent.models import Intent, RoomOptions
from furnisher.app.webapp import create_app
from furnisher.project import Project

FIXTURES = Path(__file__).parent / "fixtures"


class FakeLLM:
    def complete(self, content, *, system=None, tools=None):
        if tools:
            tools[0]("bed")
            return "Option Basic: generic:rest-double-bed-160 as the bed."
        return "canned chat reply"

    def complete_structured(self, content, schema, *, system=None):
        if schema is Intent:
            return Intent(action="furnish_room", room_id="bedroom-1", note="")
        if schema is RoomOptions:
            return RoomOptions(
                options=[
                    {
                        "label": "Basic",
                        "items": [
                            {
                                "item_id": "generic:rest-double-bed-160",
                                "purpose": "bed",
                                "hint": "wall",
                            }
                        ],
                        "rationale": "a bed",
                    }
                ]
            )
        raise AssertionError(f"unexpected schema {schema}")


@pytest.fixture
def client(tmp_path):
    Project.create(tmp_path / "proj", FIXTURES / "two-bedroom.yaml")
    return TestClient(create_app(tmp_path / "proj", llm=FakeLLM()))


def _send(client, text):
    """POST /api/message and parse the NDJSON stream into (progress_lines, final)."""
    resp = client.post("/api/message", json={"text": text})
    lines = [json.loads(line) for line in resp.text.splitlines() if line.strip()]
    progress = [entry["progress"] for entry in lines if "progress" in entry]
    return progress, lines[-1]


def _furnish(client):
    _send(client, "furnish the first bedroom")
    _, final = _send(client, "1")
    return final


def test_state(client):
    body = client.get("/api/state").json()
    assert body["name"] == "Two-bedroom fixture"
    assert "bedroom-1" in body["rooms"]
    assert body["svg"].startswith("<svg")
    assert body["spent"] == 0
    assert body["svg_scale"] == 80


def test_message_streams_progress_and_options(client):
    progress, final = _send(client, "furnish the first bedroom")
    assert any("designing options" in p for p in progress)
    assert any("searching catalog" in p for p in progress)
    assert final["options"][0]["label"] == "Basic"
    assert final["options"][0]["items"][0]["name"] == "Rest Double Bed 160"
    assert final["state"]["spent"] == 0  # nothing placed yet


def test_choose_places_items(client):
    _send(client, "furnish the first bedroom")
    body = client.post("/api/choose", json={"index": 0}).json()
    assert "Basic" in body["reply"]
    assert body["placed"][0]["name"] == "Rest Double Bed 160"
    assert body["state"]["spent"] > 0
    assert "Rest Double Bed 160" in body["state"]["shopping_list"]
    # placements carry product detail for the piece popup (image/dims/price/url)
    bed = next(p for p in body["state"]["placements"] if p["id"] == "bed")
    assert bed["item"] == "Rest Double Bed 160"
    assert "cm" in bed["dims"]
    for field in ("image", "url", "price", "currency", "type"):
        assert field in bed


def test_undo(client):
    _furnish(client)
    body = client.post("/api/undo").json()
    assert body["ok"] is True
    assert body["state"]["spent"] == 0


def test_room_image_requires_placements(client):
    resp = client.post("/api/room-image", json={"room": "bedroom-2"})
    assert resp.status_code == 400
    assert "no placements" in resp.json()["error"]


def test_apartment_image_requires_placements(client):
    resp = client.post("/api/apartment-image", json={})
    assert resp.status_code == 400


def test_index(client):
    assert "Furnisher" in client.get("/").text


def test_placement_move_and_delete(client):
    _furnish(client)
    state = client.get("/api/state").json()
    assert 'data-pid="bed"' in state["svg"]
    bed = next(p for p in state["placements"] if p["id"] == "bed")

    # nudge 10cm toward the room center (bedroom-1 center is (2.25, 5.5)); snap off so the
    # wall magnet doesn't pull it straight back
    dx = 0.1 if bed["position"][0] < 2.25 else -0.1
    dy = 0.1 if bed["position"][1] < 5.5 else -0.1
    body = client.post(
        "/api/placement",
        json={"id": "bed", "action": "move", "dx": dx, "dy": dy, "snap": False},
    ).json()
    assert body["ok"] is True
    moved = next(p for p in body["state"]["placements"] if p["id"] == "bed")
    assert moved["position"] != bed["position"]

    body = client.post("/api/placement", json={"id": "bed", "action": "move", "dx": 50}).json()
    assert body["ok"] is False  # 50m east is not in the room
    assert "does not fit" in body["error"]

    body = client.post("/api/placement", json={"id": "bed", "action": "delete"}).json()
    assert body["ok"] is True
    assert body["state"]["spent"] == 0

    resp = client.post("/api/placement", json={"id": "ghost", "action": "move"})
    assert resp.status_code == 400


def test_drag_move_snaps_to_wall(client):
    from furnisher.layout import placement_polygon
    from shapely.geometry import LineString

    _furnish(client)
    state = client.get("/api/state").json()
    bed = next(p for p in state["placements"] if p["id"] == "bed")
    # drag toward the room center, landing within snap range (0.3m) of the origin wall:
    # a 0.2m nudge leaves it ~0.25m from the wall -> the magnet should pull it back flush
    dx = 0.2 if bed["position"][0] < 2.25 else -0.2
    dy = 0.2 if bed["position"][1] < 5.5 else -0.2
    body = client.post(
        "/api/placement", json={"id": "bed", "action": "move", "dx": dx, "dy": dy}
    ).json()
    assert body["ok"] is True
    # verify the snapped footprint hugs some wall at ~5cm
    moved = next(p for p in body["state"]["placements"] if p["id"] == "bed")
    from furnisher.catalog import Catalog
    from furnisher.catalog.adapters.generic import GenericProvider
    from furnisher.model import Placement

    catalog = Catalog([GenericProvider()])
    placement = Placement(
        id="bed",
        item_ref="generic:rest-double-bed-160",
        room="bedroom-1",
        position=tuple(moved["position"]),
        rotation=moved["rotation"],
    )
    footprint = placement_polygon(placement, catalog.get("generic:rest-double-bed-160"))
    room_polygon = [(0, 4), (4.5, 4), (4.5, 7), (0, 7)]
    edges = [LineString([room_polygon[i], room_polygon[(i + 1) % 4]]) for i in range(4)]
    assert min(footprint.distance(e) for e in edges) == pytest.approx(0.05, abs=0.02)
