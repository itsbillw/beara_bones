"""
Phase 1: Fetch fixtures and store raw JSON in MinIO.

Uses ingest adapters (RapidAPI or MinIO manual upload). See football/ingest_adapters.py.
"""

import logging

from dotenv import load_dotenv
from minio import Minio

from football.ingest_adapters import run_ingest
from football.minio_utils import get_minio_client

load_dotenv()

logger = logging.getLogger(__name__)

DEFAULT_LEAGUE = 39
DEFAULT_SEASON = 2025


def get_client() -> Minio:
    """Backwards-compatible alias for tests that import football.ingest.get_client."""
    return get_minio_client()


def fetch_fixtures(league: int = DEFAULT_LEAGUE, season: int = DEFAULT_SEASON) -> dict:
    """Call configured ingest adapter. Returns full API response dict."""
    from football.ingest_adapters import get_ingest_adapter

    return get_ingest_adapter().fetch_fixtures(league=league, season=season)


if __name__ == "__main__":
    from football.logging_config import configure_logging

    configure_logging()
    run_ingest()
