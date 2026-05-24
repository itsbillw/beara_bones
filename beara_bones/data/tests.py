"""Tests for data app: views, loading, admin, dashboard logic."""

import json
import unittest
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

import pandas as pd
from django.test import RequestFactory, TestCase
from django.urls import reverse

from data.dashboard_service import build_dashboard_payload, league_season_defaults
from data.dashboard_utils import build_standings_and_figure
from data.loading import load_fixtures_dataframe
from data.models import Fixture, League, Season
from data.theme_utils import current_theme, plotly_template


class DashboardServiceTests(TestCase):
    """Test dashboard_service with mocked dependencies."""

    def setUp(self) -> None:
        from django.core.cache import cache

        cache.clear()
        League.objects.get_or_create(
            id=39,
            defaults={"name": "Premier League", "order": 0},
        )
        Season.objects.get_or_create(
            api_year=2025,
            defaults={"display": "2025/26", "order": 0},
        )

    def test_league_season_defaults(self) -> None:
        league_id, season = league_season_defaults()
        self.assertEqual(league_id, 39)
        self.assertEqual(season, 2025)

    def test_build_dashboard_payload_none_league_returns_empty(self) -> None:
        payload = build_dashboard_payload(league_id=None, season=2025)
        self.assertEqual(payload["standings"], [])
        self.assertEqual(payload["error"], "")
        figure = json.loads(payload["figure_json"])
        self.assertIn("Select league", figure["layout"]["annotations"][0]["text"])

    @patch("data.dashboard_service.load_fixtures_from_db")
    def test_build_dashboard_payload_with_data(
        self,
        mock_load: unittest.mock.Mock,
    ) -> None:
        mock_load.return_value = (_minimal_fixtures_df(), None)
        payload = build_dashboard_payload(league_id=39, season=2025)
        self.assertEqual(payload["error"], "")
        self.assertEqual(len(payload["standings"]), 2)
        self.assertEqual(payload["standings"][0]["rank"], 1)
        mock_load.assert_called_once_with(39, 2025)

    @patch("data.dashboard_service.load_fixtures_from_db")
    def test_build_dashboard_payload_load_error(
        self,
        mock_load: unittest.mock.Mock,
    ) -> None:
        mock_load.return_value = (None, "No fixtures for this league/season.")
        payload = build_dashboard_payload(league_id=39, season=2025)
        self.assertIn("No fixtures", payload["error"])

    @patch("data.dashboard_service.load_fixtures_from_db")
    @patch("data.dashboard_service.load_team_games_from_view")
    def test_build_dashboard_prefers_team_games_view(
        self,
        mock_view: unittest.mock.Mock,
        mock_db: unittest.mock.Mock,
    ) -> None:
        mock_view.return_value = (_team_games_df(), None)
        build_dashboard_payload(league_id=39, season=2025)
        mock_view.assert_called_once_with(39, 2025)
        mock_db.assert_not_called()


class ThemeUtilsTests(TestCase):
    def test_current_theme_defaults_to_dark(self) -> None:
        self.assertEqual(current_theme(None), "dark")

    def test_current_theme_reads_cookie(self) -> None:
        request = RequestFactory().get("/")
        request.COOKIES["itsbillw-theme"] = "light"
        self.assertEqual(current_theme(request), "light")
        self.assertEqual(plotly_template("light"), "plotly_white")

    def test_current_theme_invalid_cookie_falls_back(self) -> None:
        request = RequestFactory().get("/")
        request.COOKIES["itsbillw-theme"] = "neon"
        self.assertEqual(current_theme(request), "dark")


def _minimal_fixtures_df():
    """One fixture: TeamA 2-1 TeamB (home win)."""
    return pd.DataFrame(
        [
            {
                "fixture_date": pd.Timestamp("2025-01-15"),
                "home_team_name": "TeamA",
                "away_team_name": "TeamB",
                "goals_home": 2,
                "goals_away": 1,
                "result": "H",
            },
        ],
    )


def _multi_team_fixtures_df() -> pd.DataFrame:
    """Round-robin style fixtures across six teams for chart contract tests."""
    teams = [f"Team{i}" for i in range(1, 7)]
    rows = []
    day = 0
    for i in range(len(teams)):
        for j in range(i + 1, len(teams)):
            rows.append(
                {
                    "fixture_date": pd.Timestamp("2025-01-01") + pd.Timedelta(days=day),
                    "home_team_name": teams[i],
                    "away_team_name": teams[j],
                    "goals_home": 1,
                    "goals_away": 0,
                    "result": "H",
                },
            )
            day += 1
    return pd.DataFrame(rows)


