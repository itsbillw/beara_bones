"""Football dashboard data loading and caching (replaces Dash callbacks)."""

from __future__ import annotations

import json
from typing import Any, Literal

import plotly.io as pio
from django.conf import settings
from django.core.cache import cache
from django.http import HttpRequest

from .cache_utils import football_dashboard_cache_version
from .dashboard_utils import build_standings_and_figure
from .loaders import load_fixtures_from_db, load_team_games_from_view
from .models import League, Season
from .theme_utils import current_theme, plotly_template, surface_colors

XAxisOption = Literal["games_played", "fixture_date"]


def league_season_defaults() -> tuple[int | None, int | None]:
    league = League.objects.order_by("order", "id").first()
    season = Season.objects.order_by("-api_year").first()
    return (
        league.id if league is not None else None,
        season.api_year if season is not None else None,
    )


def _empty_figure(message: str, theme: str) -> dict[str, Any]:
    template = plotly_template(theme)
    page_bg, plot_bg = surface_colors(theme)
    return {
        "data": [],
        "layout": {
            "template": template,
            "height": 620,
            "paper_bgcolor": page_bg,
            "plot_bgcolor": plot_bg,
            "xaxis": {"visible": False},
            "yaxis": {"visible": False},
            "annotations": [
                {
                    "text": message,
                    "showarrow": False,
                    "xref": "paper",
                    "yref": "paper",
                    "x": 0.5,
                    "y": 0.5,
                },
            ],
        },
    }


def _apply_plotly_theme(fig_or_dict: Any, theme: str) -> Any:
    template = plotly_template(theme)
    page_bg, plot_bg = surface_colors(theme)
    layout_updates = {
        "template": template,
        "paper_bgcolor": page_bg,
        "plot_bgcolor": plot_bg,
    }
    if hasattr(fig_or_dict, "update_layout"):
        fig_or_dict.update_layout(**layout_updates)
        return fig_or_dict
    layout = fig_or_dict.setdefault("layout", {})
    layout.update(layout_updates)
    return fig_or_dict


def _serialize_figure(fig: Any) -> str:
    if hasattr(fig, "update_layout"):
        return str(pio.to_json(fig))
    return json.dumps(fig)


def build_dashboard_payload(
    *,
    league_id: int | None,
    season: int | None,
    x_axis: XAxisOption = "games_played",
    request: HttpRequest | None = None,
) -> dict[str, Any]:
    """Return dashboard context: standings, figure_json, error."""
    theme = current_theme(request)
    if league_id is None or season is None:
        return {
            "standings": [],
            "figure_json": json.dumps(_empty_figure("Select league and season", theme)),
            "error": "",
            "theme": theme,
        }

    cache_timeout = getattr(settings, "FOOTBALL_DASHBOARD_CACHE_TIMEOUT", 600)
    cache_key = f"football:dash:{football_dashboard_cache_version()}:{league_id}:{season}:{x_axis}:{theme}"
    cached = cache.get(cache_key)
    if cached is not None:
        return dict(cached)

    team_games_df, _view_err = load_team_games_from_view(league_id, season)
    if team_games_df is not None and not team_games_df.empty:
        standings, fig, err = build_standings_and_figure(
            team_games_df=team_games_df,
            x_axis=x_axis,
            plotly_template=plotly_template(theme),
        )
    else:
        df, err = load_fixtures_from_db(league_id, season)
        if err or df is None or df.empty:
            message = err or "No fixtures for this league/season. Run the pipeline from Admin."
            payload: dict[str, Any] = {
                "standings": [],
                "figure_json": json.dumps(_empty_figure(message, theme)),
                "error": message,
                "theme": theme,
            }
            return payload
        standings, fig, err = build_standings_and_figure(
            df,
            x_axis=x_axis,
            plotly_template=plotly_template(theme),
        )

    if err:
        payload = {
            "standings": [],
            "figure_json": json.dumps(_empty_figure(err, theme)),
            "error": err,
            "theme": theme,
        }
        return payload

    for index, row in enumerate(standings, start=1):
        row["rank"] = index

    fig = _apply_plotly_theme(fig, theme)
    payload = {
        "standings": standings,
        "figure_json": _serialize_figure(fig),
        "error": "",
        "theme": theme,
    }
    cache.set(cache_key, payload, timeout=cache_timeout)
    return payload
