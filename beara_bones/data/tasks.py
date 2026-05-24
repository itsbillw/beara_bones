"""Background tasks for django-rq."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def run_football_pipeline_task(source: str = "rq") -> None:
    """Run the full football pipeline management command."""
    from django.core.management import call_command

    logger.info("Starting football pipeline task (source=%s)", source)
    call_command("run_football_pipeline")
    logger.info("Football pipeline task finished")
