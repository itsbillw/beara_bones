"""Enqueue and track football pipeline jobs."""

from __future__ import annotations

import logging
import os
import subprocess  # nosec B404
from pathlib import Path

from django.conf import settings

from football.locking import get_pipeline_lock_file

logger = logging.getLogger(__name__)


def _subprocess_refresh(source: str) -> dict[str, str]:
    """Fallback when Redis/RQ is unavailable."""
    lock_file = get_pipeline_lock_file()
    if lock_file.exists():
        return {"status": "already_running", "message": "Pipeline already in progress"}
    repo_root = Path(settings.BASE_DIR).parent
    subprocess.Popen(  # nosec B603 B607
        [
            "uv",
            "run",
            "python",
            "beara_bones/manage.py",
            "run_football_pipeline",
            "--source",
            source,
        ],
        cwd=str(repo_root),
        start_new_session=True,
    )
    return {"status": "started", "message": "Refresh started"}


def _rq_refresh(source: str) -> dict[str, str]:
    import django_rq

    lock_file = get_pipeline_lock_file()
    if lock_file.exists():
        return {"status": "already_running", "message": "Pipeline already in progress"}

    queue = django_rq.get_queue("default")
    queue.enqueue("data.tasks.run_football_pipeline_task", source)
    return {"status": "started", "message": "Refresh queued", "source": source}


def enqueue_pipeline_refresh(source: str = "web") -> dict[str, str]:
    """Start a pipeline refresh via django-rq when configured, else subprocess."""
    if os.environ.get("REDIS_URL"):
        try:
            return _rq_refresh(source)
        except ImportError:
            logger.warning("django-rq not installed; falling back to subprocess refresh")
        except Exception:
            logger.exception("RQ enqueue failed; falling back to subprocess refresh")

    return _subprocess_refresh(source)
