"""
Shared logic for building league standings and points chart from fixture data.
Used by both the legacy fragment view and the Dash FootballDashboard app.
"""

from typing import Literal

import pandas as pd

X_AXIS_OPTIONS = Literal["games_played", "fixture_date"]
SEASON_START_HOVER = "Season start · 0 pts"


def build_standings_and_figure(
    df: pd.DataFrame,
    *,
    x_axis: X_AXIS_OPTIONS = "games_played",
):
    """
    Build standings table and Plotly figure from a fixtures DataFrame.
    Expects columns: date (or fixture_date), home_team_name, away_team_name,
    goals_home, goals_away. Adds result (H/D/A) if missing.

    Returns:
        tuple: (standings: list[dict], figure, error: str | None).
        standings have keys: team, P, W, D, L, GF, GA, GD, Pts (GD as string e.g. "+3").
        figure is a plotly.go.Figure or None if data insufficient.
        error is a message string or None.
    """
    if df is None or df.empty:
        return [], None, "No data"

    if "fixture_date" not in df.columns and "date" in df.columns:
        df = df.copy()
        df["fixture_date"] = df["date"]
    if "fixture_date" not in df.columns:
        return [], None, "Missing date column"
    df = df.copy()
    df["fixture_date"] = pd.to_datetime(df["fixture_date"], errors="coerce")

    if (
        "result" not in df.columns
        and "goals_home" in df.columns
        and "goals_away" in df.columns
    ):
        h, a = df["goals_home"], df["goals_away"]
        df["result"] = "D"
        df.loc[h > a, "result"] = "H"
        df.loc[h < a, "result"] = "A"

    need = [
        "fixture_date",
        "home_team_name",
        "away_team_name",
        "goals_home",
        "goals_away",
        "result",
    ]
    if not all(c in df.columns for c in need):
        return [], None, "Missing required columns"

    df_complete = df.dropna(subset=["result", "goals_home", "goals_away"]).sort_values(
        "fixture_date",
    )
    has_team_ids = "home_team_id" in df.columns and "away_team_id" in df.columns
    rows = []
    for _, r in df_complete.iterrows():
        date = r["fixture_date"]
        h, a = r["home_team_name"], r["away_team_name"]
        gh, ga = r["goals_home"], r["goals_away"]
        res = r["result"]
        pts_h = 3 if res == "H" else (1 if res == "D" else 0)
        pts_a = 3 if res == "A" else (1 if res == "D" else 0)
        res_h = "W" if res == "H" else ("D" if res == "D" else "L")
        res_a = "W" if res == "A" else ("D" if res == "D" else "L")
        score_str = f"{int(gh)}-{int(ga)}"
        hid = r.get("home_team_id") if has_team_ids else None
        aid = r.get("away_team_id") if has_team_ids else None
        rows.append(
            {
                "team": h,
                "team_id": hid,
                "date": date,
                "opponent": a,
                "venue": "Home",
                "result_letter": res_h,
                "score_display": score_str,
                "gf": int(gh),
                "ga": int(ga),
                "pts": pts_h,
            },
        )
        rows.append(
            {
                "team": a,
                "team_id": aid,
                "date": date,
                "opponent": h,
                "venue": "Away",
                "result_letter": res_a,
                "score_display": score_str,
                "gf": int(ga),
                "ga": int(gh),
                "pts": pts_a,
            },
        )

    team_games = pd.DataFrame(rows)
    # Sort by team then date so cumulative_pts is in chronological order
    team_games = team_games.sort_values(["team", "date"]).reset_index(drop=True)
    team_games["cumulative_pts"] = team_games.groupby("team")["pts"].cumsum()
    # Game number (1, 2, 3...) per team for "games played" x-axis
    team_games["game_number"] = team_games.groupby("team").cumcount() + 1
    team_games["hover"] = (
        "<b>"
        + team_games["team"]
        + "</b><br>"
        + "Gameday: "
        + team_games["game_number"].astype(str)
        + "<br>"
        + team_games["date"].dt.strftime("%d %b %Y")
        + "<br>"
        + team_games["venue"]
        + " vs "
        + team_games["opponent"]
        + ": "
        + team_games["score_display"]
        + " ("
        + team_games["result_letter"]
        + ")<br>"
        + "Season Points: "
        + team_games["cumulative_pts"].astype(str)
    )

    agg_kw = {
        "P": ("pts", "count"),
        "W": ("pts", lambda s: (s == 3).sum()),
        "D": ("pts", lambda s: (s == 1).sum()),
        "L": ("pts", lambda s: (s == 0).sum()),
        "GF": ("gf", "sum"),
        "GA": ("ga", "sum"),
        "Pts": ("pts", "sum"),
    }
    if "team_id" in team_games.columns:
        agg_kw["team_id"] = ("team_id", "first")
    agg = team_games.groupby("team").agg(**agg_kw).reset_index()
    agg["GD"] = agg["GF"] - agg["GA"]
    agg = agg.sort_values(["Pts", "GD"], ascending=[False, False]).reset_index(
        drop=True,
    )
    team_order = agg["team"].tolist()
    agg["GD"] = agg["GD"].apply(lambda x: f"+{x}" if x > 0 else str(x))
    # Crest path and markdown for grid (crest + team name)
    if "team_id" in agg.columns:
        agg["crest_path"] = agg["team_id"].apply(
            lambda tid: f"/data/crest/{tid}/" if pd.notna(tid) else None,
        )
        agg["team_display_md"] = agg.apply(
            lambda r: f"![{r['team']}]({r['crest_path']}) {r['team']}"
            if r.get("crest_path")
            else r["team"],
            axis=1,
        )
    else:
        agg["crest_path"] = None
        agg["team_display_md"] = agg["team"]
    standings = agg.to_dict("records")

    try:
        import plotly.graph_objects as go

        fig_main = go.Figure()
        for team in team_order:
            t = (
                team_games[team_games["team"] == team]
                .sort_values("date")
                .reset_index(drop=True)
            )
            # Prepend (0, 0) so every team starts at zero
            y_vals = [0] + t["cumulative_pts"].astype(int).tolist()
            hover_list = t["hover"].tolist()
            start_hover = f"<b>{team}</b><br>{SEASON_START_HOVER}"
            customdata = [start_hover] + hover_list

            if x_axis == "games_played":
                # x = 0, 1, 2, ... (games played)
                x_vals = [0] + t["game_number"].astype(int).tolist()
            else:
                # x = date; start a few days before first fixture
                first_date = t["date"].iloc[0]
                start_date = first_date - pd.Timedelta(days=5)
                x_vals = [start_date] + t["date"].tolist()

            fig_main.add_trace(
                go.Scatter(
                    x=x_vals,
                    y=y_vals,
                    name=team,
                    mode="lines+markers",
                    hovertemplate="%{customdata}<extra></extra>",
                    customdata=customdata,
                ),
            )

        xaxis_title = "Games played" if x_axis == "games_played" else "Fixture (date)"
        fig_main.update_layout(
            title="",
            xaxis_title=xaxis_title,
            yaxis_title="Points",
            template="plotly_white",
            height=620,
            hovermode="closest",
            margin=dict(r=220),
            legend=dict(orientation="v", x=1.02, y=1, xanchor="left", yanchor="top"),
        )
        return standings, fig_main, None
    except ImportError:
        return standings, None, "Plotly not installed"
