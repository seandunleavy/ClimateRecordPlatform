"""
Phase 2 — parse bronze .dly station files into silver Parquet tables.

Examples:
  # One station first (recommended while learning)
  python -m src.transform.bronze_to_silver --station USW00013872

  # All stations in bronze/stations (or only those in latest manifest)
  python -m src.transform.bronze_to_silver --all
  python -m src.transform.bronze_to_silver --from-manifest
  python -m src.transform.bronze_to_silver --stations USW00013872,USC00380001
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.common.paths import BRONZE_STATIONS, META, SILVER, SILVER_STATIONS
from src.transform.parse_dly import parse_dly_file


def _station_ids_from_manifest() -> list[str]:
    path = META / "bronze_stations_manifest.json"
    if not path.exists():
        raise SystemExit(f"Missing {path}. Run station download first.")
    data = json.loads(path.read_text(encoding="utf-8"))
    return [s["id"] for s in data.get("stations", []) if s.get("id")]


def _paths_for_ids(ids: list[str]) -> list[Path]:
    paths = []
    for sid in ids:
        p = BRONZE_STATIONS / f"{sid}.dly"
        if not p.exists():
            print(f"warn: missing {p.name}, skip")
            continue
        paths.append(p)
    if not paths:
        raise SystemExit("No bronze .dly files found for requested stations.")
    return paths


def _resolve_dly_paths(args: argparse.Namespace) -> list[Path]:
    if args.station:
        path = BRONZE_STATIONS / f"{args.station}.dly"
        if not path.exists():
            raise SystemExit(f"Missing bronze file: {path}")
        return [path]

    if args.stations:
        ids = [s.strip() for s in args.stations.split(",") if s.strip()]
        if not ids:
            raise SystemExit("--stations was empty")
        return _paths_for_ids(ids)

    if args.from_manifest:
        return _paths_for_ids(_station_ids_from_manifest())

    if args.all:
        paths = sorted(BRONZE_STATIONS.glob("*.dly"))
        if not paths:
            raise SystemExit(f"No .dly files under {BRONZE_STATIONS}")
        return paths

    raise SystemExit("Specify --station ID, --stations a,b, --from-manifest, or --all")


def rows_to_frame(rows: list[dict]) -> pd.DataFrame:
    columns = [
        "station_id",
        "date",
        "element",
        "value_raw",
        "value",
        "unit",
        "mflag",
        "qflag",
        "sflag",
        "is_missing",
    ]
    if not rows:
        return pd.DataFrame(columns=columns)
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"], format="%Y-%m-%d")
    # Stable column order
    return df[columns]


def write_station_parquet(df: pd.DataFrame, station_id: str) -> Path:
    SILVER_STATIONS.mkdir(parents=True, exist_ok=True)
    out = SILVER_STATIONS / f"{station_id}.parquet"
    df.to_parquet(out, index=False)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Bronze .dly -> silver Parquet observations")
    parser.add_argument("--station", help="Single station ID (e.g. USW00013872)")
    parser.add_argument(
        "--stations",
        help="Comma-separated station IDs (refresh subset)",
    )
    parser.add_argument(
        "--from-manifest",
        action="store_true",
        help="Parse only stations listed in bronze_stations_manifest.json",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Parse every .dly under data/bronze/stations",
    )
    parser.add_argument(
        "--elements",
        default="TMAX,TMIN,PRCP",
        help="Comma-separated elements to keep (default TMAX,TMIN,PRCP). "
        "Use ALL to keep every element.",
    )
    parser.add_argument(
        "--drop-missing",
        action="store_true",
        help="Drop rows where value was -9999 (default: keep with is_missing=True)",
    )
    args = parser.parse_args()

    keep_all = args.elements.strip().upper() == "ALL"
    elements = {e.strip().upper() for e in args.elements.split(",") if e.strip()}

    paths = _resolve_dly_paths(args)
    META.mkdir(parents=True, exist_ok=True)

    summary = []
    for path in paths:
        station_id = path.stem
        print(f"parse {path.name} ...")
        rows = parse_dly_file(path)
        df = rows_to_frame(rows)

        if not keep_all and not df.empty:
            df = df[df["element"].isin(elements)].copy()

        if args.drop_missing and not df.empty:
            df = df[~df["is_missing"]].copy()

        out = write_station_parquet(df, station_id)
        n = len(df)
        date_min = str(df["date"].min().date()) if n else None
        date_max = str(df["date"].max().date()) if n else None
        elem_counts = (
            df["element"].value_counts().to_dict() if n else {}
        )
        print(
            f"  -> {out.name}: {n:,} rows  "
            f"range={date_min} .. {date_max}  elements={elem_counts}"
        )
        summary.append(
            {
                "station_id": station_id,
                "rows": n,
                "date_min": date_min,
                "date_max": date_max,
                "elements": {str(k): int(v) for k, v in elem_counts.items()},
                "path": str(out),
            }
        )

    man_path = META / "silver_stations_manifest.json"
    # Partial runs (--station / --stations) merge so we do not wipe full-cohort inventory
    partial = bool(args.station or args.stations)
    if partial and man_path.exists():
        prior = json.loads(man_path.read_text(encoding="utf-8"))
        by_id = {
            s["station_id"]: s
            for s in prior.get("stations", [])
            if s.get("station_id")
        }
        for s in summary:
            by_id[s["station_id"]] = s
        stations_out = list(by_id.values())
        last_refresh = {
            "station_ids": [s["station_id"] for s in summary],
            "rows": sum(s["rows"] for s in summary),
        }
    else:
        stations_out = summary
        last_refresh = None

    manifest = {
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "elements_filter": "ALL" if keep_all else sorted(elements),
        "drop_missing": args.drop_missing,
        "partial_run": partial,
        "stations": stations_out,
        "total_rows": sum(s["rows"] for s in stations_out),
        "last_partial_refresh": last_refresh,
    }
    man_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"manifest: {man_path}")
    print(f"total rows: {manifest['total_rows']:,}")
    print(f"silver dir: {SILVER_STATIONS}")


if __name__ == "__main__":
    main()
