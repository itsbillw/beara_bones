"""URL routing for the data app."""

from django.urls import path

from . import admin_views
from .views import (
    crest_serve,
    dashboard_panel,
    data_page,
    data_refresh,
    pipeline_activity,
    pipeline_status,
)

app_name = "data"
urlpatterns = [
    path("data", data_page, name="data"),
    path("data/panel", dashboard_panel, name="dashboard_panel"),
    path("data/crest/<int:team_id>/", crest_serve, name="crest"),
    path("data/refresh", data_refresh, name="data_refresh"),
    path("data/pipeline/status", pipeline_status, name="pipeline_status"),
    path("data/pipeline/activity", pipeline_activity, name="pipeline_activity"),
    path("admin/data/pipeline/", admin_views.pipeline_control, name="admin_pipeline"),
    path(
        "admin/data/pipeline/refresh/",
        admin_views.pipeline_refresh,
        name="admin_pipeline_refresh",
    ),
    path(
        "admin/data/pipeline/rebuild/",
        admin_views.pipeline_rebuild,
        name="admin_pipeline_rebuild",
    ),
]
