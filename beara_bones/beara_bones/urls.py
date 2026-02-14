"""
Project URL configuration: admin and home app at site root.
"""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("data.urls")),  # data, data/fragment, data/refresh
    path("", include("home.urls")),
]
