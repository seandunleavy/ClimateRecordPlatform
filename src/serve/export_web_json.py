"""
Export JSON from gold marts for static web charts (Dunleavy).

Best practice: charts read pre-aggregated marts, not daily facts or bronze.

Default: full history (all years) for the station sample.
Optional: --year 2020 for a single-year slice only.

Examples:
  python -m src.serve.export_web_json --all-years --copy-to-dunleavy
  python -m src.serve.export_web_json --year 2020 --copy-to-dunleavy
"""
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.common.paths import GOLD_DIMS, GOLD_MARTS, META, ROOT

SERVE_WEB = ROOT / "data" / "serve" / "web"
DEFAULT_DUNLEAVY = Path(r"C:\Users\seand\GitProjects\dunleavyorganization.com")
DUNLEAVY_DATA = Path("data") / "climate-record"

DEGREE_COLS = [
    "station_id",
    "name",
    "state",
    "year",
    "month",
    "hdd_sum",
    "cdd_sum",
    "avg_tavg_c",
    "n_days_both_temps",
    "base_c",
]
EXTREMES_COLS = [
    "station_id",
    "name",
    "state",
    "year",
    "n_days_tmax_ge_32c",
    "n_days_tmax_ge_35c",
    "n_days_tmin_le_0c",
    "n_days_prcp_ge_25mm",
    "max_tmax_c",
    "min_tmin_c",
    "max_daily_prcp_mm",
]
FREEZE_COLS = [
    "station_id",
    "name",
    "state",
    "year",
    "n_freeze_days",
    "last_spring_freeze",
    "first_fall_freeze",
    "growing_season_days",
    "freeze_threshold_c",
]


def _json_default(obj: object) -> object:
    """Pandas may emit NaN/NaT; standard JSON has no NaN — use null."""
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _sanitize_for_json(payload: object) -> object:
    """Replace NaN/NaT/NA with None so json.dumps emits valid null."""
    if isinstance(payload, list):
        return [_sanitize_for_json(x) for x in payload]
    if isinstance(payload, dict):
        return {k: _sanitize_for_json(v) for k, v in payload.items()}
    # float NaN / inf
    try:
        if payload != payload:  # NaN
            return None
    except Exception:
        pass
    if payload is pd.NaT:
        return None
    if payload is pd.NA:
        return None
    return payload


