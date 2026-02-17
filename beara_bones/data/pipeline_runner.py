"""
Shared orchestration helpers for football pipeline runs.

This module is responsible for creating and updating PipelineRun records while
delegating the actual work (ingest/transform/load) to callables passed in by
management commands or other entrypoints.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from django.utils import timezone

from data.models import PipelineRun


def run_with_pipeline_run(
    *,
    league_id: int | None,
    season_year: int | None,
    source: str,
    execute: Callable[[], Any],
) -> PipelineRun:
    """
    Execute the given callable while tracking status in a PipelineRun row.

    The execute callable is responsible for the actual pipeline work
    (ingest/transform/load). Any exception raised by execute will be captured
    and recorded on the PipelineRun, then re-raised to the caller.
    """
    run = cast(
        PipelineRun,
        PipelineRun.objects.create(
            league_id=league_id,
            season_year=season_year,
            source=source,
            status=PipelineRun.Status.RUNNING,
            started_at=timezone.now(),
        ),
    )
    try:
        execute()
    except (
        Exception
    ) as exc:  # pragma: no cover - behavior asserted via higher level tests
        run.status = PipelineRun.Status.FAILED
        run.error_summary = str(exc)
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "error_summary", "finished_at"])
        raise
    else:
        run.status = PipelineRun.Status.SUCCESS
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "finished_at"])
        return run


def latest_successful_run(
    league_id: int | None = None,
    season_year: int | None = None,
) -> PipelineRun | None:
    """
    Return the most recent successful PipelineRun for the given scope, or None.
    """
    qs = PipelineRun.objects.filter(status=PipelineRun.Status.SUCCESS)
    if league_id is not None:
        qs = qs.filter(league_id=league_id)
    if season_year is not None:
        qs = qs.filter(season_year=season_year)
    return cast("PipelineRun | None", qs.order_by("-started_at", "-id").first())
