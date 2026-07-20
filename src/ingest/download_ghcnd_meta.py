"""
Phase 1 — download GHCNd metadata (bronze).

Files:
  - readme.txt
  - ghcnd-stations.txt
  - ghcnd-inventory.txt
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from src.common.http import download_file
from src.common.paths import BRONZE_META, GHCND_BASE, META


META_FILES = (
    "readme.txt",
    "ghcnd-stations.txt",
    "ghcnd-inventory.txt",
)


def main() -> None:
    BRONZE_META.mkdir(parents=True, exist_ok=True)
    META.mkdir(parents=True, exist_ok=True)

    results = []
    for name in META_FILES:
        url = f"{GHCND_BASE}/{name}"
        dest = BRONZE_META / name
        download_file(url, dest)
        results.append(
            {
                "file": name,
                "path": str(dest),
                "bytes": dest.stat().st_size if dest.exists() else 0,
            }
        )

    manifest = {
        "pulled_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_base": GHCND_BASE,
        "files": results,
    }
    manifest_path = META / "bronze_meta_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"manifest: {manifest_path}")


if __name__ == "__main__":
    main()
