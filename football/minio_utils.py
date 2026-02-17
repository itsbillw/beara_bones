"""
Shared MinIO utilities for the football pipeline.

Centralises client construction and common helpers so that ingest, transform,
processed, and crests modules don't each reimplement connection logic.
"""

from __future__ import annotations

import json
import logging
import os
from io import BytesIO
from typing import Any

from dotenv import load_dotenv
from minio import Minio

load_dotenv()

logger = logging.getLogger(__name__)


def get_minio_client() -> Minio:
    """
    Construct a MinIO client from environment variables.

    Expected env vars:
        MINIO_ENDPOINT (e.g. http://localhost:9000 or localhost:9000)
        MINIO_ACCESS_KEY
        MINIO_SECRET_KEY
        MINIO_SECURE (optional, truthy = https)
    """
    endpoint_raw = os.environ["MINIO_ENDPOINT"]
    # MinIO client expects bare host:port without scheme
    endpoint = endpoint_raw.replace("https://", "").replace("http://", "")
    secure = os.environ.get("MINIO_SECURE", "true").lower() in ("true", "1", "yes")
    return Minio(
        endpoint,
        access_key=os.environ["MINIO_ACCESS_KEY"],
        secret_key=os.environ["MINIO_SECRET_KEY"],
        secure=secure,
    )


def ensure_bucket(client: Minio, bucket: str) -> None:
    """Create bucket if it does not already exist."""
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)
        logger.info("Created MinIO bucket %s", bucket)


def get_json_object(client: Minio, bucket: str, key: str) -> dict[str, Any]:
    """Fetch an object from MinIO and decode it as JSON."""
    resp = client.get_object(bucket, key)
    try:
        raw = resp.read().decode("utf-8")
        loaded = json.loads(raw)
        if not isinstance(loaded, dict):
            raise TypeError("Expected JSON object for MinIO key, got non-dict")
        return loaded
    finally:
        resp.close()


def get_bytes_object(client: Minio, bucket: str, key: str) -> bytes:
    """Fetch an object from MinIO and return its raw bytes."""
    resp = client.get_object(bucket, key)
    try:
        data: bytes = resp.read()
        return data
    finally:
        resp.close()


def put_bytes_object(client: Minio, bucket: str, key: str, data: bytes) -> None:
    """Upload raw bytes to MinIO under the given key."""
    buf = BytesIO(data)
    client.put_object(bucket, key, buf, len(data))