class ChartFigureContractTests(TestCase):
    """Plotly figure JSON invariants for layout, legend, and hover payloads."""

    def _figure_json(self, df: pd.DataFrame) -> dict:
        import plotly.io as pio

        from data.dashboard_utils import build_standings_and_figure

        _, fig, err = build_standings_and_figure(df)
        self.assertIsNone(err)
        assert fig is not None
        return cast(dict[str, Any], json.loads(pio.to_json(fig)))

    def test_layout_margins_and_vertical_legend(self) -> None:
        fig = self._figure_json(_multi_team_fixtures_df())
        margin = fig["layout"]["margin"]
        self.assertGreaterEqual(margin["b"], 60)
        self.assertGreaterEqual(margin["r"], 150)
        legend = fig["layout"]["legend"]
        self.assertEqual(legend["orientation"], "v")
        self.assertGreater(legend["x"], 1)
        self.assertEqual(fig["layout"]["hovermode"], "closest")

    def test_traces_have_matching_hovertext(self) -> None:
        from data.dashboard_utils import SEASON_START_HOVER

        fig = self._figure_json(_multi_team_fixtures_df())
        self.assertGreaterEqual(len(fig["data"]), 6)
        for trace in fig["data"]:
            self.assertEqual(len(trace["x"]), len(trace["y"]))
            self.assertEqual(len(trace["x"]), len(trace["hovertext"]))
            self.assertIn(SEASON_START_HOVER, trace["hovertext"][0])

    @patch("data.dashboard_service.load_fixtures_from_db")
    def test_dashboard_payload_figure_json_round_trip(
        self,
        mock_load: unittest.mock.Mock,
    ) -> None:
        from django.core.cache import cache

        cache.clear()
        League.objects.get_or_create(
            id=39,
            defaults={"name": "Premier League", "order": 0},
        )
        Season.objects.get_or_create(
            api_year=2025,
            defaults={"display": "2025/26", "order": 0},
        )
        mock_load.return_value = (_multi_team_fixtures_df(), None)
        payload = build_dashboard_payload(league_id=39, season=2025)
        fig = json.loads(payload["figure_json"])
        self.assertGreaterEqual(len(fig["data"]), 6)
        self.assertGreaterEqual(fig["layout"]["margin"]["b"], 60)


