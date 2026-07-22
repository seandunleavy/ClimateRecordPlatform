"""
Phase 3 — gold star schema + analytics marts (qc_pass silver only).

Star (atomic):
  dim_station ──┐
  dim_date    ──┼── fact_observation_daily
  dim_element ──┘

Marts (pre-aggregated for fast charts — same as aggregate facts):
  mart_monthly_climate, mart_degree_days_monthly, mart_coverage_yearly,
  mart_freeze_season_yearly, mart_extremes_yearly

Nationwide scale: process one station QC file at a time (do not load all
~500M qc_pass rows into RAM). Fact is streamed with a ParquetWriter.

Degree-day method:
  tavg ≈ (TMAX+TMIN)/2; HDD=max(0,base-tavg); CDD=max(0,tavg-base); base default 18°C

Freeze-season (calendar year):
  freeze if TMIN<=0; last spring freeze month<=6; first fall freeze month>=7

Examples:
  python -m src.transform.silver_to_gold
  python -m src.transform.silver_to_gold --skip-fact
  python -m src.transform.silver_to_gold --station USW00013872
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from src.common.paths import (
    BRONZE_META,
    GOLD_DIMS,
    GOLD_FACTS,
    GOLD_MARTS,
    META,
    SILVER_STATIONS_QC,
)

DEFAULT_BASE_C = 18.0
HOT_DAY_TMAX_C = 32.0
VERY_HOT_TMAX_C = 35.0
FREEZE_TMIN_C = 0.0
WET_DAY_PRCP_MM = 25.4

# Catalog for dim_element (extend when silver keeps more elements)
ELEMENT_CATALOG: list[dict] = [
    {
        "element_code": "TMAX",
        "element_name": "Daily maximum temperature",
        "category": "temperature",
        "unit": "C",
        "source_scale": "tenths of degrees C",
    },
    {
        "element_code": "TMIN",
        "element_name": "Daily minimum temperature",
        "category": "temperature",
        "unit": "C",
        "source_scale": "tenths of degrees C",
    },
    {
        "element_code": "PRCP",
        "element_name": "Daily precipitation",
        "category": "precipitation",
        "unit": "mm",
        "source_scale": "tenths of mm",
    },
]


def list_qc_paths(station_ids: list[str] | None) -> list[Path]:
    """Paths to station QC Parquet files (one file per station)."""
    paths = sorted(SILVER_STATIONS_QC.glob("*.parquet"))
    if not paths:
        raise SystemExit(
            f"No QC Parquet under {SILVER_STATIONS_QC}. "
            "Run: python -m src.transform.apply_qc --all"
        )
    if station_ids:
        want = set(station_ids)
        paths = [p for p in paths if p.stem in want]
        if not paths:
            raise SystemExit(f"No QC files for stations={station_ids}")
    return paths


def load_qc_pass_station(path: Path) -> pd.DataFrame:
    """Load one station QC file; return qc_pass rows only."""
    df = pd.read_parquet(path)
    if "qc_pass" not in df.columns:
        raise SystemExit(f"{path.name} missing qc_pass; re-run apply_qc")
    out = df.loc[df["qc_pass"]].copy()
    if not out.empty:
        out["date"] = pd.to_datetime(out["date"])
    return out


def load_qc_frames(station_ids: list[str] | None) -> pd.DataFrame:
    """Load QC Parquet into one frame (small subsets only — not nationwide)."""
    paths = list_qc_paths(station_ids)
    if len(paths) > 50 and not station_ids:
        raise SystemExit(
            "Refusing to load all stations into one DataFrame (nationwide OOM risk). "
            "Use the streaming gold build in main(), or pass --station for a sample."
        )
    frames = [load_qc_pass_station(p) for p in paths]
    frames = [f for f in frames if not f.empty]
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def build_dim_station(station_ids: list[str]) -> pd.DataFrame:
    """
    Station dimension (conformed). Natural key: station_id (GHCNd ID is stable).
    """
    stations_path = BRONZE_META / "ghcnd-stations.txt"
    if not stations_path.exists():
        raise SystemExit(f"Missing {stations_path}; run download_ghcnd_meta")

    want = set(station_ids)
    rows = []
    for line in stations_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if len(line) < 41:
            continue
        sid = line[0:11].strip()
        if sid not in want:
            continue
        try:
            lat = float(line[12:20].strip())
            lon = float(line[21:30].strip())
        except ValueError:
            lat, lon = None, None
        elev_raw = line[31:37].strip()
        try:
            elev_m = float(elev_raw) if elev_raw else None
        except ValueError:
            elev_m = None
        rows.append(
            {
                "station_id": sid,
                "latitude": lat,
                "longitude": lon,
                "elevation_m": elev_m,
                "state": line[38:40].strip().upper(),
                "name": line[41:71].strip(),
                "network_prefix": sid[:3],
            }
        )
    dim = pd.DataFrame(rows)
    if not dim.empty:
        dim = dim.sort_values("station_id").reset_index(drop=True)
    return dim


def build_dim_date(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """
    Date dimension. Key: date_key INT YYYYMMDD (BI-friendly join key).
    Built for full calendar span covering the fact data.
    """
    days = pd.date_range(start=start.normalize(), end=end.normalize(), freq="D")
    dim = pd.DataFrame({"date": days})
    dim["date_key"] = dim["date"].dt.strftime("%Y%m%d").astype(int)
    dim["year"] = dim["date"].dt.year
    dim["quarter"] = dim["date"].dt.quarter
    dim["month"] = dim["date"].dt.month
    dim["month_name"] = dim["date"].dt.month_name()
    dim["day"] = dim["date"].dt.day
    dim["day_of_year"] = dim["date"].dt.dayofyear
    dim["day_of_week"] = dim["date"].dt.dayofweek  # Mon=0
    dim["day_name"] = dim["date"].dt.day_name()
    dim["is_weekend"] = dim["day_of_week"] >= 5
    dim["year_month"] = dim["date"].dt.strftime("%Y-%m")
    dim["year_month_key"] = dim["date"].dt.strftime("%Y%m").astype(int)
    # Meteorological season (NH): DJF winter, MAM spring, JJA summer, SON fall
    season_map = {
        12: "winter",
        1: "winter",
        2: "winter",
        3: "spring",
        4: "spring",
        5: "spring",
        6: "summer",
        7: "summer",
        8: "summer",
        9: "fall",
        10: "fall",
        11: "fall",
    }
    dim["season"] = dim["month"].map(season_map)
    return dim[
        [
            "date_key",
            "date",
            "year",
            "quarter",
            "month",
            "month_name",
            "day",
            "day_of_year",
            "day_of_week",
            "day_name",
            "is_weekend",
            "year_month",
            "year_month_key",
            "season",
        ]
    ]


def build_dim_element() -> pd.DataFrame:
    """Element dimension — measurement type catalog."""
    return pd.DataFrame(ELEMENT_CATALOG)


def build_fact_observation_daily(qc_pass: pd.DataFrame) -> pd.DataFrame:
    """
    Atomic fact — grain: station_id + date_key + element_code.

    FK-style columns (natural keys):
      station_id   -> dim_station.station_id
      date_key     -> dim_date.date_key
      element_code -> dim_element.element_code

    Degenerate dims (kept on fact): mflag, sflag (source lineage, low cardinality).
    """
    fact = qc_pass.loc[
        :,
        [c for c in ("station_id", "date", "element", "value", "unit", "mflag", "sflag") if c in qc_pass.columns],
    ].copy()
    fact = fact.rename(columns={"element": "element_code"})
    fact["date_key"] = fact["date"].dt.strftime("%Y%m%d").astype(int)
    # Measure + keys only (date kept for convenience / partition peeks; optional)
    cols = [
        "station_id",
        "date_key",
        "element_code",
        "value",
        "unit",
        "mflag",
        "sflag",
        "date",
    ]
    fact = fact[[c for c in cols if c in fact.columns]]
    fact = fact.sort_values(["station_id", "date_key", "element_code"]).reset_index(drop=True)
    return fact


def _add_month_keys(df: pd.DataFrame) -> pd.DataFrame:
    """Add year_month_key for mart ↔ dim_date month grain joins."""
    out = df.copy()
    out["year_month_key"] = (out["year"] * 100 + out["month"]).astype(int)
    return out


def build_mart_monthly_climate(qc_pass: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate fact / mart — grain: station_id + year + month.
    Fast path for monthly climate charts.
    """
    df = qc_pass.copy()
    df["year"] = df["date"].dt.year
    df["month"] = df["date"].dt.month

    parts = []
    for element, value_col, agg in (
        ("TMAX", "avg_tmax_c", "mean"),
        ("TMIN", "avg_tmin_c", "mean"),
        ("PRCP", "total_prcp_mm", "sum"),
    ):
        sub = df.loc[df["element"] == element, ["station_id", "year", "month", "value"]]
        if sub.empty:
            continue
        g = sub.groupby(["station_id", "year", "month"], as_index=False)
        if agg == "mean":
            tmp = g["value"].mean().rename(columns={"value": value_col})
        else:
            tmp = g["value"].sum().rename(columns={"value": value_col})
        cnt = (
            sub.groupby(["station_id", "year", "month"], as_index=False)
            .size()
            .rename(columns={"size": f"n_days_{element.lower()}"})
        )
        tmp = tmp.merge(cnt, on=["station_id", "year", "month"], how="left")
        parts.append(tmp)

    if not parts:
        return pd.DataFrame()

    mart = parts[0]
    for p in parts[1:]:
        mart = mart.merge(p, on=["station_id", "year", "month"], how="outer")

    for col in ("avg_tmax_c", "avg_tmin_c", "total_prcp_mm"):
        if col in mart.columns:
            mart[col] = mart[col].round(2)

    mart = _add_month_keys(mart)
    return mart.sort_values(["station_id", "year", "month"]).reset_index(drop=True)


