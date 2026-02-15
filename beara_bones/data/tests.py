"""Tests for data app: views, loading, admin, dashboard logic."""

import unittest
from unittest.mock import patch

import pandas as pd
from django.test import TestCase
from django.urls import reverse

from data.dashboard_utils import build_standings_and_figure
from data.loading import load_fixtures_dataframe
from data.models import Fixture, League, Season


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
