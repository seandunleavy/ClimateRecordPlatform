"""
Climate Record Platform — read-only API over gold marts (and optional daily fact).

Stack:
  FastAPI + DuckDB reading gold Parquet (same marts as the static web export).

Run (from repo root, venv active):
  uvicorn src.api.main:app --reload --port 8080

Docs:
  http://127.0.0.1:8080/docs
"""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from src.api.db import connect, pq, require_gold

app = FastAPI(
    title="Climate Record Platform API",
    description=(
        "Read-only queries over gold dimensional marts built from NOAA GHCNd. "
        "Heavy history stays in Parquet; each request returns a filtered slice."
    ),
    version="0.1.0",
)

# Local explorer / future Dunleavy static page on another port
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


def _rows(con, sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
    cur = con.execute(sql, params or [])
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


@app.get("/health")
def health() -> dict[str, Any]:
    try:
        require_gold()
        paths_ok = True
        detail = "gold parquet present"
    except FileNotFoundError as e:
        paths_ok = False
        detail = str(e)
    return {"status": "ok" if paths_ok else "degraded", "detail": detail}


@app.get("/stations")
def list_stations() -> list[dict[str, Any]]:
    """Station dimension — full sample list."""
    try:
        con = connect()
        return _rows(
            con,
            f"""
            select station_id, name, state, latitude, longitude, elevation_m, network_prefix
            from read_parquet('{pq("dim_station")}')
            order by state, name
            """,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e


@app.get("/degree-days")
def degree_days(
    station_id: str = Query(..., description="GHCNd station id, e.g. USW00013872"),
    year_from: int | None = Query(None, ge=1800, le=2100),
    year_to: int | None = Query(None, ge=1800, le=2100),
) -> dict[str, Any]:
    """
    Monthly heating/cooling degree-days for one station.
    Optional year_from / year_to filter (inclusive).
    """
    try:
        con = connect()
        clauses = ["station_id = ?"]
        params: list[Any] = [station_id]
        if year_from is not None:
            clauses.append("year >= ?")
            params.append(year_from)
        if year_to is not None:
            clauses.append("year <= ?")
            params.append(year_to)
        where = " and ".join(clauses)
        data = _rows(
            con,
            f"""
            select station_id, year, month, year_month_key,
                   hdd_sum, cdd_sum, n_days_both_temps, avg_tavg_c, base_c
            from read_parquet('{pq("degree_days")}')
            where {where}
            order by year, month
            """,
            params,
        )
        return {
            "station_id": station_id,
            "year_from": year_from,
            "year_to": year_to,
            "count": len(data),
            "rows": data,
        }
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e


@app.get("/extremes")
def extremes(
    station_id: str = Query(...),
    year_from: int | None = Query(None, ge=1800, le=2100),
    year_to: int | None = Query(None, ge=1800, le=2100),
) -> dict[str, Any]:
    """Yearly extreme-day counts for one station."""
    try:
        con = connect()
        clauses = ["station_id = ?"]
        params: list[Any] = [station_id]
        if year_from is not None:
            clauses.append("year >= ?")
            params.append(year_from)
        if year_to is not None:
            clauses.append("year <= ?")
            params.append(year_to)
        where = " and ".join(clauses)
        data = _rows(
            con,
            f"""
            select station_id, year,
                   n_days_tmax_ge_32c, n_days_tmax_ge_35c,
                   n_days_tmin_le_0c, n_days_prcp_ge_25mm,
                   max_tmax_c, min_tmin_c, max_daily_prcp_mm,
                   n_tmax_obs, n_tmin_obs, n_prcp_obs
            from read_parquet('{pq("extremes")}')
            where {where}
            order by year
            """,
            params,
        )
        return {
            "station_id": station_id,
            "year_from": year_from,
            "year_to": year_to,
            "count": len(data),
            "rows": data,
        }
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e


@app.get("/freeze-season")
def freeze_season(
    station_id: str = Query(...),
    year_from: int | None = Query(None, ge=1800, le=2100),
    year_to: int | None = Query(None, ge=1800, le=2100),
) -> dict[str, Any]:
    """Yearly freeze-season metrics for one station."""
    try:
        con = connect()
        clauses = ["station_id = ?"]
        params: list[Any] = [station_id]
        if year_from is not None:
            clauses.append("year >= ?")
            params.append(year_from)
        if year_to is not None:
            clauses.append("year <= ?")
            params.append(year_to)
        where = " and ".join(clauses)
        data = _rows(
            con,
            f"""
            select station_id, year, freeze_threshold_c,
                   n_tmin_obs, n_freeze_days,
                   last_spring_freeze, first_fall_freeze, growing_season_days
            from read_parquet('{pq("freeze")}')
            where {where}
            order by year
            """,
            params,
        )
        return {
            "station_id": station_id,
            "year_from": year_from,
            "year_to": year_to,
            "count": len(data),
            "rows": data,
        }
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e


@app.get("/observations")
def observations(
    station_id: str = Query(...),
    element: str = Query("TMAX", description="TMAX, TMIN, or PRCP"),
    date_from: str | None = Query(None, description="YYYY-MM-DD"),
    date_to: str | None = Query(None, description="YYYY-MM-DD"),
    limit: int = Query(500, ge=1, le=5000),
) -> dict[str, Any]:
    """
    Daily fact drill-down (qc_pass gold only). Capped by limit for safety.
    This is the 'all data on demand' path without shipping the full fact to the browser.
    """
    try:
        con = connect()
        element = element.upper()
        if element not in {"TMAX", "TMIN", "PRCP"}:
            raise HTTPException(status_code=400, detail="element must be TMAX, TMIN, or PRCP")
        clauses = ["station_id = ?", "element_code = ?"]
        params: list[Any] = [station_id, element]
        if date_from:
            clauses.append("cast(date as date) >= cast(? as date)")
            params.append(date_from)
        if date_to:
            clauses.append("cast(date as date) <= cast(? as date)")
            params.append(date_to)
        where = " and ".join(clauses)
        data = _rows(
            con,
            f"""
            select station_id, date_key, element_code, value, unit,
                   cast(date as varchar) as date
            from read_parquet('{pq("fact_daily")}')
            where {where}
            order by date_key
            limit ?
            """,
            params + [limit],
        )
        return {
            "station_id": station_id,
            "element": element,
            "date_from": date_from,
            "date_to": date_to,
            "limit": limit,
            "count": len(data),
            "rows": data,
        }
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=503,
            detail=str(e) + " Rebuild gold with fact_observation_daily if missing.",
        ) from e