def build_mart_degree_days_monthly(
    qc_pass: pd.DataFrame, *, base_c: float
) -> pd.DataFrame:
    """Aggregate fact / mart — grain: station_id + year + month (HDD/CDD)."""
    temps = qc_pass.loc[
        qc_pass["element"].isin(["TMAX", "TMIN"]),
        ["station_id", "date", "element", "value"],
    ]
    if temps.empty:
        return pd.DataFrame()

    wide = temps.pivot_table(
        index=["station_id", "date"],
        columns="element",
        values="value",
        aggfunc="first",
    ).reset_index()
    if "TMAX" not in wide.columns or "TMIN" not in wide.columns:
        return pd.DataFrame()

    wide = wide.dropna(subset=["TMAX", "TMIN"]).copy()
    wide["tavg_c"] = (wide["TMAX"] + wide["TMIN"]) / 2.0
    wide["hdd"] = (base_c - wide["tavg_c"]).clip(lower=0.0)
    wide["cdd"] = (wide["tavg_c"] - base_c).clip(lower=0.0)
    wide["year"] = wide["date"].dt.year
    wide["month"] = wide["date"].dt.month

    mart = (
        wide.groupby(["station_id", "year", "month"], as_index=False)
        .agg(
            hdd_sum=("hdd", "sum"),
            cdd_sum=("cdd", "sum"),
            n_days_both_temps=("date", "count"),
            avg_tavg_c=("tavg_c", "mean"),
        )
    )
    mart["base_c"] = base_c
    mart["hdd_sum"] = mart["hdd_sum"].round(2)
    mart["cdd_sum"] = mart["cdd_sum"].round(2)
    mart["avg_tavg_c"] = mart["avg_tavg_c"].round(2)
    mart = _add_month_keys(mart)
    return mart.sort_values(["station_id", "year", "month"]).reset_index(drop=True)


