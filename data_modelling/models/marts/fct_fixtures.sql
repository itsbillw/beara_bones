-- Mart: completed fixtures with result and goal difference (for dashboard).
select
    fixture_id,
    fixture_date,
    league_name,
    league_season,
    home_team_name,
    away_team_name,
    goals_home,
    goals_away,
    goals_home - goals_away as goal_diff_home,
    case
        when goals_home > goals_away then 'H'
        when goals_home < goals_away then 'A'
        else 'D'
    end as result
from {{ ref('stg_fixtures') }}
where status_short in ('FT', 'AET', 'PEN')  -- completed
  and goals_home is not null
  and goals_away is not null
