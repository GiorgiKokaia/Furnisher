import pytest

from furnisher.catalog import Catalog
from furnisher.catalog.adapters.generic import GenericProvider
from furnisher.layout import PlacementRequest, auto_place, validate


@pytest.fixture(scope="module")
def catalog():
    return Catalog([GenericProvider()])


@pytest.fixture
def plan(two_bedroom):
    return two_bedroom


def _req(catalog, item_id, purpose, **kw):
    return PlacementRequest(item=catalog.get(item_id), purpose=purpose, **kw)


def test_bedroom_set_places_clean(plan, catalog):
    requests = [
        _req(catalog, "generic:rest-double-bed-160", "bed"),
        _req(catalog, "generic:keep-wardrobe-2d", "wardrobe"),
        _req(catalog, "generic:dot-nightstand", "nightstand", anchor="bed"),
    ]
    placed, issues = auto_place(plan, "bedroom-1", requests, catalog)
    assert issues == []
    assert len(placed) == 3
    assert [i for i in validate(plan, placed, catalog) if i.severity == "error"] == []


def test_solver_is_deterministic(plan, catalog):
    requests = [
        _req(catalog, "generic:rest-double-bed-160", "bed"),
        _req(catalog, "generic:keep-wardrobe-2d", "wardrobe"),
    ]
    a, _ = auto_place(plan, "bedroom-2", requests, catalog)
    b, _ = auto_place(plan, "bedroom-2", requests, catalog)
    assert a == b


def test_anchored_item_sits_adjacent(plan, catalog):
    requests = [
        _req(catalog, "generic:rest-double-bed-160", "bed"),
        _req(catalog, "generic:dot-nightstand", "nightstand", anchor="bed"),
    ]
    placed, issues = auto_place(plan, "bedroom-1", requests, catalog)
    assert issues == []
    bed = next(p for p in placed if p.id == "bed")
    stand = next(p for p in placed if p.id == "nightstand")
    dist = (
        (bed.position[0] - stand.position[0]) ** 2 + (bed.position[1] - stand.position[1]) ** 2
    ) ** 0.5
    assert dist < 1.6  # right next to the bed, not across the room


def test_impossible_item_reports_issue(plan, catalog):
    # the 2x4 hallway has six openings; their swing arcs + corridors leave no room for a sofa
    placed, issues = auto_place(
        plan, "hallway", [_req(catalog, "generic:loft-sofa-3", "sofa")], catalog
    )
    assert placed == []
    assert any("could not place" in i.message for i in issues)


def test_respects_existing_placements(plan, catalog):
    first, _ = auto_place(
        plan, "bedroom-1", [_req(catalog, "generic:rest-double-bed-160", "bed")], catalog
    )
    second, issues = auto_place(
        plan,
        "bedroom-1",
        [_req(catalog, "generic:keep-wardrobe-3d", "wardrobe")],
        catalog,
        existing=first,
    )
    assert issues == []
    combined = first + second
    assert [i for i in validate(plan, combined, catalog) if i.severity == "error"] == []