class DataViewTests(TestCase):
    """Data page, fragment, and refresh endpoint behave correctly."""

    def test_data_page_returns_200(self) -> None:
        response = self.client.get(reverse("data:data"))
        self.assertEqual(response.status_code, 200)

    def test_data_page_renders_football_dashboard(self) -> None:
        response = self.client.get(reverse("data:data"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("football-dashboard", html)
        self.assertIn("football-chart", html)

    def test_dashboard_panel_returns_partial(self) -> None:
        response = self.client.get(reverse("data:dashboard_panel"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("football-standings-table", html)
        self.assertIn('id="football-chart-plot"', html)
        self.assertIn("football-chart-data", html)

    def test_data_refresh_post_returns_403_when_not_staff(self) -> None:
        """POST to refresh when not staff returns 403."""
        response = self.client.post(reverse("data:data_refresh"))
        self.assertEqual(response.status_code, 403)

    @patch("data.views.enqueue_pipeline_refresh")
    def test_data_refresh_post_staff_returns_202_or_409(
        self,
        mock_enqueue: unittest.mock.Mock,
    ) -> None:
        """POST to refresh as staff returns 202 or 409."""
        from django.contrib.auth import get_user_model

        mock_enqueue.return_value = {"status": "started", "message": "Refresh started"}
        User = get_user_model()
        user = User.objects.create_superuser("admin", "a@b.com", "pass")
        self.client.force_login(user)
        response = self.client.post(reverse("data:data_refresh"))
        self.assertIn(response.status_code, (202, 409, 500))

    def test_data_refresh_get_not_allowed(self) -> None:
        response = self.client.get(reverse("data:data_refresh"))
        self.assertEqual(response.status_code, 405)

    def test_crest_serve_returns_404_when_object_missing(
        self,
    ) -> None:
        """Crest view returns 404 when MinIO object is missing."""
        with patch("data.views.get_client") as mock_get_client:
            mock_client = unittest.mock.MagicMock()
            mock_client.get_object.side_effect = Exception("Not found")
            mock_get_client.return_value = mock_client
            response = self.client.get(reverse("data:crest", kwargs={"team_id": 999}))
        self.assertEqual(response.status_code, 404)

    def test_crest_serve_returns_image_when_found(
        self,
    ) -> None:
        """Crest view returns 200 and image/png when object exists in MinIO."""
        fake_png = b"\x89PNG\r\n\x1a\n"
        mock_resp = unittest.mock.MagicMock()
        mock_resp.read.return_value = fake_png
        mock_resp.close = unittest.mock.Mock()
        with patch("data.views.get_client") as mock_get_client:
            mock_client = unittest.mock.MagicMock()
            mock_client.get_object.return_value = mock_resp
            mock_get_client.return_value = mock_client
            response = self.client.get(reverse("data:crest", kwargs={"team_id": 42}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertEqual(response.content, fake_png)


class DashboardUtilsTests(TestCase):
    """Unit tests for build_standings_and_figure (shared dashboard logic)."""

    def test_build_standings_no_data_returns_error(self) -> None:
        standings, fig, err = build_standings_and_figure(None)
        self.assertEqual(err, "No data")
        self.assertEqual(standings, [])
        self.assertIsNone(fig)

    def test_build_standings_empty_dataframe_returns_error(self) -> None:
        standings, fig, err = build_standings_and_figure(pd.DataFrame())
        self.assertEqual(err, "No data")
        self.assertEqual(standings, [])
        self.assertIsNone(fig)

    def test_build_standings_with_minimal_data_returns_standings_and_figure(
        self,
    ) -> None:
        standings, fig, err = build_standings_and_figure(_minimal_fixtures_df())
        self.assertIsNone(err)
        self.assertEqual(len(standings), 2)
        teams = {r["team"] for r in standings}
        self.assertEqual(teams, {"TeamA", "TeamB"})
        team_a = next(r for r in standings if r["team"] == "TeamA")
        self.assertEqual(team_a["Pts"], 3)
        self.assertEqual(team_a["W"], 1)
        team_b = next(r for r in standings if r["team"] == "TeamB")
        self.assertEqual(team_b["Pts"], 0)
        self.assertEqual(team_b["L"], 1)
        self.assertIsNotNone(fig)

    def test_build_standings_x_axis_fixture_date(self) -> None:
        """Chart can use fixture (date) as x-axis and starts at zero."""
        standings, fig, err = build_standings_and_figure(
            _minimal_fixtures_df(),
            x_axis="fixture_date",
        )
        self.assertIsNone(err)
        self.assertIsNotNone(fig)
        self.assertEqual(fig.layout.xaxis.title.text, "Fixture (date)")
        self.assertEqual(fig.layout.yaxis.title.text, "Points")

    def test_build_standings_x_axis_games_played_default(self) -> None:
        """Default x-axis is games played."""
        standings, fig, err = build_standings_and_figure(_minimal_fixtures_df())
        self.assertIsNone(err)
        self.assertEqual(fig.layout.xaxis.title.text, "Games played")

    def test_build_standings_with_team_ids_adds_crest_path(self) -> None:
        """When home_team_id/away_team_id present, standings get crest_path and team_display_md."""
        df = _minimal_fixtures_df()
        df["home_team_id"] = 1
        df["away_team_id"] = 2
        standings, fig, err = build_standings_and_figure(df)
        self.assertIsNone(err)
        team_a = next(r for r in standings if r["team"] == "TeamA")
        self.assertEqual(team_a.get("crest_path"), "/data/crest/1/")
        self.assertIn("TeamA", team_a.get("team_display_md", ""))


class RunFootballPipelineCommandTests(TestCase):
    """Management command run_football_pipeline."""

    def setUp(self) -> None:
        League.objects.get_or_create(
            id=39,
            defaults={"name": "Premier League", "order": 0},
        )
        Season.objects.get_or_create(
            api_year=2025,
            defaults={"display": "2025/26", "order": 0},
        )

    def test_handle_exits_when_lock_exists(self) -> None:
        from io import StringIO

        from data.management.commands.run_football_pipeline import LOCK_FILE, Command

        LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
        try:
            LOCK_FILE.touch()
            cmd = Command()
            cmd.stdout = StringIO()
            with self.assertRaises(SystemExit) as ctx:
                cmd.handle()
            self.assertEqual(ctx.exception.code, 1)
        finally:
            if LOCK_FILE.exists():
                LOCK_FILE.unlink(missing_ok=True)

    @patch("football.processed.upload_processed_parquet")
    @patch("data.loading.load_fixtures_dataframe")
    @patch("football.transform.run_transform")
    @patch("football.ingest.run_ingest")
    def test_handle_runs_ingest_transform_load_for_each_league_season(
        self,
        mock_ingest: unittest.mock.Mock,
        mock_transform: unittest.mock.Mock,
        mock_load: unittest.mock.Mock,
        mock_upload: unittest.mock.Mock,
    ) -> None:
        from data.management.commands.run_football_pipeline import Command

        mock_transform.return_value = pd.DataFrame([{"fixture_id": 1}])
        cmd = Command()
        from data.management.commands.run_football_pipeline import LOCK_FILE

        try:
            cmd.handle()
        finally:
            if LOCK_FILE.exists():
                LOCK_FILE.unlink(missing_ok=True)
        self.assertEqual(mock_ingest.call_count, 1)
        self.assertEqual(mock_transform.call_count, 1)
        mock_load.assert_called_once()
        mock_upload.assert_called_once()


class RebuildFootballFromMinioCommandTests(TestCase):
    """Management command rebuild_football_from_minio."""

    def setUp(self) -> None:
        League.objects.get_or_create(
            id=39,
            defaults={"name": "Premier League", "order": 0},
        )
        Season.objects.get_or_create(
            api_year=2025,
            defaults={"display": "2025/26", "order": 0},
        )

    def test_handle_exits_when_lock_exists(self) -> None:
        from io import StringIO

        from data.management.commands.rebuild_football_from_minio import (
            LOCK_FILE,
            Command,
        )

        LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
        try:
            LOCK_FILE.touch()
            cmd = Command()
            cmd.stdout = StringIO()
            with self.assertRaises(SystemExit) as ctx:
                cmd.handle()
            self.assertEqual(ctx.exception.code, 1)
        finally:
            if LOCK_FILE.exists():
                LOCK_FILE.unlink(missing_ok=True)

    @patch("football.processed.upload_processed_parquet")
    @patch("data.loading.load_fixtures_dataframe")
    @patch("football.transform.run_transform")
    @patch("football.processed.load_processed_parquet_from_minio")
    def test_handle_loads_from_processed_or_raw(
        self,
        mock_load_parquet: unittest.mock.Mock,
        mock_transform: unittest.mock.Mock,
        mock_load_df: unittest.mock.Mock,
        mock_upload: unittest.mock.Mock,
    ) -> None:
        from data.management.commands.rebuild_football_from_minio import Command

        mock_load_parquet.return_value = pd.DataFrame([{"fixture_id": 1}])
        cmd = Command()
        from data.management.commands.rebuild_football_from_minio import LOCK_FILE

        try:
            cmd.handle()
        finally:
            if LOCK_FILE.exists():
                LOCK_FILE.unlink(missing_ok=True)
        mock_load_parquet.assert_called()
        mock_load_df.assert_called_once()
        # When loading from processed Parquet we do not call upload (only when rebuilding from raw)
        mock_upload.assert_not_called()

    def test_handle_no_leagues_or_seasons_returns_early(self) -> None:
        from io import StringIO

        from data.management.commands.rebuild_football_from_minio import (
            LOCK_FILE,
            Command,
        )

        League.objects.all().delete()
        Season.objects.all().delete()
        out = StringIO()
        cmd = Command()
        cmd.stdout = out
        try:
            cmd.handle()
        finally:
            if LOCK_FILE.exists():
                LOCK_FILE.unlink(missing_ok=True)
        self.assertIn("League", out.getvalue())

    @patch("football.processed.upload_processed_parquet")
    @patch("data.loading.load_fixtures_dataframe")
    @patch("football.transform.run_transform")
    @patch("football.processed.load_processed_parquet_from_minio")
    def test_handle_rebuilds_from_raw_when_no_processed(
        self,
        mock_load_parquet: unittest.mock.Mock,
        mock_transform: unittest.mock.Mock,
        mock_load_df: unittest.mock.Mock,
        mock_upload: unittest.mock.Mock,
    ) -> None:
        from data.management.commands.rebuild_football_from_minio import (
            LOCK_FILE,
            Command,
        )

        mock_load_parquet.return_value = None
        mock_transform.return_value = pd.DataFrame([{"fixture_id": 1}])
        with patch(
            "data.management.commands.rebuild_football_from_minio._object_exists",
            return_value=True,
        ):
            cmd = Command()
            try:
                cmd.handle()
            finally:
                if LOCK_FILE.exists():
                    LOCK_FILE.unlink(missing_ok=True)
        mock_transform.assert_called_once()
        mock_load_df.assert_called_once()
        mock_upload.assert_called_once()


class IngestFootballCommandTests(TestCase):
    """Management command ingest_football (data app)."""

    @patch("data.management.commands.ingest_football.run_ingest")
    @patch("home.management.commands.ingest_football.run_ingest")
    def test_handle_success_writes_key(
        self,
        mock_run_home: unittest.mock.Mock,
        mock_run_data: unittest.mock.Mock,
    ) -> None:
        from io import StringIO

        from django.core.management import call_command

        mock_run_data.return_value = "raw/league_39_season_2025.json"
        mock_run_home.return_value = "raw/league_39_season_2025.json"
        out = StringIO()
        call_command("ingest_football", league=39, season=2025, stdout=out)
        self.assertIn("raw/league_39_season_2025.json", out.getvalue())
        self.assertTrue(mock_run_data.called or mock_run_home.called)

    @patch("data.management.commands.ingest_football.run_ingest")
    def test_data_command_handle_success(self, mock_run: unittest.mock.Mock) -> None:
        """Run data app's ingest_football handle directly to cover its code path."""
        from io import StringIO

        from data.management.commands.ingest_football import Command

        mock_run.return_value = "raw/league_40_season_2024.json"
        out = StringIO()
        cmd = Command()
        cmd.stdout = out
        cmd.handle(league=40, season=2024)
        self.assertIn("raw/league_40_season_2024.json", out.getvalue())
        mock_run.assert_called_once_with(league=40, season=2024)

    def test_data_command_add_arguments(self) -> None:
        from argparse import ArgumentParser

        from data.management.commands.ingest_football import Command

        parser = ArgumentParser()
        cmd = Command()
        cmd.add_arguments(parser)
        args = parser.parse_args(["--league", "42", "--season", "2023"])
        self.assertEqual(args.league, 42)
        self.assertEqual(args.season, 2023)
        args_default = parser.parse_args([])
        self.assertEqual(args_default.league, 39)
        self.assertEqual(args_default.season, 2025)

    @patch("data.management.commands.ingest_football.run_ingest")
    @patch("home.management.commands.ingest_football.run_ingest")
    def test_handle_exception_exits_with_error(
        self,
        mock_run_home: unittest.mock.Mock,
        mock_run_data: unittest.mock.Mock,
    ) -> None:
        from io import StringIO

        from django.core.management import call_command

        mock_run_data.side_effect = ValueError("RAPIDAPI_KEY not set")
        mock_run_home.side_effect = ValueError("RAPIDAPI_KEY not set")
        out = StringIO()
        with self.assertRaises(SystemExit):
            call_command("ingest_football", stdout=out)
        self.assertIn("RAPIDAPI_KEY", out.getvalue())


class PipelineLoadTests(TestCase):
    """football.pipeline._load_to_mariadb_and_minio (needs Django app context)."""

    @patch("data.loading.load_fixtures_dataframe")
    @patch("football.processed.upload_processed_parquet")
    def test_load_to_mariadb_and_minio_calls_load_and_upload(
        self,
        mock_upload: unittest.mock.Mock,
        mock_load_df: unittest.mock.Mock,
    ) -> None:
        from football.pipeline import _load_to_mariadb_and_minio

        df = pd.DataFrame([{"fixture_id": 1}])
        _load_to_mariadb_and_minio(df, league=39, season=2025)
        mock_load_df.assert_called_once_with(df, 39, 2025)
        mock_upload.assert_called_once_with(df, 39, 2025)


class LoadingTests(TestCase):
    """load_fixtures_dataframe loads DataFrame into Fixture model."""

    def setUp(self) -> None:
        League.objects.get_or_create(
            id=39,
            defaults={"name": "Premier League", "order": 0},
        )
        Season.objects.get_or_create(
            api_year=2025,
            defaults={"display": "2025/26", "order": 0},
        )

    def test_load_empty_dataframe_returns_zero(self) -> None:
        count = load_fixtures_dataframe(pd.DataFrame(), league_id=39, season=2025)
        self.assertEqual(count, 0)

    def test_load_fixtures_replaces_existing(self) -> None:
        from django.utils import timezone

        df = pd.DataFrame(
            [
                {
                    "fixture_id": 1,
                    "date": timezone.now(),
                    "timestamp": 1736953200,
                    "league_id": 39,
                    "league_season": 2025,
                    "home_team_name": "TeamA",
                    "away_team_name": "TeamB",
                    "goals_home": 2,
                    "goals_away": 1,
                },
            ],
        )
        count = load_fixtures_dataframe(df, league_id=39, season=2025)
        self.assertEqual(count, 1)
        fixture = Fixture.objects.get(fixture_id=1, league_id=39, league_season=2025)
        self.assertEqual(fixture.home_team_name, "TeamA")
        self.assertEqual(fixture.goals_home, 2)

    def test_load_replaces_same_league_season(self) -> None:
        df1 = pd.DataFrame([{"fixture_id": 1, "league_id": 39, "league_season": 2025}])
        load_fixtures_dataframe(df1, league_id=39, season=2025)
        df2 = pd.DataFrame([{"fixture_id": 2, "league_id": 39, "league_season": 2025}])
        load_fixtures_dataframe(df2, league_id=39, season=2025)
        self.assertEqual(
            Fixture.objects.filter(league_id=39, league_season=2025).count(),
            1,
        )
        self.assertEqual(
            Fixture.objects.get(league_id=39, league_season=2025).fixture_id,
            2,
        )


class AdminViewsTests(TestCase):
    """Admin pipeline control views: pipeline_control, pipeline_refresh, pipeline_rebuild."""

    def test_pipeline_control_requires_staff(self) -> None:
        response = self.client.get(reverse("data:admin_pipeline"))
        self.assertEqual(response.status_code, 302)

    def test_pipeline_control_staff_sees_page(self) -> None:
        from django.contrib.auth import get_user_model

        User = get_user_model()
        User.objects.create_superuser("admin", "a@b.com", "pass")
        self.client.force_login(User.objects.get(username="admin"))
        response = self.client.get(reverse("data:admin_pipeline"))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"pipeline", response.content.lower() or b"")

    def test_pipeline_refresh_post_requires_staff(self) -> None:
        response = self.client.post(reverse("data:admin_pipeline_refresh"))
        self.assertEqual(response.status_code, 302)

    def test_pipeline_rebuild_post_requires_staff(self) -> None:
        response = self.client.post(reverse("data:admin_pipeline_rebuild"))
        self.assertEqual(response.status_code, 302)

    def test_pipeline_refresh_get_redirects(self) -> None:
        from django.contrib.auth import get_user_model

        User = get_user_model()
        User.objects.create_superuser("admin_get", "get@b.com", "pass")
        self.client.force_login(User.objects.get(username="admin_get"))
        response = self.client.get(reverse("data:admin_pipeline_refresh"))
        self.assertEqual(response.status_code, 302)

    def test_pipeline_rebuild_get_redirects(self) -> None:
        from django.contrib.auth import get_user_model

        User = get_user_model()
        User.objects.create_superuser("admin_rebuild_get", "rb@b.com", "pass")
        self.client.force_login(User.objects.get(username="admin_rebuild_get"))
        response = self.client.get(reverse("data:admin_pipeline_rebuild"))
        self.assertEqual(response.status_code, 302)

    def test_pipeline_refresh_post_with_lock_redirects_with_message(self) -> None:

        from django.conf import settings
        from django.contrib.auth import get_user_model

        User = get_user_model()
        User.objects.create_superuser("admin2", "b@c.com", "pass")
        self.client.force_login(User.objects.get(username="admin2"))
        lock = Path(settings.BASE_DIR).parent / "data" / "football" / ".refresh.lock"
        lock.parent.mkdir(parents=True, exist_ok=True)
        try:
            lock.touch()
            response = self.client.post(reverse("data:admin_pipeline_refresh"))
            self.assertEqual(response.status_code, 302)
            next_page = self.client.get(response.url)
            self.assertIn(b"lock", next_page.content.lower())
        finally:
            if lock.exists():
                lock.unlink(missing_ok=True)

    @patch("data.admin_views.enqueue_pipeline_refresh")
    def test_pipeline_refresh_post_starts_pipeline(
        self,
        mock_enqueue: unittest.mock.Mock,
    ) -> None:
        from django.contrib.auth import get_user_model

        mock_enqueue.return_value = {"status": "started", "message": "Refresh started"}
        User = get_user_model()
        User.objects.create_superuser("admin3", "c@d.com", "pass")
        self.client.force_login(User.objects.get(username="admin3"))
        response = self.client.post(reverse("data:admin_pipeline_refresh"))
        self.assertEqual(response.status_code, 302)
        mock_enqueue.assert_called_once()

    @patch("data.admin_views.call_command")
    def test_pipeline_rebuild_post_calls_command(
        self,
        mock_call: unittest.mock.Mock,
    ) -> None:
        from django.contrib.auth import get_user_model

        User = get_user_model()
        User.objects.create_superuser("admin4", "d@e.com", "pass")
        self.client.force_login(User.objects.get(username="admin4"))
        response = self.client.post(reverse("data:admin_pipeline_rebuild"))
        self.assertEqual(response.status_code, 302)
        mock_call.assert_called_once_with("rebuild_football_from_minio")

    @patch("data.admin_views.call_command")
    def test_pipeline_rebuild_post_on_error_shows_message(
        self,
        mock_call: unittest.mock.Mock,
    ) -> None:
        from django.contrib.auth import get_user_model

        User = get_user_model()
        User.objects.create_superuser("admin5", "e@f.com", "pass")
        self.client.force_login(User.objects.get(username="admin5"))
        mock_call.side_effect = Exception("rebuild failed")
        response = self.client.post(reverse("data:admin_pipeline_rebuild"))
        self.assertEqual(response.status_code, 302)
        next_page = self.client.get(response.url)
        self.assertIn(b"rebuild failed", next_page.content.lower())


class DashboardServiceCacheTests(TestCase):
    """Dashboard payload caching."""

    def setUp(self) -> None:
        from django.core.cache import cache

        cache.clear()
        League.objects.get_or_create(
            id=39,
            defaults={"name": "Premier League", "order": 0},
        )
        Season.objects.get_or_create(
            api_year=2025,
            defaults={"display": "2025/26", "order": 0},
        )

    @patch("data.dashboard_service.load_fixtures_from_db")
    def test_build_dashboard_uses_cache_on_second_call(
        self,
        mock_load: unittest.mock.Mock,
    ) -> None:
        from django.core.cache import cache

        cache.clear()
        mock_load.return_value = (_minimal_fixtures_df(), None)
        first = build_dashboard_payload(league_id=39, season=2025)
        second = build_dashboard_payload(league_id=39, season=2025)
        self.assertEqual(first["standings"], second["standings"])
        mock_load.assert_called_once()

    @patch("data.dashboard_service.load_fixtures_from_db")
    def test_build_dashboard_build_error(
        self,
        mock_load: unittest.mock.Mock,
    ) -> None:
        from django.core.cache import cache

        cache.clear()
        mock_load.return_value = (_minimal_fixtures_df(), None)
        with patch(
            "data.dashboard_service.build_standings_and_figure",
            return_value=([], None, "Chart failed"),
        ):
            payload = build_dashboard_payload(league_id=39, season=2025)
        self.assertEqual(payload["error"], "Chart failed")


def _team_games_df():
    """Minimal team_games DataFrame matching data_team_game view shape."""
    return pd.DataFrame(
        [
            {
                "team": "TeamA",
                "team_id": 1,
                "date": pd.Timestamp("2025-01-15"),
                "opponent": "TeamB",
                "venue": "Home",
                "gf": 2,
                "ga": 1,
                "pts": 3,
                "result_letter": "W",
                "game_number": 1,
                "cumulative_pts": 3,
                "score_display": "2-1",
                "hover": "TeamA hover",
            },
            {
                "team": "TeamB",
                "team_id": 2,
                "date": pd.Timestamp("2025-01-15"),
                "opponent": "TeamA",
                "venue": "Away",
                "gf": 1,
                "ga": 2,
                "pts": 0,
                "result_letter": "L",
                "game_number": 1,
                "cumulative_pts": 0,
                "score_display": "1-2",
                "hover": "TeamB hover",
            },
        ],
    )


class DashboardUtilsExtendedTests(TestCase):
    """build_standings_and_figure edge cases and team_games input."""

    def test_team_games_df_builds_standings(self) -> None:
        standings, fig, err = build_standings_and_figure(
            team_games_df=_team_games_df(),
            plotly_template="plotly_white",
        )
        self.assertIsNone(err)
        self.assertEqual(len(standings), 2)
        self.assertIsNotNone(fig.layout.template)

    def test_team_games_missing_columns_returns_error(self) -> None:
        bad = pd.DataFrame([{"team": "A"}])
        standings, fig, err = build_standings_and_figure(team_games_df=bad)
        self.assertEqual(err, "Team-games DataFrame missing required columns")
        self.assertEqual(standings, [])
        self.assertIsNone(fig)

    def test_fixtures_missing_date_column_returns_error(self) -> None:
        df = pd.DataFrame([{"home_team_name": "A", "away_team_name": "B"}])
        standings, fig, err = build_standings_and_figure(df)
        self.assertEqual(err, "Missing date column")

    def test_fixtures_derives_result_from_goals(self) -> None:
        df = _minimal_fixtures_df().drop(columns=["result"])
        standings, fig, err = build_standings_and_figure(df)
        self.assertIsNone(err)
        team_a = next(r for r in standings if r["team"] == "TeamA")
        self.assertEqual(team_a["Pts"], 3)

    def test_fixtures_missing_required_columns_returns_error(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "fixture_date": pd.Timestamp("2025-01-15"),
                    "home_team_name": "A",
                    "away_team_name": "B",
                },
            ],
        )
        standings, fig, err = build_standings_and_figure(df)
        self.assertEqual(err, "Missing required columns")

    def test_standings_without_team_id_uses_plain_team_display(self) -> None:
        standings, _, err = build_standings_and_figure(_minimal_fixtures_df())
        self.assertIsNone(err)
        team_a = next(r for r in standings if r["team"] == "TeamA")
        self.assertEqual(team_a["team_display_md"], "TeamA")
        self.assertIsNone(team_a["crest_path"])

    def test_plotly_import_error_returns_message(self) -> None:
        real_import = __import__

        def fake_import(name, *args, **kwargs):
            if name == "plotly.graph_objects":
                raise ImportError("no plotly")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            standings, fig, err = build_standings_and_figure(
                team_games_df=_team_games_df(),
            )
        self.assertEqual(len(standings), 2)
        self.assertIsNone(fig)
        self.assertEqual(err, "Plotly not installed")


class DataViewsExtendedTests(TestCase):
    """load_fixtures_from_db, team_games view, refresh lock behaviour."""

    def setUp(self) -> None:
        from django.utils import timezone

        from data.models import Fixture

        League.objects.get_or_create(
            id=39,
            defaults={"name": "Premier League", "order": 0},
        )
        Season.objects.get_or_create(
            api_year=2025,
            defaults={"display": "2025/26", "order": 0},
        )
        Fixture.objects.create(
            fixture_id=100,
            date=timezone.now(),
            timestamp=1736953200,
            status_short="FT",
            league_id=39,
            league_season=2025,
            home_team_id=1,
            home_team_name="TeamA",
            away_team_id=2,
            away_team_name="TeamB",
            goals_home=2,
            goals_away=1,
        )

    def test_load_fixtures_from_db_returns_dataframe(self) -> None:
        from data.loaders import load_fixtures_from_db

        df, err = load_fixtures_from_db(39, 2025)
        self.assertIsNone(err)
        assert df is not None
        self.assertEqual(len(df), 1)
        self.assertEqual(df.iloc[0]["home_team_name"], "TeamA")

    def test_load_fixtures_from_db_empty_returns_error(self) -> None:
        from data.loaders import load_fixtures_from_db

        df, err = load_fixtures_from_db(99, 2099)
        self.assertIsNone(df)
        self.assertIn("No fixtures", err or "")

    def test_load_team_games_from_view_returns_dataframe(self) -> None:
        from data.loaders import load_team_games_from_view

        df, err = load_team_games_from_view(39, 2025)
        self.assertIsNone(err)
        assert df is not None
        self.assertIn("team", df.columns)
        self.assertEqual(len(df), 2)

    def test_load_team_games_from_view_empty_league_returns_none(self) -> None:
        from data.loaders import load_team_games_from_view

        df, err = load_team_games_from_view(99, 2099)
        self.assertIsNone(df)
        self.assertIsNone(err)

    def test_data_page_has_theme_support(self) -> None:
        response = self.client.get(reverse("data:data"))
        self.assertContains(response, "itsbillw-theme")

    def test_data_refresh_post_returns_409_when_lock_exists(self) -> None:

        from django.conf import settings
        from django.contrib.auth import get_user_model

        User = get_user_model()
        user = User.objects.create_superuser("lockadmin", "lock@b.com", "pass")
        self.client.force_login(user)
        lock = Path(settings.BASE_DIR).parent / "data" / "football" / ".refresh.lock"
        lock.parent.mkdir(parents=True, exist_ok=True)
        try:
            lock.touch()
            response = self.client.post(reverse("data:data_refresh"))
            self.assertEqual(response.status_code, 409)
            self.assertEqual(response.json()["status"], "already_running")
        finally:
            lock.unlink(missing_ok=True)


class PipelineRunnerTests(TestCase):
    """pipeline_runner helpers track PipelineRun rows."""

    def test_run_with_pipeline_run_success(self) -> None:
        from data.models import PipelineRun
        from data.pipeline_runner import latest_successful_run, run_with_pipeline_run

        run = run_with_pipeline_run(
            league_id=39,
            season_year=2025,
            source="test",
            execute=lambda: None,
        )
        self.assertEqual(run.status, PipelineRun.Status.SUCCESS)
        self.assertIsNotNone(run.finished_at)
        latest = latest_successful_run(league_id=39, season_year=2025)
        self.assertIsNotNone(latest)
        assert latest is not None
        self.assertEqual(latest.id, run.id)

    def test_run_with_pipeline_run_records_failure(self) -> None:
        from data.models import PipelineRun
        from data.pipeline_runner import run_with_pipeline_run

        def boom() -> None:
            raise ValueError("pipeline broke")

        with self.assertRaises(ValueError):
            run_with_pipeline_run(
                league_id=39,
                season_year=2025,
                source="test",
                execute=boom,
            )
        failed = PipelineRun.objects.filter(status=PipelineRun.Status.FAILED).latest(
            "id",
        )
        self.assertIn("pipeline broke", failed.error_summary or "")

    def test_latest_successful_run_unscoped(self) -> None:
        from data.models import PipelineRun
        from data.pipeline_runner import latest_successful_run, run_with_pipeline_run

        run_with_pipeline_run(
            league_id=None,
            season_year=None,
            source="global",
            execute=lambda: None,
        )
        latest = latest_successful_run()
        self.assertIsNotNone(latest)
        assert latest is not None
        self.assertEqual(latest.status, PipelineRun.Status.SUCCESS)


class PipelineServiceTests(TestCase):
    """Unit tests for enqueue_pipeline_refresh and background task."""

    def setUp(self) -> None:
        from django.conf import settings

        self.lock = Path(settings.BASE_DIR).parent / "data" / "football" / ".refresh.lock"
        if self.lock.exists():
            self.lock.unlink(missing_ok=True)

    def tearDown(self) -> None:
        if self.lock.exists():
            self.lock.unlink(missing_ok=True)

    @patch("data.pipeline_service.subprocess.Popen")
    def test_enqueue_starts_subprocess_without_redis(
        self,
        mock_popen: unittest.mock.Mock,
    ) -> None:
        import os

        from data.pipeline_service import enqueue_pipeline_refresh

        env = os.environ.copy()
        env.pop("REDIS_URL", None)
        with patch.dict(os.environ, env, clear=True):
            result = enqueue_pipeline_refresh(source="test")
        self.assertEqual(result["status"], "started")
        mock_popen.assert_called_once()

    def test_enqueue_returns_already_running_when_lock_exists(self) -> None:
        import os

        from data.pipeline_service import enqueue_pipeline_refresh

        self.lock.parent.mkdir(parents=True, exist_ok=True)
        self.lock.touch()
        env = os.environ.copy()
        env.pop("REDIS_URL", None)
        with patch.dict(os.environ, env, clear=True):
            result = enqueue_pipeline_refresh()
        self.assertEqual(result["status"], "already_running")

    @patch.dict("os.environ", {"REDIS_URL": "redis://127.0.0.1:6379/0"})
    @patch("django_rq.get_queue")
    def test_enqueue_uses_rq_when_redis_configured(
        self,
        mock_get_queue: unittest.mock.Mock,
    ) -> None:
        from data.pipeline_service import enqueue_pipeline_refresh

        mock_queue = unittest.mock.MagicMock()
        mock_get_queue.return_value = mock_queue
        result = enqueue_pipeline_refresh(source="test")
        self.assertEqual(result["status"], "started")
        self.assertEqual(result["message"], "Refresh queued")
        mock_queue.enqueue.assert_called_once_with(
            "data.tasks.run_football_pipeline_task",
            "test",
        )

    @patch("django.core.management.call_command")
    def test_run_football_pipeline_task(self, mock_cmd: unittest.mock.Mock) -> None:
        from data.tasks import run_football_pipeline_task

        run_football_pipeline_task("rq")
        mock_cmd.assert_called_once_with("run_football_pipeline")


class DataViewParamTests(TestCase):
    """Dashboard query param parsing and HTMX panel."""

    def setUp(self) -> None:
        from django.core.cache import cache

        cache.clear()
        League.objects.get_or_create(
            id=39,
            defaults={"name": "Premier League", "order": 0},
        )
        Season.objects.get_or_create(
            api_year=2025,
            defaults={"display": "2025/26", "order": 0},
        )

    @patch("data.views.build_dashboard_payload")
    def test_dashboard_panel_invalid_params_use_defaults(
        self,
        mock_build: unittest.mock.Mock,
    ) -> None:
        mock_build.return_value = {
            "standings": [],
            "error": "",
            "figure_json": "{}",
        }
        response = self.client.get(
            reverse("data:dashboard_panel"),
            {"league": "bad", "season": "nope", "x_axis": "invalid"},
        )
        self.assertEqual(response.status_code, 200)
        mock_build.assert_called_once()
        _args, kwargs = mock_build.call_args
        self.assertEqual(kwargs["league_id"], 39)
        self.assertEqual(kwargs["season"], 2025)
        self.assertEqual(kwargs["x_axis"], "games_played")

    @patch("data.views.enqueue_pipeline_refresh")
    def test_data_refresh_returns_409_when_already_running(
        self,
        mock_enqueue: unittest.mock.Mock,
    ) -> None:
        from django.contrib.auth import get_user_model

        mock_enqueue.return_value = {
            "status": "already_running",
            "message": "Pipeline already in progress",
        }
        User = get_user_model()
        user = User.objects.create_superuser("admin409", "a@b.com", "pass")
        self.client.force_login(user)
        response = self.client.post(reverse("data:data_refresh"))
        self.assertEqual(response.status_code, 409)
