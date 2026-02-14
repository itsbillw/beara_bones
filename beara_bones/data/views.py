"""
Data app views: football dashboard (shell, fragment). Refresh is admin-only.
"""

import pandas as pd

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.template.loader import render_to_string
from django.template.response import TemplateResponse
from django.views.decorators.http import require_http_methods


def _load_fixtures_from_db(league_id: int, season: int):
    """Load fixture data from MariaDB for the given league/season. Returns (df, error)."""
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


def _build_dashboard_fragment(league_id: int, season: int):
    """Build chart + league table from MariaDB data. Returns dict with charts, standings, error."""
    df, err = _load_fixtures_from_db(league_id, season)
    if err or df is None or df.empty:
        return {"charts": [], "standings": [], "error": err or "No data"}
    try:
        import plotly.graph_objects as go
        import plotly.io as pio
    except ImportError:
        return {"charts": [], "standings": [], "error": "Plotly/pandas not installed."}
    if "fixture_date" not in df.columns and "date" in df.columns:
        df["fixture_date"] = df["date"]
    if "fixture_date" in df.columns:
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

    charts = []
    standings = []
    need = [
        "fixture_date",
        "home_team_name",
        "away_team_name",
        "goals_home",
        "goals_away",
        "result",
    ]
    if not all(c in df.columns for c in need):
        return {"charts": [], "standings": [], "error": None}

    df_complete = df.dropna(subset=["result", "goals_home", "goals_away"]).sort_values(
        "fixture_date",
    )
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
        rows.append(
            {
                "team": h,
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
    team_games["cumulative_pts"] = team_games.groupby("team")["pts"].cumsum()
    team_games["hover"] = (
        "<b>"
        + team_games["team"]
        + "</b><br>"
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
        + "Points: "
        + team_games["cumulative_pts"].astype(str)
    )

    agg = (
        team_games.groupby("team")
        .agg(
            P=("pts", "count"),
            W=("pts", lambda s: (s == 3).sum()),
            D=("pts", lambda s: (s == 1).sum()),
            L=("pts", lambda s: (s == 0).sum()),
            GF=("gf", "sum"),
            GA=("ga", "sum"),
            Pts=("pts", "sum"),
        )
        .reset_index()
    )
    agg["GD"] = agg["GF"] - agg["GA"]
    agg = agg.sort_values(["Pts", "GD"], ascending=[False, False]).reset_index(
        drop=True,
    )
    team_order = agg["team"].tolist()
    agg["GD"] = agg["GD"].apply(lambda x: f"+{x}" if x > 0 else str(x))
    standings = agg.to_dict("records")

    fig_main = go.Figure()
    for team in team_order:
        t = team_games[team_games["team"] == team]
        fig_main.add_trace(
            go.Scatter(
                x=t["date"],
                y=t["cumulative_pts"],
                name=team,
                mode="lines+markers",
                hovertemplate="%{customdata}<extra></extra>",
                customdata=t["hover"],
            ),
        )
    fig_main.update_layout(
        title="",
        xaxis_title="Fixture (date)",
        yaxis_title="Points",
        template="plotly_white",
        height=620,
        hovermode="closest",
        margin=dict(r=220),
        legend=dict(orientation="v", x=1.02, y=1, xanchor="left", yanchor="top"),
    )
    charts.append(pio.to_html(fig_main, full_html=False))
    return {"charts": charts, "standings": standings, "error": None}


def data_page(request):
    """Data page shell: league/season dropdowns; chart and table loaded via fragment."""
    from .models import League, Season

    leagues = list(League.objects.all())
    seasons = list(Season.objects.all())
    current_league_id = None
    current_season = None
    current_league_name = ""
    current_season_display = ""
    if leagues:
        current_league_id = leagues[0].id
        current_league_name = leagues[0].name
    if seasons:
        current_season = seasons[0].api_year
        current_season_display = seasons[0].display
    return TemplateResponse(
        request,
        "data/data.html",
        context={
            "loading": True,
            "leagues": leagues,
            "seasons": seasons,
            "current_league": current_league_id,
            "current_season": current_season,
            "current_league_name": current_league_name,
            "current_season_display": current_season_display,
        },
    )


def data_fragment(request):
    """Return dashboard HTML fragment. GET params: league, season. Cached by league and season."""
    from .models import League, Season

    league_id = request.GET.get("league")
    season = request.GET.get("season")
    leagues = list(League.objects.all())
    seasons = list(Season.objects.all())
    if not leagues or not seasons:
        html = render_to_string(
            "data/data_fragment.html",
            {
                "charts": [],
                "standings": [],
                "error": "No leagues or seasons configured. Add them in Admin.",
            },
        )
        return HttpResponse(html, content_type="text/html")
    if league_id is not None:
        try:
            league_id = int(league_id)
        except ValueError:
            league_id = leagues[0].id
    else:
        league_id = leagues[0].id
    if season is not None:
        try:
            season = int(season)
        except ValueError:
            season = seasons[0].api_year
    else:
        season = seasons[0].api_year
    cache_key = f"football_dashboard_{league_id}_{season}"
    timeout = getattr(settings, "FOOTBALL_DASHBOARD_CACHE_TIMEOUT", 600)

    cached = cache.get(cache_key)
    if cached is not None:
        html = render_to_string(
            "data/data_fragment.html",
            {
                "charts": cached.get("charts", []),
                "standings": cached.get("standings", []),
                "error": None,
            },
        )
        return HttpResponse(html, content_type="text/html")

    frag = _build_dashboard_fragment(league_id, season)
    if not frag.get("error"):
        cache.set(
            cache_key,
            {"charts": frag["charts"], "standings": frag["standings"]},
            timeout=timeout,
        )

    html = render_to_string(
        "data/data_fragment.html",
        {
            "charts": frag.get("charts", []),
            "standings": frag.get("standings", []),
            "error": frag.get("error"),
        },
    )
    return HttpResponse(html, content_type="text/html")


@require_http_methods(["POST"])
def data_refresh(request):
    """POST /data/refresh: start pipeline (staff only). Returns 403 for non-staff."""
    if not request.user.is_authenticated or not request.user.is_staff:
        return JsonResponse({"error": "Forbidden"}, status=403)
    from pathlib import Path
    import subprocess  # nosec B404

    repo_root = Path(settings.BASE_DIR).parent
    lock_file = repo_root / "data" / "football" / ".refresh.lock"
    if lock_file.exists():
        return JsonResponse(
            {"status": "already_running", "message": "Pipeline already in progress"},
            status=409,
        )
    subprocess.Popen(  # nosec B603 B607
        ["uv", "run", "python", "beara_bones/manage.py", "run_football_pipeline"],
        cwd=str(repo_root),
        start_new_session=True,
    )
    return JsonResponse({"status": "started", "message": "Refresh started"}, status=202)
