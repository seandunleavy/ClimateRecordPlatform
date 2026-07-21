"""
Light quality checks on silver station Parquet files.

  python -m src.transform.silver_quality_check
  python -m src.transform.silver_quality_check --station USW00013872
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.common.paths import META, SILVER_STATIONS


def check_station(path: Path) -> dict:
    df = pd.read_parquet(path)
    n = len(df)
    station_id = path.stem

    if n == 0:
        return {
            "station_id": station_id,
            "rows": 0,
            "ok": False,
            "issues": ["empty file"],
        }

    elements: dict = {}
    for element, g in df.groupby("element"):
        observed = g.loc[~g["is_missing"], "value"]
        elements[str(element)] = {
            "n": int(len(g)),
            "missing_rate": round(float(g["is_missing"].mean()), 4),
            "qflag_rate": round(float(g["qflag"].notna().mean()), 4),
            "date_min": str(g["date"].min().date()),
            "date_max": str(g["date"].max().date()),
            "value_min": None if observed.empty else round(float(observed.min()), 2),
            "value_max": None if observed.empty else round(float(observed.max()), 2),
        }

    wide = (
        df.loc[~df["is_missing"]]
        .pivot_table(index="date", columns="element", values="value", aggfunc="first")
    )
    both = 0
    tmax_lt_tmin = 0
    if "TMAX" in wide.columns and "TMIN" in wide.columns:
        paired = wide.dropna(subset=["TMAX", "TMIN"])
        both = int(len(paired))
        tmax_lt_tmin = int((paired["TMAX"] < paired["TMIN"]).sum())

    dups = int(df.duplicated(subset=["station_id", "date", "element"]).sum())
    missing_rate = round(float(df["is_missing"].mean()), 4)
    qflag_rate = round(float(df["qflag"].notna().mean()), 4)

    issues: list[str] = []
    if dups:
        issues.append(f"{dups} duplicate station_id+date+element keys")
    date_max = str(df["date"].max().date())
    if date_max < "2015-01-01":
        issues.append(f"series ends early ({date_max})")
    if missing_rate > 0.05:
        issues.append(f"high overall missing rate {100 * missing_rate:.1f}%")
    if both and (tmax_lt_tmin / both) > 0.01:
        issues.append(
            f"TMAX < TMIN on {tmax_lt_tmin}/{both} paired days "
            f"({100 * tmax_lt_tmin / both:.2f}%)"
        )
    for elem, stats in elements.items():
        if elem in {"TMAX", "TMIN"} and stats["value_min"] is not None:
            if stats["value_max"] > 60 or stats["value_min"] < -50:
                issues.append(
                    f"{elem} extreme range {stats['value_min']}..{stats['value_max']} C"
                )
        if elem == "PRCP" and stats["value_max"] is not None and stats["value_max"] > 500:
            issues.append(f"PRCP very high max {stats['value_max']} mm")

    return {
        "station_id": station_id,
        "rows": n,
        "date_min": str(df["date"].min().date()),
        "date_max": date_max,
        "missing_rate": missing_rate,
        "qflag_rate": qflag_rate,
        "days_both_tmax_tmin": both,
        "days_tmax_lt_tmin": tmax_lt_tmin,
        "dup_keys": dups,
        "elements": elements,
        "issues": issues,
        "ok": len(issues) == 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Quality checks for silver station Parquet")
    parser.add_argument("--station", help="Single station ID (default: all under silver/stations)")
    args = parser.parse_args()

    if args.station:
        paths = [SILVER_STATIONS / f"{args.station}.parquet"]
        if not paths[0].exists():
            raise SystemExit(f"Missing {paths[0]}")
    else:
        paths = sorted(SILVER_STATIONS.glob("*.parquet"))
        if not paths:
            raise SystemExit(f"No Parquet files under {SILVER_STATIONS}")

    reports = [check_station(p) for p in paths]

    header = (
        f"{'station':<14} {'rows':>9} {'from':<12} {'to':<12} "
        f"{'miss%':>7} {'qflag%':>7} {'TMAX<TMIN':>12} {'dups':>5} status"
    )
    print(header)
    print("-" * len(header))
    for r in reports:
        both = r.get("days_both_tmax_tmin", 0)
        bad = r.get("days_tmax_lt_tmin", 0)
        status = "OK" if r.get("ok") else "REVIEW"
        print(
            f"{r['station_id']:<14} {r['rows']:>9,} "
            f"{r.get('date_min') or '-':<12} {r.get('date_max') or '-':<12} "
            f"{100 * (r.get('missing_rate') or 0):>6.2f}% "
            f"{100 * (r.get('qflag_rate') or 0):>6.2f}% "
            f"{bad:>5}/{both:<5} {r.get('dup_keys', 0):>5} {status}"
        )

    print()
    print("Per-element missing % and range (non-missing values):")
    for r in reports:
        if not r.get("elements"):
            continue
        bits = []
        for elem in ("PRCP", "TMAX", "TMIN"):
            stats = r["elements"].get(elem)
            if not stats:
                continue
            vmin, vmax = stats["value_min"], stats["value_max"]
            bits.append(
                f"{elem} miss={100 * stats['missing_rate']:.1f}% "
                f"[{stats['date_min']}..{stats['date_max']}] "
                f"val={vmin}..{vmax}"
            )
        print(f"  {r['station_id']}")
        for b in bits:
            print(f"    {b}")

    flagged = [r for r in reports if r.get("issues")]
    print()
    if not flagged:
        print("Issues: none (all stations passed light checks)")
    else:
        print(f"Issues ({len(flagged)} station(s) need review):")
        for r in flagged:
            print(f"  {r['station_id']}:")
            for issue in r["issues"]:
                print(f"    - {issue}")

    total_rows = sum(r.get("rows", 0) for r in reports)
    print()
    print(f"stations={len(reports)}  total_rows={total_rows:,}")

    META.mkdir(parents=True, exist_ok=True)
    out = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "stations": reports,
        "total_rows": total_rows,
        "stations_ok": sum(1 for r in reports if r.get("ok")),
        "stations_review": sum(1 for r in reports if not r.get("ok")),
    }
    man = META / "silver_quality_manifest.json"
    man.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"manifest: {man}")


if __name__ == "__main__":
    main()
