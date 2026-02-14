-- Staging: cast types, rename columns for clarity.
with source as (
    select * from {{ source('raw', 'fixtures') }}
)
select
    fixture_id,
    date::date as fixture_date,
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
    goals_home::int as goals_home,
    goals_away::int as goals_away
from source
