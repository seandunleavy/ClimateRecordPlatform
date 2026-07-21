-- Staging: conformed station dimension from gold Parquet.
-- Paths are relative to the DuckDB working directory (dbt project dir).

select
    station_id,
    name,
    state,
    latitude,
    longitude,
    elevation_m,
    network_prefix
from read_parquet('data/gold/dims/dim_station.parquet')
