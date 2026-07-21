# Climate Record Platform

**Enterprise-style data platform** on public **NOAA GHCNd** (Global Historical Climatology Network — daily) weather observations.

**Not** a crew scheduler or forecast app.  
**Is** bronze → silver → QC → gold (star + marts), dbt tests, and mart-driven charts / optional API.

**Owner:** Sean Dunleavy / The Dunleavy Organization, LLC  
**Version:** **v1.1.0** (explorer chart pack on v1.0 platform) — tags `v1.0.0`, `v1.1.0`  
**Career plan pointer:** `GitProjects/career/projects/` (priorities)

---

## Goals

1. **DE proof:** medallion architecture, dimensional model, QC flags, tests  
2. **Public product:** explorer (draft on Dunleavy) — degree-days, freeze metrics, extremes  
3. **Honest science:** pre-defined metrics, documented methods, no slogan science  

---

## Status

**v1.1 complete** (platform + multi-chart explorer). See [`PROJECT_PLAN.md`](PROJECT_PLAN.md).

| Highlight | Approx. |
|-----------|---------|
| Long-record stations (SC/NC/GA, USW/USC, 50+y) | **~323** |
| Quality-pass daily observations | **~28M** |
| dbt tests | **29 PASS** |
| Explorer | Multi-chart + ranks + thematic map |

Next: **v1.2** public Dunleavy link; **v2** nationwide long-record.

---

## Quick start

```powershell
cd C:\Users\seand\GitProjects\ClimateRecordPlatform
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 1) Bronze — meta + long-record station .dly files
python -m src.ingest.download_ghcnd_meta
python -m src.ingest.download_station_days --states SC,NC,GA --max-stations 400

# 2) Silver — parse .dly → Parquet (manifest stations)
python -m src.transform.bronze_to_silver --from-manifest

# 3) QC — flag rows; keep all history
python -m src.transform.apply_qc --all

# 4) Gold — dims / facts / marts from qc_pass only
python -m src.transform.silver_to_gold

# 5) dbt + DuckDB (close DBeaver if it locks climate_record.duckdb)
.\.venv\Scripts\dbt.exe run --project-dir dbt --profiles-dir dbt
.\.venv\Scripts\dbt.exe test --project-dir dbt --profiles-dir dbt

# 6) Web mart export (per-station JSON for fast charts)
python -m src.serve.export_web_json --copy-to-dunleavy

# 7) Optional API
uvicorn src.api.main:app --reload --port 8080
# http://127.0.0.1:8080/docs
```

Data under `data/` is largely gitignored (regenerable). DuckDB: `data/gold/climate_record.duckdb`.

---

## Docs

| File | Role |
|------|------|
| [`PROJECT_PLAN.md`](PROJECT_PLAN.md) | Phases, versions, YOU ARE HERE |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | System design + methods |
| [`PORTFOLIO.md`](PORTFOLIO.md) | Hiring case study |
| [`AGENTS.md`](AGENTS.md) | Agent rules for this repo |

---

## Data source

- [GHCNd product page](https://www.ncei.noaa.gov/products/land-based-station/global-historical-climatology-network-daily)  
- Bulk/HTTPS: `https://www.ncei.noaa.gov/pub/data/ghcn/daily/`  

---

## Layout (short)

```text
data/bronze/          raw NOAA files
data/silver/          parsed + stations_qc
data/gold/            star + marts + duckdb
data/serve/web/       stations index + by_station/{id}/ mart JSON
src/ingest/           downloads
src/transform/        parse, QC, gold
src/serve/            web export
src/api/              FastAPI read-only
dbt/                  SQL models + tests
```
