"""Design-rule placement + rug (underlay) behaviour (docs/05)."""

import pytest

from furnisher.catalog import Catalog
from furnisher.catalog.adapters.generic import GenericProvider
from furnisher.layout import PlacementRequest, auto_place, placement_polygon, validate
from furnisher.layout.rules import category, is_underlay
from furnisher.model import Placement, geometry


@pytest.fixture
def cat():
    return Catalog([GenericProvider()])


def _req(cat, item_id, purpose, hint="wall"):
    return PlacementRequest(item=cat.get(item_id), purpose=purpose, hint=hint)


def test_category_and_underlay(cat):
    assert category(cat.get("generic:weave-rug-l")) == "rug"
    assert is_underlay(cat.get("generic:weave-rug-l"))
    assert category(cat.get("generic:loft-sofa-3")) == "sofa"
    assert category(cat.get("generic:dot-nightstand")) == "nightstand"
    assert category(cat.get("generic:focus-task-chair")) == "office_chair"
    assert not is_underlay(cat.get("generic:loft-sofa-3"))


def test_rug_may_overlap_furniture(cat, two_bedroom):
    reqs = [
        _req(cat, "generic:loft-sofa-3", "sofa"),
        _req(cat, "generic:weave-rug-m", "rug", hint="center"),
    ]
    placed, issues = auto_place(two_bedroom, "living-room", reqs, cat)
    assert {p.id for p in placed} == {"sofa", "rug"}
    assert not [i for i in issues if i.severity == "error"]
    # overlapping the sofa raises no validation error (rug is an underlay)
    assert not [i for i in validate(two_bedroom, placed, cat) if i.severity == "error"]


def _in_front_of(anchor, mover):
    """Is `mover` on the front side of `anchor` (front = local -y)?"""
    front = geometry.rotate((0.0, -1.0), anchor.rotation)
    d = (mover.position[0] - anchor.position[0], mover.position[1] - anchor.position[1])
    return front[0] * d[0] + front[1] * d[1] > 0


def test_nightstand_sits_beside_bed(cat, two_bedroom):
    placed, _ = auto_place(
        two_bedroom,
        "bedroom-1",
        [_req(cat, "generic:rest-double-bed-160", "bed"),
         _req(cat, "generic:dot-nightstand", "nightstand")],
        cat,
    )
    bed = next(p for p in placed if p.id == "bed")
    ns = next(p for p in placed if p.id == "nightstand")
    bed_poly = placement_polygon(bed, cat.get(bed.item_ref))
    ns_poly = placement_polygon(ns, cat.get(ns.item_ref))
    assert bed_poly.distance(ns_poly) < 0.2  # tucked right up against the bed


def test_coffee_table_in_front_of_sofa(cat, two_bedroom):
    placed, _ = auto_place(
        two_bedroom,
        "living-room",
        [_req(cat, "generic:loft-sofa-3", "sofa"),
         _req(cat, "generic:slab-coffee-table", "coffee")],
        cat,
    )
    assert _in_front_of(next(p for p in placed if p.id == "sofa"),
                        next(p for p in placed if p.id == "coffee"))


def test_office_chair_in_front_of_desk(cat, two_bedroom):
    placed, _ = auto_place(
        two_bedroom,
        "bedroom-2",
        [_req(cat, "generic:focus-desk", "desk"),
         _req(cat, "generic:focus-task-chair", "chair")],
        cat,
    )
    assert _in_front_of(next(p for p in placed if p.id == "desk"),
                        next(p for p in placed if p.id == "chair"))


def test_fill_cap_drops_overflow(cat, two_bedroom):
    # living-room is 3.5x4 = 14 m²; a 0.3 cap = 4.2 m². One 2.17 m² sofa fits, the second
    # would push past the cap and is dropped (not placed) with a warning.
    reqs = [_req(cat, "generic:loft-sofa-3", "sofa-a"),
            _req(cat, "generic:loft-sofa-3", "sofa-b")]
    placed, issues = auto_place(two_bedroom, "living-room", reqs, cat, max_fill_ratio=0.3)
    assert len(placed) == 1
    assert any("full" in i.message for i in issues)


def test_fill_cap_ignores_rugs(cat, two_bedroom):
    reqs = [_req(cat, "generic:loft-sofa-3", "sofa"),
            _req(cat, "generic:weave-rug-l", "rug", hint="center")]
    placed, _ = auto_place(two_bedroom, "living-room", reqs, cat, max_fill_ratio=0.3)
    # the rug is an underlay: it doesn't count toward the cap and is still placed
    assert {p.id for p in placed} == {"sofa", "rug"}


def test_added_item_anchors_to_existing_furniture(cat, two_bedroom):
    """Adding a nightstand when a bed already exists should still snap it beside the bed."""
    bed = Placement(id="bed", item_ref="generic:rest-double-bed-160", room="bedroom-1",
                    position=(0.9, 5.9), rotation=0)
    placed, _ = auto_place(
        two_bedroom,
        "bedroom-1",
        [_req(cat, "generic:dot-nightstand", "nightstand")],
        cat,
        existing=[bed],
    )
    assert len(placed) == 1
    bed_poly = placement_polygon(bed, cat.get(bed.item_ref))
    ns_poly = placement_polygon(placed[0], cat.get(placed[0].item_ref))
    assert bed_poly.distance(ns_poly) < 0.2