def build_mart_coverage_yearly(qc_pass: pd.DataFrame) -> pd.DataFrame:
    """Coverage mart — grain: station_id + year + element_code."""
    df = qc_pass.copy()
    df["year"] = df["date"].dt.year
    g = (
        df.groupby(["station_id", "year", "element"], as_index=False)
        .agg(n_obs=("date", "count"), date_min=("date", "min"), date_max=("date", "max"))
    )
    g = g.rename(columns={"element": "element_code"})

    def days_in_year(y: int) -> int:
        return 366 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 365

    g["days_in_year"] = g["year"].map(days_in_year)
    g["completeness"] = (g["n_obs"] / g["days_in_year"]).clip(upper=1.0).round(4)
    g["date_min"] = g["date_min"].dt.strftime("%Y-%m-%d")
    g["date_max"] = g["date_max"].dt.strftime("%Y-%m-%d")
    return g.sort_values(["station_id", "year", "element_code"]).reset_index(drop=True)


def build_mart_freeze_season_yearly(qc_pass: pd.DataFrame) -> pd.DataFrame:
    """Freeze / growing-season mart — grain: station_id + year."""
    tmin = qc_pass.loc[
        qc_pass["element"] == "TMIN",
        ["station_id", "date", "value"],
    ].copy()
    if tmin.empty:
        return pd.DataFrame()

    tmin["year"] = tmin["date"].dt.year
    tmin["month"] = tmin["date"].dt.month
    tmin["is_freeze"] = tmin["value"] <= FREEZE_TMIN_C

    rows: list[dict] = []
    for (sid, year), g in tmin.groupby(["station_id", "year"]):
        freezes = g.loc[g["is_freeze"]]
        spring = freezes.loc[freezes["month"] <= 6, "date"]
        fall = freezes.loc[freezes["month"] >= 7, "date"]
        last_spring = spring.max() if len(spring) else pd.NaT
        first_fall = fall.min() if len(fall) else pd.NaT
        growing = None
        if pd.notna(last_spring) and pd.notna(first_fall) and first_fall > last_spring:
            growing = int((first_fall - last_spring).days)

        rows.append(
            {
                "station_id": sid,
                "year": int(year),
                "freeze_threshold_c": FREEZE_TMIN_C,
                "n_tmin_obs": int(len(g)),
                "n_freeze_days": int(len(freezes)),
                "last_spring_freeze": (
                    last_spring.strftime("%Y-%m-%d") if pd.notna(last_spring) else None
                ),
                "first_fall_freeze": (
                    first_fall.strftime("%Y-%m-%d") if pd.notna(first_fall) else None
                ),
                "growing_season_days": growing,
            }
        )

    mart = pd.DataFrame(rows)
    if mart.empty:
        return mart
    return mart.sort_values(["station_id", "year"]).reset_index(drop=True)


