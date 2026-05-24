"""
Plotly Dash app: Football dashboard with points chart and AG Grid league table.
Registered as DjangoDash so it can be embedded via {% plotly_app name="FootballDashboard" %}.
"""

import dash_ag_grid as dag
from dash import Input, Output, dcc, html
from django.conf import settings
from django.core.cache import cache
from django_plotly_dash import DjangoDash

from .cache_utils import football_dashboard_cache_version
from .dashboard_utils import build_standings_and_figure
from .views import _load_fixtures_from_db, _load_team_games_from_view

# Load Plotly.js from CDN so dcc.Graph works when serve_locally=False (avoids 404 for /static/.../plotly.min.js)
PLOTLY_JS_CDN = "https://cdn.plot.ly/plotly-2.27.0.min.js"
# Crest images in grid scaled to row height (served from Django static)
CREST_GRID_CSS = "/static/data/css/crest_grid.css"
DASH_THEME_CSS = "/static/data/css/dash_theme.css"
AG_GRID_VERSION = "33.3.2"
AG_GRID_CDN = f"https://cdn.jsdelivr.net/npm/ag-grid-community@{AG_GRID_VERSION}/styles"
# Form column cell renderer (must load in iframe where the grid runs)
FORM_RENDERER_JS = "/static/data/js/dashAgGridComponentFunctions.js"
app = DjangoDash(
    "FootballDashboard",
    add_bootstrap_links=False,
    external_scripts=[
        {"src": PLOTLY_JS_CDN},
        {"src": FORM_RENDERER_JS},
    ],
    external_stylesheets=[
        {"href": CREST_GRID_CSS, "rel": "stylesheet"},
        {"href": DASH_THEME_CSS, "rel": "stylesheet"},
        {
            "href": f"{AG_GRID_CDN}/ag-grid.css",
            "rel": "stylesheet",
        },
        {
            "href": f"{AG_GRID_CDN}/ag-theme-alpine.css",
            "rel": "stylesheet",
        },
        {
            "href": f"{AG_GRID_CDN}/ag-theme-alpine-dark.css",
            "rel": "stylesheet",
        },
    ],
)

# Row height for standings grid; crests are scaled to fit
STANDINGS_ROW_HEIGHT_PX = 41
STANDINGS_CREST_MAX_HEIGHT_PX = 28  # leave padding in row

# Component IDs
ID_LEAGUE_DROPDOWN = "football-dash-league"
ID_SEASON_DROPDOWN = "football-dash-season"
ID_X_AXIS_DROPDOWN = "football-dash-x-axis"
ID_GRAPH = "football-dash-graph"
ID_GRID = "football-dash-grid"
ID_ERROR = "football-dash-error"

THEME_ACCENTS = {
    "dark": "#5ba3a6",
    "light": "#245052",
}


def _theme_from_cookie_value(raw: object) -> str | None:
    theme = str(raw or "")
    return theme if theme in ("light", "dark") else None


def _current_theme() -> str:
    """Read theme from itsbillw-theme cookie (Django request in django_plotly_dash)."""
    from data.theme_context import get_django_request

    django_request = get_django_request()
    if django_request is not None:
        theme = _theme_from_cookie_value(django_request.COOKIES.get("itsbillw-theme"))
        if theme:
            return theme

    try:
        from flask import has_request_context, request

        if has_request_context():
            theme = _theme_from_cookie_value(request.cookies.get("itsbillw-theme"))
            if theme:
                return theme
    except ImportError:
        pass

    return "dark"


def _plotly_template() -> str:
    return "plotly_white" if _current_theme() == "light" else "plotly_dark"


def _grid_theme_class() -> str:
    return "ag-theme-alpine" if _current_theme() == "light" else "ag-theme-alpine-dark"


def _grid_dash_options() -> dict:
    """AG Grid v33+ defaults to Quartz; opt into legacy CSS themes via className."""
    return {
        "animateRows": True,
        "rowHeight": STANDINGS_ROW_HEIGHT_PX,
        "theme": "legacy",
    }


def _dropdown_style(min_width: str) -> dict:
    return {
        "minWidth": min_width,
        "display": "inline-block",
    }


def _error_style() -> dict:
    theme = _current_theme()
    return {
        "color": THEME_ACCENTS.get(theme, THEME_ACCENTS["dark"]),
        "marginBottom": "8px",
    }


