select
    station_id,
    year,
    month,
    year_month_key,
    hdd_sum,
    cdd_sum,
    n_days_both_temps,
    avg_tavg_c,
    base_c
from read_parquet('data/gold/marts/mart_degree_days_monthly.parquet')
