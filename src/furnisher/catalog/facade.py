"""The Catalog facade: registered providers + shared cache, with uniform post-filtering.

Adapters stay dumb; anything a provider can't filter natively gets filtered here.
"""

from __future__ import annotations

import logging
from pathlib import Path

from furnisher.catalog.cache import CatalogCache
from furnisher.catalog.models import CatalogItem, CatalogProvider, SearchFilters

log = logging.getLogger(__name__)


class Catalog:
    def __init__(self, providers: list[CatalogProvider], cache: CatalogCache | None = None):
        self.providers = {p.provider_id: p for p in providers}
        self.cache = cache

    def search(
        self,
        query: str,
        filters: SearchFilters | None = None,
        *,
        provider: str | None = None,
        limit: int = 24,
    ) -> list[CatalogItem]:
        filters = filters or SearchFilters()
        key = f"p={provider};q={query};{filters.cache_key()};n={limit}"
        if self.cache is not None:
            cached = self.cache.get_search(key)
            if cached is not None:
                return cached

        sources = [self.providers[provider]] if provider else list(self.providers.values())
        results: list[CatalogItem] = []
        for source in sources:
            try:
                results.extend(source.search(query, filters, limit=limit))
            except Exception as exc:  # a dead provider must not take search down
                log.warning("provider %r search failed: %s", source.provider_id, exc)
        results = [i for i in results if filters.matches(i)][:limit]

        if self.cache is not None:
            self.cache.put_search(key, results)
        return results

    def get(self, item_id: str) -> CatalogItem:
        """Cache-first item lookup; routes to the provider by the id prefix."""
        if self.cache is not None:
            hit = self.cache.get_item(item_id)
            if hit is not None:
                return hit
        provider_id = item_id.split(":", 1)[0]
        if provider_id not in self.providers:
            raise KeyError(f"unknown catalog provider in item id {item_id!r}")
        item = self.providers[provider_id].get(item_id)
        if self.cache is not None:
            self.cache.put_item(item)
        return item

    def image_paths(self, item_id: str, max_images: int = 3) -> list[Path]:
        """Locally cached image files for an item, downloading them on first use."""
        if self.cache is None:
            return []
        cached = self.cache.cached_images(item_id)
        if cached:
            return cached[:max_images]
        item = self.get(item_id)
        if not item.image_urls:
            return []
        import httpx

        directory = self.cache.image_dir(item_id)
        directory.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []
        with httpx.Client(timeout=20, follow_redirects=True) as client:
            for n, url in enumerate(item.image_urls[:max_images]):
                try:
                    resp = client.get(url)
                    resp.raise_for_status()
                except httpx.HTTPError as exc:
                    log.warning("image download failed for %s: %s", item_id, exc)
                    continue
                suffix = ".jpg" if ".jpg" in url.lower() else ".png"
                path = directory / f"{n}{suffix}"
                path.write_bytes(resp.content)
                paths.append(path)
        return paths
