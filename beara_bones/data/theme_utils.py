"""Theme helpers for the football dashboard."""

from __future__ import annotations

from django.http import HttpRequest

THEME_ACCENTS = {
    "dark": "#5ba3a6",
    "light": "#245052",
}


def current_theme(request: HttpRequest | None) -> str:
    if request is None:
        return "dark"
    raw = request.COOKIES.get("itsbillw-theme", "")
    return raw if raw in ("light", "dark") else "dark"


def plotly_template(theme: str) -> str:
    return "plotly_white" if theme == "light" else "plotly_dark"


def surface_colors(theme: str) -> tuple[str, str]:
    if theme == "light":
        return "#f0f4f4", "#ffffff"
    return "#1a2628", "#121a1b"
