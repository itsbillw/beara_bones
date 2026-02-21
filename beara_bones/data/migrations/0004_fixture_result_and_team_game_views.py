# Migration: create data_fixture_result and data_team_game views for Metabase/dashboards.
# Views are read-only; no Django models. Reverse drops views in dependency order.
# Uses RunPython so we can branch: SQLite has no "CREATE OR REPLACE VIEW", so we
# use DROP VIEW IF EXISTS then CREATE VIEW for SQLite; MariaDB/MySQL use CREATE OR REPLACE.

from django.db import migrations

VIEW_FIXTURE_RESULT_BODY = """
SELECT
    fixture_id,
    date,
    timestamp,
    venue_id,
    venue_name,
    status_short,
    status_long,
    league_id,
    league_name,
    league_season,
    league_round,
    home_team_id,
    home_team_name,
    away_team_id,
    away_team_name,
    goals_home,
    goals_away,
    (goals_home - goals_away) AS goal_diff_home,
    CASE
        WHEN goals_home > goals_away THEN 'H'
        WHEN goals_home < goals_away THEN 'A'
        ELSE 'D'
    END AS result,
    CASE
        WHEN goals_home > goals_away THEN 3
        WHEN goals_home < goals_away THEN 0
        ELSE 1
    END AS pts_home,
    CASE
        WHEN goals_home < goals_away THEN 3
        WHEN goals_home > goals_away THEN 0
        ELSE 1
    END AS pts_away
FROM data_fixture
WHERE status_short IN ('FT', 'AET', 'PEN')
  AND goals_home IS NOT NULL
  AND goals_away IS NOT NULL
"""

VIEW_TEAM_GAME_BODY = """
SELECT
    league_id,
    league_season,
    fixture_id,
    fixture_date,
    team_id,
    team_name,
    opponent_id,
    opponent_name,
    venue,
    goals_for,
    goals_against,
    pts,
    result_letter,
    ROW_NUMBER() OVER (
        PARTITION BY league_id, league_season, team_name
        ORDER BY fixture_date
    ) AS game_number,
    SUM(pts) OVER (
        PARTITION BY league_id, league_season, team_name
        ORDER BY fixture_date
    ) AS cumulative_pts
FROM (
    SELECT
        league_id,
        league_season,
        fixture_id,
        date AS fixture_date,
        home_team_id AS team_id,
        home_team_name AS team_name,
        away_team_id AS opponent_id,
        away_team_name AS opponent_name,
        'Home' AS venue,
        goals_home AS goals_for,
        goals_away AS goals_against,
        CASE WHEN goals_home > goals_away THEN 3 WHEN goals_home < goals_away THEN 0 ELSE 1 END AS pts,
        CASE WHEN goals_home > goals_away THEN 'W' WHEN goals_home < goals_away THEN 'L' ELSE 'D' END AS result_letter
    FROM data_fixture
    WHERE status_short IN ('FT', 'AET', 'PEN')
      AND goals_home IS NOT NULL
      AND goals_away IS NOT NULL
    UNION ALL
    SELECT
        league_id,
        league_season,
        fixture_id,
        date AS fixture_date,
        away_team_id AS team_id,
        away_team_name AS team_name,
        home_team_id AS opponent_id,
        home_team_name AS opponent_name,
        'Away' AS venue,
        goals_away AS goals_for,
        goals_home AS goals_against,
        CASE WHEN goals_away > goals_home THEN 3 WHEN goals_away < goals_home THEN 0 ELSE 1 END AS pts,
        CASE WHEN goals_away > goals_home THEN 'W' WHEN goals_away < goals_home THEN 'L' ELSE 'D' END AS result_letter
    FROM data_fixture
    WHERE status_short IN ('FT', 'AET', 'PEN')
      AND goals_home IS NOT NULL
      AND goals_away IS NOT NULL
) AS unpivoted
"""


def create_views(apps, schema_editor):
    vendor = schema_editor.connection.vendor
    if vendor == "sqlite":
        schema_editor.execute("DROP VIEW IF EXISTS data_fixture_result")
        schema_editor.execute(
            "CREATE VIEW data_fixture_result AS" + VIEW_FIXTURE_RESULT_BODY,
        )
        schema_editor.execute("DROP VIEW IF EXISTS data_team_game")
        schema_editor.execute("CREATE VIEW data_team_game AS" + VIEW_TEAM_GAME_BODY)
    else:
        # mysql, mariadb
        schema_editor.execute(
            "CREATE OR REPLACE VIEW data_fixture_result AS" + VIEW_FIXTURE_RESULT_BODY,
        )
        schema_editor.execute(
            "CREATE OR REPLACE VIEW data_team_game AS" + VIEW_TEAM_GAME_BODY,
        )


def drop_views(apps, schema_editor):
    schema_editor.execute("DROP VIEW IF EXISTS data_team_game")
    schema_editor.execute("DROP VIEW IF EXISTS data_fixture_result")


class Migration(migrations.Migration):
    dependencies = [
        ("data", "0003_pipelinerun"),
    ]

    operations = [
        migrations.RunPython(create_views, drop_views),
    ]
