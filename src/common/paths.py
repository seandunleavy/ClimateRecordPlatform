"""Project paths."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
BRONZE = DATA / "bronze"
SILVER = DATA / "silver"
GOLD = DATA / "gold"
META = DATA / "meta"
BRONZE_META = BRONZE / "meta"
BRONZE_STATIONS = BRONZE / "stations"

# NOAA GHCNd public bulk root
GHCND_BASE = "https://www.ncei.noaa.gov/pub/data/ghcn/daily"
