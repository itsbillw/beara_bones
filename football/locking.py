"""
Locking helpers for the football pipeline.

All entrypoints (standalone pipeline, Django management commands, and views)
should use the same lock file semantics so that overlapping runs are prevented
consistently.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# Repo root = parent of football/
REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data" / "football"
DEFAULT_LOCK_FILE = DATA_DIR / ".refresh.lock"


def get_pipeline_lock_file() -> Path:
    """Return the canonical lock file path for the football pipeline."""
    return DEFAULT_LOCK_FILE


def acquire_lock(path: Path, fail_if_exists: bool = True) -> bool:
    """
    Try to acquire a filesystem lock.

    Returns True if the lock was acquired, False if it already existed and
    fail_if_exists is True.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and fail_if_exists:
        return False
    try:
        path.touch(exist_ok=False)
    except FileExistsError:
        return False
    return True


def release_lock(path: Path) -> None:
    """Release a previously acquired lock."""
    try:
        path.unlink(missing_ok=True)
    except Exception:
        # Best-effort; log but don't raise in callers
        logger.warning("Failed to remove lock file %s", path, exc_info=True)


def is_stale_lock(path: Path, max_age: timedelta) -> bool:
    """
    Determine whether an existing lock file is older than max_age.

    Used for diagnostics/UX; does not modify the lock.
    """
    if not path.exists():
        return False
    try:
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    except OSError:
        return False
    return datetime.now(tz=timezone.utc) - mtime > max_age


@contextmanager
def pipeline_lock(path: Path):
    """
    Context manager that acquires the given lock path and always releases it.

    Callers are responsible for checking acquire_lock() first if they want
    specific behavior when the lock already exists.
    """
    try:
        yield
    finally:
        release_lock(path)
