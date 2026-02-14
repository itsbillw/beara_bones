from django.db import migrations


def seed_league_season(apps, schema_editor):
    League = apps.get_model("data", "League")
    Season = apps.get_model("data", "Season")
    League.objects.get_or_create(id=39, defaults={"name": "Premier League", "order": 0})
    Season.objects.get_or_create(
        api_year=2025,
        defaults={"display": "2025/26", "order": 0},
    )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("data", "0001_football_league_season_fixture"),
    ]

    operations = [
        migrations.RunPython(seed_league_season, noop),
    ]
