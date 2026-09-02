"""SQLite persistence, rollup, and retention for health snapshots."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from pi_health.metrics import filesystems_from_json, filesystems_to_json

SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    host TEXT NOT NULL,
    cpu_pct REAL,
    mem_used INTEGER,
    mem_total INTEGER,
    temp_c REAL,
    filesystems_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_snapshots_host_ts ON snapshots(host, ts);

CREATE TABLE IF NOT EXISTS rollup_5m (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    host TEXT NOT NULL,
    cpu_pct REAL,
    mem_used INTEGER,
    mem_total INTEGER,
    temp_c REAL,
    filesystems_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rollup_host_ts ON rollup_5m(host, ts);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def insert_snapshot(conn: sqlite3.Connection, snapshot: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO snapshots (ts, host, cpu_pct, mem_used, mem_total, temp_c, filesystems_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            snapshot["ts"],
            snapshot["host"],
            snapshot.get("cpu_pct"),
            snapshot.get("mem_used"),
            snapshot.get("mem_total"),
            snapshot.get("temp_c"),
            filesystems_to_json(snapshot.get("filesystems", [])),
        ),
    )
    conn.commit()


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _format_ts(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _avg(values: list[float | None]) -> float | None:
    nums = [value for value in values if value is not None]
    if not nums:
        return None
    return round(sum(nums) / len(nums), 1)


def _avg_int(values: list[int | None]) -> int | None:
    nums = [value for value in values if value is not None]
    if not nums:
        return None
    return int(sum(nums) / len(nums))


def _rollup_filesystems(rows: list[sqlite3.Row]) -> str:
    mount_totals: dict[str, list[dict[str, int]]] = {}
    for row in rows:
        for fs in filesystems_from_json(row["filesystems_json"]):
            mount = fs["mount"]
            mount_totals.setdefault(mount, []).append(fs)
    rolled: list[dict[str, Any]] = []
    for mount, samples in sorted(mount_totals.items()):
        rolled.append(
            {
                "mount": mount,
                "total": _avg_int([sample.get("total") for sample in samples]) or 0,
                "used": _avg_int([sample.get("used") for sample in samples]) or 0,
                "avail": _avg_int([sample.get("avail") for sample in samples]) or 0,
            }
        )
    return filesystems_to_json(rolled)


def rollup_raw_snapshots(
    conn: sqlite3.Connection,
    *,
    raw_retention_hours: int,
) -> int:
    """Aggregate raw snapshots older than retention window into 5-minute buckets."""
    cutoff = datetime.now(UTC) - timedelta(hours=raw_retention_hours)
    cutoff_ts = _format_ts(cutoff)
    rows = conn.execute(
        """
        SELECT ts, host, cpu_pct, mem_used, mem_total, temp_c, filesystems_json
        FROM snapshots
        WHERE ts < ?
        ORDER BY host, ts
        """,
        (cutoff_ts,),
    ).fetchall()
    if not rows:
        return 0

    buckets: dict[tuple[str, str], list[sqlite3.Row]] = {}
    for row in rows:
        ts = _parse_ts(row["ts"])
        bucket_start = ts.replace(minute=(ts.minute // 5) * 5, second=0, microsecond=0)
        key = (row["host"], _format_ts(bucket_start))
        buckets.setdefault(key, []).append(row)

    inserted = 0
    for (host, bucket_ts), bucket_rows in buckets.items():
        existing = conn.execute(
            "SELECT 1 FROM rollup_5m WHERE host = ? AND ts = ? LIMIT 1",
            (host, bucket_ts),
        ).fetchone()
        if existing:
            continue
        conn.execute(
            """
            INSERT INTO rollup_5m (ts, host, cpu_pct, mem_used, mem_total, temp_c, filesystems_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                bucket_ts,
                host,
                _avg([row["cpu_pct"] for row in bucket_rows]),
                _avg_int([row["mem_used"] for row in bucket_rows]),
                _avg_int([row["mem_total"] for row in bucket_rows]),
                _avg([row["temp_c"] for row in bucket_rows]),
                _rollup_filesystems(bucket_rows),
            ),
        )
        inserted += 1

    conn.execute("DELETE FROM snapshots WHERE ts < ?", (cutoff_ts,))
    conn.commit()
    return inserted


def prune_rollups(conn: sqlite3.Connection, *, rollup_retention_days: int) -> int:
    cutoff = datetime.now(UTC) - timedelta(days=rollup_retention_days)
    cutoff_ts = _format_ts(cutoff)
    cursor = conn.execute("DELETE FROM rollup_5m WHERE ts < ?", (cutoff_ts,))
    conn.commit()
    return cursor.rowcount
