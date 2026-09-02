"""Tests for pi_health metrics, storage, and poller."""

from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest import mock

from pi_health.config import PollerConfig
from pi_health.metrics import (
    collect_snapshot,
    cpu_percent,
    filesystem_stats,
    filesystems_from_json,
    filesystems_to_json,
    memory_bytes,
    temperature_c,
)
from pi_health.poller import run_once
from pi_health.storage import connect, insert_snapshot, prune_rollups, rollup_raw_snapshots


class MetricsTests(unittest.TestCase):
    def test_cpu_percent_from_proc_stat(self) -> None:
        stat_lines = [
            "cpu 100 0 0 0 0 0 0 0 0 0\n",
            "cpu 200 0 0 100 0 0 0 0 0 0\n",
        ]

        def fake_open(path: str, *args: object, **kwargs: object):
            if path == "/proc/stat":
                return mock.mock_open(read_data=stat_lines.pop(0)).return_value
            raise FileNotFoundError(path)

        with mock.patch("pi_health.metrics.open", side_effect=fake_open), mock.patch("pi_health.metrics.time.sleep"):
            value = cpu_percent(interval=0)
        self.assertEqual(value, 50.0)

    def test_memory_bytes_parses_meminfo(self) -> None:
        meminfo = "MemTotal:       8192000 kB\nMemAvailable:    4096000 kB\n"

        with mock.patch("pi_health.metrics.open", mock.mock_open(read_data=meminfo)):
            used, total = memory_bytes()
        self.assertEqual(total, 8192000 * 1024)
        self.assertEqual(used, 4096000 * 1024)

    def test_temperature_reads_milli_celsius(self) -> None:
        with mock.patch("pi_health.metrics.open", mock.mock_open(read_data="51234\n")):
            self.assertEqual(temperature_c(), 51.2)

    def test_filesystem_stats_uses_statvfs(self) -> None:
        fake_stat = mock.Mock(f_frsize=4096, f_blocks=1000, f_bavail=250)
        with mock.patch("pi_health.metrics.os.statvfs", return_value=fake_stat):
            stats = filesystem_stats(["/"])
        self.assertEqual(stats[0]["total"], 4096 * 1000)
        self.assertEqual(stats[0]["avail"], 4096 * 250)

    def test_collect_snapshot_shape(self) -> None:
        with (
            mock.patch("pi_health.metrics.cpu_percent", return_value=12.3),
            mock.patch("pi_health.metrics.memory_bytes", return_value=(100, 200)),
            mock.patch("pi_health.metrics.temperature_c", return_value=45.6),
            mock.patch(
                "pi_health.metrics.filesystem_stats",
                return_value=[{"mount": "/", "total": 1, "used": 1, "avail": 0}],
            ),
        ):
            snapshot = collect_snapshot("TestHost", ["/"])
        self.assertEqual(snapshot["host"], "TestHost")
        self.assertEqual(snapshot["cpu_pct"], 12.3)

    def test_filesystems_json_round_trip(self) -> None:
        payload = [{"mount": "/", "total": 10, "used": 4, "avail": 6}]
        self.assertEqual(filesystems_from_json(filesystems_to_json(payload)), payload)


class StorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "health.sqlite"

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _snapshot(self, host: str, ts: str) -> dict:
        return {
            "ts": ts,
            "host": host,
            "cpu_pct": 10.0,
            "mem_used": 100,
            "mem_total": 200,
            "temp_c": 40.0,
            "filesystems": [{"mount": "/", "total": 1000, "used": 400, "avail": 600}],
        }

    def test_insert_and_rollup(self) -> None:
        old_ts = (datetime.now(UTC) - timedelta(hours=49)).strftime("%Y-%m-%dT%H:%M:%SZ")
        recent_ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        conn = connect(self.db_path)
        insert_snapshot(conn, self._snapshot("DietPiServer", old_ts))
        insert_snapshot(conn, self._snapshot("DietPiServer", recent_ts))
        rolled = rollup_raw_snapshots(conn, raw_retention_hours=48)
        self.assertEqual(rolled, 1)
        conn.close()

    def test_prune_rollups(self) -> None:
        conn = connect(self.db_path)
        old_ts = (datetime.now(UTC) - timedelta(days=40)).strftime("%Y-%m-%dT%H:%M:%SZ")
        conn.execute(
            """
            INSERT INTO rollup_5m (ts, host, cpu_pct, mem_used, mem_total, temp_c, filesystems_json)
            VALUES (?, 'DietPiServer', 1, 1, 2, 1, '[]')
            """,
            (old_ts,),
        )
        conn.commit()
        deleted = prune_rollups(conn, rollup_retention_days=30)
        self.assertEqual(deleted, 1)
        conn.close()


class PollerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "health.sqlite"

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_run_once_skips_remote_when_disabled(self) -> None:
        config = PollerConfig(
            db_path=str(self.db_path),
            local_hostname="DietPiServer",
            remote_hostname="MediaPi",
            remote_url="http://192.168.68.100:9105/health",
            remote_enabled=False,
            local_mount_paths=["/"],
            raw_retention_hours=48,
            rollup_retention_days=30,
            request_timeout=1,
        )
        snapshot = {
            "host": "DietPiServer",
            "ts": "2026-09-02T10:00:00Z",
            "cpu_pct": 1.0,
            "mem_used": 1,
            "mem_total": 2,
            "temp_c": 40.0,
            "filesystems": [],
        }
        with (
            mock.patch("pi_health.poller.collect_snapshot", return_value=snapshot),
            mock.patch("pi_health.poller.fetch_remote_snapshot") as remote_mock,
        ):
            written = run_once(config)
        remote_mock.assert_not_called()
        self.assertEqual(written, 1)

    def test_run_once_continues_when_remote_unreachable(self) -> None:
        config = PollerConfig(
            db_path=str(self.db_path),
            local_hostname="DietPiServer",
            remote_hostname="MediaPi",
            remote_url="http://192.168.68.100:9105/health",
            remote_enabled=True,
            local_mount_paths=["/"],
            raw_retention_hours=48,
            rollup_retention_days=30,
            request_timeout=1,
        )
        snapshot = {
            "host": "DietPiServer",
            "ts": "2026-09-02T10:00:00Z",
            "cpu_pct": 1.0,
            "mem_used": 1,
            "mem_total": 2,
            "temp_c": 40.0,
            "filesystems": [],
        }
        with (
            mock.patch("pi_health.poller.collect_snapshot", return_value=snapshot),
            mock.patch("pi_health.poller.fetch_remote_snapshot", return_value=None),
        ):
            written = run_once(config)
        self.assertEqual(written, 1)


if __name__ == "__main__":
    unittest.main()
