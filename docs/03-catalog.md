# 03 — Furniture Catalog (provider-agnostic)

**Status:** M1 built — facade + cache + `generic` (18-item starter) + `ikea` adapters,
`furnisher catalog search/show` CLI
**Depends on:** nothing (01 references its item ids)
**Code home:** `src/furnisher/catalog/`

## Purpose

Search real furniture, fetch product **dimensions** (the scale-correctness backbone), **images**
(grounding for room renders), price, and product URL — from **any provider**, cached locally so
layouts and renders never depend on live endpoints.

**We are explicitly not married to IKEA.** The hard requirement is: the user (in **Georgia, the
republic**) must actually be able to order the items. Any provider whose API/site lets us search,
filter, and get images + dimensions qualifies. IKEA is just the first adapter because its data is
well-structured — **don't over-invest in that integration.**

## The contract (this is the part that matters)

Everything outside `catalog/` codes against this; adapters are plugins behind it:

```python
@dataclass
class SearchFilters:
    category: str | None = None        # normalized: "sofa", "bed", "wardrobe", ...
    price_max: float | None = None     # budget constraint plumbing (04/08)
    price_min: float | None = None
    max_width_m: float | None = None   # layout-driven filtering ("wardrobe ≤ 0.6m deep")
    max_depth_m: float | None = None
    max_height_m: float | None = None

class CatalogProvider(Protocol):
    provider_id: str                                   # "ikea", "generic", ...
    def search(self, query: str, filters: SearchFilters, limit: int = 24) -> list[CatalogItem]: ...
    def get(self, item_id: str) -> CatalogItem: ...

@dataclass
class CatalogItem:
    id: str              # "{provider_id}:{sku}", e.g. "ikea:00263850"
    provider: str
    name: str
    type_name: str       # "3-seat sofa"
    width_m: float       # x-extent at rotation=0
    depth_m: float
    height_m: float
    price: float
    currency: str
    url: str
    image_urls: list[str]
    raw: dict            # untouched source payload (3D asset mining later, see 10)
```

A `Catalog` facade owns the registered providers + the shared cache; `search()` can fan out to
all providers or one. If a provider can't express a filter natively, the facade post-filters —
adapters stay dumb.

Providers that can't do server-side filtering are fine: fetch broad, filter locally. The
*minimum* an adapter must deliver per item: assembled dimensions, ≥1 decent image, price, URL.
Items missing a footprint are rejected at the boundary — the layout engine never sees them.

## Adapters

### `ikea` (first, baseline) — BUILT, endpoints verified 2026-07-13

Spike findings (all endpoint knowledge lives in `catalog/adapters/ikea.py`):

- **Search:** `GET https://sik.search.blue.cdtapps.com/{cc}/{lc}/search-result-page?q=...&types=PRODUCT&size=N`
  → `searchResultPage.products.main.items[].product` (+ `shelves[].result.items[]`). Has name,
  `typeName`, `itemNo`, `salesPrice.numeral/currencyCode`, `mainImageUrl`/`contextualImageUrl`,
  `pipUrl`. The old `/search` path 404s; `/search-box` is autocomplete only.
  **No assembled dimensions in search results** (`itemMeasureReferenceText` was empty on all hits).
- **Dimensions:** product (PIP) page HTML embeds hydration JSON:
  `"measurements": [{"measure": "171 cm", "name": "Breite", "type": "00047"}, ...]`.
  Type codes are language-independent: `00047` width, `00044` depth, `00041` height;
  fallback to max of `00413` (backrest) / `00138` (armrest) / `00039` (seat height) for items
  with no overall height (e.g. GLOSTAD sofa). Beware the *package* measurements blobs on the
  same page (label/value shape, flat-pack box dims) — the parser only reads typed entries.
- **Cost model:** one PIP fetch per item for dims → search keeps candidates ≤ limit, pre-filters
  on price from search data. The per-item PIP fetches within one search go out concurrently
  (bounded pool, `PIP_CONCURRENCY`); the search endpoint itself is throttled ≥1s/request.
  Cached forever after first fetch. Images for an item download concurrently too.
- Recorded fixtures: `tests/fixtures/ikea/` (trimmed real search JSON + measurement blobs).

### `generic` (build alongside, it's ~free)

A local pseudo-catalog (`~/.furnisher/generic.json`) of hand-entered items ("sofa 220×95×85,
€600, image from any URL"). Two jobs: (a) escape hatch when no provider has the right item,
(b) lets every downstream component (04–07) be built and tested with zero live-API dependency.

### Future candidates (research at M1, don't build now)

Whatever actually delivers to Georgia: local retailers, EU shops that ship there, marketplaces.
Record findings in this section when researched. The adapter surface above is the checklist for
evaluating any candidate: search? filters (or broad fetch)? images? dimensions? price?

## Cache (shared across providers)

SQLite at `~/.furnisher/catalog.db` + images under `~/.furnisher/images/{item_id}/`. Search
results cached by (provider, query, filters) with ~7-day TTL; product records effectively
immutable once fetched; `get()` never hits the network on a cache hit.

## Dimension parsing gotcha

Sources list dimensions per-variant, in cm, sometimes assembled vs. packaging. Always take
**assembled** dims, convert to meters at the parse boundary, log loudly when w/d/h is missing.

## Tasks

- [x] `CatalogItem`, `SearchFilters`, `CatalogProvider` protocol, `Catalog` facade + post-filtering
- [x] SQLite cache + image downloader (provider-agnostic)
- [x] `generic` adapter + starter file with 18 realistic items (`catalog/data/generic_catalog.json`;
      user extension point: `~/.furnisher/generic.json`)
- [x] `ikea` adapter spike: endpoints verified end-to-end for de/de, findings above
- [x] `ikea` adapter: search + dims + images, throttled
- [x] `furnisher catalog search "sofa" --max-price 400` CLI (M1 exit verified live:
      BILLY 0.80×0.28×2.02 m, 50 EUR)
- [x] Tests against recorded fixtures only (no network in tests)

## Open questions

- Which concrete providers ship to Georgia? Research task at M1 — needs the user's input on where
  they actually shop.
- Currency normalization (GEL vs EUR vs USD across providers): store native currency per item;
  budget math needs one currency — pick at M3 when budget lands in the agent.
