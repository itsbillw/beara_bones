"""
WSGI entry point for production (e.g. gunicorn).

Exposes `application` for the WSGI server. Uses production settings by default.
"""
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "beara_bones.settings")

application = get_wsgi_application()
