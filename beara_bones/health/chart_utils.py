"""Plotly figure builders for the health dashboard."""

from __future__ import annotations

import json
from typing import Any

import plotly.graph_objects as go
import plotly.io as pio
from data.theme_utils import plotly_template, surface_colors

from .health_service import RangeKey, history_rows

CHART_HEIGHT = 280


def empty_charts_payload(message: str | None = None) -> dict[str, str]:
    theme = "dark"
    payload = json.dumps(_empty_figure(message or "No data", theme))
    return {
        "cpu_figure_json": payload,
        "memory_figure_json": payload,
        "temperature_figure_json": payload,
        "storage_figure_json": payload,
    }


def _empty_figure(message: str, theme: str) -> dict[str, Any]:
    template = plotly_template(theme)
    page_bg, plot_bg = surface_colors(theme)
    return {
        "data": [],
        "layout": {
            "template": template,
            "height": CHART_HEIGHT,
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


def _apply_theme(fig: go.Figure, theme: str) -> go.Figure:
    template = plotly_template(theme)
    page_bg, plot_bg = surface_colors(theme)
    fig.update_layout(
        template=template,
        paper_bgcolor=page_bg,
        plot_bgcolor=plot_bg,
        height=CHART_HEIGHT,
        margin=dict(l=48, r=16, t=32, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
    )
    return fig


def _serialize(fig: go.Figure) -> str:
    return str(pio.to_json(fig))


def build_cpu_figure(host: str, range_key: RangeKey, theme: str) -> str:
    rows = history_rows(host, range_key)
    if not rows:
        return json.dumps(_empty_figure("No CPU history yet", theme))
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=[row.ts for row in rows],
            y=[row.cpu_pct for row in rows],
            mode="lines",
            name="CPU %",
            line=dict(width=2),
        )
    )
    fig.update_layout(title=f"{host} CPU", yaxis_title="%")
    return _serialize(_apply_theme(fig, theme))


def build_memory_figure(host: str, range_key: RangeKey, theme: str) -> str:
    rows = history_rows(host, range_key)
    if not rows:
        return json.dumps(_empty_figure("No memory history yet", theme))
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=[row.ts for row in rows],
            y=[row.mem_pct for row in rows],
            mode="lines",
            name="Memory %",
            line=dict(width=2),
        )
    )
    fig.update_layout(title=f"{host} memory", yaxis_title="%")
    return _serialize(_apply_theme(fig, theme))


def build_temperature_figure(host: str, range_key: RangeKey, theme: str) -> str:
    rows = history_rows(host, range_key)
    if not rows:
        return json.dumps(_empty_figure("No temperature history yet", theme))
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=[row.ts for row in rows],
            y=[row.temp_c for row in rows],
            mode="lines",
            name="Temp °C",
            line=dict(width=2),
        )
    )
    fig.update_layout(title=f"{host} temperature", yaxis_title="°C")
    return _serialize(_apply_theme(fig, theme))


def build_storage_figure(host: str, range_key: RangeKey, theme: str) -> str:
    rows = history_rows(host, range_key)
    if not rows:
        return json.dumps(_empty_figure("No storage history yet", theme))
    mounts = sorted({fs["mount"] for row in rows for fs in row.filesystems})
    fig = go.Figure()
    for mount in mounts:
        values: list[float | None] = []
        for row in rows:
            match = next((fs for fs in row.filesystems if fs["mount"] == mount), None)
            if not match or not match.get("total"):
                values.append(None)
            else:
                values.append(round(100.0 * match["used"] / match["total"], 1))
        fig.add_trace(
            go.Scatter(
                x=[row.ts for row in rows],
                y=values,
                mode="lines",
                name=mount,
                line=dict(width=2),
            )
        )
    fig.update_layout(title=f"{host} storage", yaxis_title="% used")
    return _serialize(_apply_theme(fig, theme))


def build_charts_payload(host: str, range_key: RangeKey, theme: str) -> dict[str, str]:
    return {
        "cpu_figure_json": build_cpu_figure(host, range_key, theme),
        "memory_figure_json": build_memory_figure(host, range_key, theme),
        "temperature_figure_json": build_temperature_figure(host, range_key, theme),
        "storage_figure_json": build_storage_figure(host, range_key, theme),
    }
