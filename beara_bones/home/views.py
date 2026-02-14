"""
Home app views: simple async views that render templates.

All routes are defined in home/urls.py. Names are used in templates via {% url 'home:...' %}.
"""
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.template.loader import render_to_string
from django.template.response import TemplateResponse


async def index(request):
    """Landing page with quick links sidebar."""
    return TemplateResponse(request, "home/index.html")


def _get_football_data_dir() -> Path | None:
    """Return data/football dir. views.py is at repo_root/beara_bones/home/views.py -> parents[2] = repo_root."""
    repo_root = Path(__file__).resolve().parents[2]
    return repo_root / "data" / "football"


def _get_football_data_mtime() -> float | None:
    """Return mtime of newest data file (parquet or duckdb) for cache key, or None."""
    data_dir = _get_football_data_dir()
    if not data_dir or not data_dir.exists():
        return None
    mtimes = []
    for name in ("fixtures.parquet", "football.duckdb"):
        p = data_dir / name
        if p.exists():
            mtimes.append(p.stat().st_mtime)
    return max(mtimes) if mtimes else None


def _load_fixtures_for_dashboard():
    """Load fixture data from parquet or DuckDB for charts. Returns (df, error)."""
    data_dir = _get_football_data_dir()
    if not data_dir:
        return None, "Data directory not found"
    parquet_path = data_dir / "fixtures.parquet"
    if parquet_path.exists():
        try:
            import pandas as pd
            df = pd.read_parquet(parquet_path)
            return df, None
        except Exception as e:
            return None, str(e)
    try:
        import duckdb
        db_path = data_dir / "football.duckdb"
        if db_path.exists():
            con = duckdb.connect(str(db_path), read_only=True)
            df = con.execute(
                "SELECT * FROM fct_fixtures"
            ).fetchdf()
            con.close()
            if df is not None and not df.empty:
                return df, None
            con = duckdb.connect(str(db_path), read_only=True)
            df = con.execute("SELECT * FROM fixtures").fetchdf()
            con.close()
            return df, None
    except Exception as e:
        return None, str(e)
    return None, "No fixtures data. Run the pipeline: make pipeline"


def _build_dashboard_fragment():
    """Build chart + league table (one chart only). Returns dict with charts, standings, error. Hover shows real score (home-away)."""
    df, err = _load_fixtures_for_dashboard()
    if err or df is None or df.empty:
        return {"charts": [], "standings": [], "error": err or "No data"}
    try:
        import pandas as pd
        import plotly.graph_objects as go
        import plotly.io as pio
    except ImportError:
        return {"charts": [], "standings": [], "error": "Plotly/pandas not installed."}
    if "fixture_date" not in df.columns and "date" in df.columns:
        df["fixture_date"] = df["date"]
    if "fixture_date" in df.columns:
        df["fixture_date"] = pd.to_datetime(df["fixture_date"], errors="coerce")
    if "result" not in df.columns and "goals_home" in df.columns and "goals_away" in df.columns:
        h, a = df["goals_home"], df["goals_away"]
        df["result"] = "D"
        df.loc[h > a, "result"] = "H"
        df.loc[h < a, "result"] = "A"

    charts = []
    standings = []
    need = ["fixture_date", "home_team_name", "away_team_name", "goals_home", "goals_away", "result"]
    if all(c in df.columns for c in need):
        df_complete = df.dropna(subset=["result", "goals_home", "goals_away"]).sort_values("fixture_date")
        rows = []
        for _, r in df_complete.iterrows():
            date, h, a, gh, ga, res = r["fixture_date"], r["home_team_name"], r["away_team_name"], r["goals_home"], r["goals_away"], r["result"]
            pts_h = 3 if res == "H" else (1 if res == "D" else 0)
            pts_a = 3 if res == "A" else (1 if res == "D" else 0)
            res_h = "W" if res == "H" else ("D" if res == "D" else "L")
            res_a = "W" if res == "A" else ("D" if res == "D" else "L")
            # Actual match score (home-away) for display; store in both rows
            score_str = f"{int(gh)}-{int(ga)}"
            rows.append({"team": h, "date": date, "opponent": a, "venue": "Home", "result_letter": res_h, "score_display": score_str, "gf": int(gh), "ga": int(ga), "pts": pts_h})
            rows.append({"team": a, "date": date, "opponent": h, "venue": "Away", "result_letter": res_a, "score_display": score_str, "gf": int(ga), "ga": int(gh), "pts": pts_a})
        team_games = pd.DataFrame(rows)
        team_games["cumulative_pts"] = team_games.groupby("team")["pts"].cumsum()
        team_games["hover"] = (
            "<b>" + team_games["team"] + "</b><br>"
            + team_games["date"].dt.strftime("%d %b %Y") + "<br>"
            + team_games["venue"] + " vs " + team_games["opponent"] + ": "
            + team_games["score_display"] + " (" + team_games["result_letter"] + ")<br>"
            + "Points: " + team_games["cumulative_pts"].astype(str)
        )

        agg = team_games.groupby("team").agg(
            P=("pts", "count"),
            W=("pts", lambda s: (s == 3).sum()),
            D=("pts", lambda s: (s == 1).sum()),
            L=("pts", lambda s: (s == 0).sum()),
            GF=("gf", "sum"),
            GA=("ga", "sum"),
            Pts=("pts", "sum"),
        ).reset_index()
        agg["GD"] = agg["GF"] - agg["GA"]
        agg = agg.sort_values(["Pts", "GD"], ascending=[False, False]).reset_index(drop=True)
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
                )
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


