"""Thread-local Django request for Dash callbacks (django_plotly_dash uses Django, not Flask)."""

from __future__ import annotations

from contextvars import ContextVar
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.http import HttpRequest

_django_request: ContextVar[HttpRequest | None] = ContextVar(
    "dash_django_request",
    default=None,
)


def set_django_request(request: HttpRequest | None) -> None:
    _django_request.set(request)


def get_django_request() -> HttpRequest | None:
    return _django_request.get()
