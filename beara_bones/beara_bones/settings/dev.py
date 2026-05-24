"""Local development settings (SQLite, DEBUG=True)."""

import os

from .base import *  # noqa: F403

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-secret-key-not-for-production")
DEBUG = True
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",  # noqa: F405
    },
}

STATIC_ROOT.mkdir(parents=True, exist_ok=True)  # noqa: F405

SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
SECURE_PROXY_SSL_HEADER = None