def build_mart_extremes_yearly(qc_pass: pd.DataFrame) -> pd.DataFrame:
    """Extremes mart — grain: station_id + year (hot/cold/wet day counts)."""
    df = qc_pass.copy()
    df["year"] = df["date"].dt.year

    rows: list[dict] = []
    for (sid, year), g in df.groupby(["station_id", "year"]):
        tmax = g.loc[g["element"] == "TMAX", "value"]
        tmin = g.loc[g["element"] == "TMIN", "value"]
        prcp = g.loc[g["element"] == "PRCP", "value"]
        rows.append(
            {
                "station_id": sid,
                "year": int(year),
                "n_days_tmax_ge_32c": int((tmax >= HOT_DAY_TMAX_C).sum()),
                "n_days_tmax_ge_35c": int((tmax >= VERY_HOT_TMAX_C).sum()),
                "n_days_tmin_le_0c": int((tmin <= FREEZE_TMIN_C).sum()),
                "n_days_prcp_ge_25mm": int((prcp >= WET_DAY_PRCP_MM).sum()),
                "max_tmax_c": round(float(tmax.max()), 2) if len(tmax) else None,
                "min_tmin_c": round(float(tmin.min()), 2) if len(tmin) else None,
                "max_daily_prcp_mm": round(float(prcp.max()), 2) if len(prcp) else None,
                "n_tmax_obs": int(len(tmax)),
                "n_tmin_obs": int(len(tmin)),
                "n_prcp_obs": int(len(prcp)),
            }
        )

    mart = pd.DataFrame(rows)
    if mart.empty:
        return mart
    return mart.sort_values(["station_id", "year"]).reset_index(drop=True)


def write_parquet(df: pd.DataFrame, path: Path) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    return {"path": str(path), "rows": int(len(df))}


