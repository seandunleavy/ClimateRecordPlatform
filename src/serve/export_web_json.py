"""
Export JSON from gold marts for static web charts (Dunleavy).

One combined file per station: by_station/{id}.json (single HTTP request on select).

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


def _records_drop_station_id(df: pd.DataFrame, cols: list[str]) -> list[dict]:
    """Rows without station_id (known from file path / parent object)."""
    use = [c for c in cols if c in df.columns and c != "station_id"]
    if df.empty:
        return []
    return df.loc[:, use].to_dict(orient="records")


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

    # Per-station latest year (not global max year only).
    # Many long-record stations have no rows in calendar year = max(year) yet
    # (closed sites, sparse end-of-record). Using only global max left ~half the
    # map without metrics / "n/a" years.
    latest_global = int(extremes["year"].max())
    idx = extremes.groupby("station_id", sort=False)["year"].idxmax()
    summary = extremes.loc[idx].merge(
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
    # Alias for older consumers
    _write_json(SERVE_WEB / f"network_extremes_{latest_global}.json", summary_out)

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
        # One HTTP request per station select (not five separate files).
        payload = {
            "station_id": str(sid),
            "degree_days": _records_drop_station_id(
                degree.loc[degree["station_id"] == sid].sort_values(["year", "month"]),
                DEGREE_COLS,
            ),
            "extremes": _records_drop_station_id(
                extremes.loc[extremes["station_id"] == sid].sort_values("year"),
                EXTREMES_COLS,
            ),
            "freeze": _records_drop_station_id(
                freeze.loc[freeze["station_id"] == sid].sort_values("year"),
                FREEZE_COLS,
            ),
            "climate": _records_drop_station_id(
                climate.loc[climate["station_id"] == sid].sort_values(["year", "month"]),
                CLIMATE_COLS,
            ),
            "coverage": _records_drop_station_id(
                coverage.loc[coverage["station_id"] == sid].sort_values(
                    ["year", "element_code"]
                ),
                COVERAGE_COLS,
            ),
        }
        _write_json(by_station / f"{sid}.json", payload)
        n_files += 1

    meta = {
        "exported_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "all_years_per_station_v1_2",
        "year_min": year_min,
        "year_max": year_max,
        "station_count": len(stations_out),
        "layout": {
            "stations": "stations.json",
            "stations_map": "stations_map.json",
            "per_station": "by_station/{station_id}.json",
            "per_station_keys": [
                "station_id",
                "degree_days",
                "extremes",
                "freeze",
                "climate",
                "coverage",
            ],
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
        "performance_note": (
            "UI loads indexes once, then one by_station/{id}.json per station selection"
        ),
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
