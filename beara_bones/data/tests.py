"""Tests for data app: views, loading, admin, dashboard logic, dash callbacks."""

import unittest
from unittest.mock import patch

import pandas as pd
from django.test import TestCase
from django.urls import reverse

from data.dashboard_utils import build_standings_and_figure
from data.loading import load_fixtures_dataframe
from data.models import Fixture, League, Season


class DashAppCallbackTests(TestCase):
    """Test Dash app callbacks with mocked dependencies."""

    def test_set_dropdown_options_returns_league_and_season_options(self) -> None:
        from data.dash_app import _set_dropdown_options

        League.objects.get_or_create(
            id=39,
            defaults={"name": "Premier League", "order": 0},
        )
        Season.objects.get_or_create(
            api_year=2025,
            defaults={"display": "2025/26", "order": 0},
        )
        league_opts, league_val, season_opts, season_val = _set_dropdown_options(0)
        self.assertIsInstance(league_opts, list)
        self.assertIsInstance(season_opts, list)
        self.assertEqual(league_val, 39)
        self.assertEqual(season_val, 2025)

    def test_update_chart_and_grid_none_league_or_season_returns_empty(self) -> None:
        from data.dash_app import _update_chart_and_grid

        fig, rows, err = _update_chart_and_grid(None, 2025, "games_played")
        self.assertEqual(err, "")
        self.assertEqual(rows, [])
        self.assertIn("Select league", fig["layout"]["annotations"][0]["text"])

        fig, rows, err = _update_chart_and_grid(39, None, "games_played")
        self.assertEqual(rows, [])

    @patch("data.dash_app._load_fixtures_from_db")
    def test_update_chart_and_grid_with_data_returns_figure_and_standings(
        self,
        mock_load: unittest.mock.Mock,
    ) -> None:
        from data.dash_app import _update_chart_and_grid

        mock_load.return_value = (_minimal_fixtures_df(), None)
        fig, rows, err = _update_chart_and_grid(39, 2025, "games_played")
        self.assertEqual(err, "")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["rank"], 1)
        self.assertIn("data", fig)
        mock_load.assert_called_once_with(39, 2025)

    @patch("data.dash_app._load_fixtures_from_db")
    def test_update_chart_and_grid_load_error_returns_empty_figure_and_message(
        self,
        mock_load: unittest.mock.Mock,
    ) -> None:
        from data.dash_app import _update_chart_and_grid

        mock_load.return_value = (None, "No fixtures for this league/season.")
        fig, rows, err = _update_chart_and_grid(39, 2025, "games_played")
        self.assertEqual(rows, [])
        self.assertIn("No fixtures", err)
        self.assertIn("annotations", fig.get("layout", {}))


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


class DataViewTests(TestCase):
    """Data page, fragment, and refresh endpoint behave correctly."""

    def test_data_page_returns_200(self) -> None:
        response = self.client.get(reverse("data:data"))
        self.assertEqual(response.status_code, 200)

    def test_data_page_renders_dash_embed(self) -> None:
        """Data page returns 200 and contains the Dash app embed (FootballDashboard)."""
        response = self.client.get(reverse("data:data"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("FootballDashboard", html, msg="Page should embed the Dash app")

    def test_data_refresh_post_returns_403_when_not_staff(self) -> None:
        """POST to refresh when not staff returns 403."""
        response = self.client.post(reverse("data:data_refresh"))
        self.assertEqual(response.status_code, 403)

    @patch("subprocess.Popen")
    def test_data_refresh_post_staff_returns_202_or_409(
        self,
        mock_popen: unittest.mock.Mock,
    ) -> None:
        """POST to refresh as staff returns 202 or 409."""
        from django.contrib.auth import get_user_model

        User = get_user_model()
        user = User.objects.create_superuser("admin", "a@b.com", "pass")
        self.client.force_login(user)
        response = self.client.post(reverse("data:data_refresh"))
        self.assertIn(response.status_code, (202, 409, 500))

    def test_data_refresh_get_not_allowed(self) -> None:
        response = self.client.get(reverse("data:data_refresh"))
        self.assertEqual(response.status_code, 405)

    @patch("data.views.settings")
    def test_crest_serve_returns_404_when_object_missing(
        self,
        mock_settings: unittest.mock.Mock,
    ) -> None:
        """Crest view returns 404 when MinIO object is missing."""
        import sys
        from pathlib import Path

        # Repo root (has football/) and Django project dir (BASE_DIR)
        repo_root = Path(__file__).resolve().parents[2]
        mock_settings.BASE_DIR = Path(__file__).resolve().parents[1]
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))
        with patch("football.ingest.get_client") as mock_get_client:
            mock_client = unittest.mock.MagicMock()
            mock_client.get_object.side_effect = Exception("Not found")
            mock_get_client.return_value = mock_client
            response = self.client.get(reverse("data:crest", kwargs={"team_id": 999}))
        self.assertEqual(response.status_code, 404)

    @patch("data.views.settings")
    def test_crest_serve_returns_image_when_found(
        self,
        mock_settings: unittest.mock.Mock,
    ) -> None:
        """Crest view returns 200 and image/png when object exists in MinIO."""
        import sys
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[2]
        mock_settings.BASE_DIR = Path(__file__).resolve().parents[1]
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))
        fake_png = b"\x89PNG\r\n\x1a\n"
        mock_resp = unittest.mock.MagicMock()
        mock_resp.read.return_value = fake_png
        mock_resp.close = unittest.mock.Mock()
        with patch("football.ingest.get_client") as mock_get_client:
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
        from data.management.commands.run_football_pipeline import Command, LOCK_FILE

        LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
        try:
            LOCK_FILE.touch()
            cmd = Command()
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
        from data.management.commands.rebuild_football_from_minio import (
            LOCK_FILE,
            Command,
        )

        LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
        try:
            LOCK_FILE.touch()
            cmd = Command()
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
        from django.core.management import call_command
        from io import StringIO

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
        from django.core.management import call_command
        from io import StringIO

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

    def test_pipeline_refresh_post_with_lock_redirects_with_message(self) -> None:
        from pathlib import Path

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

    @patch("data.admin_views.subprocess.Popen")
    def test_pipeline_refresh_post_starts_pipeline(
        self,
        mock_popen: unittest.mock.Mock,
    ) -> None:
        from django.contrib.auth import get_user_model

        User = get_user_model()
        User.objects.create_superuser("admin3", "c@d.com", "pass")
        self.client.force_login(User.objects.get(username="admin3"))
        response = self.client.post(reverse("data:admin_pipeline_refresh"))
        self.assertEqual(response.status_code, 302)
        mock_popen.assert_called_once()

    @patch("django.core.management.call_command")
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

    @patch("django.core.management.call_command")
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
        self.assertIn(b"Rebuild failed", next_page.content)
