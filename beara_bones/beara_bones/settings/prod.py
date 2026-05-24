"""Production settings (MariaDB, HTTPS). Used on Raspberry Pi behind NGINX."""

import os

from .base import *  # noqa: F403

_SECRET_KEY = os.getenv("DJANGO_SECRET_KEY")
if not _SECRET_KEY:
    raise ValueError("DJANGO_SECRET_KEY environment variable must be set in production")
SECRET_KEY = _SECRET_KEY

DEBUG = False

_allowed = os.getenv("ALLOWED_HOSTS", "").strip()
ALLOWED_HOSTS = [h.strip() for h in _allowed.split(",") if h.strip()]
if not ALLOWED_HOSTS:
    raise ValueError("ALLOWED_HOSTS must contain at least one host (e.g. itsbillw.eu)")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": os.getenv("DB_NAME"),
        "USER": os.getenv("DB_USER"),
        "PASSWORD": os.getenv("DB_PASSWORD"),
        "HOST": os.getenv("DB_HOST"),
        "PORT": os.getenv("DB_PORT"),
    },
}

SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 3600
SECURE_HSTS_PRELOAD = True
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
