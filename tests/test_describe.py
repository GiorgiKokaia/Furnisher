import re

from furnisher.catalog import Catalog
from furnisher.catalog.adapters.generic import GenericProvider
from furnisher.model import Placement
from furnisher.render3d.describe import (
    describe_apartment_layout,
    describe_room_layout,
    room_camera,
)


def catalog():
    return Catalog([GenericProvider()])


def _bedroom_placements():
    return [
        Placement(id="bed", item_ref="generic:rest-double-bed-160", room="bedroom-1",
                  position=(1.2, 5.5), rotation=90),
        Placement(id="stand", item_ref="generic:dot-nightstand", room="bedroom-1",
                  position=(2.6, 6.5), rotation=0),
    ]


def test_room_camera_uses_a_door(two_bedroom):
    pos, fwd, desc = room_camera(two_bedroom, "bedroom-1")
    assert len(pos) == 2 and abs(fwd[0] ** 2 + fwd[1] ** 2 - 1) < 1e-6
    assert "eye level" in desc
    assert "doorway" in desc or "passage" in desc


def test_describe_room_layout_is_spatial(two_bedroom):
    text = describe_room_layout(two_bedroom, "bedroom-1", _bedroom_placements(), catalog())
    assert "Walls and openings:" in text
    assert "Rest Double Bed 160" in text  # named, biggest first
    # every item gets a wall/corner position, a frame position, and a facing direction
    assert "wall" in text or "corner" in text
    assert "of the frame" in text or "the viewer's" in text or "centred in the frame" in text
    assert "facing" in text
    # windows and the door are reported by wall
    assert "window" in text and "door" in text


def test_describe_room_layout_respects_rotation(two_bedroom):
    """A bed rotated 90 vs 0 must yield a different stated facing direction."""
    p0 = [Placement(id="bed", item_ref="generic:rest-double-bed-160", room="bedroom-1",
                    position=(1.2, 5.5), rotation=0)]
    p90 = [Placement(id="bed", item_ref="generic:rest-double-bed-160", room="bedroom-1",
                     position=(1.2, 5.5), rotation=90)]
    cam = room_camera(two_bedroom, "bedroom-1")
    t0 = describe_room_layout(two_bedroom, "bedroom-1", p0, catalog(), camera=cam)
    t90 = describe_room_layout(two_bedroom, "bedroom-1", p90, catalog(), camera=cam)
    facing0 = re.search(r"facing (north|south|east|west)", t0).group(1)
    facing90 = re.search(r"facing (north|south|east|west)", t90).group(1)
    assert facing0 != facing90


def test_describe_apartment_layout(two_bedroom):
    text = describe_apartment_layout(two_bedroom, _bedroom_placements(), catalog())
    assert "Room arrangement" in text
    assert "Furniture per room" in text
    assert "Rest Double Bed 160" in text
    # room quadrant guidance present
    assert "of the plan" in text
