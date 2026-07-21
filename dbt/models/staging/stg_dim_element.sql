select
    element_code,
    element_name,
    category,
    unit,
    source_scale
from read_parquet('data/gold/dims/dim_element.parquet')
