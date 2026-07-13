import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from furnisher.catalog import Catalog
from furnisher.catalog.adapters.generic import GenericProvider
from furnisher.model import Placement
from furnisher.project import Project
from furnisher.render2d import render_room_crop
from furnisher.render3d import generate_room_image

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def catalog():
    return Catalog([GenericProvider()])


def _bedroom_placements():
    return [
        Placement(
            id="bed",
            item_ref="generic:rest-double-bed-160",
            room="bedroom-1",
            position=(1.2, 5.5),
            rotation=90,
        ),
        Placement(
            id="stand",
            item_ref="generic:dot-nightstand",
            room="bedroom-1",
            position=(2.6, 6.5),
            rotation=0,
        ),
    ]


def test_room_crop_render(two_bedroom, catalog):
    svg, legend, camera = render_room_crop(two_bedroom, "bedroom-1", _bedroom_placements(), catalog)
    ET.fromstring(svg)  # well-formed
    assert len(legend) == 2
    assert legend[0].startswith("1. Rest Double Bed 160")  # biggest first
    assert "166×207 cm" in legend[0]
    assert "CAMERA" in svg
    assert "window" in svg and "door" in svg
    assert "doorway" in camera or "door" in camera


class FakeImageLLM:
    def __init__(self):
        self.calls = []

    def generate_image(self, content):
        self.calls.append(content)
        return b"\x89PNG fake"


@pytest.fixture
def project(tmp_path):
    project = Project.create(tmp_path / "proj", FIXTURES / "two-bedroom.yaml")
    project.placements = _bedroom_placements()
    project.save()
    return project


def test_generate_room_image_writes_and_caches(project, catalog):
    llm = FakeImageLLM()
    out = generate_room_image(llm, catalog, project, "bedroom-1")
    assert out.exists() and out.read_bytes().startswith(b"\x89PNG")
    assert out.with_suffix("").with_suffix(".prompt.txt").name  # prompt dumped
    prompt = (out.parent / (out.stem + ".prompt.txt")).read_text(encoding="utf-8")
    assert "Rest Double Bed 160" in prompt
    assert "4.5 × 3.0 m" in prompt

    # second call: cache hit, no new LLM call
    again = generate_room_image(llm, catalog, project, "bedroom-1")
    assert again == out
    assert len(llm.calls) == 1

    # feedback changes the hash -> regenerates
    third = generate_room_image(llm, catalog, project, "bedroom-1", feedback="wrong bed color")
    assert third != out
    assert len(llm.calls) == 2
    assert "wrong bed color" in (third.parent / (third.stem + ".prompt.txt")).read_text(
        encoding="utf-8"
    )


def test_generate_room_image_requires_placements(project, catalog):
    with pytest.raises(ValueError, match="no placements"):
        generate_room_image(FakeImageLLM(), catalog, project, "bedroom-2")
