"""Catalog data model and provider contract (docs/03).

Everything outside `catalog/` codes against these; providers are plugins behind them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field


class CatalogItem(BaseModel):
    id: str  # "{provider}:{sku}", e.g. "ikea:00263850" or "generic:sofa-3seat"
    provider: str
    name: str
    type_name: str  # "3-seat sofa"
    width_m: float = Field(gt=0)  # x-extent at rotation=0
    depth_m: float = Field(gt=0)
    height_m: float = Field(gt=0)
    price: float
    currency: str
    url: str = ""
    image_urls: list[str] = Field(default_factory=list)
    raw: dict = Field(default_factory=dict)  # untouched source payload (3D assets later, docs/10)

    def footprint(self) -> tuple[float, float]:
        return (self.width_m, self.depth_m)

    def summary(self) -> str:
        return (
            f"{self.id}  {self.name} — {self.type_name}, "
            f"{self.width_m:.2f}×{self.depth_m:.2f}×{self.height_m:.2f} m, "
            f"{self.price:.0f} {self.currency}"
        )


@dataclass
class SearchFilters:
    category: str | None = None  # normalized keyword: "sofa", "bed", "wardrobe", ...
    price_max: float | None = None  # budget constraint plumbing (docs/00: budget is first-class)
    price_min: float | None = None
    max_width_m: float | None = None  # as-listed orientation; rotation is the layout engine's job
    max_depth_m: float | None = None
    max_height_m: float | None = None

    def matches(self, item: CatalogItem) -> bool:
        if self.price_max is not None and item.price > self.price_max:
            return False
        if self.price_min is not None and item.price < self.price_min:
            return False
        if self.max_width_m is not None and item.width_m > self.max_width_m:
            return False
        if self.max_depth_m is not None and item.depth_m > self.max_depth_m:
            return False
        if self.max_height_m is not None and item.height_m > self.max_height_m:
            return False
        if (
            self.category is not None
            and self.category.lower() not in (item.type_name + " " + item.name).lower()
        ):
            return False
        return True

    def cache_key(self) -> str:
        return (
            f"cat={self.category};pmax={self.price_max};pmin={self.price_min};"
            f"w={self.max_width_m};d={self.max_depth_m};h={self.max_height_m}"
        )


@runtime_checkable
class CatalogProvider(Protocol):
    """A furniture source. Providers may ignore filters they can't express natively —
    the Catalog facade post-filters everything anyway. The minimum per item: assembled
    dimensions, price, and (for real providers) at least one image URL."""

    provider_id: str

    def search(self, query: str, filters: SearchFilters, limit: int = 24) -> list[CatalogItem]: ...

    def get(self, item_id: str) -> CatalogItem: ...
