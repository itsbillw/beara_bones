"""
Run full football pipeline for all League × Season pairs: ingest → transform → load to MariaDB → upload processed Parquet.
Uses a lock file to prevent overlapping runs.
"""

import sys
from pathlib import Path

from django.core.management.base import BaseCommand
from django.core.cache import cache

_repo_root = Path(__file__).resolve().parents[4]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

LOCK_FILE = _repo_root / "data" / "football" / ".refresh.lock"


class Command(BaseCommand):
    help = "Ingest (API → MinIO) → transform → load to MariaDB → upload processed Parquet for all League×Season"

    def handle(self, *args, **options):
        from data.models import League, Season
        from data.loading import load_fixtures_dataframe
        from football.ingest import run_ingest
        from football.transform import run_transform
        from football.processed import upload_processed_parquet

        LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
        if LOCK_FILE.exists():
            self.stdout.write(self.style.ERROR(
                f"Lock file exists; another run may be in progress. Remove {LOCK_FILE} to force."
            ))
            raise SystemExit(1)

        try:
            LOCK_FILE.touch()
            leagues = list(League.objects.all())
            seasons = list(Season.objects.all())
            if not leagues or not seasons:
                self.stdout.write(self.style.WARNING("No League or Season in DB. Add them in Admin."))
                return
            for league in leagues:
                for season in seasons:
                    self.stdout.write(f"Processing league={league.id} season={season.api_year} ...")
                    run_ingest(league=league.id, season=season.api_year)
                    df = run_transform(league=league.id, season=season.api_year, write_files=False)
                    load_fixtures_dataframe(df, league.id, season.api_year)
                    upload_processed_parquet(df, league.id, season.api_year)
            # Clear dashboard cache so fragment refetches
            try:
                from django.conf import settings
                if hasattr(settings, "CACHES") and settings.CACHES:
                    cache.clear()
            except Exception:
                pass
            self.stdout.write(self.style.SUCCESS("Pipeline completed."))
        finally:
            if LOCK_FILE.exists():
                LOCK_FILE.unlink(missing_ok=True)
