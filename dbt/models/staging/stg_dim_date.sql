select
    date_key,
    cast(date as date) as date_day,
    year,
    quarter,
    month,
    month_name,
    day,
    day_of_year,
    day_of_week,
    day_name,
    is_weekend,
    year_month,
    year_month_key,
    season
from read_parquet('data/gold/dims/dim_date.parquet')
