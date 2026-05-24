"""Pipeline status aggregation for the Data dashboard UI."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from django.utils import timezone

from data.models import League, PipelineRun, Season
from data.pipeline_runner import latest_successful_run
from football.locking import get_pipeline_lock_file, is_stale_lock

STALE_LOCK_MAX_AGE = timedelta(hours=2)


def _league_name(league_id: int | None) -> str | None:
    if league_id is None:
        return None
    league = League.objects.filter(id=league_id).first()
    return league.name if league else f"League {league_id}"


def _serialize_run(run: PipelineRun) -> dict:
    return {
        "id": run.id,
        "league_id": run.league_id,
        "season_year": run.season_year,
        "league_name": _league_name(run.league_id),
        "source": run.source,
        "status": run.status,
        "error_summary": run.error_summary,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
    }


def _batch_start(lock_exists: bool, running_runs: list[PipelineRun]) -> datetime | None:
    candidates: list[datetime] = []
    if lock_exists:
        lock_file = get_pipeline_lock_file()
        try:
            candidates.append(
                datetime.fromtimestamp(lock_file.stat().st_mtime, tz=UTC),
            )
        except OSError:
            pass
    if running_runs:
        candidates.append(min(run.started_at for run in running_runs))
    if not candidates:
        return None
    return min(candidates)


def get_pipeline_status() -> dict:
    """
    Return a JSON-serializable snapshot of pipeline activity.

    Used by GET /data/pipeline/status and the activity panel partial.
    """
    lock_file = get_pipeline_lock_file()
    lock_exists = lock_file.exists()
    stale_lock = is_stale_lock(lock_file, STALE_LOCK_MAX_AGE) if lock_exists else False

    total_pairs = League.objects.count() * Season.objects.count()
    running_runs = list(
        PipelineRun.objects.filter(status=PipelineRun.Status.RUNNING).order_by(
            "started_at",
        ),
    )
    running = lock_exists or bool(running_runs)

    batch_start = _batch_start(lock_exists, running_runs)
    batch_runs: list[PipelineRun] = []
    if batch_start is not None:
        batch_runs = list(
            PipelineRun.objects.filter(started_at__gte=batch_start).order_by(
                "started_at",
            ),
        )

    completed = sum(1 for run in batch_runs if run.status == PipelineRun.Status.SUCCESS)
    failed = sum(1 for run in batch_runs if run.status == PipelineRun.Status.FAILED)
    in_progress = sum(1 for run in batch_runs if run.status == PipelineRun.Status.RUNNING)

    current = None
    if running_runs:
        active = running_runs[0]
        current = {
            "league_id": active.league_id,
            "season_year": active.season_year,
            "league_name": _league_name(active.league_id),
        }

    errors = [
        {
            "league_id": run.league_id,
            "season_year": run.season_year,
            "league_name": _league_name(run.league_id),
            "summary": run.error_summary,
        }
        for run in batch_runs
        if run.status == PipelineRun.Status.FAILED and run.error_summary
    ]

    latest = latest_successful_run()
    last_success_at = latest.finished_at.isoformat() if latest and latest.finished_at else None

    batch_outcome = None
    if not running and batch_runs:
        if failed and completed:
            batch_outcome = "partial"
        elif failed:
            batch_outcome = "failed"
        elif completed:
            batch_outcome = "success"

    recent_runs = [_serialize_run(run) for run in PipelineRun.objects.order_by("-started_at", "-id")[:5]]

    batch_items = [_serialize_run(run) for run in batch_runs]

    return {
        "running": running,
        "stale_lock": stale_lock,
        "total_pairs": total_pairs,
        "completed": completed,
        "failed": failed,
        "in_progress": in_progress,
        "current": current,
        "last_success_at": last_success_at,
        "errors": errors,
        "batch_outcome": batch_outcome,
        "recent_runs": recent_runs,
        "batch_items": batch_items,
        "now": timezone.now().isoformat(),
    }
