from pathlib import Path

from furnisher.catalog.cache import CatalogCache
from furnisher.catalog.facade import Catalog
from furnisher.catalog.models import CatalogItem, CatalogProvider, SearchFilters

__all__ = [
    "Catalog",
    "CatalogCache",
    "CatalogItem",
    "CatalogProvider",
    "SearchFilters",
    "default_catalog",
]


def default_catalog(cache_dir: Path | None = None) -> Catalog:
    """The standard provider stack: packaged generic catalog (+ user's ~/.furnisher/generic.json
    if present) and the IKEA baseline adapter, sharing one cache."""
    from furnisher.catalog.adapters.generic import STARTER_CATALOG, GenericProvider
    from furnisher.config import Settings

    settings = Settings()
    cache_dir = cache_dir or settings.cache_dir
    user_file = cache_dir / "generic.json"
    generic_paths = [STARTER_CATALOG] + ([user_file] if user_file.is_file() else [])
    providers: list[CatalogProvider] = [GenericProvider(generic_paths)]
    try:
        from furnisher.catalog.adapters.ikea import IkeaProvider

        providers.append(IkeaProvider(settings.ikea_country, settings.ikea_language))
    except ImportError:  # adapter optional while it's a spike
        pass
    return Catalog(providers, CatalogCache(cache_dir))
