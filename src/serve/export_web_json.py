"""
Export small JSON files from gold marts for static web charts (Dunleavy).

Best practice: charts read pre-aggregated marts, not daily facts or bronze.

Output (default):
  data/serve/web/stations.json
  data/serve/web/degree_days_2020.json
  data/serve/web/extremes_2020.json
  data/serve/web/freeze_2020.json
  data/serve/web/meta.json

Also copies into Dunleavy data folder when --copy-to-dunleavy is set
(or DUNLEAVY_ROOT env / sibling path exists).

Examples:
  python -m src.serve.export_web_json
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

DEFAULT_YEAR = 2020
SERVE_WEB = ROOT / "data" / "serve" / "web"
DEFAULT_DUNLEAVY = Path(r"C:\Users\seand\GitProjects\dunleavyorganization.com")
DUNLEAVY_DATA = Path("data") / "climate-record"


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"  wrote {path} ({path.stat().st_size:,} bytes)")


def export_year(year: int) -> dict:
    stations = pd.read_parquet(GOLD_DIMS / "dim_station.parquet")
    degree = pd.read_parquet(GOLD_MARTS / "mart_degree_days_monthly.parquet")
    extremes = pd.read_parquet(GOLD_MARTS / "mart_extremes_yearly.parquet")
    freeze = pd.read_parquet(GOLD_MARTS / "mart_freeze_season_yearly.parquet")

    stations_out = (
        stations.sort_values(["state", "name"])
        .loc[:, ["station_id", "name", "state", "latitude", "longitude", "network_prefix"]]
        .to_dict(orient="records")
    )

    deg_y = degree.loc[degree["year"] == year].copy()
    deg_y = deg_y.merge(
        stations[["station_id", "name", "state"]],
        on="station_id",
        how="left",
    )
    degree_out = (
        deg_y.sort_values(["state", "name", "month"])
        .loc[
            :,
            [
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
            ],
        ]
        .to_dict(orient="records")
    )

    ext_y = extremes.loc[extremes["year"] == year].copy()
    ext_y = ext_y.merge(
        stations[["station_id", "name", "state"]],
        on="station_id",
        how="left",
    )
    extremes_out = (
        ext_y.sort_values(["state", "name"])
        .loc[
            :,
            [
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
            ],
        ]
        .to_dict(orient="records")
    )

    fr_y = freeze.loc[freeze["year"] == year].copy()
    fr_y = fr_y.merge(
        stations[["station_id", "name", "state"]],
        on="station_id",
        how="left",
    )
    freeze_out = (
        fr_y.sort_values(["state", "name"])
        .loc[
            :,
            [
                "station_id",
                "name",
                "state",
                "year",
                "n_freeze_days",
                "last_spring_freeze",
                "first_fall_freeze",
                "growing_season_days",
                "freeze_threshold_c",
            ],
        ]
        .to_dict(orient="records")
    )

    meta = {
        "exported_at_utc": datetime.now(timezone.utc).isoformat(),
        "year": year,
        "station_count": len(stations_out),
        "sources": {
            "dim_station": "data/gold/dims/dim_station.parquet",
            "mart_degree_days_monthly": "data/gold/marts/mart_degree_days_monthly.parquet",
            "mart_extremes_yearly": "data/gold/marts/mart_extremes_yearly.parquet",
            "mart_freeze_season_yearly": "data/gold/marts/mart_freeze_season_yearly.parquet",
        },
        "methods": {
            "qc": "Gold uses silver stations_qc rows with qc_pass=True only",
            "degree_days": "tavg=(TMAX+TMIN)/2; HDD/CDD vs base 18 C; monthly sums",
            "extremes": "Hot TMAX>=32/35 C; freeze TMIN<=0 C; wet PRCP>=25.4 mm",
            "freeze_season": "Freeze TMIN<=0; last spring freeze month<=6; first fall month>=7",
        },
        "scope": "SC, NC, GA long-record USW/USC sample — portfolio demo, not full NCEI product",
    }

    SERVE_WEB.mkdir(parents=True, exist_ok=True)
    print(f"Export year={year} -> {SERVE_WEB}")
    _write_json(SERVE_WEB / "stations.json", stations_out)
    _write_json(SERVE_WEB / "degree_days_2020.json" if year == 2020 else SERVE_WEB / f"degree_days_{year}.json", degree_out)
    # keep stable names for the demo year plus generic
    _write_json(SERVE_WEB / f"degree_days_{year}.json", degree_out)
    _write_json(SERVE_WEB / f"extremes_{year}.json", extremes_out)
    _write_json(SERVE_WEB / f"freeze_{year}.json", freeze_out)
    if year == 2020:
        _write_json(SERVE_WEB / "degree_days_2020.json", degree_out)
        _write_json(SERVE_WEB / "extremes_2020.json", extremes_out)
        _write_json(SERVE_WEB / "freeze_2020.json", freeze_out)
    _write_json(SERVE_WEB / "meta.json", meta)

    man = {
        "built_at_utc": meta["exported_at_utc"],
        "year": year,
        "serve_dir": str(SERVE_WEB),
        "files": [p.name for p in sorted(SERVE_WEB.glob("*.json"))],
    }
    META.mkdir(parents=True, exist_ok=True)
    man_path = META / "serve_web_manifest.json"
    man_path.write_text(json.dumps(man, indent=2), encoding="utf-8")
    print(f"manifest: {man_path}")
    return meta


def copy_to_dunleavy(dunleavy_root: Path, year: int) -> Path:
    dest = dunleavy_root / DUNLEAVY_DATA
    dest.mkdir(parents=True, exist_ok=True)
    names = [
        "stations.json",
        "meta.json",
        f"degree_days_{year}.json",
        f"extremes_{year}.json",
        f"freeze_{year}.json",
    ]
    if year == 2020:
        names.extend(["degree_days_2020.json", "extremes_2020.json", "freeze_2020.json"])
    for name in sorted(set(names)):
        src = SERVE_WEB / name
        if src.exists():
            shutil.copy2(src, dest / name)
            print(f"  copy -> {dest / name}")
    return dest


def main() -> None:
    parser = argparse.ArgumentParser(description="Export gold marts to web JSON")
    parser.add_argument("--year", type=int, default=DEFAULT_YEAR)
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

    export_year(args.year)
    if args.copy_to_dunleavy:
        if not args.dunleavy_root.exists():
            raise SystemExit(f"Dunleavy root not found: {args.dunleavy_root}")
        print(f"Copy to Dunleavy: {args.dunleavy_root}")
        copy_to_dunleavy(args.dunleavy_root, args.year)


if __name__ == "__main__":
    main()
