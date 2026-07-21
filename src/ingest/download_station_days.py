"""
Phase 1 — download daily observation files for a subset of US stations.

GHCNd bulk per-station files:
  {GHCND_BASE}/all/{STATION_ID}.dly

Selection (default):
  - States from --states (default SC,NC,GA)
  - Prefer long-record networks: USW (first-order/airport) and USC (coop)
  - Require inventory coverage for TMAX, TMIN, and PRCP
  - Rank by approximate overlapping year span; optional state balance

Filters:
  --states SC,NC,GA
  --max-stations 25
  --min-span-years 50
  --prefixes USW,USC
  --list-only   (print picks, do not download)
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from src.common.http import download_file
from src.common.paths import BRONZE_META, BRONZE_STATIONS, GHCND_BASE, META

CORE_ELEMENTS = ("TMAX", "TMIN", "PRCP")


def parse_stations(stations_path: Path, states: set[str], prefixes: set[str]) -> list[dict]:
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
        if prefixes and station_id[:3] not in prefixes:
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
                "prefix": station_id[:3],
            }
        )
    return rows


def parse_inventory_spans(inventory_path: Path) -> dict[str, dict[str, tuple[int, int]]]:
    """
    ghcnd-inventory.txt:
    ID 1-11, LAT, LON, ELEMENT 32-35, FIRSTYEAR 36-40, LASTYEAR 41-45
    (1-based columns from NOAA readme; 0-based slices below)
    """
    by_station: dict[str, dict[str, tuple[int, int]]] = defaultdict(dict)
    text = inventory_path.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        if len(line) < 45:
            continue
        station_id = line[0:11].strip()
        element = line[31:35].strip()
        if element not in CORE_ELEMENTS:
            continue
        try:
            first_year = int(line[36:40])
            last_year = int(line[41:45])
        except ValueError:
            continue
        by_station[station_id][element] = (first_year, last_year)
    return by_station


def overlapping_span_years(elem_years: dict[str, tuple[int, int]]) -> int | None:
    """Years where TMAX, TMIN, and PRCP can all exist (rough overlap of ranges)."""
    if not all(e in elem_years for e in CORE_ELEMENTS):
        return None
    first = max(elem_years[e][0] for e in CORE_ELEMENTS)
    last = min(elem_years[e][1] for e in CORE_ELEMENTS)
    if last < first:
        return None
    return last - first + 1


def select_stations(
    stations: list[dict],
    inventory: dict[str, dict[str, tuple[int, int]]],
    *,
    max_stations: int,
    min_span_years: int,
    balance_states: bool,
) -> list[dict]:
    """Rank long-record stations; optionally round-robin across states."""
    scored: list[dict] = []
    for s in stations:
        years = inventory.get(s["id"], {})
        span = overlapping_span_years(years)
        if span is None or span < min_span_years:
            continue
        scored.append(
            {
                **s,
                "span_years": span,
                "tmax_years": list(years["TMAX"]),
                "tmin_years": list(years["TMIN"]),
                "prcp_years": list(years["PRCP"]),
            }
        )

    # Longest records first; id tie-break for stable runs
    scored.sort(key=lambda r: (-r["span_years"], r["id"]))

    if not scored:
        return []

    if not balance_states:
        return scored[:max_stations]

    # Round-robin by state so SC/NC/GA all show up in small samples
    by_state: dict[str, list[dict]] = defaultdict(list)
    for row in scored:
        by_state[row["state"]].append(row)

    state_order = sorted(by_state.keys())
    picks: list[dict] = []
    idx = {st: 0 for st in state_order}
    while len(picks) < max_stations:
        progress = False
        for st in state_order:
            i = idx[st]
            if i < len(by_state[st]):
                picks.append(by_state[st][i])
                idx[st] = i + 1
                progress = True
                if len(picks) >= max_stations:
                    break
        if not progress:
            break
    return picks


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download GHCNd station daily .dly files (bronze), preferring long records"
    )
    parser.add_argument(
        "--states",
        default="SC,NC,GA",
        help="Comma-separated US state codes (default SC,NC,GA)",
    )
    parser.add_argument(
        "--max-stations",
        type=int,
        default=400,
        help="Max stations to download (default 400 ≈ all long-record SC/NC/GA)",
    )
    parser.add_argument(
        "--min-span-years",
        type=int,
        default=50,
        help="Min overlapping TMAX/TMIN/PRCP year span (default 50)",
    )
    parser.add_argument(
        "--prefixes",
        default="USW,USC",
        help="Station ID prefixes to allow (default USW,USC). Empty = any US",
    )
    parser.add_argument(
        "--balance-states",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Round-robin picks across states (default on)",
    )
    parser.add_argument(
        "--list-only",
        action="store_true",
        help="Print selected stations and exit without downloading",
    )
    args = parser.parse_args()
    states = {s.strip().upper() for s in args.states.split(",") if s.strip()}
    prefixes = {p.strip().upper() for p in args.prefixes.split(",") if p.strip()}

    stations_path = BRONZE_META / "ghcnd-stations.txt"
    inventory_path = BRONZE_META / "ghcnd-inventory.txt"
    if not stations_path.exists():
        raise SystemExit(
            f"Missing {stations_path}. Run: python -m src.ingest.download_ghcnd_meta"
        )
    if not inventory_path.exists():
        raise SystemExit(
            f"Missing {inventory_path}. Run: python -m src.ingest.download_ghcnd_meta"
        )

    stations = parse_stations(stations_path, states, prefixes)
    if not stations:
        raise SystemExit(
            f"No stations found for states={sorted(states)} prefixes={sorted(prefixes)}"
        )

    inventory = parse_inventory_spans(inventory_path)
    selected = select_stations(
        stations,
        inventory,
        max_stations=args.max_stations,
        min_span_years=args.min_span_years,
        balance_states=args.balance_states,
    )
    if not selected:
        raise SystemExit(
            f"No stations with TMAX+TMIN+PRCP span>={args.min_span_years} years "
            f"for states={sorted(states)} prefixes={sorted(prefixes)}"
        )

    print(
        f"selected {len(selected)} stations "
        f"(min_span={args.min_span_years}y, prefixes={sorted(prefixes)}, "
        f"balance_states={args.balance_states})"
    )
    for s in selected:
        print(
            f"  {s['id']}  {s['state']}  span~{s['span_years']}y  {s['name']}"
        )

    if args.list_only:
        print("list-only: no download")
        return

    BRONZE_STATIONS.mkdir(parents=True, exist_ok=True)
    META.mkdir(parents=True, exist_ok=True)

    downloaded = []
    errors = []
    for s in selected:
        sid = s["id"]
        dly_url = f"{GHCND_BASE}/all/{sid}.dly"
        dly_dest = BRONZE_STATIONS / f"{sid}.dly"
        try:
            download_file(dly_url, dly_dest)
            downloaded.append({**s, "format": "dly", "path": str(dly_dest)})
        except Exception as e:  # noqa: BLE001
            errors.append({"id": sid, "error": str(e)})
            print(f"error {sid}: {e}")

    manifest = {
        "pulled_at_utc": datetime.now(timezone.utc).isoformat(),
        "states": sorted(states),
        "prefixes": sorted(prefixes),
        "max_stations": args.max_stations,
        "min_span_years": args.min_span_years,
        "balance_states": args.balance_states,
        "requested": len(selected),
        "downloaded": len(downloaded),
        "errors": errors,
        "stations": downloaded,
    }
    out = META / "bronze_stations_manifest.json"
    out.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"manifest: {out}")
    print(f"downloaded {len(downloaded)} / {len(selected)} (errors={len(errors)})")


if __name__ == "__main__":
    main()
