"""
URLs config for beara_bones project.
"""

from django.urls import path

from . import views

APP_NAME = "main"
urlpatterns = [
    # Home page.
    path("", views.index, name="index"),
]
