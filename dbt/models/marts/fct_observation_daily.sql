-- Mart-layer fact for SQL consumers (DuckDB table materialization).
-- Same grain as staging; explicit star keys for joins / tests.

select
    station_id,
    date_key,
    element_code,
    value,
    unit,
    mflag,
    sflag,
    date_day
from {{ ref('stg_fact_observation_daily') }}
