"""
Unit tests for the football package (ingest, transform, processed, build logic).

Run from repo root: uv run pytest tests/test_football.py -v
"""

import io
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

from football.crests import (
    CREST_KEY_TEMPLATE,
    sync_crests_from_response,
)
from football.ingest import (
    ensure_bucket,
    fetch_fixtures,
    get_client,
    upload_raw,
)
from football.processed import (
    load_processed_parquet_from_minio,
    upload_processed_parquet,
)
from football.transform import clean, flatten_fixtures, run_transform


class TestCrests:
    """sync_crests_from_response and key template."""

    def test_crest_key_template(self) -> None:
        assert CREST_KEY_TEMPLATE.format(team_id=42) == "crests/team_42.png"

    def test_sync_crests_empty_response(self) -> None:
        sync_crests_from_response({})
        sync_crests_from_response({"response": []})

    @patch("football.crests.get_client")
    def test_sync_crests_skips_when_object_exists(
        self,
        mock_get_client: MagicMock,
    ) -> None:
        mock_client = MagicMock()
        mock_client.stat_object.return_value = None  # exists
        mock_get_client.return_value = mock_client
        raw = {
            "response": [
                {
                    "teams": {
                        "home": {"id": 1, "logo": "https://example.com/1.png"},
                        "away": {"id": 2, "logo": "https://example.com/2.png"},
                    },
                },
            ],
        }
        sync_crests_from_response(raw, bucket="b", client=mock_client)
        mock_client.stat_object.assert_called()
        mock_client.put_object.assert_not_called()

    def test_object_exists_returns_false_when_stat_raises(self) -> None:
        from football.crests import _object_exists

        mock_client = MagicMock()
        mock_client.stat_object.side_effect = Exception("Not found")
        assert _object_exists(mock_client, "b", "k") is False

    @patch("football.crests.requests.get")
    def test_ensure_crest_downloads_and_uploads_when_missing(
        self,
        mock_get: MagicMock,
    ) -> None:
        from football.crests import _ensure_crest

        mock_client = MagicMock()
        mock_client.stat_object.side_effect = Exception("missing")
        mock_resp = MagicMock()
        mock_resp.content = b"fake-png"
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp
        _ensure_crest(mock_client, "bucket", 10, "https://example.com/logo.png")
        mock_get.assert_called_once_with("https://example.com/logo.png", timeout=10)
        mock_client.put_object.assert_called_once()

    def test_ensure_crest_skips_invalid_url(self) -> None:
        from football.crests import _ensure_crest

        mock_client = MagicMock()
        mock_client.stat_object.side_effect = Exception("missing")
        _ensure_crest(mock_client, "bucket", 10, "")
        _ensure_crest(mock_client, "bucket", 11, "not-http://x.com")
        mock_client.put_object.assert_not_called()

    @patch("football.crests.requests.get")
    def test_ensure_crest_handles_request_failure(self, mock_get: MagicMock) -> None:
        from football.crests import _ensure_crest

        mock_client = MagicMock()
        mock_client.stat_object.side_effect = Exception("missing")
        mock_get.side_effect = Exception("timeout")
        _ensure_crest(mock_client, "bucket", 10, "https://example.com/logo.png")
        mock_client.put_object.assert_not_called()


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

    @patch("football.ingest.get_client")
    @patch("football.ingest.fetch_fixtures")
    def test_run_ingest_calls_fetch_upload_and_crests(
        self,
        mock_fetch: MagicMock,
        mock_get_client: MagicMock,
    ) -> None:
        mock_fetch.return_value = {"response": []}
        mock_client = MagicMock()
        mock_client.bucket_exists.return_value = True
        mock_get_client.return_value = mock_client
        with patch.dict("os.environ", {"MINIO_BUCKET": "b"}, clear=False):
            from football.ingest import run_ingest

            key = run_ingest(league=39, season=2025, bucket="b")
        assert key == "raw/league_39_season_2025.json"
        mock_fetch.assert_called_once_with(league=39, season=2025)
        mock_client.put_object.assert_called_once()

    def test_upload_raw_puts_correct_key(self) -> None:
        mock_client = MagicMock()
        key = upload_raw(
            mock_client,
            "b",
            {"response": [{"id": 1}]},
            league=40,
            season=2024,
        )
        assert key == "raw/league_40_season_2024.json"
        mock_client.put_object.assert_called_once()
        call_kw = mock_client.put_object.call_args[1]
        assert call_kw["length"] > 0

    @patch.dict(
        "os.environ",
        {
            "MINIO_ENDPOINT": "localhost",
            "MINIO_ACCESS_KEY": "k",
            "MINIO_SECRET_KEY": "s",
        },
    )
    def test_get_client_returns_minio(self) -> None:
        client = get_client()
        assert client is not None


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


