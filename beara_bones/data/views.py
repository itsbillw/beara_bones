"""
Data app views: football dashboard (Dash embed), refresh endpoint. Refresh is admin-only.
"""

import pandas as pd

from django.conf import settings
from django.http import JsonResponse
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


def data_page(request):
    """Data page: embeds Plotly Dash FootballDashboard (chart + AG Grid league table)."""
    return TemplateResponse(request, "data/data.html")


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
