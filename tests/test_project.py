from pathlib import Path

import pytest

from furnisher.model import Placement
from furnisher.project import Project

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def project(tmp_path):
    return Project.create(tmp_path / "proj", FIXTURES / "studio.yaml")


def test_create_and_load_round_trip(project):
    project.meta["budget"] = 500
    project.placements = [
        Placement(id="p1", item_ref="generic:dot-nightstand", room="main", position=(1, 1))
    ]
    project.save()
    again = Project.load(project.path)
    assert again.meta["budget"] == 500
    assert again.placements == project.placements
    assert again.plan.room("main").area() == 20.0


def test_create_refuses_existing(project, tmp_path):
    with pytest.raises(FileExistsError):
        Project.create(project.path, FIXTURES / "studio.yaml")


def test_snapshot_undo(project):
    project.snapshot()
    project.placements = [
        Placement(id="p1", item_ref="generic:dot-nightstand", room="main", position=(1, 1))
    ]
    project.meta["budget"] = 999
    project.save()
    assert project.undo() is True
    assert project.placements == []
    assert project.meta["budget"] is None
    assert project.undo() is False  # snapshot consumed


def test_chat_log(project):
    project.append_chat("user", "hello")
    project.append_chat("assistant", "hi")
    history = project.chat_history()
    assert [h["role"] for h in history] == ["user", "assistant"]
