"""IKEA baseline adapter (docs/03). Unofficial endpoints — verified 2026-07-13:

- Search: https://sik.search.blue.cdtapps.com/{cc}/{lc}/search-result-page?q=...&types=PRODUCT
  Returns name, typeName, itemNo, salesPrice, image URLs, pipUrl. NO assembled dimensions.
- Dimensions: the product (PIP) page HTML embeds hydration JSON with
  "measurements": [{"measure": "171 cm", "name": "Breite", "type": "00047"}, ...].
  Type codes are language-independent: 00047 width, 00044 depth, 00041 height
  (00413 backrest / 00138 armrest height as fallback for sofas that list no overall height).

One PIP fetch per item (cached forever via the facade). Search endpoints are throttled
≥1s apart; the per-item PIP fetches within one search go out concurrently (bounded pool)
rather than serially, so a search costs one round-trip's latency, not one per candidate.
This is a baseline integration — expect breakage; all endpoint knowledge stays in this file.
"""

from __future__ import annotations

import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor

import httpx

from furnisher.catalog.models import CatalogItem, SearchFilters

log = logging.getLogger(__name__)

SEARCH_URL = "https://sik.search.blue.cdtapps.com/{cc}/{lc}/search-result-page"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) furnisher-prototype"
PIP_CONCURRENCY = 6  # max PIP pages in flight at once — polite ceiling that replaces the 1s gap

WIDTH_TYPE = "00047"
DEPTH_TYPE = "00044"
HEIGHT_TYPE = "00041"
HEIGHT_FALLBACK_TYPES = ("00413", "00138", "00039")  # backrest, armrest, seat height
DEPTH_FALLBACK_TYPES = ("00001",)  # "Länge" — beds list length instead of depth


def _cm_to_m(measure: str) -> float | None:
    m = re.match(r"([\d.]+)\s*cm", measure)
    return float(m.group(1)) / 100 if m else None


def parse_measurements(html: str) -> dict[str, float]:
    """Extract {width_m, depth_m, height_m} from PIP-page hydration JSON."""
    by_type: dict[str, float] = {}
    for m in re.finditer(r'"measurements":(\[)', html):
        start = m.start(1)
        depth = 0
        for j in range(start, len(html)):
            if html[j] == "[":
                depth += 1
            elif html[j] == "]":
                depth -= 1
                if depth == 0:
                    try:
                        entries = json.loads(html[start : j + 1])
                    except json.JSONDecodeError:
                        entries = []
                    for e in entries:
                        if isinstance(e, dict) and "type" in e and "measure" in e:
                            value = _cm_to_m(e["measure"])
                            if value is not None:
                                by_type[e["type"]] = max(by_type.get(e["type"], 0), value)
                    break
    dims: dict[str, float] = {}
    if WIDTH_TYPE in by_type:
        dims["width_m"] = by_type[WIDTH_TYPE]
    if DEPTH_TYPE in by_type:
        dims["depth_m"] = by_type[DEPTH_TYPE]
    else:
        fallbacks = [by_type[t] for t in DEPTH_FALLBACK_TYPES if t in by_type]
        if fallbacks:
            dims["depth_m"] = max(fallbacks)
    if HEIGHT_TYPE in by_type:
        dims["height_m"] = by_type[HEIGHT_TYPE]
    else:
        fallbacks = [by_type[t] for t in HEIGHT_FALLBACK_TYPES if t in by_type]
        if fallbacks:
            dims["height_m"] = max(fallbacks)
    return dims


def parse_search_products(payload: dict) -> list[dict]:
    """Flatten main + shelf hits from a search-result-page response into product dicts."""
    products_node = payload.get("searchResultPage", {}).get("products", {})
    raw_items = list(products_node.get("main", {}).get("items", []))
    for shelf in products_node.get("shelves", []):
        raw_items.extend(shelf.get("result", {}).get("items", []))
    products = []
    seen = set()
    for entry in raw_items:
        product = entry.get("product")
        if not product or product.get("itemNo") in seen:
            continue
        seen.add(product["itemNo"])
        products.append(product)
    return products


