"""Local pseudo-catalog: hand-entered items from a JSON file (docs/03).

Two jobs: (a) escape hatch when no live provider has the right item, (b) lets every
downstream component be built and tested with zero live-API dependency. A packaged starter
catalog ships with realistic dimensions/prices; users can add their own file too.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from furnisher.catalog.models import CatalogItem, SearchFilters

STARTER_CATALOG = Path(__file__).parent.parent / "data" / "generic_catalog.json"


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


class GenericProvider:
    provider_id = "generic"

    def __init__(self, paths: list[Path] | None = None):
        self.paths = paths if paths is not None else [STARTER_CATALOG]
        self._items: dict[str, CatalogItem] | None = None

    def _load(self) -> dict[str, CatalogItem]:
        if self._items is None:
            self._items = {}
            for path in self.paths:
                if not path.is_file():
                    continue
                data = json.loads(path.read_text(encoding="utf-8"))
                for entry in data.get("items", []):
                    entry = dict(entry)
                    tags = entry.pop("tags", "")
                    item_id = entry.pop("id", None) or f"generic:{_slug(entry['name'])}"
                    if not item_id.startswith("generic:"):
                        item_id = f"generic:{item_id}"
                    item = CatalogItem(
                        id=item_id, provider=self.provider_id, raw={"tags": tags}, **entry
                    )
                    self._items[item.id] = item
        return self._items

    def search(self, query: str, filters: SearchFilters, limit: int = 24) -> list[CatalogItem]:
        words = query.lower().split()
        results = []
        for item in self._load().values():
            haystack = f"{item.name} {item.type_name} {item.raw.get('tags', '')}".lower()
            if all(w in haystack for w in words):  # empty query matches everything
                results.append(item)
        return results[:limit]

    def get(self, item_id: str) -> CatalogItem:
        items = self._load()
        if item_id not in items:
            raise KeyError(f"no generic catalog item {item_id!r}")
        return items[item_id]
