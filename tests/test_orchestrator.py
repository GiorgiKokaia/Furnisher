"""Orchestrator wiring tests with a scripted fake LLM — no network."""

from pathlib import Path

import pytest

from furnisher.agent.models import Intent, ProposedItem, RoomOptions, StyleProfile
from furnisher.app.orchestrator import Orchestrator
from furnisher.catalog import Catalog
from furnisher.catalog.adapters.generic import GenericProvider
from furnisher.layout import validate
from furnisher.model import Placement
from furnisher.project import Project

FIXTURES = Path(__file__).parent / "fixtures"


class FakeLLM:
    """Returns canned objects per schema; exercises the tool path for realism."""

    def complete(self, content, *, system=None, tools=None):
        if tools:
            tools[0]("bed")  # simulate the agent searching
            return (
                "Option Essentials: generic:rest-double-bed-160 as the bed. "
                "Option Comfort adds generic:dot-nightstand."
            )
        return "canned chat reply"

    def complete_structured(self, content, schema, *, system=None):
        if schema is Intent:
            return Intent(action="furnish_room", room_id="bedroom-1", note="")
        if schema is RoomOptions:
            return RoomOptions(
                options=[
                    {
                        "label": "Essentials",
                        "items": [
                            {
                                "item_id": "generic:rest-double-bed-160",
                                "purpose": "bed",
                                "hint": "wall",
                            },
                            {"item_id": "generic:invented-item", "purpose": "ghost"},
                        ],
                        "rationale": "just a bed",
                    },
                    {
                        "label": "Comfort",
                        "items": [
                            {
                                "item_id": "generic:rest-double-bed-160",
                                "purpose": "bed",
                                "hint": "wall",
                            },
                            {
                                "item_id": "generic:dot-nightstand",
                                "purpose": "nightstand",
                                "hint": "free",
                                "anchor": "bed",
                            },
                        ],
                        "rationale": "bed plus nightstand",
                    },
                ]
            )
        if schema is StyleProfile:
            return StyleProfile(style_tags=["scandinavian"], notes="light woods")
        raise AssertionError(f"unexpected schema {schema}")


@pytest.fixture
def orch(tmp_path):
    project = Project.create(tmp_path / "proj", FIXTURES / "two-bedroom.yaml")
    return Orchestrator(project, Catalog([GenericProvider()]), FakeLLM())


def test_furnish_returns_options_without_placing(orch):
    result = orch.handle_message("furnish the first bedroom please")
    assert "pick one" in result["reply"]
    assert len(result["options"]) == 2
    # invented item was dropped by grounding; essentials has 1 real item
    assert len(result["options"][0]["items"]) == 1
    assert result["options"][1]["items"][1]["name"] == "Dot Nightstand"
    assert orch.project.placements == []  # nothing placed until the user picks


def test_choose_option_places_and_persists(orch):
    orch.handle_message("furnish the first bedroom please")
    result = orch.handle_message("2")  # digit shortcut picks Comfort
    assert "Comfort" in result["reply"]
    assert {p.item_ref for p in orch.project.placements} == {
        "generic:rest-double-bed-160",
        "generic:dot-nightstand",
    }
    assert [i["name"] for i in result["placed"]] == ["Rest Double Bed 160", "Dot Nightstand"]
    errors = [
        i
        for i in validate(orch.project.plan, orch.project.placements, orch.catalog)
        if i.severity == "error"
    ]
    assert errors == []
    again = Project.load(orch.project.path)
    assert len(again.placements) == 2
    assert (orch.project.path / "renders" / "plan.svg").exists()


def test_choose_without_pending(orch):
    result = orch.choose_option(0)
    assert "no options pending" in result["reply"]


def test_budget_flow(orch):
    orch.set_budget(1000)
    orch.handle_message("furnish the first bedroom please")
    orch.handle_message("1")
    remaining = orch.budget_remaining()
    assert remaining == 1000 - orch.project.spent(orch.catalog)


def test_clear_room(orch):
    orch.handle_message("furnish the first bedroom please")
    orch.handle_message("1")
    assert orch.project.placements
    orch.clear_room("bedroom-1")
    assert orch.project.placements == []


def test_undo_restores_placements(orch):
    orch.handle_message("furnish the first bedroom please")
    orch.handle_message("1")
    assert orch.project.placements
    assert orch.project.undo() is True
    assert orch.project.placements == []


def test_progress_callback(orch):
    seen = []
    orch.on_progress = seen.append
    orch.handle_message("furnish the first bedroom please")
    assert any("designing options" in m for m in seen)
    assert any("searching catalog" in m for m in seen)


class ReplaceLLM:
    """Routes to replace_item and proposes a cheaper sofa via the (grounded) tool path."""

    def __init__(self, replacement_id="generic:loft-sofa-2"):
        self.replacement_id = replacement_id

    def complete(self, content, *, system=None, tools=None):
        if tools:
            tools[0]("sofa")  # populate the grounding set with real ids
            return f"Best replacement: {self.replacement_id}, cheaper 2-seat sofa."
        return "canned chat reply"

    def complete_structured(self, content, schema, *, system=None):
        if schema is Intent:
            return Intent(action="replace_item", target="sofa", note="cheaper")
        if schema is ProposedItem:
            return ProposedItem(item_id=self.replacement_id, purpose="sofa")
        raise AssertionError(f"unexpected schema {schema}")


@pytest.fixture
def furnished(tmp_path):
    project = Project.create(tmp_path / "proj", FIXTURES / "two-bedroom.yaml")
    project.placements = [
        Placement(id="sofa", item_ref="generic:loft-sofa-3", room="living-room",
                  position=(7.0, 0.6), rotation=0),
    ]
    project.save()
    return project


def test_replace_item_swaps_and_keeps_spot(furnished):
    orch = Orchestrator(furnished, Catalog([GenericProvider()]), ReplaceLLM())
    result = orch.handle_message("replace the sofa with a cheaper one")
    assert "Replaced" in result["reply"]
    assert result["placed"][0]["name"] == "Loft Sofa 2"
    # exactly one placement, now the replacement, id preserved
    assert len(orch.project.placements) == 1
    swapped = orch.project.placements[0]
    assert swapped.id == "sofa"
    assert swapped.item_ref == "generic:loft-sofa-2"
    # persisted + still valid
    assert Project.load(orch.project.path).placements[0].item_ref == "generic:loft-sofa-2"
    errors = [
        i
        for i in validate(orch.project.plan, orch.project.placements, orch.catalog)
        if i.severity == "error"
    ]
    assert errors == []


def test_replace_item_unknown_target_lists_items(furnished):
    orch = Orchestrator(furnished, Catalog([GenericProvider()]), ReplaceLLM())
    result = orch.replace_item("nonexistent widget", None, "")
    assert "couldn't tell which item" in result["reply"]
    assert "Loft Sofa 3" in result["reply"]  # shows what is currently placed
    assert orch.project.placements[0].item_ref == "generic:loft-sofa-3"  # unchanged


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
