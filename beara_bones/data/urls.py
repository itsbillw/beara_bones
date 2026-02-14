"""
URL routing for the data app.

Included from project urls.py at '' so paths are at site root.
Use {% url 'data:data' %}, {% url 'data:data_fragment' %}, {% url 'data:data_refresh' %} in templates.
"""

from django.urls import path

from . import admin_views
from .views import data_fragment, data_page, data_refresh

app_name = "data"
urlpatterns = [
    path("data", data_page, name="data"),
    path("data/fragment", data_fragment, name="data_fragment"),
    path("data/refresh", data_refresh, name="data_refresh"),
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
