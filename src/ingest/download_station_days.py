"""
Phase 1 — download daily observation files for US stations.

GHCNd bulk per-station files:
  {GHCND_BASE}/all/{STATION_ID}.dly

Selection (same rules regional and nationwide):
  - USW (first-order/airport) and USC (coop) by default
  - Inventory overlap for TMAX + TMIN + PRCP ≥ min span (default 50 years)
  - States from --states (default SC,NC,GA) or --nationwide (all states + DC)

Examples:
  python -m src.ingest.download_station_days --states SC,NC,GA --max-stations 400
  python -m src.ingest.download_station_days --nationwide --list-only
  python -m src.ingest.download_station_days --nationwide
  python -m src.ingest.download_station_days --from-manifest --force
  python -m src.ingest.download_station_days --from-manifest --force --limit 5
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

# Contiguous + AK/HI + DC — same long-record rules as regional v1, full map
US_STATES_NATIONWIDE = frozenset(
    {
        "AL",
        "AK",
        "AZ",
        "AR",
        "CA",
        "CO",
        "CT",
        "DE",
        "FL",
        "GA",
        "HI",
        "ID",
        "IL",
        "IN",
        "IA",
        "KS",
        "KY",
        "LA",
        "ME",
        "MD",
        "MA",
        "MI",
        "MN",
        "MS",
        "MO",
        "MT",
        "NE",
        "NV",
        "NH",
        "NJ",
        "NM",
        "NY",
        "NC",
        "ND",
        "OH",
        "OK",
        "OR",
        "PA",
        "RI",
        "SC",
        "SD",
        "TN",
        "TX",
        "UT",
        "VT",
        "VA",
        "WA",
        "WV",
        "WI",
        "WY",
        "DC",
    }
)


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
    max_stations: int | None,
    min_span_years: int,
    balance_states: bool,
) -> list[dict]:
    """Rank long-record stations; optionally round-robin across states.

    max_stations=None means take every station that passes the span filter
    (used for nationwide full long-record set).
    """
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

    limit = len(scored) if max_stations is None else max_stations

    if not balance_states:
        return scored[:limit]

    # Round-robin by state so multi-state samples stay balanced when capped
    by_state: dict[str, list[dict]] = defaultdict(list)
    for row in scored:
        by_state[row["state"]].append(row)

    state_order = sorted(by_state.keys())
    picks: list[dict] = []
    idx = {st: 0 for st in state_order}
    while len(picks) < limit:
        progress = False
        for st in state_order:
            i = idx[st]
            if i < len(by_state[st]):
                picks.append(by_state[st][i])
                idx[st] = i + 1
                progress = True
                if len(picks) >= limit:
                    break
        if not progress:
            break
    return picks


def _load_manifest_stations() -> tuple[list[dict], dict]:
    """Stations already selected (refresh cohort). Preserves v2 nationwide set."""
    path = META / "bronze_stations_manifest.json"
    if not path.exists():
        raise SystemExit(
            f"Missing {path}. Run a full download first "
            "(e.g. python -m src.ingest.download_station_days --nationwide)."
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    stations = data.get("stations") or []
    if not stations:
        raise SystemExit(f"No stations listed in {path}")
    return stations, data


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download GHCNd station daily .dly files (bronze), long-record USW/USC"
    )
    parser.add_argument(
        "--states",
        default="SC,NC,GA",
        help="Comma-separated US state codes (default SC,NC,GA). Ignored if --nationwide.",
    )
    parser.add_argument(
        "--nationwide",
        action="store_true",
        help=(
            "All US states + DC with the same long-record rules as regional v1 "
            "(USW/USC, 50y TMAX+TMIN+PRCP). Takes every qualifying station "
            "(max-stations 0). Disables state balance."
        ),
    )
    parser.add_argument(
        "--from-manifest",
        action="store_true",
        help=(
            "Refresh downloads for stations already in bronze_stations_manifest.json "
            "(preserves the locked cohort; use with --force for NOAA updates)."
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download .dly files even if they already exist (refresh path)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only first N stations (smoke / partial refresh). Applies after selection.",
    )
    parser.add_argument(
        "--max-stations",
        type=int,
        default=None,
        help=(
            "Max stations to download. Default: 400 regional, unlimited with --nationwide. "
            "Use 0 for unlimited. Ignored with --from-manifest (use --limit)."
        ),
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
        help="Round-robin picks across states when max is capped (default on)",
    )
    parser.add_argument(
        "--list-only",
        action="store_true",
        help="Print selected stations and exit without downloading",
    )
    parser.add_argument(
        "--quiet-list",
        action="store_true",
        help="With --list-only, print summary only (no per-station lines)",
    )
    args = parser.parse_args()

    if args.from_manifest and (args.nationwide or args.states != "SC,NC,GA"):
        # states default is always set; only warn when user also passed nationwide
        if args.nationwide:
            print("note: --from-manifest ignores --nationwide (cohort from manifest)")

    # --- selection: either locked cohort or re-select from inventory ---
    if args.from_manifest:
        selected, prior = _load_manifest_stations()
        # Normalize keys: manifest may use "id" only
        normalized: list[dict] = []
        for s in selected:
            row = dict(s)
            if "id" not in row and "station_id" in row:
                row["id"] = row["station_id"]
            normalized.append(row)
        selected = normalized
        scope_label = prior.get("scope") or (
            "nationwide" if prior.get("nationwide") else "manifest"
        )
        states = set(prior.get("states") or [])
        prefixes = set(prior.get("prefixes") or [])
        max_stations = prior.get("max_stations")
        balance_states = bool(prior.get("balance_states", False))
        min_span = prior.get("min_span_years", args.min_span_years)
        print(
            f"from-manifest: {len(selected)} stations "
            f"(scope={scope_label}, force={args.force})"
        )
    else:
        if args.nationwide:
            states = set(US_STATES_NATIONWIDE)
            balance_states = False
            scope_label = "nationwide"
            if args.max_stations is None or args.max_stations == 0:
                max_stations: int | None = None
            else:
                max_stations = args.max_stations
        else:
            states = {s.strip().upper() for s in args.states.split(",") if s.strip()}
            balance_states = args.balance_states
            scope_label = "regional"
            if args.max_stations is None:
                max_stations = 400
            elif args.max_stations == 0:
                max_stations = None
            else:
                max_stations = args.max_stations

        prefixes = {p.strip().upper() for p in args.prefixes.split(",") if p.strip()}
        min_span = args.min_span_years

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
            max_stations=max_stations,
            min_span_years=min_span,
            balance_states=balance_states,
        )
        if not selected:
            raise SystemExit(
                f"No stations with TMAX+TMIN+PRCP span>={min_span} years "
                f"for states={sorted(states)} prefixes={sorted(prefixes)}"
            )

    if args.limit is not None:
        if args.limit < 1:
            raise SystemExit("--limit must be >= 1")
        selected = selected[: args.limit]
        print(f"limit: first {len(selected)} stations")

    from collections import Counter

    by_st = Counter(s.get("state") or "?" for s in selected)
    print(
        f"selected {len(selected)} stations ({scope_label}) "
        f"min_span={min_span}y prefixes={sorted(prefixes) if prefixes else 'n/a'} "
        f"balance_states={balance_states} states={len(by_st)} force={args.force}"
    )
    if not args.quiet_list:
        for s in selected:
            span = s.get("span_years", "?")
            print(
                f"  {s['id']}  {s.get('state', '?')}  span~{span}y  {s.get('name', '')}"
            )
    else:
        print("top states:", by_st.most_common(12))

    if args.list_only:
        print("list-only: no download")
        return

    BRONZE_STATIONS.mkdir(parents=True, exist_ok=True)
    META.mkdir(parents=True, exist_ok=True)

    downloaded = []
    errors = []
    changed_ids: list[str] = []
    unchanged_ids: list[str] = []
    total = len(selected)
    for i, s in enumerate(selected, start=1):
        sid = s["id"]
        dly_url = f"{GHCND_BASE}/all/{sid}.dly"
        dly_dest = BRONZE_STATIONS / f"{sid}.dly"
        try:
            if i == 1 or i % 50 == 0 or i == total:
                print(f"progress {i}/{total} …")
            info = download_file(dly_url, dly_dest, force=args.force)
            row = {
                **{k: v for k, v in s.items() if k not in ("path", "format")},
                "format": "dly",
                "path": str(dly_dest),
                "bytes": info["bytes"],
                "previous_bytes": info["previous_bytes"],
                "skipped": info["skipped"],
                "changed": info["changed"],
            }
            downloaded.append(row)
            if info["changed"]:
                changed_ids.append(sid)
            else:
                unchanged_ids.append(sid)
        except Exception as e:  # noqa: BLE001
            errors.append({"id": sid, "error": str(e)})
            print(f"error {sid}: {e}")

    # Preserve full cohort on partial refresh; replace station rows on full refresh.
    prior_meta: dict = {}
    if args.from_manifest:
        prior_stations, prior_meta = _load_manifest_stations()
        if args.limit is not None:
            by_id = {s["id"]: dict(s) for s in prior_stations if "id" in s}
            for row in downloaded:
                by_id[row["id"]] = {**by_id.get(row["id"], {}), **row}
            order = [s["id"] for s in prior_stations if "id" in s]
            manifest_stations = [by_id[i] for i in order if i in by_id]
            requested = len(prior_stations)
        else:
            manifest_stations = downloaded
            requested = len(selected)
    else:
        manifest_stations = downloaded
        requested = len(selected)

    default_rules = (
        "USW/USC; inventory overlapping TMAX+TMIN+PRCP span >= min_span_years "
        "(same rules as regional v1)"
    )
    manifest = {
        "pulled_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": prior_meta.get("scope", scope_label) if args.from_manifest else scope_label,
        "nationwide": (
            bool(prior_meta.get("nationwide", False))
            if args.from_manifest
            else bool(args.nationwide)
        ),
        "from_manifest": bool(args.from_manifest),
        "force": args.force,
        "limit": args.limit,
        "states": prior_meta.get("states") or sorted(states),
        "prefixes": prior_meta.get("prefixes") or sorted(prefixes),
        "max_stations": (
            prior_meta.get("max_stations") if args.from_manifest else max_stations
        ),
        "min_span_years": (
            prior_meta.get("min_span_years", min_span) if args.from_manifest else min_span
        ),
        "balance_states": (
            prior_meta.get("balance_states", False) if args.from_manifest else balance_states
        ),
        "selection_rules": prior_meta.get("selection_rules", default_rules),
        "requested": requested,
        "downloaded": len(manifest_stations),
        "errors": errors,
        "last_pull_changed_station_ids": changed_ids,
        "last_pull_unchanged_station_ids": unchanged_ids,
        "last_pull_changed_count": len(changed_ids),
        "last_pull_count": len(downloaded),
        "stations": manifest_stations,
    }

    out = META / "bronze_stations_manifest.json"
    out.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"manifest: {out}")
    print(
        f"downloaded {len(downloaded)} / {len(selected)} "
        f"(errors={len(errors)}, changed={len(changed_ids)}, unchanged={len(unchanged_ids)})"
    )


if __name__ == "__main__":
    main()
