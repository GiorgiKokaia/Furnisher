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
