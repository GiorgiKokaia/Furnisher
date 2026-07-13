import xml.etree.ElementTree as ET

from furnisher.render2d import render_plan


def _render_and_parse(plan):
    svg = render_plan(plan)
    return svg, ET.fromstring(svg)  # raises if not well-formed XML


def test_studio_renders(studio):
    svg, root = _render_and_parse(studio)
    assert root.tag.endswith("svg")
    for label in ("Main", "Bathroom", "Entry"):
        assert label in svg
    assert "m²" in svg


def test_two_bedroom_renders(two_bedroom):
    svg, _ = _render_and_parse(two_bedroom)
    for label in ("Kitchen", "Bedroom 1", "Bedroom 2", "Living Room", "Hallway"):
        assert label in svg


def test_door_and_window_symbols_present(two_bedroom):
    svg, root = _render_and_parse(two_bedroom)
    ns = {"svg": "http://www.w3.org/2000/svg"}
    polylines = root.findall(".//svg:polyline", ns)
    polygons = root.findall(".//svg:polygon", ns)
    # 6 rooms + 5 window panes
    assert len(polygons) == 11
    # every door contributes a gap + arc + leaf; passage contributes a gap; windows a center line
    assert len(polylines) >= 5 * 3 + 1 + 5


def test_render_is_deterministic(studio):
    assert render_plan(studio) == render_plan(studio)
