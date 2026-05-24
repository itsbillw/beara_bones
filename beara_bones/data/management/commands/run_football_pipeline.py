"""
Run full football pipeline for all League × Season pairs: ingest → transform → load to MariaDB → upload processed Parquet.
Uses a lock file to prevent overlapping runs.
"""

import sys
from pathlib import Path

from django.core.management.base import BaseCommand

_repo_root = Path(__file__).resolve().parents[4]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from data.pipeline_runner import run_with_pipeline_run  # noqa: E402
from football.locking import (  # noqa: E402
    acquire_lock,
    get_pipeline_lock_file,
    pipeline_lock,
)

LOCK_FILE = get_pipeline_lock_file()


class Command(BaseCommand):
    help = "Ingest (API → MinIO) → transform → load to MariaDB → upload processed Parquet for all League×Season"

    def handle(self, *args, **options):
        from data.loading import load_fixtures_dataframe
        from data.models import League, Season
        from football.ingest import run_ingest
        from football.processed import upload_processed_parquet
        from football.transform import run_transform

        LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
        if not acquire_lock(LOCK_FILE, fail_if_exists=True):
            self.stdout.write(
                self.style.ERROR(
                    f"Lock file exists; another run may be in progress. Remove {LOCK_FILE} to force.",
                ),
            )
            raise SystemExit(1)

        with pipeline_lock(LOCK_FILE):
            leagues = list(League.objects.all())
            seasons = list(Season.objects.all())
            if not leagues or not seasons:
                self.stdout.write(
                    self.style.WARNING("No League or Season in DB. Add them in Admin."),
                )
                return
            for league in leagues:
                for season in seasons:
                    lid = league.id
                    sy = season.api_year
                    self.stdout.write(
                        f"Processing league={lid} season={sy} ...",
                    )

                    def _execute() -> None:
                        df = run_transform(
                            league=lid,
                            season=sy,
                            write_files=False,
                        )
                        load_fixtures_dataframe(df, lid, sy)
                        upload_processed_parquet(df, lid, sy)

                    # Ingest outside the tracked run so raw data is always present.
                    run_ingest(league=lid, season=sy)
                    try:
                        run_with_pipeline_run(
                            league_id=lid,
                            season_year=sy,
                            source="mgmt_cmd_run_football_pipeline",
                            execute=_execute,
                        )
                    except Exception as exc:
                        self.stdout.write(
                            self.style.ERROR(
                                f"Pipeline failed for league={lid} season={sy}: {exc}",
                            ),
                        )
            try:
                from data.cache_utils import invalidate_football_dashboard_cache

                invalidate_football_dashboard_cache()
            except Exception:  # nosec B110
                pass
            self.stdout.write(self.style.SUCCESS("Pipeline completed."))