def _concat_marts(parts: list[pd.DataFrame]) -> pd.DataFrame:
    if not parts:
        return pd.DataFrame()
    return pd.concat(parts, ignore_index=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build gold star schema (dims+fact) and analytics marts"
    )
    parser.add_argument(
        "--station",
        action="append",
        dest="stations",
        help="Limit to station ID (repeatable). Default: all QC files.",
    )
    parser.add_argument(
        "--base-c",
        type=float,
        default=DEFAULT_BASE_C,
        help=f"HDD/CDD base temperature in °C (default {DEFAULT_BASE_C})",
    )
    parser.add_argument(
        "--skip-fact",
        action="store_true",
        help="Skip writing full fact_observation_daily (large file)",
    )
    args = parser.parse_args()

    paths = list_qc_paths(args.stations)
    total = len(paths)
    print(
        f"Streaming gold build from {SILVER_STATIONS_QC} "
        f"({total} station files; one-at-a-time to avoid OOM)"
    )

    station_ids: list[str] = []
    date_min: pd.Timestamp | None = None
    date_max: pd.Timestamp | None = None
    qc_pass_rows = 0

    monthly_parts: list[pd.DataFrame] = []
    degree_parts: list[pd.DataFrame] = []
    coverage_parts: list[pd.DataFrame] = []
    freeze_parts: list[pd.DataFrame] = []
    extremes_parts: list[pd.DataFrame] = []

    fact_writer: pq.ParquetWriter | None = None
    fact_path = GOLD_FACTS / "fact_observation_daily.parquet"
    fact_rows = 0
    if not args.skip_fact:
        GOLD_FACTS.mkdir(parents=True, exist_ok=True)
        if fact_path.exists():
            fact_path.unlink()

    for i, path in enumerate(paths, start=1):
        qc = load_qc_pass_station(path)
        if qc.empty:
            if i == 1 or i % 100 == 0 or i == total:
                print(f"progress {i}/{total} (empty qc_pass: {path.stem})")
            continue

        sid = str(qc["station_id"].iloc[0]) if "station_id" in qc.columns else path.stem
        station_ids.append(sid)
        d0, d1 = qc["date"].min(), qc["date"].max()
        date_min = d0 if date_min is None else min(date_min, d0)
        date_max = d1 if date_max is None else max(date_max, d1)
        qc_pass_rows += len(qc)

        m = build_mart_monthly_climate(qc)
        if not m.empty:
            monthly_parts.append(m)
        d = build_mart_degree_days_monthly(qc, base_c=args.base_c)
        if not d.empty:
            degree_parts.append(d)
        c = build_mart_coverage_yearly(qc)
        if not c.empty:
            coverage_parts.append(c)
        f = build_mart_freeze_season_yearly(qc)
        if not f.empty:
            freeze_parts.append(f)
        e = build_mart_extremes_yearly(qc)
        if not e.empty:
            extremes_parts.append(e)

        if not args.skip_fact:
            fact = build_fact_observation_daily(qc)
            if not fact.empty:
                table = pa.Table.from_pandas(fact, preserve_index=False)
                if fact_writer is None:
                    fact_writer = pq.ParquetWriter(str(fact_path), table.schema)
                fact_writer.write_table(table)
                fact_rows += len(fact)

        if i == 1 or i % 50 == 0 or i == total:
            print(
                f"progress {i}/{total}  stations_ok={len(station_ids)}  "
                f"qc_pass_rows={qc_pass_rows:,}  fact_rows={fact_rows:,}"
            )

    if fact_writer is not None:
        fact_writer.close()

    if not station_ids or date_min is None or date_max is None:
        raise SystemExit("No qc_pass rows found — cannot build gold.")

    station_ids = sorted(set(station_ids))
    print(f"\nBuilding dims for {len(station_ids)} stations  "
          f"dates {date_min.date()} .. {date_max.date()}")
    print(f"Concatenating marts ({len(monthly_parts)} monthly parts) ...")

    monthly = _concat_marts(monthly_parts)
    degree = _concat_marts(degree_parts)
    coverage = _concat_marts(coverage_parts)
    freeze = _concat_marts(freeze_parts)
    extremes = _concat_marts(extremes_parts)

    # Stable sort after streaming concat
    if not monthly.empty:
        monthly = monthly.sort_values(["station_id", "year", "month"]).reset_index(drop=True)
    if not degree.empty:
        degree = degree.sort_values(["station_id", "year", "month"]).reset_index(drop=True)
    if not coverage.empty:
        coverage = coverage.sort_values(
            ["station_id", "year", "element_code"]
        ).reset_index(drop=True)
    if not freeze.empty:
        freeze = freeze.sort_values(["station_id", "year"]).reset_index(drop=True)
    if not extremes.empty:
        extremes = extremes.sort_values(["station_id", "year"]).reset_index(drop=True)

    dim_station = build_dim_station(station_ids)
    dim_date = build_dim_date(date_min, date_max)
    dim_element = build_dim_element()

    outputs = {
        "dim_station": write_parquet(dim_station, GOLD_DIMS / "dim_station.parquet"),
        "dim_date": write_parquet(dim_date, GOLD_DIMS / "dim_date.parquet"),
        "dim_element": write_parquet(dim_element, GOLD_DIMS / "dim_element.parquet"),
        "mart_monthly_climate": write_parquet(
            monthly, GOLD_MARTS / "mart_monthly_climate.parquet"
        ),
        "mart_degree_days_monthly": write_parquet(
            degree, GOLD_MARTS / "mart_degree_days_monthly.parquet"
        ),
        "mart_coverage_yearly": write_parquet(
            coverage, GOLD_MARTS / "mart_coverage_yearly.parquet"
        ),
        "mart_freeze_season_yearly": write_parquet(
            freeze, GOLD_MARTS / "mart_freeze_season_yearly.parquet"
        ),
        "mart_extremes_yearly": write_parquet(
            extremes, GOLD_MARTS / "mart_extremes_yearly.parquet"
        ),
    }
    if not args.skip_fact and fact_path.exists():
        outputs["fact_observation_daily"] = {
            "path": str(fact_path),
            "rows": int(fact_rows),
        }

    print("\nStar schema (dims + atomic fact):")
    for name in ("dim_station", "dim_date", "dim_element", "fact_observation_daily"):
        if name in outputs:
            print(f"  {name}: {outputs[name]['rows']:,} rows")

    print("\nMarts (pre-agg for fast viz):")
    for name, meta in outputs.items():
        if name.startswith("mart_"):
            print(f"  {name}: {meta['rows']:,} rows -> {meta['path']}")

    if not degree.empty and "USW00013872" in set(degree["station_id"]):
        peek = degree.loc[
            (degree["station_id"] == "USW00013872") & (degree["year"] == 2020)
        ].sort_values("month")
        if not peek.empty:
            print("\nSample — Asheville 2020 monthly HDD/CDD:")
            print(
                peek[
                    [
                        "year",
                        "month",
                        "year_month_key",
                        "hdd_sum",
                        "cdd_sum",
                        "avg_tavg_c",
                    ]
                ].to_string(index=False)
            )

    META.mkdir(parents=True, exist_ok=True)
    man = {
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "base_c": args.base_c,
        "build_mode": "stream_per_station",
        "stations": station_ids,
        "station_count": len(station_ids),
        "qc_pass_rows": int(qc_pass_rows),
        "date_min": str(date_min.date()),
        "date_max": str(date_max.date()),
        "outputs": outputs,
        "star_schema": {
            "dims": ["dim_station", "dim_date", "dim_element"],
            "fact": "fact_observation_daily",
            "fact_grain": "station_id + date_key + element_code",
            "keys": {
                "station_id": "dim_station.station_id",
                "date_key": "dim_date.date_key (YYYYMMDD int)",
                "element_code": "dim_element.element_code",
            },
        },
        "viz_guidance": {
            "prefer_for_dashboards": [
                "mart_monthly_climate",
                "mart_degree_days_monthly",
                "mart_extremes_yearly",
                "mart_freeze_season_yearly",
                "dim_station",
            ],
            "use_atomic_fact_for": "drill-down, ad-hoc, custom thresholds",
        },
        "method_notes": {
            "degree_days": "tavg=(TMAX+TMIN)/2; "
            f"HDD/CDD vs base_c={args.base_c}",
            "freeze_season": f"TMIN<={FREEZE_TMIN_C}; spring month<=6; fall month>=7",
            "extremes": f"TMAX>={HOT_DAY_TMAX_C}/{VERY_HOT_TMAX_C}; "
            f"TMIN<={FREEZE_TMIN_C}; PRCP>={WET_DAY_PRCP_MM}",
            "qc": "only stations_qc rows with qc_pass=True",
        },
    }
    man_path = META / "gold_manifest.json"
    man_path.write_text(json.dumps(man, indent=2), encoding="utf-8")
    print(f"\nmanifest: {man_path}")
    print(f"done: stations={len(station_ids)} qc_pass_rows={qc_pass_rows:,}")


if __name__ == "__main__":
    main()
