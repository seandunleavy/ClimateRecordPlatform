select
    station_id,
    year,
    freeze_threshold_c,
    n_tmin_obs,
    n_freeze_days,
    last_spring_freeze,
    first_fall_freeze,
    growing_season_days
from read_parquet('data/gold/marts/mart_freeze_season_yearly.parquet')
