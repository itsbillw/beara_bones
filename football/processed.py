"""
Upload processed (clean) fixtures DataFrame to MinIO as Parquet; load from MinIO for rebuild.
"""

import io
import logging
import os

import pandas as pd

from football.minio_utils import ensure_bucket, get_bytes_object, get_minio_client

logger = logging.getLogger(__name__)


def load_processed_parquet_from_minio(
    league: int,
    season: int,
    bucket: str | None = None,
) -> pd.DataFrame | None:
    """
    Read processed Parquet from MinIO for (league, season). Returns None if object does not exist.
    """
    resolved_bucket: str = bucket or os.environ.get("MINIO_BUCKET") or "football"
    key = f"processed/league_{league}_season_{season}.parquet"
    try:
        client = get_minio_client()
        data = get_bytes_object(client, resolved_bucket, key)
        return pd.read_parquet(io.BytesIO(data))
    except Exception as e:
        logger.debug("No processed parquet at %s/%s: %s", resolved_bucket, key, e)
        return None


def upload_processed_parquet(
    df: pd.DataFrame,
    league: int,
    season: int,
    bucket: str | None = None,
) -> str:
    """
    Write DataFrame to Parquet in memory and upload to MinIO (same bucket as raw, under processed/ prefix).
    Key: processed/league_{league}_season_{season}.parquet
    Returns the object key.
    """
    resolved_bucket: str = bucket or os.environ.get("MINIO_BUCKET") or "football"
    key = f"processed/league_{league}_season_{season}.parquet"
    buf = io.BytesIO()
    df.to_parquet(buf, index=False)
    buf.seek(0)
    client = get_minio_client()
    ensure_bucket(client, resolved_bucket)
    client.put_object(resolved_bucket, key, buf, len(buf.getvalue()))
    logger.info("Uploaded %s to %s/%s", key, resolved_bucket, key)
    return key
