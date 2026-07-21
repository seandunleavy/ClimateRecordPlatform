"""
Phase 2 — parse bronze .dly station files into silver Parquet tables.

Examples:
  # One station first (recommended while learning)
  python -m src.transform.bronze_to_silver --station USW00013872

  # All stations in bronze/stations (or only those in latest manifest)
  python -m src.transform.bronze_to_silver --all
  python -m src.transform.bronze_to_silver --from-manifest
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
    return [s["id"] for s in data.get("stations", [])]


def _resolve_dly_paths(args: argparse.Namespace) -> list[Path]:
    if args.station:
        path = BRONZE_STATIONS / f"{args.station}.dly"
        if not path.exists():
            raise SystemExit(f"Missing bronze file: {path}")
        return [path]

    if args.from_manifest:
        ids = _station_ids_from_manifest()
        paths = []
        for sid in ids:
            p = BRONZE_STATIONS / f"{sid}.dly"
            if not p.exists():
                print(f"warn: missing {p.name}, skip")
                continue
            paths.append(p)
        if not paths:
            raise SystemExit("No bronze .dly files found for manifest stations.")
        return paths

    if args.all:
        paths = sorted(BRONZE_STATIONS.glob("*.dly"))
        if not paths:
            raise SystemExit(f"No .dly files under {BRONZE_STATIONS}")
        return paths

    raise SystemExit("Specify --station ID, --from-manifest, or --all")


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

    manifest = {
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "elements_filter": "ALL" if keep_all else sorted(elements),
        "drop_missing": args.drop_missing,
        "stations": summary,
        "total_rows": sum(s["rows"] for s in summary),
    }
    man_path = META / "silver_stations_manifest.json"
    man_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"manifest: {man_path}")
    print(f"total rows: {manifest['total_rows']:,}")
    print(f"silver dir: {SILVER_STATIONS}")


if __name__ == "__main__":
    main()
