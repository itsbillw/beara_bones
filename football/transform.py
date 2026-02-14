"""
Phase 2: Load raw JSON from MinIO, flatten to DataFrame, clean, write CSV/Parquet.
Output: data/football/fixtures.csv (and optionally fixtures.parquet).
"""

import logging
import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from minio import Minio

load_dotenv()

logger = logging.getLogger(__name__)

# Repo root = parent of football/
REPO_ROOT = Path(__file__).resolve().parents[1]
REPO_DATA_DIR = REPO_ROOT / "data" / "football"


def _data_dir() -> Path:
    return REPO_DATA_DIR


def get_client() -> Minio:
    endpoint = (
        os.environ["MINIO_ENDPOINT"].replace("https://", "").replace("http://", "")
    )
    return Minio(
        endpoint,
        access_key=os.environ["MINIO_ACCESS_KEY"],
        secret_key=os.environ["MINIO_SECRET_KEY"],
        secure=os.environ.get("MINIO_SECURE", "true").lower() in ("true", "1", "yes"),
    )


def load_raw_from_minio(bucket: str, object_key: str) -> dict:
    client = get_client()
    resp = client.get_object(bucket, object_key)
    try:
        import json
        from typing import Any

        out: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
        return out
    finally:
        resp.close()


def flatten_fixtures(raw: dict) -> pd.DataFrame:
    """Turn API response array into a flat table (one row per fixture)."""
    rows = raw.get("response") or []
    if not rows:
        return pd.DataFrame()

    records = []
    for item in rows:
        fixture = item.get("fixture") or {}
        league = item.get("league") or {}
        teams = item.get("teams") or {}
        goals = item.get("goals") or {}
        record = {
            "fixture_id": fixture.get("id"),
            "date": fixture.get("date"),
            "timestamp": fixture.get("timestamp"),
            "venue_id": (fixture.get("venue") or {}).get("id"),
            "venue_name": (fixture.get("venue") or {}).get("name"),
            "status_short": (fixture.get("status") or {}).get("short"),
            "status_long": (fixture.get("status") or {}).get("long"),
            "league_id": league.get("id"),
            "league_name": league.get("name"),
            "league_season": league.get("season"),
            "league_round": league.get("round"),
            "home_team_id": (teams.get("home") or {}).get("id"),
            "home_team_name": (teams.get("home") or {}).get("name"),
            "away_team_id": (teams.get("away") or {}).get("id"),
            "away_team_name": (teams.get("away") or {}).get("name"),
            "goals_home": goals.get("home"),
            "goals_away": goals.get("away"),
        }
        records.append(record)

    df = pd.DataFrame(records)
    # Coerce types
    if not df.empty:
        for col in (
            "fixture_id",
            "timestamp",
            "venue_id",
            "league_id",
            "league_season",
            "home_team_id",
            "away_team_id",
        ):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        for col in ("goals_home", "goals_away"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """Drop full duplicates; optional: drop rows with null fixture_id."""
    if df.empty:
        return df
    out = df.drop_duplicates()
    out = out[out["fixture_id"].notna()]
    return out.reset_index(drop=True)


def run_transform(
    bucket: str | None = None,
    object_key: str | None = None,
    league: int = 39,
    season: int = 2025,
    output_dir: Path | None = None,
    write_parquet: bool = True,
    write_files: bool = True,
) -> pd.DataFrame:
    """
    Load raw from MinIO, flatten and clean, optionally write CSV/Parquet to disk.
    When write_files=False (e.g. when loading to MariaDB), only return the DataFrame.
    """
    resolved_bucket = bucket or os.environ.get("MINIO_BUCKET", "football") or "football"
    resolved_key = object_key or f"raw/league_{league}_season_{season}.json"
    out_dir = output_dir or _data_dir()
    out_dir = Path(out_dir)
    if write_files:
        out_dir.mkdir(parents=True, exist_ok=True)

    raw = load_raw_from_minio(resolved_bucket, resolved_key)
    df = flatten_fixtures(raw)
    df = clean(df)

    if write_files:
        csv_path = out_dir / "fixtures.csv"
        df.to_csv(csv_path, index=False)
        logger.info("Wrote %s (%d rows)", csv_path, len(df))
        if write_parquet:
            pq_path = out_dir / "fixtures.parquet"
            df.to_parquet(pq_path, index=False)
            logger.info("Wrote %s", pq_path)

    return df


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_transform()
