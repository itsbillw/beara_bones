"""Tests for the health dashboard app."""

from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse


def _seed_db(path: Path, *, include_mediapi: bool = True) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            host TEXT NOT NULL,
            cpu_pct REAL,
            mem_used INTEGER,
            mem_total INTEGER,
            temp_c REAL,
            filesystems_json TEXT NOT NULL
        );
        CREATE TABLE rollup_5m (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            host TEXT NOT NULL,
            cpu_pct REAL,
            mem_used INTEGER,
            mem_total INTEGER,
            temp_c REAL,
            filesystems_json TEXT NOT NULL
        );
        """
    )
    filesystems = json.dumps([{"mount": "/", "total": 1000, "used": 400, "avail": 600}])
    conn.execute(
        """
        INSERT INTO snapshots (ts, host, cpu_pct, mem_used, mem_total, temp_c, filesystems_json)
        VALUES ('2026-09-02T10:00:00Z', 'DietPiServer', 12.5, 400, 1000, 44.0, ?)
        """,
        (filesystems,),
    )
    if include_mediapi:
        conn.execute(
            """
            INSERT INTO snapshots (ts, host, cpu_pct, mem_used, mem_total, temp_c, filesystems_json)
            VALUES ('2026-09-02T10:00:30Z', 'MediaPi', 20.0, 600, 2000, 51.0, ?)
            """,
            (filesystems,),
        )
    conn.commit()
    conn.close()


class HealthViewTests(TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "health.sqlite"
        _seed_db(self.db_path)
        self.settings = override_settings(
            HEALTH_SQLITE_PATH=str(self.db_path),
            HEALTH_HOSTS="DietPiServer,MediaPi",
        )
        self.settings.enable()
        self.addCleanup(self.settings.disable)
        self.addCleanup(self.tempdir.cleanup)

        user_model = get_user_model()
        self.staff = user_model.objects.create_user(username="staff", is_staff=True)
        self.staff.set_unusable_password()
        self.staff.save()
        self.user = user_model.objects.create_user(username="user", is_staff=False)
        self.user.set_unusable_password()
        self.user.save()
        self.client = Client()

    def test_health_page_requires_staff(self) -> None:
        response = self.client.get(reverse("health:health"))
        self.assertEqual(response.status_code, 302)

        self.client.force_login(self.user)
        response = self.client.get(reverse("health:health"))
        self.assertEqual(response.status_code, 403)

    def test_health_page_renders_for_staff(self) -> None:
        self.client.force_login(self.staff)
        response = self.client.get(reverse("health:health"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("Pi health", html)
        self.assertIn("DietPiServer", html)
        self.assertIn("MediaPi", html)

    def test_health_cards_partial(self) -> None:
        self.client.force_login(self.staff)
        response = self.client.get(reverse("health:cards"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("health-cards-grid", response.content.decode())

    def test_health_charts_partial(self) -> None:
        self.client.force_login(self.staff)
        response = self.client.get(
            reverse("health:charts"),
            {"host": "DietPiServer", "range": "24h"},
        )
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("health-chart-cpu", html)
        self.assertIn("health-chart-data", html)

    def test_health_page_renders_when_mediapi_offline(self) -> None:
        offline_db = Path(self.tempdir.name) / "offline.sqlite"
        _seed_db(offline_db, include_mediapi=False)
        with override_settings(HEALTH_SQLITE_PATH=str(offline_db)):
            self.client.force_login(self.staff)
            response = self.client.get(reverse("health:health"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("DietPiServer", html)
        self.assertIn("MediaPi", html)
        self.assertIn("Offline", html)

    def test_health_charts_for_offline_host(self) -> None:
        offline_db = Path(self.tempdir.name) / "offline-charts.sqlite"
        _seed_db(offline_db, include_mediapi=False)
        with override_settings(HEALTH_SQLITE_PATH=str(offline_db)):
            self.client.force_login(self.staff)
            response = self.client.get(
                reverse("health:charts"),
                {"host": "MediaPi", "range": "24h"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertIn("offline or has no recent data", response.content.decode())

    def test_health_page_without_database(self) -> None:
        missing = Path(self.tempdir.name) / "missing.sqlite"
        with override_settings(HEALTH_SQLITE_PATH=str(missing), HEALTH_HOSTS="DietPiServer,MediaPi"):
            self.client.force_login(self.staff)
            response = self.client.get(reverse("health:health"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("Pi health", response.content.decode())


class HealthServiceTests(TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "health.sqlite"
        _seed_db(self.db_path)
        self.settings = override_settings(
            HEALTH_SQLITE_PATH=str(self.db_path),
            HEALTH_HOSTS="DietPiServer,MediaPi",
        )
        self.settings.enable()
        self.addCleanup(self.settings.disable)
        self.addCleanup(self.tempdir.cleanup)

    def test_latest_snapshots(self) -> None:
        from health.health_service import latest_snapshots

        snapshots = latest_snapshots()
        self.assertEqual(set(snapshots.keys()), {"DietPiServer", "MediaPi"})
        self.assertEqual(snapshots["MediaPi"].cpu_pct, 20.0)

    def test_format_bytes(self) -> None:
        from health.health_service import format_bytes

        self.assertEqual(format_bytes(1024), "1.0 KB")
        self.assertEqual(format_bytes(None), "—")
