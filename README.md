# Climate Record Platform

**Enterprise-style data platform** on public **NOAA GHCNd** (Global Historical Climatology Network — daily) weather observations.

**Not** a crew scheduler or forecast app.  
**Is** bronze → silver → gold modeling, quality-aware transforms, tests, and (later) public visualizations + transparent methods.

**Owner:** Sean Dunleavy / The Dunleavy Organization, LLC  
**Career plan pointer:** `GitProjects/career/projects/` (priorities)

---

## Goals

1. **DE proof:** medallion architecture, dimensional model, SCD on stations, incremental loads, data tests  
2. **Public product (later):** explorer on dunleavyorganization.com — normals, HDD/CDD, freeze metrics, extremes, coverage quality  
3. **Honest science:** pre-defined metrics, documented methods, no slogan science  

---

## Quick start (Phase 1 — bronze)

```powershell
cd C:\Users\seand\GitProjects\ClimateRecordPlatform
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m src.ingest.download_ghcnd_meta
python -m src.ingest.download_station_days --states SC,NC,GA --max-stations 25
```

Data lands under `data/bronze/` (gitignored payloads).

---

## Docs

| File | Role |
|------|------|
| [`PROJECT_PLAN.md`](PROJECT_PLAN.md) | Phases, YOU ARE HERE |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | System design + Mermaid |
| [`PORTFOLIO.md`](PORTFOLIO.md) | Hiring case study (fill as you ship) |
| [`AGENTS.md`](AGENTS.md) | Agent rules for this repo |

---

## Data source

- [GHCNd product page](https://www.ncei.noaa.gov/products/land-based-station/global-historical-climatology-network-daily)  
- Bulk/HTTPS: `https://www.ncei.noaa.gov/pub/data/ghcn/daily/`  

---

## Status

See **YOU ARE HERE** in `PROJECT_PLAN.md`.
