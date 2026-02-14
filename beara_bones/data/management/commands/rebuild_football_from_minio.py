"""
Rebuild football data in MariaDB from MinIO (no API calls).
For each League×Season: try processed Parquet first (load only); else try raw JSON (transform + load + upload processed).
Uses same lock file as run_football_pipeline.
"""

import sys
from pathlib import Path

from django.core.management.base import BaseCommand

_repo_root = Path(__file__).resolve().parents[4]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

LOCK_FILE = _repo_root / "data" / "football" / ".refresh.lock"


def _object_exists(bucket: str, key: str) -> bool:
    from football.ingest import get_client
    try:
        get_client().stat_object(bucket, key)
        return True
    except Exception:
        return False


class Command(BaseCommand):
    help = "Rebuild MariaDB from MinIO (processed Parquet or raw JSON) for all League×Season"

    def handle(self, *args, **options):
        import os
        from data.models import League, Season
        from data.loading import load_fixtures_dataframe
        from football.transform import run_transform
        from football.processed import load_processed_parquet_from_minio, upload_processed_parquet

        raw_bucket = os.environ.get("MINIO_BUCKET", "football") or "football"
        processed_bucket = os.environ.get("MINIO_BUCKET_PROCESSED", "football-processed")

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
                    lid, say = league.id, season.api_year
                    # Prefer processed Parquet (faster)
                    df = load_processed_parquet_from_minio(lid, say, bucket=processed_bucket)
                    if df is not None and not df.empty:
                        self.stdout.write(f"Loading from processed: league={lid} season={say}")
                        load_fixtures_dataframe(df, lid, say)
                        continue
                    # Fall back to raw JSON
                    key = f"raw/league_{lid}_season_{say}.json"
                    if not _object_exists(raw_bucket, key):
                        self.stdout.write(self.style.WARNING(f"No raw or processed data for league={lid} season={say}; skipping."))
                        continue
                    self.stdout.write(f"Rebuilding from raw: league={lid} season={say}")
                    df = run_transform(bucket=raw_bucket, object_key=key, league=lid, season=say, write_files=False)
                    load_fixtures_dataframe(df, lid, say)
                    upload_processed_parquet(df, lid, say, bucket=processed_bucket)
            self.stdout.write(self.style.SUCCESS("Rebuild completed."))
        finally:
            if LOCK_FILE.exists():
                LOCK_FILE.unlink(missing_ok=True)