def _write_json(path: Path, payload: object, *, compact: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    clean = _sanitize_for_json(payload)
    if compact:
        text = json.dumps(clean, allow_nan=False, separators=(",", ":"))
    else:
        text = json.dumps(clean, allow_nan=False, indent=2)
    path.write_text(text, encoding="utf-8")
    print(f"  wrote {path} ({path.stat().st_size:,} bytes)")


def _load_frames() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    stations = pd.read_parquet(GOLD_DIMS / "dim_station.parquet")
    degree = pd.read_parquet(GOLD_MARTS / "mart_degree_days_monthly.parquet")
    extremes = pd.read_parquet(GOLD_MARTS / "mart_extremes_yearly.parquet")
    freeze = pd.read_parquet(GOLD_MARTS / "mart_freeze_season_yearly.parquet")
    return stations, degree, extremes, freeze


def _stations_payload(stations: pd.DataFrame) -> list[dict]:
    return (
        stations.sort_values(["state", "name"])
        .loc[:, ["station_id", "name", "state", "latitude", "longitude", "network_prefix"]]
        .to_dict(orient="records")
    )


def _degree_payload(degree: pd.DataFrame, stations: pd.DataFrame) -> list[dict]:
    deg = degree.merge(
        stations[["station_id", "name", "state"]],
        on="station_id",
        how="left",
    )
    return (
        deg.sort_values(["station_id", "year", "month"])
        .loc[:, DEGREE_COLS]
        .to_dict(orient="records")
    )


def _extremes_payload(extremes: pd.DataFrame, stations: pd.DataFrame) -> list[dict]:
    ext = extremes.merge(
        stations[["station_id", "name", "state"]],
        on="station_id",
        how="left",
    )
    return (
        ext.sort_values(["station_id", "year"])
        .loc[:, EXTREMES_COLS]
        .to_dict(orient="records")
    )


def _freeze_payload(freeze: pd.DataFrame, stations: pd.DataFrame) -> list[dict]:
    fr = freeze.merge(
        stations[["station_id", "name", "state"]],
        on="station_id",
        how="left",
    )
    return (
        fr.sort_values(["station_id", "year"])
        .loc[:, FREEZE_COLS]
        .to_dict(orient="records")
    )


def export_all_years() -> dict:
    """Full-history mart JSON for the web explorer (still tiny vs daily facts)."""
    stations, degree, extremes, freeze = _load_frames()
    stations_out = _stations_payload(stations)
    degree_out = _degree_payload(degree, stations)
    extremes_out = _extremes_payload(extremes, stations)
    freeze_out = _freeze_payload(freeze, stations)

    year_min = int(min(degree["year"].min(), extremes["year"].min()))
    year_max = int(max(degree["year"].max(), extremes["year"].max()))

    meta = {
        "exported_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "all_years",
        "year_min": year_min,
        "year_max": year_max,
        "station_count": len(stations_out),
        "row_counts": {
            "degree_days_monthly": len(degree_out),
            "extremes_yearly": len(extremes_out),
            "freeze_yearly": len(freeze_out),
        },
        "files": {
            "stations": "stations.json",
            "degree_days_monthly": "degree_days_monthly.json",
            "extremes_yearly": "extremes_yearly.json",
            "freeze_yearly": "freeze_yearly.json",
        },
        "sources": {
            "dim_station": "data/gold/dims/dim_station.parquet",
            "mart_degree_days_monthly": "data/gold/marts/mart_degree_days_monthly.parquet",
            "mart_extremes_yearly": "data/gold/marts/mart_extremes_yearly.parquet",
            "mart_freeze_season_yearly": "data/gold/marts/mart_freeze_season_yearly.parquet",
        },
        "methods": {
            "qc": "Gold uses silver stations_qc rows with qc_pass=True only",
            "degree_days": "tavg=(TMAX+TMIN)/2; heating/cooling degree-days vs base 18 C; monthly sums",
            "extremes": "Hot TMAX>=32/35 C; freeze TMIN<=0 C; wet PRCP>=25.4 mm",
            "freeze_season": "Freeze TMIN<=0; last spring freeze month<=6; first fall month>=7",
        },
        "scope": (
            "South Carolina, North Carolina, Georgia long-record USW/USC sample "
            "— portfolio demo, not a national NCEI product"
        ),
    }

    SERVE_WEB.mkdir(parents=True, exist_ok=True)
    print(f"Export ALL YEARS ({year_min}-{year_max}) -> {SERVE_WEB}")
    _write_json(SERVE_WEB / "stations.json", stations_out)
    _write_json(SERVE_WEB / "degree_days_monthly.json", degree_out)
    _write_json(SERVE_WEB / "extremes_yearly.json", extremes_out)
    _write_json(SERVE_WEB / "freeze_yearly.json", freeze_out)
    _write_json(SERVE_WEB / "meta.json", meta, compact=False)

    _write_manifest(meta)
    return meta


def export_year(year: int) -> dict:
    """Single calendar-year slice (legacy demo files)."""
    stations, degree, extremes, freeze = _load_frames()
    stations_out = _stations_payload(stations)

    degree_out = _degree_payload(degree.loc[degree["year"] == year], stations)
    extremes_out = _extremes_payload(extremes.loc[extremes["year"] == year], stations)
    freeze_out = _freeze_payload(freeze.loc[freeze["year"] == year], stations)

    meta = {
        "exported_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "single_year",
        "year": year,
        "station_count": len(stations_out),
        "methods": {
            "qc": "Gold uses silver stations_qc rows with qc_pass=True only",
            "degree_days": "tavg=(TMAX+TMIN)/2; heating/cooling degree-days vs base 18 C",
        },
        "scope": "South Carolina, North Carolina, Georgia long-record sample",
    }

    SERVE_WEB.mkdir(parents=True, exist_ok=True)
    print(f"Export year={year} -> {SERVE_WEB}")
    _write_json(SERVE_WEB / "stations.json", stations_out)
    _write_json(SERVE_WEB / f"degree_days_{year}.json", degree_out, compact=False)
    _write_json(SERVE_WEB / f"extremes_{year}.json", extremes_out, compact=False)
    _write_json(SERVE_WEB / f"freeze_{year}.json", freeze_out, compact=False)
    _write_json(SERVE_WEB / "meta.json", meta, compact=False)
    _write_manifest(meta)
    return meta


def _write_manifest(meta: dict) -> None:
    META.mkdir(parents=True, exist_ok=True)
    man = {
        "built_at_utc": meta.get("exported_at_utc"),
        "mode": meta.get("mode"),
        "serve_dir": str(SERVE_WEB),
        "files": [p.name for p in sorted(SERVE_WEB.glob("*.json"))],
        "meta": meta,
    }
    man_path = META / "serve_web_manifest.json"
    man_path.write_text(json.dumps(man, indent=2), encoding="utf-8")
    print(f"manifest: {man_path}")


def copy_to_dunleavy(dunleavy_root: Path, *, all_years: bool, year: int | None) -> Path:
    dest = dunleavy_root / DUNLEAVY_DATA
    dest.mkdir(parents=True, exist_ok=True)
    if all_years:
        names = [
            "stations.json",
            "meta.json",
            "degree_days_monthly.json",
            "extremes_yearly.json",
            "freeze_yearly.json",
        ]
    else:
        y = year or 2020
        names = [
            "stations.json",
            "meta.json",
            f"degree_days_{y}.json",
            f"extremes_{y}.json",
            f"freeze_{y}.json",
        ]
    for name in names:
        src = SERVE_WEB / name
        if src.exists():
            shutil.copy2(src, dest / name)
            print(f"  copy -> {dest / name}")
    return dest


def main() -> None:
    parser = argparse.ArgumentParser(description="Export gold marts to web JSON")
    parser.add_argument(
        "--all-years",
        action="store_true",
        default=True,
        help="Export full history (default). Preferred for the explorer demo.",
    )
    parser.add_argument(
        "--single-year",
        type=int,
        default=None,
        metavar="YEAR",
        help="Export only one calendar year instead of full history",
    )
    parser.add_argument(
        "--year",
        type=int,
        default=None,
        help="Deprecated alias for --single-year",
    )
    parser.add_argument(
        "--copy-to-dunleavy",
        action="store_true",
        help="Copy JSON into dunleavyorganization.com/data/climate-record/",
    )
    parser.add_argument(
        "--dunleavy-root",
        type=Path,
        default=DEFAULT_DUNLEAVY,
        help="Path to dunleavyorganization.com repo",
    )
    args = parser.parse_args()

    single = args.single_year if args.single_year is not None else args.year
    if single is not None:
        export_year(single)
        all_years = False
    else:
        export_all_years()
        all_years = True

    if args.copy_to_dunleavy:
        if not args.dunleavy_root.exists():
            raise SystemExit(f"Dunleavy root not found: {args.dunleavy_root}")
        print(f"Copy to Dunleavy: {args.dunleavy_root}")
        copy_to_dunleavy(args.dunleavy_root, all_years=all_years, year=single)


if __name__ == "__main__":
    main()
