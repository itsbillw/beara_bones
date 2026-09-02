"""Read health snapshots from the poller's SQLite database."""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from django.conf import settings

LOG = logging.getLogger(__name__)

RangeKey = Literal["1h", "6h", "24h", "7d", "30d"]

RANGE_HOURS: dict[RangeKey, int] = {
    "1h": 1,
    "6h": 6,
    "24h": 24,
    "7d": 24 * 7,
    "30d": 24 * 30,
}


@dataclass(frozen=True)
class HostSnapshot:
    host: str
    ts: str
    cpu_pct: float | None
    mem_used: int | None
    mem_total: int | None
    temp_c: float | None
    filesystems: list[dict[str, Any]]

    @property
    def mem_pct(self) -> float | None:
        mem_total = self.mem_total
        if self.mem_used is None or not mem_total:
            return None
        return round(100.0 * self.mem_used / mem_total, 1)


def db_path() -> Path:
    return Path(getattr(settings, "HEALTH_SQLITE_PATH", ""))


def connect_readonly() -> sqlite3.Connection:
    path = db_path()
    if not path.exists():
        raise FileNotFoundError(f"Health database not found: {path}")
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _row_to_snapshot(row: sqlite3.Row) -> HostSnapshot | None:
    try:
        filesystems = json.loads(row["filesystems_json"])
    except (json.JSONDecodeError, TypeError) as exc:
        LOG.warning("Skipping corrupt filesystems_json for %s at %s: %s", row["host"], row["ts"], exc)
        filesystems = []
    if not isinstance(filesystems, list):
        filesystems = []
    return HostSnapshot(
        host=row["host"],
        ts=row["ts"],
        cpu_pct=row["cpu_pct"],
        mem_used=row["mem_used"],
        mem_total=row["mem_total"],
        temp_c=row["temp_c"],
        filesystems=filesystems,
    )


def list_hosts() -> list[str]:
    configured = getattr(settings, "HEALTH_HOSTS", None)
    if configured:
        return [host.strip() for host in configured.split(",") if host.strip()]
    try:
        conn = connect_readonly()
    except (FileNotFoundError, sqlite3.Error) as exc:
        LOG.debug("Health host list unavailable: %s", exc)
        return []
    try:
        with conn:
            rows = conn.execute(
                """
                SELECT DISTINCT host FROM snapshots
                UNION
                SELECT DISTINCT host FROM rollup_5m
                ORDER BY host
                """
            ).fetchall()
        return [row["host"] for row in rows]
    except sqlite3.Error as exc:
        LOG.warning("Health host list query failed: %s", exc)
        return []


def latest_snapshots() -> dict[str, HostSnapshot]:
    try:
        conn = connect_readonly()
    except (FileNotFoundError, sqlite3.Error) as exc:
        LOG.debug("Health snapshots unavailable: %s", exc)
        return {}
    snapshots: dict[str, HostSnapshot] = {}
    try:
        with conn:
            rows = conn.execute(
                """
                SELECT s.*
                FROM snapshots s
                INNER JOIN (
                    SELECT host, MAX(ts) AS max_ts
                    FROM snapshots
                    GROUP BY host
                ) latest ON s.host = latest.host AND s.ts = latest.max_ts
                ORDER BY s.host
                """
            ).fetchall()
            for row in rows:
                snapshot = _row_to_snapshot(row)
                if snapshot is not None:
                    snapshots[snapshot.host] = snapshot
    except sqlite3.Error as exc:
        LOG.warning("Health snapshot query failed: %s", exc)
    return snapshots


def default_chart_host(hosts: list[str], snapshots: dict[str, HostSnapshot]) -> str | None:
    """Prefer the first host that currently has data."""
    for host in hosts:
        if host in snapshots:
            return host
    return hosts[0] if hosts else None


def _cutoff_ts(hours: int) -> str:
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    return cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")


def _history_table(range_key: RangeKey) -> str:
    return "snapshots" if RANGE_HOURS[range_key] <= 48 else "rollup_5m"


def history_rows(host: str, range_key: RangeKey) -> list[HostSnapshot]:
    table = _history_table(range_key)
    cutoff = _cutoff_ts(RANGE_HOURS[range_key])
    try:
        conn = connect_readonly()
    except (FileNotFoundError, sqlite3.Error) as exc:
        LOG.debug("Health history unavailable for %s: %s", host, exc)
        return []
    rows: list[HostSnapshot] = []
    try:
        with conn:
            if table == "snapshots":
                raw_rows = conn.execute(
                    """
                    SELECT ts, host, cpu_pct, mem_used, mem_total, temp_c, filesystems_json
                    FROM snapshots
                    WHERE host = ? AND ts >= ?
                    ORDER BY ts
                    """,
                    (host, cutoff),
                ).fetchall()
            else:
                raw_rows = conn.execute(
                    """
                    SELECT ts, host, cpu_pct, mem_used, mem_total, temp_c, filesystems_json
                    FROM rollup_5m
                    WHERE host = ? AND ts >= ?
                    ORDER BY ts
                    """,
                    (host, cutoff),
                ).fetchall()
        for row in raw_rows:
            snapshot = _row_to_snapshot(row)
            if snapshot is not None:
                rows.append(snapshot)
    except sqlite3.Error as exc:
        LOG.warning("Health history query failed for %s: %s", host, exc)
    return rows


def format_bytes(value: int | None) -> str:
    if value is None:
        return "—"
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(value)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"
