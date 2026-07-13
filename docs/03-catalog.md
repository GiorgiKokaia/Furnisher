# 03 — Furniture Catalog (provider-agnostic)

**Status:** not started
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

### `ikea` (first, baseline)

No official public API. Community-known unofficial endpoints (verify before building):
search via `https://sik.search.blue.cdtapps.com/{cc}/{lc}/search-box?q=...`; full dimensions and
image sets from the JSON-LD / data blobs embedded in product pages as fallback. Isolate all
endpoint knowledge in `catalog/adapters/ikea.py`, be a polite client (≥1s between requests,
honest UA, cache hard). Timebox this — it's a baseline, not the product.

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

- [ ] `CatalogItem`, `SearchFilters`, `CatalogProvider` protocol, `Catalog` facade + post-filtering
- [ ] SQLite cache + image downloader (provider-agnostic)
- [ ] `generic` adapter + a starter file with ~15 realistic items (unblocks 04–07)
- [ ] `ikea` adapter spike: verify endpoints end-to-end for one market, record findings here
- [ ] `ikea` adapter: search + product detail + images (timeboxed)
- [ ] `furnisher catalog search "sofa" --max-price 400` CLI (M1 exit criterion)
- [ ] Tests against recorded fixtures only (no network in tests)

## Open questions

- Which concrete providers ship to Georgia? Research task at M1 — needs the user's input on where
  they actually shop.
- Currency normalization (GEL vs EUR vs USD across providers): store native currency per item;
  budget math needs one currency — pick at M3 when budget lands in the agent.
