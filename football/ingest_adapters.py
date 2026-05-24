"""Football fixture ingest adapters (RapidAPI, optional FOSS sources)."""

from __future__ import annotations

import json
import logging
import os
from abc import ABC, abstractmethod
from typing import Any

import requests
from minio import Minio

from football.crests import sync_crests_from_response
from football.minio_utils import ensure_bucket, get_minio_client

logger = logging.getLogger(__name__)

RAPIDAPI_BASE = "https://api-football-v1.p.rapidapi.com/v3"
DEFAULT_LEAGUE = 39
DEFAULT_SEASON = 2025


class IngestAdapter(ABC):
    @abstractmethod
    def fetch_fixtures(self, league: int, season: int) -> dict[str, Any]:
        raise NotImplementedError


class RapidAPIIngest(IngestAdapter):
    """Paid RapidAPI API-Football v3 source (optional if RAPIDAPI_KEY set)."""

    def fetch_fixtures(self, league: int, season: int) -> dict[str, Any]:
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


class ManualUploadIngest(IngestAdapter):
    """Load previously uploaded raw JSON from MinIO (no external API)."""

    def __init__(self, client: Minio | None = None, bucket: str | None = None) -> None:
        self.client = client or get_minio_client()
        self.bucket = bucket or os.environ.get("MINIO_BUCKET", "football") or "football"

    def fetch_fixtures(self, league: int, season: int) -> dict[str, Any]:
        key = f"raw/league_{league}_season_{season}.json"
        response = self.client.get_object(self.bucket, key)
        try:
            payload = json.loads(response.read())
        finally:
            response.close()
            response.release_conn()
        if not isinstance(payload, dict):
            raise ValueError(f"MinIO object {key} is not a JSON object")
        return payload


def get_ingest_adapter(source: str | None = None) -> IngestAdapter:
    """Resolve ingest adapter from FOOTBALL_INGEST_SOURCE env or auto-detect."""
    resolved = (source or os.environ.get("FOOTBALL_INGEST_SOURCE", "auto")).lower()
    if resolved == "rapidapi":
        return RapidAPIIngest()
    if resolved in ("minio", "manual"):
        return ManualUploadIngest()
    if resolved == "auto":
        if os.environ.get("RAPIDAPI_KEY"):
            return RapidAPIIngest()
        return ManualUploadIngest()
    raise ValueError(f"Unknown FOOTBALL_INGEST_SOURCE: {resolved}")


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
    source: str | None = None,
) -> str:
    resolved_bucket = bucket or os.environ.get("MINIO_BUCKET", "football") or "football"
    adapter = get_ingest_adapter(source)
    logger.info(
        "Running ingest via %s for league=%s season=%s",
        adapter.__class__.__name__,
        league,
        season,
    )
    data = adapter.fetch_fixtures(league=league, season=season)
    client = get_minio_client()
    ensure_bucket(client, resolved_bucket)
    sync_crests_from_response(data, bucket=resolved_bucket, client=client)
    return upload_raw(client, resolved_bucket, data, league, season)
