"""
Phase 3 (start) — build first gold tables from QC-pass silver.

Input:
  data/silver/stations_qc/*.parquet   (rows with qc_pass / qc_reasons)

Output (Parquet):
  data/gold/dims/dim_station.parquet
  data/gold/facts/fact_observation_daily.parquet   (qc_pass only)
  data/gold/marts/mart_monthly_climate.parquet
  data/gold/marts/mart_degree_days_monthly.parquet
  data/gold/marts/mart_coverage_yearly.parquet
  data/gold/marts/mart_freeze_season_yearly.parquet
  data/gold/marts/mart_extremes_yearly.parquet

What is a "mart"?
  A mart is a ready-to-use summary table for a question (dashboard/report),
  not the raw daily fact. Example: "HDD by station-month" is a mart;
  every daily TMAX row is a fact.

Degree-day method (documented, simple):
  Daily mean temp ≈ (TMAX + TMIN) / 2   when both pass QC that day
  HDD = max(0, base_c - tavg)           default base 18 °C (~65 °F)
  CDD = max(0, tavg - base_c)
  Monthly marts sum daily HDD/CDD.

Freeze-season method (calendar year, simple):
  Freeze day: TMIN <= 0 °C (qc_pass).
  last_spring_freeze: last freeze date with month <= 6
  first_fall_freeze: first freeze date with month >= 7
  growing_season_days: days between those two when both exist

Extremes method (calendar year):
  Counts of hot / cold / wet days using fixed thresholds (see code).

Only qc_pass rows feed gold. Failures stay in silver_qc for audit.

Examples:
  python -m src.transform.silver_to_gold
  python -m src.transform.silver_to_gold --base-c 18
  python -m src.transform.silver_to_gold --station USW00013872
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.common.paths import (
    BRONZE_META,
    GOLD_DIMS,
    GOLD_FACTS,
    GOLD_MARTS,
    META,
    SILVER_STATIONS_QC,
)

DEFAULT_BASE_C = 18.0
# Extremes thresholds (°C / mm) — product definitions, documented for portfolio honesty
HOT_DAY_TMAX_C = 32.0  # ~90 °F
VERY_HOT_TMAX_C = 35.0  # ~95 °F
FREEZE_TMIN_C = 0.0
WET_DAY_PRCP_MM = 25.4  # ~1 inch


def load_qc_frames(station_ids: list[str] | None) -> pd.DataFrame:
    """Load silver QC Parquet; keep qc_pass rows only."""
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

    frames = []
    for path in paths:
        df = pd.read_parquet(path)
        if "qc_pass" not in df.columns:
            raise SystemExit(f"{path.name} missing qc_pass; re-run apply_qc")
        passed = df.loc[df["qc_pass"]].copy()
        frames.append(passed)

    out = pd.concat(frames, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"])
    return out


def build_dim_station(station_ids: list[str]) -> pd.DataFrame:
    """
    Station dimension from ghcnd-stations.txt for IDs we actually modeled.
    One current row per station (SCD2 later if needed).
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
    # Stable order
    if not dim.empty:
        dim = dim.sort_values("station_id").reset_index(drop=True)
    return dim


def build_fact_observation_daily(qc_pass: pd.DataFrame) -> pd.DataFrame:
    """Slim daily fact: one row per station + date + element (pass only)."""
    cols = ["station_id", "date", "element", "value", "unit", "mflag", "sflag"]
    fact = qc_pass.loc[:, [c for c in cols if c in qc_pass.columns]].copy()
    fact = fact.sort_values(["station_id", "date", "element"]).reset_index(drop=True)
    return fact


