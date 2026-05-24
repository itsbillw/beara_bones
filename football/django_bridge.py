"""Single entry point for loading Django from the football CLI package."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_DJANGO_READY = False


def ensure_django() -> None:
    """Add beara_bones to sys.path once and call django.setup()."""
    global _DJANGO_READY
    if _DJANGO_READY:
        return

    beara_dir = Path(__file__).resolve().parents[1] / "beara_bones"
    beara_str = str(beara_dir)
    if beara_str not in sys.path:
        sys.path.insert(0, beara_str)

    os.environ.setdefault(
        "DJANGO_SETTINGS_MODULE",
        os.environ.get("DJANGO_SETTINGS_MODULE", "beara_bones.settings_dev"),
    )
    import django

    django.setup()
    _DJANGO_READY = True
