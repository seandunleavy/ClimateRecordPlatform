"""
DuckDB access for the API.

Prefers querying gold Parquet directly (always present after pipeline).
Optional: attach dbt DuckDB file if it exists — not required.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import duckdb

from src.common.paths import GOLD_DIMS, GOLD_FACTS, GOLD_MARTS, ROOT

DUCKDB_PATH = ROOT / "data" / "gold" / "climate_record.duckdb"


@lru_cache(maxsize=1)
def parquet_paths() -> dict[str, Path]:
    return {
        "dim_station": GOLD_DIMS / "dim_station.parquet",
        "degree_days": GOLD_MARTS / "mart_degree_days_monthly.parquet",
        "extremes": GOLD_MARTS / "mart_extremes_yearly.parquet",
        "freeze": GOLD_MARTS / "mart_freeze_season_yearly.parquet",
        "fact_daily": GOLD_FACTS / "fact_observation_daily.parquet",
    }


def require_gold() -> None:
    missing = [k for k, p in parquet_paths().items() if k != "fact_daily" and not p.exists()]
    if missing:
        raise FileNotFoundError(
            "Missing gold Parquet: "
            + ", ".join(missing)
            + ". Run silver_to_gold first."
        )


def connect() -> duckdb.DuckDBPyConnection:
    """In-memory DuckDB that can read Parquet; no write to warehouse files."""
    require_gold()
    return duckdb.connect(database=":memory:")


def pq(name: str) -> str:
    """SQL literal path for read_parquet (forward slashes for DuckDB on Windows)."""
    path = parquet_paths()[name]
    if not path.exists():
        raise FileNotFoundError(f"Missing {path}")
    return str(path.resolve()).replace("\\", "/")
