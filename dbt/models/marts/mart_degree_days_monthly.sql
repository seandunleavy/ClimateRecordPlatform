-- Fast-viz mart: monthly HDD/CDD by station (pre-aggregated in Python gold).

select * from {{ ref('stg_mart_degree_days_monthly') }}
