"""
Production Django settings for beara_bones.

Used on the server (e.g. Raspberry Pi / DietPi). Requires .env with
DJANGO_SECRET_KEY, ALLOWED_HOSTS, and DB_* (MariaDB). For local development
use settings_dev.py and set DJANGO_SETTINGS_MODULE=beara_bones.settings_dev.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Project root (directory containing manage.py).
BASE_DIR = Path(__file__).resolve().parent.parent

# --- Security & environment (required in production) ---
_SECRET_KEY = os.getenv("DJANGO_SECRET_KEY")
if not _SECRET_KEY:
    raise ValueError("DJANGO_SECRET_KEY environment variable must be set in production")
SECRET_KEY = _SECRET_KEY

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

_allowed = os.getenv("ALLOWED_HOSTS", "").strip()
ALLOWED_HOSTS = [h.strip() for h in _allowed.split(",") if h.strip()]
if not ALLOWED_HOSTS:
    raise ValueError("ALLOWED_HOSTS must contain at least one host (e.g. itsbillw.eu)")

# --- Apps & middleware ---

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_plotly_dash.apps.DjangoPlotlyDashConfig",
    "home",
    "data",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_plotly_dash.middleware.BaseMiddleware",
]

ROOT_URLCONF = "beara_bones.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "beara_bones.wsgi.application"

# --- Database (MariaDB; credentials from .env) ---
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

# --- Password validation ---
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# --- Internationalization ---
LANGUAGE_CODE = "en-us"

TIME_ZONE = "Europe/Madrid"

USE_I18N = True

USE_TZ = True

# --- Static & media (collectstatic writes to STATIC_ROOT) ---
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "static"
MEDIA_ROOT = BASE_DIR / "media"

# Use CDN for Dash assets (plotly, dash_ag_grid, etc.). Avoids 404s from local static.
PLOTLY_DASH = {"serve_locally": False}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Allow embedding Dash apps in same-origin frames
X_FRAME_OPTIONS = "SAMEORIGIN"

# --- HTTPS (site is behind NGINX/Certbot; Django trusts X-Forwarded-Proto) ---
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 3600
SECURE_HSTS_PRELOAD = True
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
# Ensure Django knows it's behind a proxy
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Hashed filenames for cache busting; use collectstatic --clear if static files don’t update.
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# Cache for football dashboard (avoids recomputing Plotly charts on every request)
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
        "LOCATION": BASE_DIR / "cache",
        "OPTIONS": {"MAX_ENTRIES": 100},
        "TIMEOUT": 600,
    },
}
FOOTBALL_DASHBOARD_CACHE_TIMEOUT = 600  # seconds
