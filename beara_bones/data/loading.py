"""
Load fixtures DataFrame to MariaDB (Fixture model) and optional upload to MinIO processed bucket.
Called from management commands; requires Django to be set up.
"""

import logging
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


def load_fixtures_dataframe(df: pd.DataFrame, league_id: int, season: int) -> int:
    """
    Replace fixtures for (league_id, season) with rows from the DataFrame.
    Returns the number of rows inserted.
    """
    from .models import Fixture

    Fixture.objects.filter(league_id=league_id, league_season=season).delete()
    if df.empty:
        logger.info("No rows to load for league_id=%s season=%s", league_id, season)
        return 0

    # Map DataFrame columns to Fixture fields; handle date
    records = []
    for _, row in df.iterrows():
        date_val = row.get("date")
        if pd.isna(date_val):
            date_val = None
        elif hasattr(date_val, "to_pydatetime"):
            date_val = date_val.to_pydatetime()
        records.append(
            Fixture(
                fixture_id=int(row["fixture_id"]) if pd.notna(row.get("fixture_id")) else None,
                date=date_val,
                timestamp=int(row["timestamp"]) if pd.notna(row.get("timestamp")) else None,
                venue_id=int(row["venue_id"]) if pd.notna(row.get("venue_id")) else None,
                venue_name=str(row.get("venue_name", "")) if pd.notna(row.get("venue_name")) else "",
                status_short=str(row.get("status_short", "")) if pd.notna(row.get("status_short")) else "",
                status_long=str(row.get("status_long", "")) if pd.notna(row.get("status_long")) else "",
                league_id=int(row["league_id"]) if pd.notna(row.get("league_id")) else league_id,
                league_name=str(row.get("league_name", "")) if pd.notna(row.get("league_name")) else "",
                league_season=int(row["league_season"]) if pd.notna(row.get("league_season")) else season,
                league_round=str(row.get("league_round", "")) if pd.notna(row.get("league_round")) else "",
                home_team_id=int(row["home_team_id"]) if pd.notna(row.get("home_team_id")) else None,
                home_team_name=str(row.get("home_team_name", "")) if pd.notna(row.get("home_team_name")) else "",
                away_team_id=int(row["away_team_id"]) if pd.notna(row.get("away_team_id")) else None,
                away_team_name=str(row.get("away_team_name", "")) if pd.notna(row.get("away_team_name")) else "",
                goals_home=int(row["goals_home"]) if pd.notna(row.get("goals_home")) else None,
                goals_away=int(row["goals_away"]) if pd.notna(row.get("goals_away")) else None,
            )
        )
    Fixture.objects.bulk_create(records)
    logger.info("Loaded %d fixtures for league_id=%s season=%s", len(records), league_id, season)
    return len(records)
