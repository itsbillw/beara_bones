from django.db import models


class League(models.Model):
    """API league id and display name. Used for pipeline and dashboard dropdowns."""

    id = models.IntegerField(
        primary_key=True,
    )  # API league id (e.g. 39 = Premier League)
    name = models.CharField(max_length=255)
    order = models.PositiveSmallIntegerField(default=0, help_text="Dropdown order")

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.name


class Season(models.Model):
    """Season by API year with display label (e.g. 2025 -> 2025/26)."""

    api_year = models.IntegerField(unique=True)  # What the API uses (e.g. 2025)
    display = models.CharField(max_length=20)  # e.g. "2025/26"
    order = models.PositiveSmallIntegerField(
        default=0,
        help_text="Dropdown order, higher = more recent",
    )

    class Meta:
        ordering = ["-api_year"]

    def __str__(self):
        return self.display


class Fixture(models.Model):
    """One row per fixture; matches transform output. Filter by league_id + league_season."""

    fixture_id = models.BigIntegerField(db_index=True)
    date = models.DateTimeField(null=True, blank=True)
    timestamp = models.BigIntegerField(null=True, blank=True)
    venue_id = models.IntegerField(null=True, blank=True)
    venue_name = models.CharField(max_length=255, blank=True)
    status_short = models.CharField(max_length=20, blank=True)
    status_long = models.CharField(max_length=100, blank=True)
    league_id = models.IntegerField(db_index=True)
    league_name = models.CharField(max_length=255, blank=True)
    league_season = models.IntegerField(db_index=True)
    league_round = models.CharField(max_length=100, blank=True)
    home_team_id = models.IntegerField(null=True, blank=True)
    home_team_name = models.CharField(max_length=255, blank=True)
    away_team_id = models.IntegerField(null=True, blank=True)
    away_team_name = models.CharField(max_length=255, blank=True)
    goals_home = models.IntegerField(null=True, blank=True)
    goals_away = models.IntegerField(null=True, blank=True)

    class Meta:
        db_table = "data_fixture"
        ordering = ["league_id", "league_season", "date"]
        indexes = [
            models.Index(fields=["league_id", "league_season"]),
        ]

    def __str__(self):
        return f"{self.home_team_name} v {self.away_team_name} ({self.league_season})"


class PipelineRun(models.Model):
    """Tracks executions of the football data pipeline per League×Season."""

    class Status(models.TextChoices):
        RUNNING = "RUNNING", "Running"
        SUCCESS = "SUCCESS", "Success"
        FAILED = "FAILED", "Failed"
        PARTIAL_SUCCESS = "PARTIAL_SUCCESS", "Partial success"

    league_id = models.IntegerField(null=True, blank=True, help_text="API league id")
    season_year = models.IntegerField(
        null=True,
        blank=True,
        help_text="Season year as used by the API (e.g. 2025).",
    )
    source = models.CharField(
        max_length=50,
        blank=True,
        help_text="Trigger source, e.g. admin_button, mgmt_cmd, api_refresh, cli.",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.RUNNING,
    )
    error_summary = models.TextField(blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at", "-id"]
        indexes = [
            models.Index(fields=["league_id", "season_year", "started_at"]),
        ]

    def __str__(self) -> str:
        scope = []
        if self.league_id is not None:
            scope.append(f"league={self.league_id}")
        if self.season_year is not None:
            scope.append(f"season={self.season_year}")
        scope_str = " ".join(scope) if scope else "global"
        return f"PipelineRun({scope_str}, status={self.status})"
