"""Orchestrator wiring tests with a scripted fake LLM — no network."""

from pathlib import Path

import pytest

from furnisher.agent.models import Intent, RoomProposal, StyleProfile
from furnisher.app.orchestrator import Orchestrator
from furnisher.catalog import Catalog
from furnisher.catalog.adapters.generic import GenericProvider
from furnisher.layout import validate
from furnisher.project import Project

FIXTURES = Path(__file__).parent / "fixtures"


class FakeLLM:
    """Returns canned objects per schema; exercises the tool path for realism."""

    def complete(self, content, *, system=None, tools=None):
        if tools:
            tools[0]("bed")  # simulate the agent searching
            return (
                "I picked generic:rest-double-bed-160 as the bed and "
                "generic:dot-nightstand as the nightstand."
            )
        return "canned chat reply"

    def complete_structured(self, content, schema, *, system=None):
        if schema is Intent:
            return Intent(action="furnish_room", room_id="bedroom-1", note="")
        if schema is RoomProposal:
            return RoomProposal(
                items=[
                    {"item_id": "generic:rest-double-bed-160", "purpose": "bed", "hint": "wall"},
                    {
                        "item_id": "generic:dot-nightstand",
                        "purpose": "nightstand",
                        "hint": "free",
                        "anchor": "bed",
                    },
                    {"item_id": "generic:invented-item", "purpose": "ghost", "hint": "free"},
                ],
                rationale="a bed and a nightstand",
            )
        if schema is StyleProfile:
            return StyleProfile(style_tags=["scandinavian"], notes="light woods")
        raise AssertionError(f"unexpected schema {schema}")


@pytest.fixture
def orch(tmp_path):
    project = Project.create(tmp_path / "proj", FIXTURES / "two-bedroom.yaml")
    return Orchestrator(project, Catalog([GenericProvider()]), FakeLLM())


def test_furnish_room_end_to_end(orch):
    reply = orch.handle_message("furnish the first bedroom please")
    assert "Rest Double Bed 160" in reply
    rooms = {p.room for p in orch.project.placements}
    assert rooms == {"bedroom-1"}
    # the invented item was dropped by grounding enforcement
    assert all("invented" not in p.item_ref for p in orch.project.placements)
    errors = [
        i
        for i in validate(orch.project.plan, orch.project.placements, orch.agent.catalog)
        if i.severity == "error"
    ]
    assert errors == []
    # persisted + rendered
    assert (orch.project.path / "renders" / "plan.svg").exists()
    again = Project.load(orch.project.path)
    assert len(again.placements) == 2


def test_budget_flow(orch):
    orch.set_budget(1000)
    orch.handle_message("furnish the first bedroom please")
    remaining = orch.budget_remaining()
    assert remaining is not None
    assert remaining == 1000 - orch.project.spent(orch.agent.catalog)


def test_clear_room(orch):
    orch.handle_message("furnish the first bedroom please")
    assert orch.project.placements
    orch.clear_room("bedroom-1")
    assert orch.project.placements == []


def test_undo_restores_placements(orch):
    orch.handle_message("furnish the first bedroom please")
    assert orch.project.placements
    assert orch.project.undo() is True
    assert orch.project.placements == []


def test_inspire_from_ikea(orch, monkeypatch):
    class FakeIkea:
        provider_id = "ikea"

        def inspiration_images(self, query, limit=4):
            return [
                {"url": "https://x/1.jpg", "title": "a"},
                {"url": "https://x/2.jpg", "title": "b"},
            ]

        def search(self, query, filters, limit=24):
            return []

        def get(self, item_id):
            raise KeyError(item_id)

    orch.catalog.providers["ikea"] = FakeIkea()
    monkeypatch.setattr(Orchestrator, "_download_image", staticmethod(lambda url: b"jpegbytes"))
    reply = orch.inspire_from_ikea("scandinavian bedroom")
    assert "pulled 2 IKEA photos" in reply
    saved = list((orch.project.path / "inspiration").glob("ikea-*.jpg"))
    assert len(saved) == 2
    assert orch.project.meta["style_profile"]["style_tags"] == ["scandinavian"]
