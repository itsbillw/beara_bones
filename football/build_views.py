"""
Create stg_fixtures and fct_fixtures views in football.duckdb.
Used when dbt build segfaults (e.g. dbt-duckdb + Python 3.13) so the pipeline still completes.
"""

import logging
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = REPO_ROOT / "data" / "football" / "football.duckdb"

logger = logging.getLogger(__name__)


def run() -> None:
    if not DB_PATH.exists():
        logger.warning(
            "DuckDB file not found: %s. Run transform and load_csv_to_duckdb first.",
            DB_PATH,
        )
        return
    import duckdb

    con = duckdb.connect(str(DB_PATH))
    con.execute("""
        CREATE OR REPLACE VIEW main.stg_fixtures AS
        SELECT
            fixture_id,
            date::date AS fixture_date,
            timestamp,
            venue_id,
            venue_name,
            status_short,
            status_long,
            league_id,
            league_name,
            league_season,
            league_round,
            home_team_id,
            home_team_name,
            away_team_id,
            away_team_name,
            goals_home::int AS goals_home,
            goals_away::int AS goals_away
        FROM main.fixtures
    """)
    logger.info("Created view main.stg_fixtures")
    con.execute("""
        CREATE OR REPLACE VIEW main.fct_fixtures AS
        SELECT
            fixture_id,
            fixture_date,
            league_name,
            league_season,
            home_team_name,
            away_team_name,
            goals_home,
            goals_away,
            goals_home - goals_away AS goal_diff_home,
            CASE
                WHEN goals_home > goals_away THEN 'H'
                WHEN goals_home < goals_away THEN 'A'
                ELSE 'D'
            END AS result
        FROM main.stg_fixtures
        WHERE status_short IN ('FT', 'AET', 'PEN')
          AND goals_home IS NOT NULL
          AND goals_away IS NOT NULL
    """)
    logger.info("Created view main.fct_fixtures")
    con.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
