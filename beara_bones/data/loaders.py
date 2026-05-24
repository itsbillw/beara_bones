"""Database loaders for the football dashboard."""

from __future__ import annotations

import pandas as pd


def load_fixtures_from_db(league_id: int, season: int):
    """Load fixture data for the given league/season. Returns (df, error)."""
    from .models import Fixture

    qs = Fixture.objects.filter(league_id=league_id, league_season=season).order_by(
        "date",
    )
    if not qs.exists():
        return None, "No fixtures for this league/season. Run the pipeline from Admin."
    rows = list(
        qs.values(
            "fixture_id",
            "date",
            "timestamp",
            "venue_id",
            "venue_name",
            "status_short",
            "status_long",
            "league_id",
            "league_name",
            "league_season",
            "league_round",
            "home_team_id",
            "home_team_name",
            "away_team_id",
            "away_team_name",
            "goals_home",
            "goals_away",
        ),
    )
    df = pd.DataFrame(rows)
    return df, None


def load_team_games_from_view(league_id: int, season: int):
    """
    Load team-games from data_team_game view for the given league/season.
    Returns (DataFrame, error). Empty league returns (None, None).
    """
    from django.db import connection

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    team_name,
                    team_id,
                    fixture_date,
                    opponent_name,
                    venue,
                    goals_for,
                    goals_against,
                    pts,
                    result_letter,
                    game_number,
                    cumulative_pts
                FROM data_team_game
                WHERE league_id = %s AND league_season = %s
                ORDER BY team_name, fixture_date
                """,
                [league_id, season],
            )
            columns = [col[0] for col in cursor.description]
            rows = cursor.fetchall()
    except Exception as e:
        return None, str(e)
    if not rows:
        return None, None
    df = pd.DataFrame(rows, columns=columns)
    df = df.rename(
        columns={
            "team_name": "team",
            "fixture_date": "date",
            "opponent_name": "opponent",
            "goals_for": "gf",
            "goals_against": "ga",
        },
    )
    df["score_display"] = df["gf"].astype(str) + "-" + df["ga"].astype(str)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["hover"] = (
        "<b>" + df["team"] + "</b><br>"
        "Gameday: "
        + df["game_number"].astype(str)
        + "<br>"
        + df["date"].dt.strftime("%d %b %Y")
        + "<br>"
        + df["venue"]
        + " vs "
        + df["opponent"]
        + ": "
        + df["score_display"]
        + " ("
        + df["result_letter"]
        + ")<br>"
        "Season Points: " + df["cumulative_pts"].astype(str)
    )
    return df, None
