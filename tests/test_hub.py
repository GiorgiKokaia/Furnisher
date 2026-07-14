import pytest
from fastapi.testclient import TestClient

from furnisher.catalog import Catalog
from furnisher.catalog.adapters.generic import GenericProvider
from furnisher.hub import Workspace, create_hub


class FakeLLM:
    """The hub only needs an LLM object to hand to furnish sessions; state() never calls it."""

    def complete(self, *a, **k):
        return "ok"


@pytest.fixture
def workspace(tmp_path):
    return Workspace(tmp_path / "ws")


@pytest.fixture
def client(workspace):
    hub = create_hub(workspace, llm=FakeLLM(), catalog=Catalog([GenericProvider()]))
    return TestClient(hub)


def test_workspace_seeds_starter_samples(workspace):
    ids = {s["id"] for s in workspace.list_samples()}
    assert {"studio", "two-bedroom", "my-apartment"} <= ids
    studio = next(s for s in workspace.list_samples() if s["id"] == "studio")
    assert studio["rooms"] == 3
    assert studio["area"] > 0
    assert studio["svg"].startswith("<svg")
    assert studio["has_project"] is False


def test_home_and_samples(client):
    assert "Furnisher" in client.get("/").text
    samples = client.get("/hub/samples").json()["samples"]
    assert any(s["id"] == "studio" for s in samples)


def test_new_layout_opens_editor_on_named_blank(client, workspace):
    body = client.post("/hub/new", json={"name": "Loft 2"}).json()
    assert body["sample_id"] == "loft-2"
    assert body["editor_url"] == "/editor/"
    # the editor is now pointed at the new (not-yet-saved) layout, carrying the name
    plan = client.get("/editor/api/plan").json()
    assert plan["sample_id"] == "loft-2"
    assert plan["plan"]["name"] == "Loft 2"
    assert plan["plan"]["rooms"] == []


def test_saving_a_new_layout_makes_it_a_sample(client, workspace):
    client.post("/hub/new", json={"name": "Tiny"})
    plan_body = {
        "name": "Tiny",
        "rooms": [{"id": "main", "type": "other",
                   "polygon": [[0, 0], [3, 0], [3, 3], [0, 3]]}],
        "openings": [],
    }
    saved = client.post("/editor/api/plan", json=plan_body).json()
    assert saved["saved"] is True
    assert workspace.has_sample("tiny")
    assert any(s["id"] == "tiny" for s in workspace.list_samples())


def test_new_layout_ids_are_unique(client, workspace):
    a = client.post("/hub/new", json={"name": "Place"}).json()["sample_id"]
    # save it so the id is taken, then request the same name again
    client.post("/editor/api/plan", json={
        "name": "Place",
        "rooms": [{"id": "r", "type": "other", "polygon": [[0, 0], [2, 0], [2, 2], [0, 2]]}],
        "openings": [],
    })
    b = client.post("/hub/new", json={"name": "Place"}).json()["sample_id"]
    assert a == "place" and b == "place-2"


def test_edit_redirects_to_editor(client):
    r = client.get("/hub/edit/studio", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/editor/"
    assert client.get("/editor/api/plan").json()["sample_id"] == "studio"


def test_edit_unknown_layout_404(client):
    assert client.get("/hub/edit/nope", follow_redirects=False).status_code == 404


def test_furnish_creates_project_and_opens_session(client, workspace):
    r = client.get("/hub/furnish/studio", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/furnish/"
    assert (workspace.project_dir("studio") / "project.json").exists()
    # the furnish app now serves that project
    state = client.get("/furnish/api/state").json()
    assert state["name"]  # Studio fixture
    assert "main" in state["rooms"]
    # and the sample now reports an in-progress session
    assert next(s for s in workspace.list_samples() if s["id"] == "studio")["has_project"]


def test_furnish_reopens_same_project(client, workspace):
    client.get("/hub/furnish/studio", follow_redirects=False)
    marker = workspace.project_dir("studio") / "project.json"
    first = marker.read_text(encoding="utf-8")
    # re-selecting continues the same project (does not recreate it)
    client.get("/hub/furnish/studio", follow_redirects=False)
    assert marker.read_text(encoding="utf-8") == first
