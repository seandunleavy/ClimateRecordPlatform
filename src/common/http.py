"""Small HTTP helpers for public NOAA downloads."""
from __future__ import annotations

import time
from pathlib import Path

import requests

DEFAULT_TIMEOUT = 120
USER_AGENT = "ClimateRecordPlatform/0.1 (portfolio ETL; local research)"


def download_file(
    url: str,
    dest: Path,
    *,
    force: bool = False,
    retries: int = 3,
    sleep_s: float = 1.5,
) -> dict:
    """
    Download url to dest.

    Skips when dest exists and size > 0 unless force=True (refresh path).

    Returns:
      path, skipped, bytes, previous_bytes, changed
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    previous_bytes = dest.stat().st_size if dest.exists() else 0

    if not force and dest.exists() and previous_bytes > 0:
        print(f"skip (exists): {dest.name}")
        return {
            "path": dest,
            "skipped": True,
            "bytes": previous_bytes,
            "previous_bytes": previous_bytes,
            "changed": False,
        }

    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            label = "GET (force)" if force and previous_bytes > 0 else "GET"
            print(f"{label} {url} -> {dest} (attempt {attempt})")
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
            new_bytes = dest.stat().st_size
            changed = new_bytes != previous_bytes or previous_bytes == 0
            print(f"ok: {dest} ({new_bytes:,} bytes" + ("; changed" if changed else "; same size") + ")")
            return {
                "path": dest,
                "skipped": False,
                "bytes": new_bytes,
                "previous_bytes": previous_bytes,
                "changed": changed,
            }
        except Exception as e:  # noqa: BLE001 — surface and retry
            last_err = e
            print(f"fail: {e}")
            time.sleep(sleep_s * attempt)
    raise RuntimeError(f"Failed download {url}: {last_err}")
