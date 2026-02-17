"""
Download team crests from API-Football logo URLs and store in MinIO.
Only downloads and stores if the crest is not already present (by team id).
"""

import io
import logging
import os
from typing import Any

import requests
from minio import Minio

from football.minio_utils import ensure_bucket, get_minio_client

logger = logging.getLogger(__name__)

CRESTS_PREFIX = "crests"
CREST_KEY_TEMPLATE = f"{CRESTS_PREFIX}/team_{{team_id}}.png"


def _object_exists(client: Minio, bucket: str, key: str) -> bool:
    try:
        client.stat_object(bucket, key)
        return True
    except Exception:
        return False


def get_client() -> Minio:
    """
    Backwards-compatible alias for tests that import football.crests.get_client.
    """
    return get_minio_client()


def _ensure_crest(
    client: Minio,
    bucket: str,
    team_id: int,
    logo_url: str,
) -> None:
    """Download logo from logo_url and upload to MinIO if not already present."""
    key = CREST_KEY_TEMPLATE.format(team_id=team_id)
    if _object_exists(client, bucket, key):
        logger.debug("Crest already exists: %s/%s", bucket, key)
        return
    if not logo_url or not str(logo_url).strip().startswith("http"):
        logger.debug("Skipping invalid logo URL for team %s", team_id)
        return
    try:
        resp = requests.get(logo_url, timeout=10)
        resp.raise_for_status()
        data = resp.content
        if not data:
            return
        client.put_object(
            bucket,
            key,
            data=io.BytesIO(data),
            length=len(data),
        )
        logger.info("Stored crest for team %s at %s/%s", team_id, bucket, key)
    except Exception as e:
        logger.warning("Failed to store crest for team %s: %s", team_id, e)


def sync_crests_from_response(
    raw: dict[str, Any],
    bucket: str | None = None,
    client: Minio | None = None,
) -> None:
    """
    Extract unique teams (id, logo URL) from API response and ensure each crest
    is stored in MinIO. Skips if object already exists.
    """
    rows = raw.get("response") or []
    if not rows:
        return
    seen: set[int] = set()
    teams_to_fetch: list[tuple[int, str]] = []
    for item in rows:
        teams = item.get("teams") or {}
        for side in ("home", "away"):
            t = teams.get(side) or {}
            tid = t.get("id")
            logo = t.get("logo") or t.get("crest") or ""
            if tid is not None and tid not in seen:
                seen.add(int(tid))
                teams_to_fetch.append((int(tid), logo or ""))

    if not teams_to_fetch:
        return
    resolved_bucket = bucket or os.environ.get("MINIO_BUCKET", "football") or "football"
    c = client or get_minio_client()
    ensure_bucket(c, resolved_bucket)
    for team_id, logo_url in teams_to_fetch:
        _ensure_crest(c, resolved_bucket, team_id, logo_url)
