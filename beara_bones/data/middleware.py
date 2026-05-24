"""Expose the active Django request to Dash app code."""

from __future__ import annotations

from data.theme_context import set_django_request


class ThemeRequestMiddleware:
    """Make request.COOKIES available inside django_plotly_dash layout/callbacks."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        set_django_request(request)
        try:
            return self.get_response(request)
        finally:
            set_django_request(None)