class TestPipeline:
    """football.pipeline: run_pipeline, load_csv_to_duckdb, _run."""

    def test_run_pipeline_returns_1_when_lock_exists(self, tmp_path: Path) -> None:
        from football import pipeline as pl

        lock = tmp_path / "lock"
        lock.touch()
        with patch.object(pl, "LOCK_FILE", lock):
            with patch.object(pl, "DATA_DIR", tmp_path):
                rc = pl.run_pipeline(league=39, season=2025)
        assert rc == 1

    @patch("football.pipeline._run")
    @patch("football.pipeline._load_to_mariadb_and_minio")
    @patch("football.build_views.run")
    @patch("football.pipeline.load_csv_to_duckdb")
    @patch("football.transform.run_transform")
    @patch("football.ingest.run_ingest")
    def test_run_pipeline_calls_soda_when_contract_files_exist(
        self,
        mock_ingest: MagicMock,
        mock_transform: MagicMock,
        mock_load_csv: MagicMock,
        mock_build: MagicMock,
        mock_load_mariadb: MagicMock,
        mock_run: MagicMock,
        tmp_path: Path,
    ) -> None:
        from football import pipeline as pl

        (tmp_path / "football" / "soda").mkdir(parents=True)
        (tmp_path / "football" / "soda" / "ds_config.yml").write_text("x")
        (tmp_path / "football" / "soda" / "contracts").mkdir(parents=True)
        (tmp_path / "football" / "soda" / "contracts" / "fixtures.yaml").write_text("y")
        mock_transform.return_value = pd.DataFrame([{"fixture_id": 1}])
        mock_run.return_value = 0
        with patch.object(pl, "LOCK_FILE", tmp_path / "lock"):
            with patch.object(pl, "DATA_DIR", tmp_path):
                with patch.object(pl, "REPO_ROOT", tmp_path):
                    rc = pl.run_pipeline(league=39, season=2025, skip_ingest=True)
        assert rc == 0
        assert mock_run.called
        call_args = [c[0][0] for c in mock_run.call_args_list if c[0]]
        assert any("soda" in str(a) for a in call_args)

    @patch("football.pipeline._load_to_mariadb_and_minio")
    @patch("football.build_views.run")
    @patch("football.pipeline.load_csv_to_duckdb")
    @patch("football.transform.run_transform")
    @patch("football.ingest.run_ingest")
    def test_run_pipeline_skip_ingest_calls_transform_and_load(
        self,
        mock_ingest: MagicMock,
        mock_transform: MagicMock,
        mock_load_csv: MagicMock,
        mock_build: MagicMock,
        mock_load_mariadb: MagicMock,
        tmp_path: Path,
    ) -> None:
        from football import pipeline as pl

        mock_transform.return_value = pd.DataFrame([{"fixture_id": 1}])
        with patch.object(pl, "LOCK_FILE", tmp_path / "lock"):
            with patch.object(pl, "DATA_DIR", tmp_path):
                with patch.object(pl, "_run", return_value=0):
                    with patch.object(pl, "REPO_ROOT", tmp_path):
                        rc = pl.run_pipeline(
                            league=39,
                            season=2025,
                            skip_ingest=True,
                        )
        assert rc == 0
        mock_ingest.assert_not_called()
        mock_transform.assert_called_once()
        mock_load_csv.assert_called_once()
        mock_build.assert_called_once()
        mock_load_mariadb.assert_called_once()

    def test_load_csv_to_duckdb_no_csv(self, tmp_path: Path) -> None:
        from football.pipeline import load_csv_to_duckdb

        with patch("football.pipeline.DATA_DIR", tmp_path):
            load_csv_to_duckdb()
        assert not (tmp_path / "football.duckdb").exists()

    def test_load_csv_to_duckdb_with_csv(self, tmp_path: Path) -> None:
        import duckdb

        from football.pipeline import load_csv_to_duckdb

        csv_path = tmp_path / "fixtures.csv"
        csv_path.write_text("fixture_id,date\n1,2025-01-15\n")
        with patch("football.pipeline.DATA_DIR", tmp_path):
            load_csv_to_duckdb()
        db_path = tmp_path / "football.duckdb"
        assert db_path.exists()
        con = duckdb.connect(str(db_path))
        out = con.execute("SELECT COUNT(*) FROM fixtures").fetchone()
        assert out[0] == 1
        con.close()

    def test_run_returns_exit_code(self) -> None:
        from football.pipeline import _run

        rc = _run(["true"])
        assert rc == 0

    @patch("football.pipeline._load_to_mariadb_and_minio")
    @patch("football.build_views.run")
    @patch("football.pipeline.load_csv_to_duckdb")
    @patch("football.transform.run_transform")
    @patch("football.ingest.run_ingest")
    def test_run_pipeline_skips_load_when_df_empty(
        self,
        mock_ingest: MagicMock,
        mock_transform: MagicMock,
        mock_load_csv: MagicMock,
        mock_build: MagicMock,
        mock_load_mariadb: MagicMock,
        tmp_path: Path,
    ) -> None:
        from football import pipeline as pl

        mock_transform.return_value = pd.DataFrame()
        with patch.object(pl, "LOCK_FILE", tmp_path / "lock"):
            with patch.object(pl, "DATA_DIR", tmp_path):
                with patch.object(pl, "_run", return_value=0):
                    with patch.object(pl, "REPO_ROOT", tmp_path):
                        rc = pl.run_pipeline(league=39, season=2025, skip_ingest=True)
        assert rc == 0
        mock_load_mariadb.assert_not_called()


class TestBuildViews:
    """build_views creates DuckDB views. Uses temp fixtures table."""

    def test_build_views_warns_when_db_missing(self, tmp_path: Path) -> None:
        with patch("football.build_views.DB_PATH", tmp_path / "nonexistent.duckdb"):
            from football.build_views import run

            run()
        assert not (tmp_path / "nonexistent.duckdb").exists()

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