# Fixed width (96px) for compact numeric columns
NUM_COL_WIDTH = 96
STANDINGS_COLUMN_DEFS = [
    {
        "field": "rank",
        "headerName": "#",
        "width": NUM_COL_WIDTH,
        "minWidth": NUM_COL_WIDTH,
        "maxWidth": NUM_COL_WIDTH,
    },
    {
        "field": "team_display_md",
        "headerName": "Team",
        "flex": 1,
        "cellRenderer": "markdown",
    },
    {
        "field": "P",
        "headerName": "P",
        "width": NUM_COL_WIDTH,
        "minWidth": NUM_COL_WIDTH,
        "maxWidth": NUM_COL_WIDTH,
    },
    {
        "field": "W",
        "headerName": "W",
        "width": NUM_COL_WIDTH,
        "minWidth": NUM_COL_WIDTH,
        "maxWidth": NUM_COL_WIDTH,
    },
    {
        "field": "D",
        "headerName": "D",
        "width": NUM_COL_WIDTH,
        "minWidth": NUM_COL_WIDTH,
        "maxWidth": NUM_COL_WIDTH,
    },
    {
        "field": "L",
        "headerName": "L",
        "width": NUM_COL_WIDTH,
        "minWidth": NUM_COL_WIDTH,
        "maxWidth": NUM_COL_WIDTH,
    },
    {
        "field": "GF",
        "headerName": "GF",
        "width": NUM_COL_WIDTH,
        "minWidth": NUM_COL_WIDTH,
        "maxWidth": NUM_COL_WIDTH,
    },
    {
        "field": "GA",
        "headerName": "GA",
        "width": NUM_COL_WIDTH,
        "minWidth": NUM_COL_WIDTH,
        "maxWidth": NUM_COL_WIDTH,
    },
    {
        "field": "GD",
        "headerName": "GD",
        "width": NUM_COL_WIDTH,
        "minWidth": NUM_COL_WIDTH,
        "maxWidth": NUM_COL_WIDTH,
    },
    {
        "field": "Pts",
        "headerName": "Pts",
        "width": NUM_COL_WIDTH,
        "minWidth": NUM_COL_WIDTH,
        "maxWidth": NUM_COL_WIDTH,
    },
    {
        "field": "form",
        "headerName": "Form",
        "width": 168,
        "minWidth": 168,
        "cellRenderer": "FormCellRenderer",
        "sortable": False,
    },
]


def _options_from_model(model_class, value_attr, label_attr):
    """Build Dash dropdown options from a Django model queryset."""
    try:
        qs = model_class.objects.all()
        return [
            {"label": getattr(o, label_attr), "value": getattr(o, value_attr)}
            for o in qs
        ]
    except Exception:
        return []


def _dash_surface_colors() -> tuple[str, str]:
    """Return (page background, plot/chart background) for the active theme."""
    if _current_theme() == "light":
        return "#f0f4f4", "#ffffff"
    return "#1a2628", "#121a1b"


def layout_with_dropdowns():
    """Build layout with dropdowns and placeholder graph/grid. Options filled in callback."""
    theme = _current_theme()
    page_bg, _plot_bg = _dash_surface_colors()
    return html.Div(
        [
            dcc.Store(id="football-dash-init", data=0),
            html.Div(
                [
                    html.Label(
                        "League",
                        htmlFor=ID_LEAGUE_DROPDOWN,
                        style={"marginRight": "8px"},
                    ),
                    dcc.Dropdown(
                        id=ID_LEAGUE_DROPDOWN,
                        options=[],
                        value=None,
                        clearable=False,
                        className="football-dash-dropdown",
                        style=_dropdown_style("200px"),
                    ),
                    html.Label(
                        "Season",
                        htmlFor=ID_SEASON_DROPDOWN,
                        style={"marginLeft": "16px", "marginRight": "8px"},
                    ),
                    dcc.Dropdown(
                        id=ID_SEASON_DROPDOWN,
                        options=[],
                        value=None,
                        clearable=False,
                        className="football-dash-dropdown",
                        style=_dropdown_style("120px"),
                    ),
                    html.Label(
                        "Chart x-axis",
                        htmlFor=ID_X_AXIS_DROPDOWN,
                        style={"marginLeft": "16px", "marginRight": "8px"},
                    ),
                    dcc.Dropdown(
                        id=ID_X_AXIS_DROPDOWN,
                        options=[
                            {"label": "Games played", "value": "games_played"},
                            {"label": "Fixture (date)", "value": "fixture_date"},
                        ],
                        value="games_played",
                        clearable=False,
                        className="football-dash-dropdown",
                        style=_dropdown_style("140px"),
                    ),
                ],
                style={"marginBottom": "16px"},
            ),
            html.Div(id=ID_ERROR, style=_error_style()),
            dcc.Graph(
                id=ID_GRAPH,
                figure=_empty_figure("Loading…"),
                style={"marginBottom": "24px"},
            ),
            html.Div(
                [
                    html.H3("League table", style={"marginBottom": "8px"}),
                    dag.AgGrid(
                        id=ID_GRID,
                        rowData=[],
                        columnDefs=STANDINGS_COLUMN_DEFS,
                        defaultColDef={"sortable": True, "filter": True},
                        columnSize="sizeToFit",
                        className=_grid_theme_class(),
                        dashGridOptions=_grid_dash_options(),
                        style={"height": "480px", "width": "100%"},
                    ),
                ],
            ),
        ],
        className=f"football-dash-root football-dash-theme-{theme}",
        style={"padding": "16px", "backgroundColor": page_bg},
    )


