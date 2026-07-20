"""Small HTTP helpers for public NOAA downloads."""
from __future__ import annotations

import time
from pathlib import Path

import requests

DEFAULT_TIMEOUT = 120
USER_AGENT = "ClimateRecordPlatform/0.1 (portfolio ETL; local research)"


def download_file(url: str, dest: Path, *, retries: int = 3, sleep_s: float = 1.5) -> Path:
    """Download url to dest. Skips if dest exists and size > 0."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        print(f"skip (exists): {dest.name}")
        return dest

    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            print(f"GET {url} -> {dest} (attempt {attempt})")
            with requests.get(
                url,
                stream=True,
                timeout=DEFAULT_TIMEOUT,
                headers={"User-Agent": USER_AGENT},
            ) as r:
                r.raise_for_status()
                tmp = dest.with_suffix(dest.suffix + ".part")
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1024 * 256):
                        if chunk:
                            f.write(chunk)
                tmp.replace(dest)
            print(f"ok: {dest} ({dest.stat().st_size:,} bytes)")
            return dest
        except Exception as e:  # noqa: BLE001 — surface and retry
            last_err = e
            print(f"fail: {e}")
            time.sleep(sleep_s * attempt)
    raise RuntimeError(f"Failed download {url}: {last_err}")
