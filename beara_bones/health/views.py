"""Staff-only Pi health dashboard views."""

from __future__ import annotations

import logging
from collections.abc import Callable
from functools import wraps
from typing import Any

from data.theme_utils import current_theme
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.template.response import TemplateResponse
from django.views.decorators.http import require_http_methods

from .chart_utils import build_charts_payload, empty_charts_payload
from .health_service import (
    RANGE_HOURS,
    RangeKey,
    default_chart_host,
    format_bytes,
    latest_snapshots,
    list_hosts,
)

LOG = logging.getLogger(__name__)


def staff_required[F: Callable[..., HttpResponse]](view_func: F) -> F:
    @wraps(view_func)
    @login_required
    def _wrapped(request: HttpRequest, *args, **kwargs):
        if not request.user.is_staff:
            if request.headers.get("HX-Request"):
                return JsonResponse({"error": "Forbidden"}, status=403)
            return HttpResponse("Forbidden", status=403)
        return view_func(request, *args, **kwargs)

    return _wrapped  # type: ignore[return-value]


def _parse_range(raw: str | None) -> RangeKey:
    if raw in RANGE_HOURS:
        return raw  # type: ignore[return-value]
    return "24h"


def _parse_host(raw: str | None, hosts: list[str], snapshots: dict) -> str | None:
    if raw and raw in hosts:
        return raw
    return default_chart_host(hosts, snapshots)


def _build_cards(hosts: list[str], snapshots: dict) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for name in hosts:
        snapshot = snapshots.get(name)
        if snapshot is None:
            cards.append({"host": name, "missing": True, "offline": True})
            continue
        cards.append(
            {
                "host": name,
                "missing": False,
                "offline": False,
                "ts": snapshot.ts,
                "cpu_pct": snapshot.cpu_pct,
                "mem_pct": snapshot.mem_pct,
                "temp_c": snapshot.temp_c,
                "filesystems": [
                    {
                        "mount": fs["mount"],
                        "used_label": format_bytes(fs.get("used")),
                        "total_label": format_bytes(fs.get("total")),
                        "pct": round(100.0 * fs["used"] / fs["total"], 1) if fs.get("total") else None,
                    }
                    for fs in snapshot.filesystems
                ],
            }
        )
    return cards


def _safe_charts_payload(host: str | None, range_key: RangeKey, theme: str) -> dict[str, str]:
    if host is None:
        return empty_charts_payload()
    try:
        return build_charts_payload(host, range_key, theme)
    except Exception as exc:
        LOG.exception("Health chart build failed for %s: %s", host, exc)
        return empty_charts_payload("Charts temporarily unavailable")


@staff_required
@require_http_methods(["GET"])
def health_page(request: HttpRequest) -> HttpResponse:
    hosts = list_hosts()
    snapshots = latest_snapshots()
    host = _parse_host(request.GET.get("host"), hosts, snapshots)
    range_key = _parse_range(request.GET.get("range"))
    charts = _safe_charts_payload(host, range_key, current_theme(request))
    return TemplateResponse(
        request,
        "health/health.html",
        {
            "hosts": hosts,
            "selected_host": host,
            "range_key": range_key,
            "range_options": RANGE_HOURS.keys(),
            "cards": _build_cards(hosts, snapshots),
            "db_warning": None if snapshots or not hosts else "Waiting for first poller run.",
            **charts,
        },
    )


@staff_required
@require_http_methods(["GET"])
def health_cards(request: HttpRequest) -> HttpResponse:
    hosts = list_hosts()
    snapshots = latest_snapshots()
    return TemplateResponse(
        request,
        "health/_cards_panel.html",
        {"cards": _build_cards(hosts, snapshots)},
    )


@staff_required
@require_http_methods(["GET"])
def health_charts(request: HttpRequest) -> HttpResponse:
    hosts = list_hosts()
    snapshots = latest_snapshots()
    host = _parse_host(request.GET.get("host"), hosts, snapshots)
    range_key = _parse_range(request.GET.get("range"))
    if host is None:
        return TemplateResponse(
            request,
            "health/_charts_panel.html",
            {
                "selected_host": None,
                "range_key": range_key,
                "error": "No health data yet. Run the poller on DietPiServer.",
                **empty_charts_payload(),
            },
        )
    has_history = host in snapshots
    payload = _safe_charts_payload(host, range_key, current_theme(request))
    error = None
    if not has_history:
        error = f"{host} is offline or has no recent data. Showing empty charts."
    return TemplateResponse(
        request,
        "health/_charts_panel.html",
        {
            "selected_host": host,
            "range_key": range_key,
            "error": error,
            **payload,
        },
    )
