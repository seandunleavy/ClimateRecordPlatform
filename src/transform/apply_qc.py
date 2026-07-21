"""
Apply row-level QC flags to silver station Parquet.

Keeps every row (faithful silver). Adds:
  - qc_pass (bool)
  - qc_reasons (string; comma-separated codes when failed)

Default rules (SE US daily TMAX/TMIN/PRCP oriented):
  missing      — is_missing is True (NOAA -9999)
  qflag        — NOAA quality flag present
  range_temp   — TMAX/TMIN outside [temp_min_c, temp_max_c]
  range_prcp   — PRCP < 0 or PRCP > prcp_max_mm
  tmax_lt_tmin — same calendar day TMAX < TMIN (both fail)

Examples:
  python -m src.transform.apply_qc --station USW00013872
  python -m src.transform.apply_qc --all
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from src.common.paths import META, SILVER_STATIONS, SILVER_STATIONS_QC

DEFAULT_TEMP_MIN_C = -40.0
DEFAULT_TEMP_MAX_C = 55.0
DEFAULT_PRCP_MAX_MM = 500.0


def apply_qc_flags(
    df: pd.DataFrame,
    *,
    temp_min_c: float = DEFAULT_TEMP_MIN_C,
    temp_max_c: float = DEFAULT_TEMP_MAX_C,
    prcp_max_mm: float = DEFAULT_PRCP_MAX_MM,
) -> pd.DataFrame:
    """Return a copy with qc_pass and qc_reasons columns."""
    out = df.reset_index(drop=True).copy()
    n = len(out)
    if n == 0:
        out["qc_pass"] = pd.Series(dtype=bool)
        out["qc_reasons"] = pd.Series(dtype=object)
        return out

    is_missing = out["is_missing"].fillna(False).to_numpy()
    has_qflag = out["qflag"].notna() & (out["qflag"].astype(str).str.len() > 0)
    has_qflag = has_qflag.to_numpy()

    element = out["element"].to_numpy()
    value = out["value"].to_numpy(dtype=float)
    is_temp = np.isin(element, ["TMAX", "TMIN"])
    is_prcp = element == "PRCP"
    observed = ~is_missing & ~np.isnan(value)

    bad_temp = is_temp & observed & ((value < temp_min_c) | (value > temp_max_c))
    bad_prcp = is_prcp & observed & ((value < 0) | (value > prcp_max_mm))

    # Same-day TMAX < TMIN
    bad_pair = np.zeros(n, dtype=bool)
    temps = out.loc[is_temp & ~is_missing, ["date", "element", "value"]]
    if not temps.empty:
        wide = temps.pivot_table(
            index="date", columns="element", values="value", aggfunc="first"
        )
        if "TMAX" in wide.columns and "TMIN" in wide.columns:
            bad_days = set(wide.index[wide["TMAX"] < wide["TMIN"]])
            if bad_days:
                bad_pair = (
                    out["date"].isin(bad_days)
                    & out["element"].isin(["TMAX", "TMIN"])
                    & ~out["is_missing"].fillna(False)
                ).to_numpy()

    # Build reason strings vectorized via stacked masks
    reason_lists: list[str | None] = [None] * n
    for i in range(n):
        parts: list[str] = []
        if is_missing[i]:
            parts.append("missing")
        if has_qflag[i]:
            parts.append("qflag")
        if bad_temp[i]:
            parts.append("range_temp")
        if bad_prcp[i]:
            parts.append("range_prcp")
        if bad_pair[i]:
            parts.append("tmax_lt_tmin")
        reason_lists[i] = ",".join(parts) if parts else None

    out["qc_reasons"] = reason_lists
    out["qc_pass"] = out["qc_reasons"].isna()
    return out


def summarize(df: pd.DataFrame) -> dict:
    n = len(df)
    if n == 0:
        return {"rows": 0, "pass": 0, "fail": 0, "pass_rate": None, "reason_counts": {}}

    fail = df.loc[~df["qc_pass"], "qc_reasons"].dropna()
    reason_counts: dict[str, int] = {}
    for cell in fail:
        for code in str(cell).split(","):
            reason_counts[code] = reason_counts.get(code, 0) + 1

    n_pass = int(df["qc_pass"].sum())
    return {
        "rows": n,
        "pass": n_pass,
        "fail": n - n_pass,
        "pass_rate": round(n_pass / n, 4),
        "reason_counts": reason_counts,
        "value_min_pass_temp": _minmax_pass(df, ["TMAX", "TMIN"], "min"),
        "value_max_pass_temp": _minmax_pass(df, ["TMAX", "TMIN"], "max"),
        "value_max_pass_prcp": _minmax_pass(df, ["PRCP"], "max"),
    }


def _minmax_pass(df: pd.DataFrame, elements: list[str], which: str) -> float | None:
    sub = df.loc[
        df["qc_pass"] & df["element"].isin(elements) & df["value"].notna(),
        "value",
    ]
    if sub.empty:
        return None
    return round(float(sub.min() if which == "min" else sub.max()), 2)


def process_station(
    path: Path,
    *,
    temp_min_c: float,
    temp_max_c: float,
    prcp_max_mm: float,
) -> dict:
    df = pd.read_parquet(path)
    flagged = apply_qc_flags(
        df,
        temp_min_c=temp_min_c,
        temp_max_c=temp_max_c,
        prcp_max_mm=prcp_max_mm,
    )
    SILVER_STATIONS_QC.mkdir(parents=True, exist_ok=True)
    out_path = SILVER_STATIONS_QC / path.name
    flagged.to_parquet(out_path, index=False)
    stats = summarize(flagged)
    stats["station_id"] = path.stem
    stats["path"] = str(out_path)
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Flag silver rows with qc_pass / qc_reasons")
    parser.add_argument("--station", help="Single station ID")
    parser.add_argument("--all", action="store_true", help="All silver station Parquet files")
    parser.add_argument("--temp-min-c", type=float, default=DEFAULT_TEMP_MIN_C)
    parser.add_argument("--temp-max-c", type=float, default=DEFAULT_TEMP_MAX_C)
    parser.add_argument("--prcp-max-mm", type=float, default=DEFAULT_PRCP_MAX_MM)
    args = parser.parse_args()

    if args.station:
        paths = [SILVER_STATIONS / f"{args.station}.parquet"]
        if not paths[0].exists():
            raise SystemExit(f"Missing {paths[0]}")
    elif args.all:
        paths = sorted(SILVER_STATIONS.glob("*.parquet"))
        if not paths:
            raise SystemExit(f"No Parquet under {SILVER_STATIONS}")
    else:
        raise SystemExit("Specify --station ID or --all")

    rules = {
        "temp_min_c": args.temp_min_c,
        "temp_max_c": args.temp_max_c,
        "prcp_max_mm": args.prcp_max_mm,
        "rules": ["missing", "qflag", "range_temp", "range_prcp", "tmax_lt_tmin"],
    }

    print(
        f"QC rules: temp [{args.temp_min_c}, {args.temp_max_c}] C, "
        f"prcp [0, {args.prcp_max_mm}] mm + missing + qflag + tmax_lt_tmin"
    )
    print(f"{'station':<14} {'rows':>9} {'pass':>9} {'fail':>8} {'pass%':>7}  top fails")
    print("-" * 72)

    summaries = []
    for path in paths:
        stats = process_station(
            path,
            temp_min_c=args.temp_min_c,
            temp_max_c=args.temp_max_c,
            prcp_max_mm=args.prcp_max_mm,
        )
        summaries.append(stats)
        reasons = stats["reason_counts"]
        top = ", ".join(
            f"{k}={v}" for k, v in sorted(reasons.items(), key=lambda x: -x[1])[:4]
        )
        print(
            f"{stats['station_id']:<14} {stats['rows']:>9,} {stats['pass']:>9,} "
            f"{stats['fail']:>8,} {100 * stats['pass_rate']:>6.2f}%  {top or '-'}"
        )

    total_rows = sum(s["rows"] for s in summaries)
    total_pass = sum(s["pass"] for s in summaries)
    total_fail = sum(s["fail"] for s in summaries)
    print("-" * 72)
    print(
        f"{'TOTAL':<14} {total_rows:>9,} {total_pass:>9,} {total_fail:>8,} "
        f"{100 * total_pass / total_rows if total_rows else 0:>6.2f}%"
    )
    print(f"output: {SILVER_STATIONS_QC}")

    META.mkdir(parents=True, exist_ok=True)
    man = {
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "rules": rules,
        "stations": summaries,
        "total_rows": total_rows,
        "total_pass": total_pass,
        "total_fail": total_fail,
    }
    man_path = META / "silver_qc_manifest.json"
    man_path.write_text(json.dumps(man, indent=2), encoding="utf-8")
    print(f"manifest: {man_path}")


if __name__ == "__main__":
    main()
