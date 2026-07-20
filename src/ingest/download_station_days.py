"""
Phase 1 — download daily observation files for a subset of US stations.

GHCNd per-station CSV (preferred):
  {GHCND_BASE}/all/{STATION_ID}.csv

US stations in ghcnd-stations.txt have IDs like USC0038.... / USW0001....

Filters:
  --states SC,NC,GA   (from station file columns)
  --max-stations 25
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from src.common.http import download_file
from src.common.paths import BRONZE_META, BRONZE_STATIONS, GHCND_BASE, META


def parse_stations(stations_path: Path, states: set[str]) -> list[dict]:
    """
    ghcnd-stations.txt fixed-ish format:
    ID 0-11, LAT 12-20, LON 21-30, ELEV 31-37, STATE 38-40, NAME 41-71, ...
    """
    rows: list[dict] = []
    text = stations_path.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        if len(line) < 41:
            continue
        station_id = line[0:11].strip()
        if not station_id.startswith("US"):
            continue
        state = line[38:40].strip().upper()
        if states and state not in states:
            continue
        name = line[41:71].strip()
        try:
            lat = float(line[12:20].strip())
            lon = float(line[21:30].strip())
        except ValueError:
            continue
        rows.append(
            {
                "id": station_id,
                "state": state,
                "name": name,
                "lat": lat,
                "lon": lon,
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Download GHCNd station daily CSVs (bronze)")
    parser.add_argument(
        "--states",
        default="SC,NC,GA",
        help="Comma-separated US state codes (default SC,NC,GA)",
    )
    parser.add_argument(
        "--max-stations",
        type=int,
        default=25,
        help="Max stations to download (default 25)",
    )
    parser.add_argument(
        "--prefer-recent",
        action="store_true",
        default=True,
        help="Prefer stations whose IDs sort later (rough proxy); default on",
    )
    args = parser.parse_args()
    states = {s.strip().upper() for s in args.states.split(",") if s.strip()}

    stations_path = BRONZE_META / "ghcnd-stations.txt"
    if not stations_path.exists():
        raise SystemExit(
            f"Missing {stations_path}. Run: python -m src.ingest.download_ghcnd_meta"
        )

    stations = parse_stations(stations_path, states)
    if not stations:
        raise SystemExit(f"No US stations found for states={sorted(states)}")

    # Deterministic sample: sort by id, take first N (stable portfolio runs)
    stations = sorted(stations, key=lambda r: r["id"])[: args.max_stations]

    BRONZE_STATIONS.mkdir(parents=True, exist_ok=True)
    META.mkdir(parents=True, exist_ok=True)

    downloaded = []
    errors = []
    for s in stations:
        sid = s["id"]
        # CSV form under all/ — some IDs only have .dly; try csv then dly
        csv_url = f"{GHCND_BASE}/all/{sid}.csv"
        dly_url = f"{GHCND_BASE}/all/{sid}.dly"
        csv_dest = BRONZE_STATIONS / f"{sid}.csv"
        dly_dest = BRONZE_STATIONS / f"{sid}.dly"
        try:
            try:
                download_file(csv_url, csv_dest)
                downloaded.append({**s, "format": "csv", "path": str(csv_dest)})
            except Exception:
                download_file(dly_url, dly_dest)
                downloaded.append({**s, "format": "dly", "path": str(dly_dest)})
        except Exception as e:  # noqa: BLE001
            errors.append({"id": sid, "error": str(e)})
            print(f"error {sid}: {e}")

    manifest = {
        "pulled_at_utc": datetime.now(timezone.utc).isoformat(),
        "states": sorted(states),
        "max_stations": args.max_stations,
        "requested": len(stations),
        "downloaded": len(downloaded),
        "errors": errors,
        "stations": downloaded,
    }
    out = META / "bronze_stations_manifest.json"
    out.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"manifest: {out}")
    print(f"downloaded {len(downloaded)} / {len(stations)} (errors={len(errors)})")


if __name__ == "__main__":
    main()
