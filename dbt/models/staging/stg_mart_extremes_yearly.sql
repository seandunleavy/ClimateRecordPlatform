select
    station_id,
    year,
    n_days_tmax_ge_32c,
    n_days_tmax_ge_35c,
    n_days_tmin_le_0c,
    n_days_prcp_ge_25mm,
    max_tmax_c,
    min_tmin_c,
    max_daily_prcp_mm,
    n_tmax_obs,
    n_tmin_obs,
    n_prcp_obs
from read_parquet('data/gold/marts/mart_extremes_yearly.parquet')
