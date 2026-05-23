"""Football dashboard cache helpers."""

from __future__ import annotations

from django.core.cache import cache

FOOTBALL_DASH_VERSION_KEY = "football:dash:version"


def football_dashboard_cache_version() -> int:
    return int(cache.get(FOOTBALL_DASH_VERSION_KEY, 0))


def invalidate_football_dashboard_cache() -> None:
    """Bump version so cached dashboard figures are ignored without clearing learning cache."""
    version = football_dashboard_cache_version()
    cache.set(FOOTBALL_DASH_VERSION_KEY, version + 1, timeout=None)
