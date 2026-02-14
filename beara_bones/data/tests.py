"""Tests for data app: views (page, fragment, refresh), dashboard logic, and fragment content."""
import unittest
from unittest.mock import patch

import pandas as pd
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from data.views import _build_dashboard_fragment, data_page


def _minimal_fixtures_df():
    """One fixture: TeamA 2-1 TeamB (home win)."""
    return pd.DataFrame([
        {
            "fixture_date": pd.Timestamp("2025-01-15"),
            "home_team_name": "TeamA",
            "away_team_name": "TeamB",
            "goals_home": 2,
            "goals_away": 1,
            "result": "H",
        },
    ])


class DataViewTests(TestCase):
    """Data page, fragment, and refresh endpoint behave correctly."""

    def test_data_page_returns_200(self) -> None:
        response = self.client.get(reverse("data:data"))
        self.assertEqual(response.status_code, 200)

    def test_data_page_context(self) -> None:
        response = self.client.get(reverse("data:data"))
        self.assertTrue(response.context["loading"])
        self.assertEqual(response.context["current_league_name"], "Premier League")
        self.assertEqual(response.context["current_season"], 2025)

    def test_data_fragment_returns_200(self) -> None:
        response = self.client.get(reverse("data:data_fragment"))
        self.assertEqual(response.status_code, 200)

    def test_data_fragment_returns_html_content(self) -> None:
        """Fragment returns meaningful HTML: either league table or error/help message."""
        response = self.client.get(reverse("data:data_fragment"))
        html = response.content.decode()
        has_table = "League table" in html
        has_error_help = "make pipeline" in html or "alert" in html
        self.assertTrue(has_table or has_error_help, msg="Fragment should show table or error/help")

    @patch("data.views._load_fixtures_for_dashboard")
    def test_data_fragment_with_mock_data_returns_chart_and_standings(self, mock_load: unittest.mock.Mock) -> None:
        """When loader returns minimal data, fragment HTML contains plotly and standings."""
        cache.clear()
        mock_load.return_value = (_minimal_fixtures_df(), None)
        response = self.client.get(reverse("data:data_fragment"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("League table", html)
        self.assertIn("TeamA", html)
        self.assertIn("TeamB", html)
        self.assertIn("plotly", html.lower(), msg="Chart should render Plotly div/script")

    @patch("subprocess.Popen")
    def test_data_refresh_post_allowed(self, mock_popen: unittest.mock.Mock) -> None:
        """POST to refresh returns 202/409/500; pipeline is not actually run."""
        response = self.client.post(reverse("data:data_refresh"))
        self.assertIn(response.status_code, (202, 409, 500))

    def test_data_refresh_get_not_allowed(self) -> None:
        response = self.client.get(reverse("data:data_refresh"))
        self.assertEqual(response.status_code, 405)


class DashboardFragmentUnitTests(TestCase):
    """Unit tests for _build_dashboard_fragment with mocked data loading."""

    @patch("data.views._load_fixtures_for_dashboard")
    def test_build_fragment_no_data_returns_error(self, mock_load: unittest.mock.Mock) -> None:
        mock_load.return_value = (None, "No fixtures data.")
        out = _build_dashboard_fragment()
        self.assertEqual(out["error"], "No fixtures data.")
        self.assertEqual(out["charts"], [])
        self.assertEqual(out["standings"], [])

    @patch("data.views._load_fixtures_for_dashboard")
    def test_build_fragment_empty_dataframe_returns_error(self, mock_load: unittest.mock.Mock) -> None:
        mock_load.return_value = (pd.DataFrame(), None)
        out = _build_dashboard_fragment()
        self.assertIn("error", out)
        self.assertEqual(out["charts"], [])
        self.assertEqual(out["standings"], [])

    @patch("data.views._load_fixtures_for_dashboard")
    def test_build_fragment_with_minimal_data_returns_chart_and_standings(self, mock_load: unittest.mock.Mock) -> None:
        mock_load.return_value = (_minimal_fixtures_df(), None)
        out = _build_dashboard_fragment()
        self.assertIsNone(out.get("error"))
        self.assertEqual(len(out["charts"]), 1)
        self.assertIn("plotly", out["charts"][0].lower())
        self.assertEqual(len(out["standings"]), 2)
        teams = {r["team"] for r in out["standings"]}
        self.assertEqual(teams, {"TeamA", "TeamB"})
        team_a = next(r for r in out["standings"] if r["team"] == "TeamA")
        self.assertEqual(team_a["Pts"], 3)
        self.assertEqual(team_a["W"], 1)
        team_b = next(r for r in out["standings"] if r["team"] == "TeamB")
        self.assertEqual(team_b["Pts"], 0)
        self.assertEqual(team_b["L"], 1)


# Ingest command tests require football on PYTHONPATH (run tests from repo root with
# PYTHONPATH=. or use: uv run pytest tests/test_football.py). Django view/unit tests above
# cover the data app fully.