app.layout = layout_with_dropdowns


@app.callback(
    [
        Output(ID_LEAGUE_DROPDOWN, "options"),
        Output(ID_LEAGUE_DROPDOWN, "value"),
        Output(ID_SEASON_DROPDOWN, "options"),
        Output(ID_SEASON_DROPDOWN, "value"),
    ],
    Input("football-dash-init", "data"),
    prevent_initial_call=False,
)
def _set_dropdown_options(_data):
    """Populate league/season dropdowns from DB and set initial values."""
    from .models import League, Season

    league_opts = _options_from_model(League, "id", "name")
    season_opts = _options_from_model(Season, "api_year", "display")
    first_league = league_opts[0]["value"] if league_opts else None
    first_season = season_opts[0]["value"] if season_opts else None
    return league_opts, first_league, season_opts, first_season


def _empty_figure(message: str):
    """Return a figure dict safe for dcc.Graph with a message (no data)."""
    template = _plotly_template()
    page_bg, plot_bg = _dash_surface_colors()
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


def _apply_plotly_theme(fig_or_dict, template: str | None = None):
    """Ensure Plotly figures use the active theme template."""
    template = template or _plotly_template()
    page_bg, plot_bg = _dash_surface_colors()
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


def _figure_to_json_safe_dict(fig):
    """Convert Plotly figure to a dict that serializes to JSON (fixes numpy/datetime types)."""
    import plotly.io as pio

    return pio.from_json(pio.to_json(fig))


@app.callback(
    [
        Output(ID_GRAPH, "figure"),
        Output(ID_GRID, "rowData"),
        Output(ID_ERROR, "children"),
    ],
    [
        Input(ID_LEAGUE_DROPDOWN, "value"),
        Input(ID_SEASON_DROPDOWN, "value"),
        Input(ID_X_AXIS_DROPDOWN, "value"),
    ],
    prevent_initial_call=False,
)
def _update_chart_and_grid(league_id, season, x_axis):
    """Load data for league/season and update points chart and standings grid.
    Prefers data_team_game view when available; falls back to fixtures from DB.
    """
    if league_id is None or season is None:
        return _empty_figure("Select league and season"), [], ""
    x_axis = x_axis or "games_played"
    theme = _current_theme()
    plotly_template = _plotly_template()
    cache_timeout = getattr(settings, "FOOTBALL_DASHBOARD_CACHE_TIMEOUT", 600)
    cache_key = (
        f"football:dash:{football_dashboard_cache_version()}:"
        f"{league_id}:{season}:{x_axis}:{theme}"
    )
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    team_games_df, view_err = _load_team_games_from_view(league_id, season)
    if team_games_df is not None and not team_games_df.empty:
        standings, fig, err = build_standings_and_figure(
            team_games_df=team_games_df,
            x_axis=x_axis,
            plotly_template=plotly_template,
        )
    else:
        df, err = _load_fixtures_from_db(league_id, season)
        if err or df is None or df.empty:
            return (
                _empty_figure(err or "No data"),
                [],
                err
                or "No fixtures for this league/season. Run the pipeline from Admin.",
            )
        standings, fig, err = build_standings_and_figure(
            df,
            x_axis=x_axis,
            plotly_template=plotly_template,
        )
    if err:
        return _empty_figure(err), [], err
    # Add rank (position) for AG Grid
    for i, row in enumerate(standings, start=1):
        row["rank"] = i
    # Use JSON round-trip so the figure is safe for the frontend (no numpy/datetime64)
    fig = _apply_plotly_theme(fig, plotly_template)
    figure = _figure_to_json_safe_dict(fig)
    result = (figure, standings, "")
    cache.set(cache_key, result, timeout=cache_timeout)
    return result
