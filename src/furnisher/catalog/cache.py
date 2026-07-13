"""SQLite catalog cache + image store (docs/03).

Product records are effectively immutable once fetched; search results carry a TTL.
Everything lives under one directory (default ~/.furnisher/) so layouts and renders keep
working offline once data has been fetched.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from furnisher.catalog.models import CatalogItem

SEARCH_TTL_SECONDS = 7 * 24 * 3600

_SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id TEXT PRIMARY KEY,
    payload TEXT NOT NULL,
    fetched_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS searches (
    key TEXT PRIMARY KEY,
    item_ids TEXT NOT NULL,
    fetched_at REAL NOT NULL
);
"""


class CatalogCache:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.images_dir = self.root / "images"
        self._db = sqlite3.connect(self.root / "catalog.db")
        self._db.executescript(_SCHEMA)

    def close(self) -> None:
        self._db.close()

    # --- items ---
    def put_item(self, item: CatalogItem) -> None:
        self._db.execute(
            "INSERT OR REPLACE INTO items (id, payload, fetched_at) VALUES (?, ?, ?)",
            (item.id, item.model_dump_json(), time.time()),
        )
        self._db.commit()

    def get_item(self, item_id: str) -> CatalogItem | None:
        row = self._db.execute("SELECT payload FROM items WHERE id = ?", (item_id,)).fetchone()
        return CatalogItem.model_validate_json(row[0]) if row else None

    # --- searches ---
    def put_search(self, key: str, items: list[CatalogItem]) -> None:
        for item in items:
            self.put_item(item)
        self._db.execute(
            "INSERT OR REPLACE INTO searches (key, item_ids, fetched_at) VALUES (?, ?, ?)",
            (key, json.dumps([i.id for i in items]), time.time()),
        )
        self._db.commit()

    def get_search(self, key: str, ttl: float = SEARCH_TTL_SECONDS) -> list[CatalogItem] | None:
        row = self._db.execute(
            "SELECT item_ids, fetched_at FROM searches WHERE key = ?", (key,)
        ).fetchone()
        if row is None or time.time() - row[1] > ttl:
            return None
        items = [self.get_item(item_id) for item_id in json.loads(row[0])]
        return [i for i in items if i is not None]

    # --- images ---
    def image_dir(self, item_id: str) -> Path:
        safe = item_id.replace(":", "_").replace("/", "_")
        return self.images_dir / safe

    def cached_images(self, item_id: str) -> list[Path]:
        directory = self.image_dir(item_id)
        if not directory.is_dir():
            return []
        return sorted(p for p in directory.iterdir() if p.is_file())
