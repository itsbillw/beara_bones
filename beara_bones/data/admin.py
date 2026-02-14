from django.contrib import admin

from .models import Fixture, League, Season


@admin.register(League)
class LeagueAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "order")
    ordering = ("order", "id")


@admin.register(Season)
class SeasonAdmin(admin.ModelAdmin):
    list_display = ("api_year", "display", "order")
    ordering = ("-api_year",)


@admin.register(Fixture)
class FixtureAdmin(admin.ModelAdmin):
    list_display = (
        "fixture_id",
        "league_id",
        "league_season",
        "home_team_name",
        "away_team_name",
        "goals_display",
    )
    list_filter = ("league_id", "league_season")
    search_fields = ("home_team_name", "away_team_name", "league_name")
    readonly_fields = (
        "fixture_id",
        "date",
        "timestamp",
        "venue_id",
        "venue_name",
        "status_short",
        "status_long",
        "league_id",
        "league_name",
        "league_season",
        "league_round",
        "home_team_id",
        "home_team_name",
        "away_team_id",
        "away_team_name",
        "goals_home",
        "goals_away",
    )

    def goals_display(self, obj):
        if obj.goals_home is not None and obj.goals_away is not None:
            return f"{obj.goals_home}-{obj.goals_away}"
        return "-"

    goals_display.short_description = "Score"  # type: ignore[attr-defined]
