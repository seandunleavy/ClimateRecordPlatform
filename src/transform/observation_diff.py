"""
Compare previous vs new silver daily rows for a station (refresh observability).

Grain: station_id + date + element (same as silver / gold fact keys without QC).

Counts:
  - inserted: key present only in new file (new daily values)
  - deleted: key present only in old file (removed from NOAA file / filter)
  - value_changed: same key, value_raw or is_missing differs (corrections)
  - flag_only_changed: same value, but mflag/qflag/sflag differs
  - unchanged: same key and same value + flags

This is run metadata only — not part of the gold star schema.

Used by bronze_to_silver before overwriting each station parquet.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

KEY_COLS = ["date", "element"]
VALUE_COLS = ["value_raw", "is_missing"]
FLAG_COLS = ["mflag", "qflag", "sflag"]


def _norm_for_compare(df: pd.DataFrame) -> pd.DataFrame:
    """Stable key + compare columns; empty frame with correct columns if no rows."""
    if df is None or df.empty:
        cols = KEY_COLS + VALUE_COLS + FLAG_COLS
        return pd.DataFrame(columns=cols)

    out = df.copy()
    out["date"] = pd.to_datetime(out["date"]).dt.normalize()
    out["element"] = out["element"].astype(str)

    # value_raw may be float; missing rows often still have -9999 or NaN
    out["value_raw"] = pd.to_numeric(out["value_raw"], errors="coerce")
    if "is_missing" in out.columns:
        out["is_missing"] = out["is_missing"].fillna(False).astype(bool)
    else:
        out["is_missing"] = False

    for c in FLAG_COLS:
        if c not in out.columns:
            out[c] = ""
        # Normalize NaN/None flags to empty string for equality
        out[c] = out[c].fillna("").astype(str).replace({"nan": "", "None": ""})

    # One row per key (silver should already be unique; keep last if not)
    out = out[KEY_COLS + VALUE_COLS + FLAG_COLS]
    out = out.drop_duplicates(subset=KEY_COLS, keep="last")
    return out


def diff_station_frames(
    old_df: pd.DataFrame | None,
    new_df: pd.DataFrame,
    *,
    station_id: str,
) -> dict[str, Any]:
    """
    Diff old silver vs newly parsed silver for one station.

    If there is no prior parquet, all new rows count as inserted (first_run=True).
    """
    new_n = 0 if new_df is None or new_df.empty else len(new_df)
    if old_df is None or (hasattr(old_df, "empty") and old_df.empty):
        date_min = date_max = None
        if new_df is not None and not new_df.empty and "date" in new_df.columns:
            d = pd.to_datetime(new_df["date"])
            date_min = str(d.min().date())
            date_max = str(d.max().date())
        return {
            "station_id": station_id,
            "first_run": True,
            "prior_rows": 0,
            "new_rows": int(new_n),
            "inserted": int(new_n),
            "deleted": 0,
            "value_changed": 0,
            "flag_only_changed": 0,
            "unchanged": 0,
            "net_row_delta": int(new_n),
            "inserted_date_min": date_min,
            "inserted_date_max": date_max,
            "value_changed_date_min": None,
            "value_changed_date_max": None,
        }

    old = _norm_for_compare(old_df)
    new = _norm_for_compare(new_df)

    old_keys = old.set_index(KEY_COLS)
    new_keys = new.set_index(KEY_COLS)

    old_idx = set(old_keys.index)
    new_idx = set(new_keys.index)

    only_new = new_idx - old_idx
    only_old = old_idx - new_idx
    both = old_idx & new_idx

    inserted = len(only_new)
    deleted = len(only_old)

    value_changed = 0
    flag_only_changed = 0
    unchanged = 0
    vc_dates: list[pd.Timestamp] = []
    ins_dates: list[pd.Timestamp] = []

    for key in only_new:
        # key is tuple (date, element) or scalar if single-level (won't be)
        d = key[0] if isinstance(key, tuple) else key
        ins_dates.append(pd.Timestamp(d))

    for key in both:
        o = old_keys.loc[key]
        n = new_keys.loc[key]
        # .loc can return Series; if duplicate keys slipped through, take first
        if isinstance(o, pd.DataFrame):
            o = o.iloc[0]
        if isinstance(n, pd.DataFrame):
            n = n.iloc[0]

        # Float-safe value compare
        ov = o["value_raw"]
        nv = n["value_raw"]
        if pd.isna(ov) and pd.isna(nv):
            same_val = True
        elif pd.isna(ov) or pd.isna(nv):
            same_val = False
        else:
            same_val = float(ov) == float(nv)

        same_missing = bool(o["is_missing"]) == bool(n["is_missing"])
        same_value_block = same_val and same_missing

        same_flags = all(str(o[c]) == str(n[c]) for c in FLAG_COLS)

        if not same_value_block:
            value_changed += 1
            d = key[0] if isinstance(key, tuple) else key
            vc_dates.append(pd.Timestamp(d))
        elif not same_flags:
            flag_only_changed += 1
        else:
            unchanged += 1

    def _minmax(dates: list[pd.Timestamp]) -> tuple[str | None, str | None]:
        if not dates:
            return None, None
        s = pd.Series(dates)
        return str(s.min().date()), str(s.max().date())

    ins_min, ins_max = _minmax(ins_dates)
    vc_min, vc_max = _minmax(vc_dates)

    return {
        "station_id": station_id,
        "first_run": False,
        "prior_rows": int(len(old)),
        "new_rows": int(len(new)),
        "inserted": int(inserted),
        "deleted": int(deleted),
        "value_changed": int(value_changed),
        "flag_only_changed": int(flag_only_changed),
        "unchanged": int(unchanged),
        "net_row_delta": int(inserted - deleted),
        "inserted_date_min": ins_min,
        "inserted_date_max": ins_max,
        "value_changed_date_min": vc_min,
        "value_changed_date_max": vc_max,
    }


def aggregate_diffs(station_diffs: list[dict[str, Any]]) -> dict[str, Any]:
    """Roll up per-station diffs for refresh_manifest / meta."""
    if not station_diffs:
        return {
            "stations_compared": 0,
            "stations_with_prior": 0,
            "stations_first_run": 0,
            "inserted": 0,
            "deleted": 0,
            "value_changed": 0,
            "flag_only_changed": 0,
            "unchanged": 0,
            "net_row_delta": 0,
            "stations_with_inserts": 0,
            "stations_with_value_changes": 0,
            "inserted_date_max": None,
            "value_changed_date_max": None,
            "top_by_inserted": [],
            "top_by_value_changed": [],
        }

    def _sum(key: str) -> int:
        return int(sum(int(s.get(key) or 0) for s in station_diffs))

    first = [s for s in station_diffs if s.get("first_run")]
    with_prior = [s for s in station_diffs if not s.get("first_run")]

    ins_maxes = [s["inserted_date_max"] for s in station_diffs if s.get("inserted_date_max")]
    vc_maxes = [
        s["value_changed_date_max"]
        for s in station_diffs
        if s.get("value_changed_date_max")
    ]

    top_ins = sorted(
        (s for s in with_prior if (s.get("inserted") or 0) > 0),
        key=lambda s: s.get("inserted") or 0,
        reverse=True,
    )[:10]
    top_vc = sorted(
        (s for s in with_prior if (s.get("value_changed") or 0) > 0),
        key=lambda s: s.get("value_changed") or 0,
        reverse=True,
    )[:10]

    def _brief(s: dict[str, Any], metric: str) -> dict[str, Any]:
        return {
            "station_id": s["station_id"],
            metric: s.get(metric),
            "deleted": s.get("deleted"),
            "value_changed": s.get("value_changed"),
            "inserted": s.get("inserted"),
            "inserted_date_max": s.get("inserted_date_max"),
            "value_changed_date_max": s.get("value_changed_date_max"),
        }

    return {
        "stations_compared": len(station_diffs),
        "stations_with_prior": len(with_prior),
        "stations_first_run": len(first),
        "inserted": _sum("inserted"),
        "deleted": _sum("deleted"),
        "value_changed": _sum("value_changed"),
        "flag_only_changed": _sum("flag_only_changed"),
        "unchanged": _sum("unchanged"),
        "net_row_delta": _sum("net_row_delta"),
        "stations_with_inserts": sum(
            1 for s in with_prior if (s.get("inserted") or 0) > 0
        ),
        "stations_with_value_changes": sum(
            1 for s in with_prior if (s.get("value_changed") or 0) > 0
        ),
        "inserted_date_max": max(ins_maxes) if ins_maxes else None,
        "value_changed_date_max": max(vc_maxes) if vc_maxes else None,
        "top_by_inserted": [_brief(s, "inserted") for s in top_ins],
        "top_by_value_changed": [_brief(s, "value_changed") for s in top_vc],
    }
