"""
Export JSON from gold marts for static web charts (Dunleavy).

At large station counts, full-history degree-day JSON is tens of MB.
Default strategy for performance:
  - stations.json + meta.json (tiny)
  - per-station files under by_station/{id}/  (load only what the UI selects)

Best practice: charts read pre-aggregated marts, not daily facts.

Examples:
  python -m src.serve.export_web_json --copy-to-dunleavy
  python -m src.serve.export_web_json --single-year 2020
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


def _sanitize_for_json(payload: object) -> object:
    if isinstance(payload, list):
        return [_sanitize_for_json(x) for x in payload]
    if isinstance(payload, dict):
        return {k: _sanitize_for_json(v) for k, v in payload.items()}
    try:
        if payload != payload:  # NaN
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
    print(f"  wrote {path} ({path.stat().st_size:,} bytes)")


def _load_frames() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    stations = pd.read_parquet(GOLD_DIMS / "dim_station.parquet")
    degree = pd.read_parquet(GOLD_MARTS / "mart_degree_days_monthly.parquet")
    extremes = pd.read_parquet(GOLD_MARTS / "mart_extremes_yearly.parquet")
    freeze = pd.read_parquet(GOLD_MARTS / "mart_freeze_season_yearly.parquet")
    return stations, degree, extremes, freeze


def export_all_years() -> dict:
    """Full-history mart JSON: stations index + per-station mart files."""
    stations, degree, extremes, freeze = _load_frames()

    stations_out = (
        stations.sort_values(["state", "name"])
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

    # Optional small network summary for multi-station charts (latest year extremes)
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
    _write_json(SERVE_WEB / f"network_extremes_{latest}.json", summary_out)
    _write_json(SERVE_WEB / "network_extremes_latest.json", summary_out)

    n_files = 0
    for sid, g_deg in degree.groupby("station_id"):
        folder = by_station / str(sid)
        deg_rows = g_deg.sort_values(["year", "month"]).loc[:, DEGREE_COLS].to_dict(orient="records")
        ext_rows = (
            extremes.loc[extremes["station_id"] == sid]
            .sort_values("year")
            .loc[:, EXTREMES_COLS]
            .to_dict(orient="records")
        )
        fr_rows = (
            freeze.loc[freeze["station_id"] == sid]
            .sort_values("year")
            .loc[:, FREEZE_COLS]
            .to_dict(orient="records")
        )
        _write_json(folder / "degree_days_monthly.json", deg_rows)
        _write_json(folder / "extremes_yearly.json", ext_rows)
        _write_json(folder / "freeze_yearly.json", fr_rows)
        n_files += 3

    meta = {
        "exported_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "all_years_per_station",
        "year_min": year_min,
        "year_max": year_max,
        "station_count": len(stations_out),
        "layout": {
            "stations": "stations.json",
            "per_station_dir": "by_station/{station_id}/",
            "files_per_station": [
                "degree_days_monthly.json",
                "extremes_yearly.json",
                "freeze_yearly.json",
            ],
            "network_extremes_latest": "network_extremes_latest.json",
        },
        "row_counts": {
            "degree_days_monthly": int(len(degree)),
            "extremes_yearly": int(len(extremes)),
            "freeze_yearly": int(len(freeze)),
            "per_station_json_files": n_files,
        },
        "methods": {
            "qc": "Gold uses silver stations_qc rows with qc_pass=True only",
            "degree_days": "tavg=(TMAX+TMIN)/2; heating/cooling degree-days vs base 18 C; monthly sums",
            "extremes": "Hot TMAX>=32/35 C; freeze TMIN<=0 C; wet PRCP>=25.4 mm",
            "freeze_season": "Freeze TMIN<=0; last spring freeze month<=6; first fall month>=7",
        },
        "scope": (
            "South Carolina, North Carolina, Georgia long-record USW/USC sample "
            "(50+ year TMAX+TMIN+PRCP overlap) — portfolio demo, not a national NCEI product"
        ),
        "performance_note": (
            "UI should load stations.json once, then only by_station/{id}/*.json for the selected station"
        ),
    }
    _write_json(SERVE_WEB / "meta.json", meta, compact=False)

    man = {
        "built_at_utc": meta["exported_at_utc"],
        "mode": meta["mode"],
        "station_count": meta["station_count"],
        "serve_dir": str(SERVE_WEB),
        "meta": meta,
    }
    META.mkdir(parents=True, exist_ok=True)
    (META / "serve_web_manifest.json").write_text(json.dumps(man, indent=2), encoding="utf-8")
    print(f"manifest: {META / 'serve_web_manifest.json'}")
    print(f"stations={len(stations_out)}  per-station file groups={len(stations_out)}")
    return meta


def export_year(year: int) -> dict:
    """Single-year combined files (legacy / small demos)."""
    stations, degree, extremes, freeze = _load_frames()
    stations_out = (
        stations.sort_values(["state", "name"])
        .loc[:, ["station_id", "name", "state", "latitude", "longitude", "network_prefix"]]
        .to_dict(orient="records")
    )
    deg = degree.loc[degree["year"] == year].merge(
        stations[["station_id", "name", "state"]], on="station_id", how="left"
    )
    ext = extremes.loc[extremes["year"] == year].merge(
        stations[["station_id", "name", "state"]], on="station_id", how="left"
    )
    fr = freeze.loc[freeze["year"] == year].merge(
        stations[["station_id", "name", "state"]], on="station_id", how="left"
    )
    SERVE_WEB.mkdir(parents=True, exist_ok=True)
    _write_json(SERVE_WEB / "stations.json", stations_out, compact=False)
    _write_json(
        SERVE_WEB / f"degree_days_{year}.json",
        deg.sort_values(["state", "name", "month"]).to_dict(orient="records"),
        compact=False,
    )
    _write_json(
        SERVE_WEB / f"extremes_{year}.json",
        ext.sort_values(["state", "name"]).to_dict(orient="records"),
        compact=False,
    )
    _write_json(
        SERVE_WEB / f"freeze_{year}.json",
        fr.sort_values(["state", "name"]).to_dict(orient="records"),
        compact=False,
    )
    meta = {
        "mode": "single_year",
        "year": year,
        "station_count": len(stations_out),
        "exported_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    _write_json(SERVE_WEB / "meta.json", meta, compact=False)
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
    parser.add_argument("--single-year", type=int, default=None, metavar="YEAR")
    parser.add_argument("--year", type=int, default=None, help="Alias for --single-year")
    parser.add_argument("--copy-to-dunleavy", action="store_true")
    parser.add_argument("--dunleavy-root", type=Path, default=DEFAULT_DUNLEAVY)
    args = parser.parse_args()

    single = args.single_year if args.single_year is not None else args.year
    if single is not None:
        export_year(single)
    else:
        export_all_years()

    if args.copy_to_dunleavy:
        if not args.dunleavy_root.exists():
            raise SystemExit(f"Dunleavy root not found: {args.dunleavy_root}")
        print(f"Copy to Dunleavy: {args.dunleavy_root}")
        copy_to_dunleavy(args.dunleavy_root)


if __name__ == "__main__":
    main()
