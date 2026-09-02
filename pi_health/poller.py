#!/usr/bin/env python3
"""Collect local + remote health snapshots and persist them to SQLite."""

from __future__ import annotations

import json
import logging
import sys
import urllib.error
import urllib.request

from pi_health.config import PollerConfig
from pi_health.metrics import collect_snapshot
from pi_health.storage import connect, insert_snapshot, prune_rollups, rollup_raw_snapshots

LOG = logging.getLogger("pi_health.poller")


def fetch_remote_snapshot(url: str, *, timeout: float) -> dict | None:
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec B310
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        LOG.warning("Remote health fetch failed (%s): %s", url, exc)
        return None
    if not isinstance(payload, dict) or "host" not in payload:
        LOG.warning("Remote health payload invalid from %s", url)
        return None
    return payload


def run_once(config: PollerConfig) -> int:
    conn = connect(config.db_path)
    written = 0

    local_snapshot = collect_snapshot(config.local_hostname, config.local_mount_paths)
    insert_snapshot(conn, local_snapshot)
    written += 1
    LOG.info("Stored local snapshot for %s", config.local_hostname)

    if config.remote_enabled:
        remote_snapshot = fetch_remote_snapshot(config.remote_url, timeout=config.request_timeout)
        if remote_snapshot is not None:
            remote_snapshot["host"] = config.remote_hostname
            insert_snapshot(conn, remote_snapshot)
            written += 1
            LOG.info("Stored remote snapshot for %s", config.remote_hostname)
    else:
        LOG.info("Remote health collection disabled (HEALTH_REMOTE_ENABLED=false)")

    rolled = rollup_raw_snapshots(conn, raw_retention_hours=config.raw_retention_hours)
    pruned = prune_rollups(conn, rollup_retention_days=config.rollup_retention_days)
    if rolled:
        LOG.info("Inserted %s rollup buckets", rolled)
    if pruned:
        LOG.info("Pruned %s old rollup rows", pruned)

    conn.close()
    return written


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config = PollerConfig.from_env()
    try:
        written = run_once(config)
    except OSError as exc:
        LOG.error("Poller failed: %s", exc)
        return 1
    LOG.info("Poller complete (%s snapshots written)", written)
    return 0


if __name__ == "__main__":
    sys.exit(main())
