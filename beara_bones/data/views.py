"""
Data app views: football dashboard (Dash embed), refresh endpoint, crest image proxy. Refresh is admin-only.
"""

import os

import pandas as pd

from django.conf import settings
from django.http import HttpResponse, HttpResponseNotFound, JsonResponse
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


def _load_team_games_from_view(league_id: int, season: int):
    """
    Load team-games from data_team_game view for the given league/season.
    Returns (DataFrame with same shape as dashboard_utils team_games, error).
    Falls back to (None, error_msg) if the view is unavailable or empty.
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
        return None, None  # No data for this league/season
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


def data_page(request):
    """Data page: embeds Plotly Dash FootballDashboard (chart + AG Grid league table)."""
    return TemplateResponse(request, "data/data.html")


def crest_serve(request, team_id: int):
    """Serve team crest image from MinIO. GET /data/crest/<team_id>/"""
    import sys
    from pathlib import Path

    repo_root = Path(settings.BASE_DIR).parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from football.crests import CREST_KEY_TEMPLATE
    from football.ingest import get_client

    bucket = os.environ.get("MINIO_BUCKET", "football") or "football"
    key = CREST_KEY_TEMPLATE.format(team_id=team_id)
    try:
        client = get_client()
        resp = client.get_object(bucket, key)
        data = resp.read()
        resp.close()
        return HttpResponse(data, content_type="image/png")
    except Exception:
        return HttpResponseNotFound()


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
