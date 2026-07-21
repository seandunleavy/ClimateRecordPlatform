"""
Parse NOAA GHCNd fixed-width .dly files into daily observation rows.

One .dly line = one station + year + month + element, with up to 31 day slots.
We explode that into one row per real calendar day.

See data/bronze/meta/readme.txt section III for the official layout.
"""
from __future__ import annotations

import calendar
from pathlib import Path
from typing import Any, Iterator

# NOAA missing sentinel in VALUE fields
MISSING = -9999

# Columns are 1-based in the readme; slices below are 0-based.
# ID 1-11, YEAR 12-15, MONTH 16-17, ELEMENT 18-21
# Then for day d=1..31: VALUE (5) + MFLAG (1) + QFLAG (1) + SFLAG (1) = 8 chars
# Day 1 VALUE starts at column 22 (index 21).

# Convert VALUE to a friendlier unit where NOAA uses "tenths of …"
# Unknown elements: value stays None; value_raw still kept.
SCALE_TO_UNIT: dict[str, tuple[float, str]] = {
    "PRCP": (0.1, "mm"),  # tenths of mm
    "TMAX": (0.1, "C"),  # tenths of degrees C
    "TMIN": (0.1, "C"),
    "TAVG": (0.1, "C"),
    "ADPT": (0.1, "C"),
    "AWBT": (0.1, "C"),
    "SNOW": (1.0, "mm"),
    "SNWD": (1.0, "mm"),
    "AWND": (0.1, "m_s"),  # tenths of m/s
    "AWDR": (1.0, "deg"),
}


def _scale_value(element: str, value_raw: int | None) -> tuple[float | None, str | None]:
    if value_raw is None:
        return None, SCALE_TO_UNIT.get(element, (None, None))[1] if element in SCALE_TO_UNIT else None
    if element in SCALE_TO_UNIT:
        factor, unit = SCALE_TO_UNIT[element]
        return value_raw * factor, unit
    return float(value_raw), None


def parse_dly_line(line: str) -> Iterator[dict[str, Any]]:
    """Yield daily observation dicts from one .dly record line."""
    # Right-strip only; internal spaces are significant for fixed width.
    # Lines are typically 269 chars; allow shorter (missing trailing days).
    if len(line) < 21:
        return

    station_id = line[0:11].strip()
    try:
        year = int(line[11:15])
        month = int(line[15:17])
    except ValueError:
        return
    element = line[17:21].strip()
    if not station_id or not element:
        return

    days_in_month = calendar.monthrange(year, month)[1]

    for day in range(1, 32):
        start = 21 + (day - 1) * 8
        chunk = line[start : start + 8]
        if len(chunk) < 5:
            break

        raw_str = chunk[0:5].strip()
        mflag = chunk[5] if len(chunk) > 5 else " "
        qflag = chunk[6] if len(chunk) > 6 else " "
        sflag = chunk[7] if len(chunk) > 7 else " "

        # Empty value slot — treat as no observation
        if raw_str == "":
            continue

        try:
            value_raw_int = int(raw_str)
        except ValueError:
            continue

        # Skip impossible calendar days (e.g. day 31 in June)
        if day > days_in_month:
            continue

        if value_raw_int == MISSING:
            value_raw: int | None = None
            value: float | None = None
            unit = SCALE_TO_UNIT[element][1] if element in SCALE_TO_UNIT else None
            is_missing = True
        else:
            value_raw = value_raw_int
            value, unit = _scale_value(element, value_raw)
            is_missing = False

        yield {
            "station_id": station_id,
            "date": f"{year:04d}-{month:02d}-{day:02d}",
            "element": element,
            "value_raw": value_raw,
            "value": value,
            "unit": unit,
            "mflag": mflag.strip() or None,
            "qflag": qflag.strip() or None,
            "sflag": sflag.strip() or None,
            "is_missing": is_missing,
        }


def parse_dly_file(path: Path) -> list[dict[str, Any]]:
    """Parse an entire station .dly file into daily rows."""
    rows: list[dict[str, Any]] = []
    text = path.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        if not line or line.isspace():
            continue
        rows.extend(parse_dly_line(line))
    return rows
