"""
Export silver QC fail rows to CSV for easy review (Excel, etc.).

  python -m src.transform.export_qc_fails
  python -m src.transform.export_qc_fails --reason range_temp
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from src.common.paths import META, SILVER_STATIONS_QC


def main() -> None:
    parser = argparse.ArgumentParser(description="Export qc_pass=False rows to CSV")
    parser.add_argument(
        "--reason",
        help="Only rows whose qc_reasons contain this code (e.g. range_temp, qflag, missing)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output CSV path (default under data/meta/)",
    )
    args = parser.parse_args()

    paths = sorted(SILVER_STATIONS_QC.glob("*.parquet"))
    if not paths:
        raise SystemExit(f"No Parquet under {SILVER_STATIONS_QC}")

    cols = [
        "station_id",
        "date",
        "element",
        "value",
        "value_raw",
        "mflag",
        "qflag",
        "sflag",
        "is_missing",
        "qc_reasons",
    ]
    frames: list[pd.DataFrame] = []
    for path in paths:
        print(f"read {path.name} ...")
        df = pd.read_parquet(path)
        fail = df.loc[~df["qc_pass"]].copy()
        keep = [c for c in cols if c in fail.columns]
        frames.append(fail[keep])

    out = pd.concat(frames, ignore_index=True)
    if args.reason:
        out = out.loc[
            out["qc_reasons"].fillna("").str.contains(args.reason, regex=False)
        ].copy()

    META.mkdir(parents=True, exist_ok=True)
    if args.out is not None:
        dest = args.out
    elif args.reason:
        dest = META / f"qc_fails_{args.reason}.csv"
    else:
        dest = META / "qc_fails_export.csv"

    out.to_csv(dest, index=False)
    print(f"wrote {dest}  rows={len(out):,}")


if __name__ == "__main__":
    main()
