"""
Django management command: ingest football fixtures from RapidAPI to MinIO.
Usage: python manage.py ingest_football [--league 39] [--season 2025]
"""
import sys

from django.core.management.base import BaseCommand

# Run from beara_bones (project root); football package at repo root
# Repo root (football package) is beara_bones/../ = parents[4]
_repo_root = __import__("pathlib").Path(__file__).resolve().parents[4]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from football.ingest import run_ingest


class Command(BaseCommand):
    help = "Fetch fixtures from RapidAPI and store raw JSON in MinIO"

    def add_arguments(self, parser):
        parser.add_argument("--league", type=int, default=39, help="League ID (default: 39)")
        parser.add_argument("--season", type=int, default=2025, help="Season year (default: 2025)")

    def handle(self, *args, **options):
        league = options["league"]
        season = options["season"]
        try:
            key = run_ingest(league=league, season=season)
            self.stdout.write(self.style.SUCCESS(f"Ingested to MinIO: {key}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(str(e)))
            raise SystemExit(1)