def build_mart_monthly_climate(qc_pass: pd.DataFrame) -> pd.DataFrame:
    """
    Grain: station_id + year + month.
    avg_tmax_c, avg_tmin_c, total_prcp_mm, n_days_* completeness helpers.
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
        # day counts for that element
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

    # Round for readability
    for col in ("avg_tmax_c", "avg_tmin_c", "total_prcp_mm"):
        if col in mart.columns:
            mart[col] = mart[col].round(2)

    return mart.sort_values(["station_id", "year", "month"]).reset_index(drop=True)


def build_mart_degree_days_monthly(
    qc_pass: pd.DataFrame, *, base_c: float
) -> pd.DataFrame:
    """
    Grain: station_id + year + month.
    Requires both TMAX and TMIN on the same day (both already qc_pass).
    """
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
    # Simple daily mean used by many degree-day approximations
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
    return mart.sort_values(["station_id", "year", "month"]).reset_index(drop=True)


def build_mart_coverage_yearly(qc_pass: pd.DataFrame) -> pd.DataFrame:
    """
    Grain: station_id + year + element.
    n_obs vs days in year — rough completeness for portfolio/coverage mart.
    """
    df = qc_pass.copy()
    df["year"] = df["date"].dt.year
    g = (
        df.groupby(["station_id", "year", "element"], as_index=False)
        .agg(n_obs=("date", "count"), date_min=("date", "min"), date_max=("date", "max"))
    )
    # Days in calendar year (ignore leap nuance for ratio denominator use 365/366)
    def days_in_year(y: int) -> int:
        return 366 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 365

    g["days_in_year"] = g["year"].map(days_in_year)
    g["completeness"] = (g["n_obs"] / g["days_in_year"]).clip(upper=1.0).round(4)
    g["date_min"] = g["date_min"].dt.strftime("%Y-%m-%d")
    g["date_max"] = g["date_max"].dt.strftime("%Y-%m-%d")
    return g.sort_values(["station_id", "year", "element"]).reset_index(drop=True)


def build_mart_freeze_season_yearly(qc_pass: pd.DataFrame) -> pd.DataFrame:
    """
    Grain: station_id + year (calendar year).

    Simple freeze definitions for portfolio transparency — not NWS climate division product.
    """
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
    """
    Grain: station_id + year.
    Fixed thresholds — good for charts; document units when publishing.
    """
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Build gold dims/facts/marts from silver QC")
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

    print(f"Loading qc_pass rows from {SILVER_STATIONS_QC} ...")
    qc = load_qc_frames(args.stations)
    station_ids = sorted(qc["station_id"].unique())
    print(f"  stations={len(station_ids)}  qc_pass_rows={len(qc):,}")

    dim = build_dim_station(station_ids)
    fact = None if args.skip_fact else build_fact_observation_daily(qc)
    monthly = build_mart_monthly_climate(qc)
    degree = build_mart_degree_days_monthly(qc, base_c=args.base_c)
    coverage = build_mart_coverage_yearly(qc)
    freeze = build_mart_freeze_season_yearly(qc)
    extremes = build_mart_extremes_yearly(qc)

    outputs = {
        "dim_station": write_parquet(dim, GOLD_DIMS / "dim_station.parquet"),
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
    if fact is not None:
        outputs["fact_observation_daily"] = write_parquet(
            fact, GOLD_FACTS / "fact_observation_daily.parquet"
        )

    for name, meta in outputs.items():
        print(f"  {name}: {meta['rows']:,} rows -> {meta['path']}")

    # Quick sanity peek: latest full year-ish for Asheville if present
    if not degree.empty and "USW00013872" in set(degree["station_id"]):
        peek = degree.loc[
            (degree["station_id"] == "USW00013872") & (degree["year"] == 2020)
        ].sort_values("month")
        if not peek.empty:
            print("\nSample — Asheville 2020 monthly HDD/CDD (base °C =", args.base_c, "):")
            print(
                peek[
                    ["year", "month", "hdd_sum", "cdd_sum", "avg_tavg_c", "n_days_both_temps"]
                ].to_string(index=False)
            )

    if not freeze.empty and "USW00013872" in set(freeze["station_id"]):
        fz = freeze.loc[
            (freeze["station_id"] == "USW00013872") & (freeze["year"] == 2020)
        ]
        if not fz.empty:
            print("\nSample — Asheville 2020 freeze season:")
            print(fz.to_string(index=False))

    if not extremes.empty and "USW00013872" in set(extremes["station_id"]):
        ex = extremes.loc[
            (extremes["station_id"] == "USW00013872") & (extremes["year"] == 2020)
        ]
        if not ex.empty:
            print("\nSample — Asheville 2020 extremes:")
            print(ex.to_string(index=False))

    META.mkdir(parents=True, exist_ok=True)
    man = {
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "base_c": args.base_c,
        "stations": station_ids,
        "qc_pass_rows": int(len(qc)),
        "outputs": outputs,
        "method_notes": {
            "degree_days": "tavg=(TMAX+TMIN)/2 on days both pass QC; "
            f"HDD=max(0,base-tavg), CDD=max(0,tavg-base), base_c={args.base_c}",
            "freeze_season": f"freeze if TMIN<={FREEZE_TMIN_C}; "
            "last spring freeze month<=6; first fall freeze month>=7",
            "extremes": f"hot TMAX>={HOT_DAY_TMAX_C}/{VERY_HOT_TMAX_C}; "
            f"freeze TMIN<={FREEZE_TMIN_C}; wet PRCP>={WET_DAY_PRCP_MM} mm",
            "qc": "only silver stations_qc rows with qc_pass=True",
        },
    }
    man_path = META / "gold_manifest.json"
    man_path.write_text(json.dumps(man, indent=2), encoding="utf-8")
    print(f"\nmanifest: {man_path}")


if __name__ == "__main__":
    main()
