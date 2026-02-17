"""
Phase 1: Fetch fixtures from RapidAPI (API-Football v3) and store raw JSON in MinIO.
"""

import json
import logging
import os
from typing import Any

import requests
from dotenv import load_dotenv
from minio import Minio

from football.minio_utils import ensure_bucket, get_minio_client

load_dotenv()

logger = logging.getLogger(__name__)

RAPIDAPI_BASE = "https://api-football-v1.p.rapidapi.com/v3"
DEFAULT_LEAGUE = 39  # Premier League
DEFAULT_SEASON = 2025


def get_client() -> Minio:
    """
    Backwards-compatible alias for tests that import football.ingest.get_client.
    """
    return get_minio_client()


def fetch_fixtures(league: int = DEFAULT_LEAGUE, season: int = DEFAULT_SEASON) -> dict:
    """Call RapidAPI fixtures endpoint. Returns full API response dict."""
    key = os.environ.get("RAPIDAPI_KEY")
    if not key:
        raise ValueError("RAPIDAPI_KEY not set in environment")
    url = f"{RAPIDAPI_BASE}/fixtures"
    params = {"league": league, "season": season}
    headers = {
        "x-rapidapi-key": key,
        "x-rapidapi-host": "api-football-v1.p.rapidapi.com",
    }
    resp = requests.get(url, params=params, headers=headers, timeout=30)
    resp.raise_for_status()
    data: dict[str, Any] = resp.json()
    # Handle pagination if API returns it (paging may vary by plan)
    if "paging" in data and data.get("response"):
        total_pages = data["paging"].get("total", 1)
        all_response = list(data.get("response", []))
        for page in range(2, total_pages + 1):
            resp2 = requests.get(
                url,
                params={**params, "page": page},
                headers=headers,
                timeout=30,
            )
            resp2.raise_for_status()
            data2 = resp2.json()
            all_response.extend(data2.get("response", []))
        data["response"] = all_response
    return data


def upload_raw(client: Minio, bucket: str, data: dict, league: int, season: int) -> str:
    key = f"raw/league_{league}_season_{season}.json"
    body = json.dumps(data).encode("utf-8")
    client.put_object(
        bucket,
        key,
        data=__import__("io").BytesIO(body),
        length=len(body),
    )
    logger.info("Uploaded %s to %s/%s", key, bucket, key)
    return key


def run_ingest(
    league: int = DEFAULT_LEAGUE,
    season: int = DEFAULT_SEASON,
    bucket: str | None = None,
) -> str:
    resolved_bucket = bucket or os.environ.get("MINIO_BUCKET", "football") or "football"
    data = fetch_fixtures(league=league, season=season)
    client = get_client()
    ensure_bucket(client, resolved_bucket)
    from football.crests import sync_crests_from_response

    sync_crests_from_response(data, bucket=resolved_bucket, client=client)
    return upload_raw(client, resolved_bucket, data, league, season)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_ingest()
