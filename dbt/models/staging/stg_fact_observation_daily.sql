-- Atomic fact (qc_pass gold). Grain: station_id + date_key + element_code

select
    station_id,
    date_key,
    element_code,
    value,
    unit,
    mflag,
    sflag,
    cast(date as date) as date_day
from read_parquet('data/gold/facts/fact_observation_daily.parquet')
