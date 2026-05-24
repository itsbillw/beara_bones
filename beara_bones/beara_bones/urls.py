"""
Project URL configuration: admin and home app at site root.
"""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("", include("data.urls")),
    path("admin/", admin.site.urls),
    path("learning/", include("learning.urls")),
    path("", include("home.urls")),
]
