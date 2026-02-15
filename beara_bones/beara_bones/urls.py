"""
Project URL configuration: admin and home app at site root.
"""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("", include("data.urls")),  # data, data/fragment, admin/data/pipeline, etc.
    path("django_plotly_dash/", include("django_plotly_dash.urls")),
    path("admin/", admin.site.urls),
    path("", include("home.urls")),
]
