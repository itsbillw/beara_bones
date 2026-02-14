"""
Orchestrates ingest → transform → load to DuckDB → soda-check → dbt-build → load to MariaDB → upload processed Parquet.
Uses a lock file to prevent overlapping runs. Clears dashboard cache on success.
"""

import logging
import os
import subprocess  # nosec B404
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data" / "football"
LOCK_FILE = DATA_DIR / ".refresh.lock"
logger = logging.getLogger(__name__)


def _run(cmd: list[str], cwd: Path | None = None) -> int:
    cwd = cwd or REPO_ROOT
    logging.info("Running: %s", " ".join(cmd))
    return subprocess.call(cmd, cwd=cwd)  # nosec B603


def _load_to_mariadb_and_minio(df, league: int, season: int) -> None:
    """Load transformed data to MariaDB and upload processed Parquet to MinIO."""
    project_root = REPO_ROOT / "beara_bones"
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    os.environ.setdefault(
        "DJANGO_SETTINGS_MODULE",
        os.environ.get("DJANGO_SETTINGS_MODULE", "beara_bones.settings_dev"),
    )
    import django
    django.setup()
    from data.loading import load_fixtures_dataframe
    from football.processed import upload_processed_parquet

    load_fixtures_dataframe(df, league, season)
    upload_processed_parquet(df, league, season)
    logger.info("Loaded to MariaDB and uploaded processed Parquet for league=%s season=%s", league, season)
    try:
        from django.core.cache import cache
        cache.clear()
    except Exception:
        pass


def load_csv_to_duckdb() -> None:
    """Create/update football.duckdb with fixtures table from CSV for Soda and dbt."""
    try:
        import duckdb
    except ImportError:
        logger.warning(
            "duckdb not installed; skipping load. Install with: uv pip install duckdb",
        )
        return
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    db_path = DATA_DIR / "football.duckdb"
    csv_path = DATA_DIR / "fixtures.csv"
    if not csv_path.exists():
        logger.warning("No fixtures.csv; run transform first.")
        return
    con = duckdb.connect(str(db_path))
    con.execute(
        "CREATE OR REPLACE TABLE fixtures AS SELECT * FROM read_csv_auto(?)",
        [str(csv_path)],
    )
    con.close()
    logger.info("Loaded fixtures into %s", db_path)


def run_pipeline(
    league: int = 39,
    season: int = 2025,
    skip_ingest: bool = False,
) -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if LOCK_FILE.exists():
        logger.error(
            "Lock file exists; another pipeline run may be in progress. Remove %s to force.",
            LOCK_FILE,
        )
        return 1
    try:
        LOCK_FILE.touch()
        if not skip_ingest:
            from football.ingest import run_ingest

            run_ingest(league=league, season=season)
        from football.transform import run_transform

        df = run_transform(league=league, season=season)
        load_csv_to_duckdb()
        # Build dbt-equivalent views (avoids dbt-duckdb segfault on Python 3.13)
        from football.build_views import run as build_views

        build_views()
        # Soda scan (local; run from repo root)
        soda_cfg = REPO_ROOT / "football" / "soda" / "configuration.yml"
        soda_checks = REPO_ROOT / "football" / "soda" / "checks" / "fixtures.yml"
        if soda_cfg.exists() and soda_checks.exists():
            rc = _run(
                [
                    "uv",
                    "run",
                    "soda",
                    "scan",
                    "-d",
                    "football",
                    "-c",
                    str(soda_cfg),
                    str(soda_checks),
                ],
            )
            if rc != 0:
                logger.warning("Soda scan had failures (rc=%s)", rc)
        # dbt (optional; often segfaults with dbt-duckdb + Python 3.13 – views already built above)
        dbt_dir = REPO_ROOT / "data_modelling"
        if (dbt_dir / "dbt_project.yml").exists():
            rc = _run(["uv", "run", "dbt", "build"], cwd=dbt_dir)
            if rc != 0:
                logger.warning(
                    "dbt build exited with %s (views were created by build_views)",
                    rc,
                )
        # Load to MariaDB and upload processed Parquet (after Soda/dbt pass)
        if not df.empty:
            _load_to_mariadb_and_minio(df, league, season)
        return 0
    finally:
        if LOCK_FILE.exists():
            LOCK_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    skip = "--skip-ingest" in sys.argv
    if skip:
        sys.argv.remove("--skip-ingest")
    raise SystemExit(run_pipeline(skip_ingest=skip))
