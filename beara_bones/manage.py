#!/usr/bin/env python
"""
Django management script. Run from this directory (beara_bones/).

Defaults to production settings. For local dev use:
  DJANGO_SETTINGS_MODULE=beara_bones.settings_dev python manage.py runserver
  or: make run-dev (from repo root)
"""

import os
import sys


def main():
    """Run administrative tasks."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "beara_bones.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?",
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
