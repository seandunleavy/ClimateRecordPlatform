"""
Phase 1 — download GHCNd metadata (bronze).

Files:
  - readme.txt
  - ghcnd-stations.txt
  - ghcnd-inventory.txt

Examples:
  python -m src.ingest.download_ghcnd_meta
  python -m src.ingest.download_ghcnd_meta --force   # refresh (re-download)
"""
from __future__ import annotations

import argparse
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
    parser = argparse.ArgumentParser(description="Download GHCNd bronze metadata")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download even if files already exist (refresh path)",
    )
    args = parser.parse_args()

    BRONZE_META.mkdir(parents=True, exist_ok=True)
    META.mkdir(parents=True, exist_ok=True)

    results = []
    for name in META_FILES:
        url = f"{GHCND_BASE}/{name}"
        dest = BRONZE_META / name
        info = download_file(url, dest, force=args.force)
        results.append(
            {
                "file": name,
                "path": str(dest),
                "bytes": info["bytes"],
                "previous_bytes": info["previous_bytes"],
                "skipped": info["skipped"],
                "changed": info["changed"],
            }
        )

    manifest = {
        "pulled_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_base": GHCND_BASE,
        "force": args.force,
        "files": results,
    }
    manifest_path = META / "bronze_meta_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"manifest: {manifest_path}")


if __name__ == "__main__":
    main()
