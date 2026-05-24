"""Seed DuckDB with a minimal fixtures table for CI dbt/Soda checks."""

from __future__ import annotations

from pathlib import Path

import duckdb

DB_PATH = Path("data/football/football.duckdb")

CREATE_FIXTURES = """
CREATE TABLE IF NOT EXISTS fixtures (
    fixture_id BIGINT,
    date DATE,
    timestamp BIGINT,
    venue_id INTEGER,
    venue_name VARCHAR,
    status_short VARCHAR,
    status_long VARCHAR,
    league_id INTEGER,
    league_name VARCHAR,
    league_season INTEGER,
    league_round VARCHAR,
    home_team_id INTEGER,
    home_team_name VARCHAR,
    away_team_id INTEGER,
    away_team_name VARCHAR,
    goals_home INTEGER,
    goals_away INTEGER
)
"""

INSERT_FIXTURE = """
INSERT INTO fixtures VALUES (
    1,
    '2025-01-15',
    0,
    1,
    'Test Arena',
    'FT',
    'Match Finished',
    39,
    'Premier League',
    2025,
    'Regular Season - 1',
    1,
    'TeamA',
    2,
    'TeamB',
    2,
    1
)
"""


def main() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()
    con = duckdb.connect(str(DB_PATH))
    try:
        con.execute(CREATE_FIXTURES)
        con.execute(INSERT_FIXTURE)
    finally:
        con.close()


if __name__ == "__main__":
    main()
