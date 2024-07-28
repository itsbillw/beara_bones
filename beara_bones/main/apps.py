"""
This module configures the main application.
"""

from django.apps import AppConfig


class MainConfig(AppConfig):
    """Configuration for the main application."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "main"
