import json
from pathlib import Path

import pytest

from furnisher.catalog import Catalog, CatalogCache, CatalogItem, SearchFilters
from furnisher.catalog.adapters.generic import GenericProvider
from furnisher.catalog.adapters.ikea import parse_measurements, parse_search_products

FIXTURES = Path(__file__).parent / "fixtures" / "ikea"


@pytest.fixture
def generic():
    return GenericProvider()


@pytest.fixture
def catalog(generic, tmp_path):
    return Catalog([generic], CatalogCache(tmp_path / "cache"))


def test_generic_search_matches_tags(generic):
    items = generic.search("sofa", SearchFilters())
    assert items
    assert all("sofa" in (i.name + i.type_name + i.raw["tags"]).lower() for i in items)


def test_generic_all_items_have_dimensions(generic):
    for item in generic.search("", SearchFilters(), limit=100):
        assert item.width_m > 0 and item.depth_m > 0 and item.height_m > 0
        assert item.price > 0 and item.currency == "EUR"


def test_facade_post_filters_price_and_size(catalog):
    items = catalog.search("sofa", SearchFilters(price_max=400))
    assert items
    assert all(i.price <= 400 for i in items)
    narrow = catalog.search("wardrobe", SearchFilters(max_width_m=1.2))
    assert narrow and all(i.width_m <= 1.2 for i in narrow)


def test_facade_caches_searches(generic, tmp_path):
    cache = CatalogCache(tmp_path / "cache")
    catalog = Catalog([generic], cache)
    first = catalog.search("bed", SearchFilters())
    # poison the provider: cached search must not hit it again
    catalog.providers["generic"] = None
    second = catalog.search("bed", SearchFilters())
    assert [i.id for i in first] == [i.id for i in second]


def test_facade_get_routes_by_prefix(catalog):
    item = catalog.get("generic:loft-sofa-3")
    assert item.width_m == 2.28
    with pytest.raises(KeyError):
        catalog.get("nope:123")


def test_cache_item_round_trip(tmp_path):
    cache = CatalogCache(tmp_path / "cache")
    item = CatalogItem(
        id="x:1",
        provider="x",
        name="Thing",
        type_name="thing",
        width_m=1,
        depth_m=1,
        height_m=1,
        price=9.5,
        currency="EUR",
    )
    cache.put_item(item)
    assert cache.get_item("x:1") == item
    assert cache.get_item("x:2") is None


# --- IKEA parsers against recorded fixtures (no network) ---


def test_ikea_parse_search_fixture():
    payload = json.loads((FIXTURES / "search-sofa.json").read_text(encoding="utf-8"))
    products = parse_search_products(payload)
    assert len(products) == 3  # 2 main + 1 shelf, deduped
    first = products[0]
    assert first["name"] == "VIMLE"
    assert first["salesPrice"]["currencyCode"] == "EUR"
    assert first["pipUrl"].startswith("https://www.ikea.com/")


def test_ikea_parse_measurements_fixture():
    html = (FIXTURES / "pip-glostad.html").read_text(encoding="utf-8")
    dims = parse_measurements(html)
    assert dims["width_m"] == pytest.approx(1.71)
    assert dims["depth_m"] == pytest.approx(0.78)
    # GLOSTAD lists no overall height; falls back to backrest height
    assert dims["height_m"] == pytest.approx(0.68)


def test_ikea_measurements_ignore_package_dims():
    html = (FIXTURES / "pip-glostad.html").read_text(encoding="utf-8")
    dims = parse_measurements(html)
    assert dims["width_m"] != pytest.approx(0.65)  # 65cm is the flat-pack box width


def test_ikea_bed_length_used_as_depth():
    # beds list "Länge" (00001) instead of "Tiefe" (00044) — real MALM structure
    html = (
        '<script>{"measurements":[{"measure": "209 cm", "name": "Länge", "type": "00001"},'
        '{"measure": "156 cm", "name": "Breite", "type": "00047"},'
        '{"measure": "100 cm", "name": "Höhe", "type": "00041"}]}</script>'
    )
    dims = parse_measurements(html)
    assert dims == {
        "width_m": pytest.approx(1.56),
        "depth_m": pytest.approx(2.09),
        "height_m": pytest.approx(1.0),
    }