class IkeaProvider:
    provider_id = "ikea"

    def __init__(
        self,
        country: str = "de",
        language: str = "de",
        client: httpx.Client | None = None,
        min_interval: float = 1.0,
    ):
        self.country = country
        self.language = language
        self.min_interval = min_interval
        self._client = client
        self._last_request = 0.0

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                headers={"User-Agent": USER_AGENT}, timeout=20, follow_redirects=True
            )
        return self._client

    def _throttle(self) -> None:
        wait = self.min_interval - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()

    def _search_raw(self, query: str, size: int) -> list[dict]:
        self._throttle()
        resp = self.client.get(
            SEARCH_URL.format(cc=self.country, lc=self.language),
            params={"q": query, "types": "PRODUCT", "size": size},
        )
        resp.raise_for_status()
        return parse_search_products(resp.json())

    def _fetch_dims(self, pip_url: str) -> dict[str, float]:
        # No _throttle() here: these run concurrently under PIP_CONCURRENCY (see search()),
        # and httpx.Client is safe to share across threads. The bounded pool is the rate limit.
        resp = self.client.get(pip_url)
        resp.raise_for_status()
        return parse_measurements(resp.text)

    def _to_item(self, product: dict) -> CatalogItem | None:
        pip_url = product.get("pipUrl", "")
        try:
            dims = self._fetch_dims(pip_url) if pip_url else {}
        except httpx.HTTPError as exc:
            log.warning("ikea: PIP fetch failed for %s: %s", product.get("itemNo"), exc)
            return None
        if not {"width_m", "depth_m", "height_m"} <= dims.keys():
            log.warning(
                "ikea: skipping %s %r — incomplete dimensions %s",
                product.get("itemNo"),
                product.get("name"),
                dims,
            )
            return None
        price = product.get("salesPrice") or {}
        images = [u for u in (product.get("mainImageUrl"), product.get("contextualImageUrl")) if u]
        return CatalogItem(
            id=f"ikea:{product['itemNo']}",
            provider=self.provider_id,
            name=product.get("name", ""),
            type_name=product.get("typeName", ""),
            price=price.get("numeral", 0.0),
            currency=price.get("currencyCode", ""),
            url=pip_url,
            image_urls=images,
            raw=product,
            **dims,
        )

    def search(self, query: str, filters: SearchFilters, limit: int = 24) -> list[CatalogItem]:
        # Dimensions need one PIP fetch per candidate, so keep candidate count = limit.
        # Cheap pre-filter on price (present in search results) before paying for PIP fetches.
        products = self._search_raw(query, size=max(limit * 2, 8))
        if filters.price_max is not None:
            products = [
                p
                for p in products
                if (p.get("salesPrice") or {}).get("numeral", 0) <= filters.price_max
            ]
        candidates = products[:limit]
        if not candidates:
            return []
        # Fetch all PIP pages at once instead of one-at-a-time — order preserved by map().
        with ThreadPoolExecutor(max_workers=min(PIP_CONCURRENCY, len(candidates))) as pool:
            items = pool.map(self._to_item, candidates)
        return [item for item in items if item is not None]

    def inspiration_images(self, query: str, limit: int = 4) -> list[dict]:
        """Styled lifestyle room photos: the contextualImageUrl on product search hits.

        (IKEA's /rooms/ gallery exists but is a JS app with no query API — the per-product
        contextual shots are the reliable, query-driven inspiration source.)"""
        products = self._search_raw(query, size=max(limit * 3, 12))
        seen: set[str] = set()
        photos = []
        for product in products:
            url = product.get("contextualImageUrl")
            if not url or url in seen:
                continue
            seen.add(url)
            photos.append(
                {"url": url, "title": product.get("contextualImageAlt") or product.get("name", "")}
            )
            if len(photos) >= limit:
                break
        return photos

    def get(self, item_id: str) -> CatalogItem:
        item_no = item_id.split(":", 1)[1]
        for product in self._search_raw(item_no, size=8):
            if product.get("itemNo") == item_no:
                item = self._to_item(product)
                if item is not None:
                    return item
        raise KeyError(f"ikea item {item_id!r} not found or has no usable dimensions")