def beara_bones_data(request):
    """Data page shell: loads fast; chart and table are injected by JS from /data/fragment/."""
    return TemplateResponse(
        request,
        "home/data.html",
        context={
            "loading": True,
            "current_league": 39,
            "current_league_name": "Premier League",
            "current_season": 2025,
        },
    )


def data_fragment(request):
    """Return dashboard HTML fragment (chart + league table). Cached by data file mtime; used for async load."""
    data_mtime = _get_football_data_mtime()
    cache_key = f"football_dashboard_{data_mtime}" if data_mtime else None
    timeout = getattr(settings, "FOOTBALL_DASHBOARD_CACHE_TIMEOUT", 600)

    if cache_key:
        cached = cache.get(cache_key)
        if cached is not None:
            html = render_to_string(
                "home/data_fragment.html",
                {"charts": cached.get("charts", []), "standings": cached.get("standings", []), "error": None},
            )
            return HttpResponse(html, content_type="text/html")

    frag = _build_dashboard_fragment()
    if cache_key and not frag.get("error"):
        cache.set(cache_key, {"charts": frag["charts"], "standings": frag["standings"]}, timeout=timeout)

    html = render_to_string(
        "home/data_fragment.html",
        {"charts": frag.get("charts", []), "standings": frag.get("standings", []), "error": frag.get("error")},
    )
    return HttpResponse(html, content_type="text/html")


async def about_me(request):
    """About page: site and itsbillw background."""
    return TemplateResponse(request, "home/about.html")


async def poetry(request):
    """If— by Rudyard Kipling (static poem page)."""
    return TemplateResponse(request, "home/if-.html")


def data_refresh(request):
    """POST /data/refresh/: start pipeline in background, return 202."""
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)
    data_dir = _get_football_data_dir()
    if not data_dir:
        return JsonResponse({"error": "Data dir not found"}, status=500)
    lock_file = data_dir / ".refresh.lock"
    if lock_file.exists():
        return JsonResponse(
            {"status": "already_running", "message": "Pipeline already in progress"},
            status=409,
        )
    repo_root = data_dir.parent.parent  # data/football -> data -> repo
    import subprocess
    subprocess.Popen(
        ["uv", "run", "python", "-m", "football.pipeline"],
        cwd=str(repo_root),
        start_new_session=True,
    )
    return JsonResponse({"status": "started", "message": "Refresh started"}, status=202)
