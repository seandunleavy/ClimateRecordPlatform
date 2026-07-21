"""
Export JSON from gold marts for static web charts (Dunleavy).

Per-station files under by_station/{id}/ keep UI fast at 300+ stations.

Examples:
  python -m src.serve.export_web_json --copy-to-dunleavy
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
    "year",
    "n_freeze_days",
    "last_spring_freeze",
    "first_fall_freeze",
    "growing_season_days",
    "freeze_threshold_c",
]
CLIMATE_COLS = [
    "station_id",
    "year",
    "month",
    "avg_tmax_c",
    "avg_tmin_c",
    "total_prcp_mm",
    "n_days_tmax",
    "n_days_tmin",
    "n_days_prcp",
]
COVERAGE_COLS = [
    "station_id",
    "year",
    "element_code",
    "n_obs",
    "days_in_year",
    "completeness",
]


def _sanitize_for_json(payload: object) -> object:
    if isinstance(payload, list):
        return [_sanitize_for_json(x) for x in payload]
    if isinstance(payload, dict):
        return {k: _sanitize_for_json(v) for k, v in payload.items()}
    try:
        if payload != payload:
            return None
    except Exception:
        pass
    if payload is pd.NaT or payload is pd.NA:
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


def _load_frames():
    stations = pd.read_parquet(GOLD_DIMS / "dim_station.parquet")
    degree = pd.read_parquet(GOLD_MARTS / "mart_degree_days_monthly.parquet")
    extremes = pd.read_parquet(GOLD_MARTS / "mart_extremes_yearly.parquet")
    freeze = pd.read_parquet(GOLD_MARTS / "mart_freeze_season_yearly.parquet")
    climate = pd.read_parquet(GOLD_MARTS / "mart_monthly_climate.parquet")
    coverage = pd.read_parquet(GOLD_MARTS / "mart_coverage_yearly.parquet")
    return stations, degree, extremes, freeze, climate, coverage


def export_all_years() -> dict:
    stations, degree, extremes, freeze, climate, coverage = _load_frames()

    stations_out = (
        stations.sort_values(["name", "state"])
        .loc[:, ["station_id", "name", "state", "latitude", "longitude", "network_prefix"]]
        .to_dict(orient="records")
    )

    year_min = int(min(degree["year"].min(), extremes["year"].min()))
    year_max = int(max(degree["year"].max(), extremes["year"].max()))

    SERVE_WEB.mkdir(parents=True, exist_ok=True)
    by_station = SERVE_WEB / "by_station"
    if by_station.exists():
        shutil.rmtree(by_station)
    by_station.mkdir(parents=True, exist_ok=True)

    print(f"Export ALL YEARS ({year_min}-{year_max}) per-station -> {SERVE_WEB}")
    _write_json(SERVE_WEB / "stations.json", stations_out, compact=False)

    latest = int(extremes["year"].max())
    summary = extremes.loc[extremes["year"] == latest].merge(
        stations[["station_id", "name", "state"]], on="station_id", how="left"
    )
    summary_out = (
        summary.sort_values(["state", "name"])
        .loc[
            :,
            [
                "station_id",
                "name",
                "state",
                "year",
                "n_days_tmax_ge_32c",
                "n_days_tmin_le_0c",
                "n_days_prcp_ge_25mm",
                "max_tmax_c",
                "min_tmin_c",
            ],
        ]
        .to_dict(orient="records")
    )
    _write_json(SERVE_WEB / "network_extremes_latest.json", summary_out)

    # Map points for station map chart
    _write_json(
        SERVE_WEB / "stations_map.json",
        [
            {
                "station_id": s["station_id"],
                "name": s["name"],
                "state": s["state"],
                "lat": s["latitude"],
                "lon": s["longitude"],
            }
            for s in stations_out
            if s.get("latitude") is not None and s.get("longitude") is not None
        ],
        compact=False,
    )

    n_files = 0
    for sid in stations["station_id"].tolist():
        folder = by_station / str(sid)
        folder.mkdir(parents=True, exist_ok=True)
        payloads = {
            "degree_days_monthly.json": degree.loc[degree["station_id"] == sid]
            .sort_values(["year", "month"])
            .loc[:, DEGREE_COLS]
            .to_dict(orient="records"),
            "extremes_yearly.json": extremes.loc[extremes["station_id"] == sid]
            .sort_values("year")
            .loc[:, EXTREMES_COLS]
            .to_dict(orient="records"),
            "freeze_yearly.json": freeze.loc[freeze["station_id"] == sid]
            .sort_values("year")
            .loc[:, FREEZE_COLS]
            .to_dict(orient="records"),
            "monthly_climate.json": climate.loc[climate["station_id"] == sid]
            .sort_values(["year", "month"])
            .loc[:, [c for c in CLIMATE_COLS if c in climate.columns]]
            .to_dict(orient="records"),
            "coverage_yearly.json": coverage.loc[coverage["station_id"] == sid]
            .sort_values(["year", "element_code"])
            .loc[:, [c for c in COVERAGE_COLS if c in coverage.columns]]
            .to_dict(orient="records"),
        }
        for name, rows in payloads.items():
            _write_json(folder / name, rows)
            n_files += 1

    meta = {
        "exported_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "all_years_per_station_v1_1",
        "year_min": year_min,
        "year_max": year_max,
        "station_count": len(stations_out),
        "layout": {
            "stations": "stations.json",
            "stations_map": "stations_map.json",
            "per_station_dir": "by_station/{station_id}/",
            "files_per_station": list(payloads.keys()),
            "network_extremes_latest": "network_extremes_latest.json",
        },
        "row_counts": {
            "degree_days_monthly": int(len(degree)),
            "extremes_yearly": int(len(extremes)),
            "freeze_yearly": int(len(freeze)),
            "monthly_climate": int(len(climate)),
            "coverage_yearly": int(len(coverage)),
            "per_station_json_files": n_files,
        },
        "methods": {
            "qc": "Gold uses silver stations_qc rows with qc_pass=True only",
            "degree_days": "tavg=(TMAX+TMIN)/2; heating/cooling degree-days vs base 18 C",
            "extremes": "Hot TMAX>=32/35 C; freeze TMIN<=0 C; wet PRCP>=25.4 mm",
            "freeze_season": "Freeze TMIN<=0; growing season between last spring and first fall freeze",
        },
        "scope": (
            "South Carolina, North Carolina, Georgia long-record USW/USC "
            "(50+ year TMAX+TMIN+PRCP) — v1 regional platform"
        ),
        "performance_note": "UI loads stations once, then by_station/{id}/* for selection only",
    }
    _write_json(SERVE_WEB / "meta.json", meta, compact=False)
    META.mkdir(parents=True, exist_ok=True)
    (META / "serve_web_manifest.json").write_text(
        json.dumps({"built_at_utc": meta["exported_at_utc"], "meta": meta}, indent=2),
        encoding="utf-8",
    )
    print(f"stations={len(stations_out)} files={n_files}")
    return meta


def copy_to_dunleavy(dunleavy_root: Path) -> Path:
    dest = dunleavy_root / DUNLEAVY_DATA
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(SERVE_WEB, dest)
    print(f"  copied tree -> {dest}")
    return dest


def main() -> None:
    parser = argparse.ArgumentParser(description="Export gold marts to web JSON")
    parser.add_argument("--copy-to-dunleavy", action="store_true")
    parser.add_argument("--dunleavy-root", type=Path, default=DEFAULT_DUNLEAVY)
    args = parser.parse_args()
    export_all_years()
    if args.copy_to_dunleavy:
        if not args.dunleavy_root.exists():
            raise SystemExit(f"Dunleavy root not found: {args.dunleavy_root}")
        copy_to_dunleavy(args.dunleavy_root)


if __name__ == "__main__":
    main()
