"""
Plotly Dash app: Football dashboard with points chart and AG Grid league table.
Registered as DjangoDash so it can be embedded via {% plotly_app name="FootballDashboard" %}.
"""

import dash_ag_grid as dag
from dash import Input, Output, dcc, html
from django_plotly_dash import DjangoDash

from .dashboard_utils import build_standings_and_figure
from .views import _load_fixtures_from_db, _load_team_games_from_view

# Load Plotly.js from CDN so dcc.Graph works when serve_locally=False (avoids 404 for /static/.../plotly.min.js)
PLOTLY_JS_CDN = "https://cdn.plot.ly/plotly-2.27.0.min.js"
# Crest images in grid scaled to row height (served from Django static)
CREST_GRID_CSS = "/static/data/css/crest_grid.css"
# Form column cell renderer (must load in iframe where the grid runs)
FORM_RENDERER_JS = "/static/data/js/dashAgGridComponentFunctions.js"
app = DjangoDash(
    "FootballDashboard",
    add_bootstrap_links=False,
    external_scripts=[
        {"src": PLOTLY_JS_CDN},
        {"src": FORM_RENDERER_JS},
    ],
    external_stylesheets=[{"href": CREST_GRID_CSS, "rel": "stylesheet"}],
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


def layout_with_dropdowns():
    """Build layout with dropdowns and placeholder graph/grid. Options filled in callback."""
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
                        style={"minWidth": "200px", "display": "inline-block"},
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
                        style={"minWidth": "120px", "display": "inline-block"},
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
                        style={"minWidth": "140px", "display": "inline-block"},
                    ),
                ],
                style={"marginBottom": "16px"},
            ),
            html.Div(id=ID_ERROR, style={"color": "#856404", "marginBottom": "8px"}),
            dcc.Graph(
                id=ID_GRAPH,
                figure={"layout": {"height": 620}},
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
                        dashGridOptions={
                            "animateRows": True,
                            "rowHeight": STANDINGS_ROW_HEIGHT_PX,
                        },
                        style={"height": "480px", "width": "100%"},
                    ),
                ],
            ),
        ],
        style={"padding": "16px"},
    )


app.layout = layout_with_dropdowns()


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
    return {
        "data": [],
        "layout": {
            "height": 620,
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
    team_games_df, view_err = _load_team_games_from_view(league_id, season)
    if team_games_df is not None and not team_games_df.empty:
        standings, fig, err = build_standings_and_figure(
            team_games_df=team_games_df,
            x_axis=x_axis,
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
        standings, fig, err = build_standings_and_figure(df, x_axis=x_axis)
    if err:
        return _empty_figure(err), [], err
    # Add rank (position) for AG Grid
    for i, row in enumerate(standings, start=1):
        row["rank"] = i
    # Use JSON round-trip so the figure is safe for the frontend (no numpy/datetime64)
    figure = _figure_to_json_safe_dict(fig)
    return figure, standings, ""
