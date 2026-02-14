"""
Django management command: ingest football fixtures from RapidAPI to MinIO.

Usage: python manage.py ingest_football [--league 39] [--season 2025]

Run from beara_bones (project root). football package is at repo root.
Repo root from data/management/commands/ingest_football.py = parents[4].
"""

import sys
from pathlib import Path

from django.core.management.base import BaseCommand

_repo_root = Path(__file__).resolve().parents[4]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from football.ingest import run_ingest  # noqa: E402 (import after path setup)


class Command(BaseCommand):
    help = "Fetch fixtures from RapidAPI and store raw JSON in MinIO"

    def add_arguments(self, parser):
        parser.add_argument(
            "--league",
            type=int,
            default=39,
            help="League ID (default: 39)",
        )
        parser.add_argument(
            "--season",
            type=int,
            default=2025,
            help="Season year (default: 2025)",
        )

    def handle(self, *args, **options):
        league = options["league"]
        season = options["season"]
        try:
            key = run_ingest(league=league, season=season)
            self.stdout.write(self.style.SUCCESS(f"Ingested to MinIO: {key}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(str(e)))
            raise SystemExit(1)
