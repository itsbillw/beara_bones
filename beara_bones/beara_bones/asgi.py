"""
ASGI entry point for async servers (e.g. uvicorn).

Exposes `application` for the ASGI server. Required for async views.
"""
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "beara_bones.settings")

application = get_asgi_application()
