"""Storage abstraction for learning documents: MinIO in production, local media fallback in dev."""

from __future__ import annotations

import logging
import os
import sys
from io import BytesIO
from pathlib import Path
from typing import BinaryIO

from django.conf import settings

logger = logging.getLogger(__name__)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _minio_available() -> bool:
    required = ("MINIO_ENDPOINT", "MINIO_ACCESS_KEY", "MINIO_SECRET_KEY")
    return all(os.environ.get(k) for k in required)


def learning_bucket() -> str:
    return os.environ.get("MINIO_LEARNING_BUCKET", "learning") or "learning"


def build_storage_key(
    user_id: int,
    directory_uuid: str,
    document_uuid: str,
    filename: str,
) -> str:
    safe_name = Path(filename).name
    return f"users/{user_id}/{directory_uuid}/{document_uuid}_{safe_name}"


def _local_path(storage_key: str) -> Path:
    return Path(settings.MEDIA_ROOT) / "learning" / storage_key


def save_file(
    user_id: int,
    directory_uuid: str,
    document_uuid: str,
    filename: str,
    file_obj: BinaryIO,
) -> str:
    """Persist file bytes and return the storage key."""
    storage_key = build_storage_key(user_id, directory_uuid, document_uuid, filename)
    data = file_obj.read()

    if _minio_available():
        repo_root = _repo_root()
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))
        from football.minio_utils import ensure_bucket, get_minio_client

        client = get_minio_client()
        bucket = learning_bucket()
        ensure_bucket(client, bucket)
        client.put_object(bucket, storage_key, BytesIO(data), len(data))
        logger.debug("Saved learning file to MinIO: %s/%s", bucket, storage_key)
    else:
        path = _local_path(storage_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        logger.debug("Saved learning file locally: %s", path)

    return storage_key


def open_file(storage_key: str) -> bytes:
    """Load file bytes from MinIO or local media."""
    if _minio_available():
        repo_root = _repo_root()
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))
        from football.minio_utils import get_bytes_object, get_minio_client

        return get_bytes_object(get_minio_client(), learning_bucket(), storage_key)

    path = _local_path(storage_key)
    if not path.is_file():
        raise FileNotFoundError(storage_key)
    return path.read_bytes()


def delete_file(storage_key: str) -> None:
    """Remove file from MinIO or local media."""
    if _minio_available():
        repo_root = _repo_root()
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))
        from football.minio_utils import get_minio_client

        client = get_minio_client()
        bucket = learning_bucket()
        try:
            client.remove_object(bucket, storage_key)
        except Exception:
            logger.exception("Failed to delete MinIO object %s/%s", bucket, storage_key)
        return

    path = _local_path(storage_key)
    if path.is_file():
        path.unlink()
