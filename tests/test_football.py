"""
Unit tests for the football package (ingest, transform, processed, build logic).

Run from repo root: uv run pytest tests/test_football.py -v
"""

import io
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

from football.ingest import ensure_bucket, fetch_fixtures, upload_raw
from football.processed import (
    load_processed_parquet_from_minio,
    upload_processed_parquet,
)
from football.transform import clean, flatten_fixtures, run_transform


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


class TestIngest:
    """ingest: ensure_bucket, upload_raw, fetch_fixtures with mocks."""

    def test_ensure_bucket_creates_when_missing(self) -> None:
        mock_client = MagicMock()
        mock_client.bucket_exists.return_value = False
        ensure_bucket(mock_client, "my-bucket")
        mock_client.make_bucket.assert_called_once_with("my-bucket")

    def test_ensure_bucket_skips_when_exists(self) -> None:
        mock_client = MagicMock()
        mock_client.bucket_exists.return_value = True
        ensure_bucket(mock_client, "my-bucket")
        mock_client.make_bucket.assert_not_called()

    def test_upload_raw(self) -> None:
        mock_client = MagicMock()
        data: dict[str, list[object]] = {"response": []}
        key = upload_raw(mock_client, "bucket", data, league=39, season=2025)
        assert key == "raw/league_39_season_2025.json"
        mock_client.put_object.assert_called_once()

    @patch("football.ingest.requests.get")
    def test_fetch_fixtures(self, mock_get: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"response": [{"fixture": {"id": 1}}]}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp
        with patch.dict(
            "os.environ",
            {"RAPIDAPI_KEY": "test-key"},  # pragma: allowlist secret
            clear=False,
        ):
            result = fetch_fixtures(league=39, season=2025)
        assert "response" in result
        assert len(result["response"]) == 1


class TestRunTransform:
    """run_transform loads from MinIO, flattens, cleans. Uses mocked MinIO."""

    @patch("football.transform.load_raw_from_minio")
    def test_run_transform_returns_dataframe(
        self,
        mock_load: MagicMock,
        tmp_path: Path,
    ) -> None:
        raw = {
            "response": [
                {
                    "fixture": {"id": 10, "date": "2025-01-15T15:00:00+00:00"},
                    "league": {"id": 39},
                    "teams": {"home": {"name": "A"}, "away": {"name": "B"}},
                    "goals": {"home": 1, "away": 0},
                },
            ],
        }
        mock_load.return_value = raw
        df = run_transform(
            league=39,
            season=2025,
            output_dir=tmp_path,
            write_files=True,
        )
        assert len(df) == 1
        assert df["fixture_id"].iloc[0] == 10
        assert (tmp_path / "fixtures.csv").exists()


class TestProcessed:
    """upload_processed_parquet and load_processed_parquet_from_minio with mocked MinIO."""

    @patch("football.processed.get_client")
    def test_upload_processed_parquet(self, mock_get_client: MagicMock) -> None:
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        df = pd.DataFrame([{"fixture_id": 1, "date": "2025-01-15"}])
        key = upload_processed_parquet(df, league=39, season=2025, bucket="test-bucket")
        assert key == "processed/league_39_season_2025.parquet"
        mock_client.put_object.assert_called_once()

    @patch("football.processed.get_client")
    def test_load_processed_parquet_from_minio_not_found(
        self,
        mock_get_client: MagicMock,
    ) -> None:
        mock_client = MagicMock()
        mock_client.get_object.side_effect = Exception("Not found")
        mock_get_client.return_value = mock_client
        result = load_processed_parquet_from_minio(39, 2025, bucket="test-bucket")
        assert result is None

    @patch("football.processed.get_client")
    def test_load_processed_parquet_from_minio_success(
        self,
        mock_get_client: MagicMock,
    ) -> None:
        df_expected = pd.DataFrame([{"fixture_id": 1}])
        buf = io.BytesIO()
        df_expected.to_parquet(buf, index=False)
        buf.seek(0)
        mock_resp = MagicMock()
        mock_resp.read.return_value = buf.getvalue()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = lambda s, *a: None
        mock_client = MagicMock()
        mock_client.get_object.return_value = mock_resp
        mock_get_client.return_value = mock_client
        result = load_processed_parquet_from_minio(39, 2025, bucket="test-bucket")
        assert result is not None
        assert len(result) == 1
        assert result["fixture_id"].iloc[0] == 1


class TestBuildViews:
    """build_views creates DuckDB views. Uses temp fixtures table."""

    def test_build_views_creates_views(self, tmp_path: Path) -> None:
        import duckdb

        db_path = tmp_path / "football.duckdb"
        con = duckdb.connect(str(db_path))
        con.execute(
            """
            CREATE TABLE fixtures (
                fixture_id BIGINT, date DATE, timestamp BIGINT, venue_id INT,
                venue_name VARCHAR, status_short VARCHAR, status_long VARCHAR,
                league_id INT, league_name VARCHAR, league_season INT, league_round VARCHAR,
                home_team_id INT, home_team_name VARCHAR, away_team_id INT, away_team_name VARCHAR,
                goals_home INT, goals_away INT
            )
            """,
        )
        con.execute(
            "INSERT INTO fixtures VALUES (1, '2025-01-15', 0, 1, '', 'FT', '', 39, '', 2025, '', 1, 'A', 2, 'B', 1, 0)",
        )
        con.close()
        with patch("football.build_views.DB_PATH", db_path):
            from football.build_views import run

            run()
        con = duckdb.connect(str(db_path))
        out = con.execute("SELECT COUNT(*) FROM main.fct_fixtures").fetchone()
        assert out[0] == 1
        con.close()
