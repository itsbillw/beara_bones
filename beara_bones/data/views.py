"""
Data app views: football dashboard, refresh endpoint, crest image proxy.
"""

from __future__ import annotations

from django.http import HttpResponse, HttpResponseNotFound, JsonResponse
from django.template.response import TemplateResponse
from django.views.decorators.http import require_http_methods

from football.crests import CREST_KEY_TEMPLATE
from football.ingest import get_client

from .dashboard_service import build_dashboard_payload, league_season_defaults
from .models import League, Season
from .pipeline_service import enqueue_pipeline_refresh


def _parse_dashboard_params(request) -> tuple[int | None, int | None, str]:
    default_league, default_season = league_season_defaults()
    league_raw = request.GET.get("league", default_league)
    season_raw = request.GET.get("season", default_season)
    x_axis = request.GET.get("x_axis", "games_played")
    if x_axis not in ("games_played", "fixture_date"):
        x_axis = "games_played"
    try:
        league_id = int(league_raw) if league_raw is not None else None
    except (TypeError, ValueError):
        league_id = default_league
    try:
        season = int(season_raw) if season_raw is not None else None
    except (TypeError, ValueError):
        season = default_season
    return league_id, season, x_axis


def data_page(request):
    """Football dashboard page with HTMX-driven chart and standings table."""
    league_id, season, x_axis = _parse_dashboard_params(request)
    payload = build_dashboard_payload(
        league_id=league_id,
        season=season,
        x_axis=x_axis,
        request=request,
    )
    return TemplateResponse(
        request,
        "data/data.html",
        {
            "leagues": League.objects.all(),
            "seasons": Season.objects.all(),
            "league_id": league_id,
            "season": season,
            "x_axis": x_axis,
            **payload,
        },
    )


def dashboard_panel(request):
    """HTMX partial: chart JSON + standings table for selected league/season."""
    league_id, season, x_axis = _parse_dashboard_params(request)
    payload = build_dashboard_payload(
        league_id=league_id,
        season=season,
        x_axis=x_axis,
        request=request,
    )
    return TemplateResponse(
        request,
        "data/_dashboard_panel.html",
        {
            "league_id": league_id,
            "season": season,
            "x_axis": x_axis,
            **payload,
        },
    )


def crest_serve(request, team_id: int):
    """Serve team crest image from MinIO. GET /data/crest/<team_id>/"""
    import os

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

    result = enqueue_pipeline_refresh(source="api_refresh")
    status_code = 409 if result["status"] == "already_running" else 202
    return JsonResponse(result, status=status_code)
