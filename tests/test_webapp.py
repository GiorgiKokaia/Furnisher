from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from furnisher.agent.models import Intent, RoomProposal
from furnisher.app.webapp import create_app
from furnisher.project import Project

FIXTURES = Path(__file__).parent / "fixtures"


class FakeLLM:
    def complete(self, content, *, system=None, tools=None):
        if tools:
            tools[0]("bed")
            return "I picked generic:rest-double-bed-160 as the bed."
        return "canned chat reply"

    def complete_structured(self, content, schema, *, system=None):
        if schema is Intent:
            return Intent(action="furnish_room", room_id="bedroom-1", note="")
        if schema is RoomProposal:
            return RoomProposal(
                items=[
                    {"item_id": "generic:rest-double-bed-160", "purpose": "bed", "hint": "wall"}
                ],
                rationale="a bed",
            )
        raise AssertionError(f"unexpected schema {schema}")


@pytest.fixture
def client(tmp_path):
    Project.create(tmp_path / "proj", FIXTURES / "two-bedroom.yaml")
    return TestClient(create_app(tmp_path / "proj", llm=FakeLLM()))


def test_state(client):
    body = client.get("/api/state").json()
    assert body["name"] == "Two-bedroom fixture"
    assert "bedroom-1" in body["rooms"]
    assert body["svg"].startswith("<svg")
    assert body["spent"] == 0


def test_message_furnishes_and_updates_state(client):
    body = client.post("/api/message", json={"text": "furnish the first bedroom"}).json()
    assert "Rest Double Bed 160" in body["reply"]
    assert body["state"]["spent"] > 0
    assert "Rest Double Bed 160" in body["state"]["shopping_list"]


def test_undo(client):
    client.post("/api/message", json={"text": "furnish the first bedroom"})
    body = client.post("/api/undo").json()
    assert body["ok"] is True
    assert body["state"]["spent"] == 0


def test_room_image_requires_placements(client):
    resp = client.post("/api/room-image", json={"room": "bedroom-2"})
    assert resp.status_code == 400
    assert "no placements" in resp.json()["error"]


def test_index(client):
    assert "Furnisher" in client.get("/").text


def test_placement_move_and_delete(client):
    client.post("/api/message", json={"text": "furnish the first bedroom"})
    state = client.get("/api/state").json()
    assert 'data-pid="bed"' in state["svg"]
    bed = next(p for p in state["placements"] if p["id"] == "bed")

    # nudge 10cm toward the room center (bedroom-1 center is (2.25, 5.5)) — always legal
    dx = 0.1 if bed["position"][0] < 2.25 else -0.1
    dy = 0.1 if bed["position"][1] < 5.5 else -0.1
    body = client.post(
        "/api/placement", json={"id": "bed", "action": "move", "dx": dx, "dy": dy}
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
