"""
Unit tests for the football package (ingest, transform, build logic).

Run from repo root: uv run pytest tests/test_football.py -v
"""

import pandas as pd

from football.transform import clean, flatten_fixtures


class TestFlattenFixtures:
    """flatten_fixtures turns API response into a DataFrame."""

    def test_empty_response(self) -> None:
        out = flatten_fixtures({})
        assert out.empty
        assert isinstance(out, pd.DataFrame)

    def test_response_without_response_key(self) -> None:
        out = flatten_fixtures({"get": "fixtures"})
        assert out.empty

    def test_single_fixture(self) -> None:
        raw = {
            "response": [
                {
                    "fixture": {
                        "id": 1,
                        "date": "2025-01-15T15:00:00+00:00",
                        "timestamp": 1736953200,
                    },
                    "league": {"id": 39, "name": "Premier League", "season": 2025},
                    "teams": {
                        "home": {"id": 1, "name": "TeamA"},
                        "away": {"id": 2, "name": "TeamB"},
                    },
                    "goals": {"home": 2, "away": 1},
                },
            ],
        }
        df = flatten_fixtures(raw)
        assert len(df) == 1
        assert df["fixture_id"].iloc[0] == 1
        assert df["home_team_name"].iloc[0] == "TeamA"
        assert df["away_team_name"].iloc[0] == "TeamB"
        assert df["goals_home"].iloc[0] == 2
        assert df["goals_away"].iloc[0] == 1

    def test_missing_optional_fields(self) -> None:
        raw = {
            "response": [
                {"fixture": {"id": 2}, "league": {}, "teams": {}, "goals": {}},
            ],
        }
        df = flatten_fixtures(raw)
        assert len(df) == 1
        assert df["fixture_id"].iloc[0] == 2
        assert (
            pd.isna(df["home_team_name"].iloc[0])
            or df["home_team_name"].iloc[0] is None
        )


class TestClean:
    """clean() drops duplicates and null fixture_id."""

    def test_empty_dataframe(self) -> None:
        out = clean(pd.DataFrame())
        assert out.empty

    def test_drops_null_fixture_id(self) -> None:
        df = pd.DataFrame([{"fixture_id": 1}, {"fixture_id": None}, {"fixture_id": 2}])
        out = clean(df)
        assert len(out) == 2
        assert out["fixture_id"].tolist() == [1, 2]

    def test_drops_duplicates(self) -> None:
        df = pd.DataFrame([{"fixture_id": 1}, {"fixture_id": 1}, {"fixture_id": 2}])
        out = clean(df)
        assert len(out) == 2
        assert out["fixture_id"].tolist() == [1, 2]
