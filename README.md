# Climate Record Platform

**Enterprise-style data platform** on public **NOAA GHCNd** (Global Historical Climatology Network — daily) weather observations.

**Not** a crew scheduler or forecast app.  
**Is** bronze → silver → QC → gold modeling, quality-aware transforms, and (later) public visualizations + transparent methods.

**Owner:** Sean Dunleavy / The Dunleavy Organization, LLC  
**Career plan pointer:** `GitProjects/career/projects/` (priorities)

---

## Goals

1. **DE proof:** medallion architecture, dimensional model, QC flags, tests, incremental patterns  
2. **Public product (later):** explorer on dunleavyorganization.com — normals, HDD/CDD, freeze metrics, extremes, coverage quality  
3. **Honest science:** pre-defined metrics, documented methods, no slogan science  

---

## Status

See **YOU ARE HERE** in [`PROJECT_PLAN.md`](PROJECT_PLAN.md).  
**Shipped through gold v1** (dims, daily fact, monthly climate, HDD/CDD, coverage) for a 15-station SC/NC/GA long-record sample.

---

## Quick start

```powershell
cd C:\Users\seand\GitProjects\ClimateRecordPlatform
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 1) Bronze — meta + long-record station .dly files
python -m src.ingest.download_ghcnd_meta
python -m src.ingest.download_station_days --states SC,NC,GA --max-stations 15

# 2) Silver — parse .dly → Parquet (use manifest stations, not leftover US1* files)
python -m src.transform.bronze_to_silver --from-manifest

# 3) QC — flag rows; keep all history
python -m src.transform.apply_qc --all

# 4) Gold — dims / facts / marts from qc_pass only
python -m src.transform.silver_to_gold

# 5) dbt + DuckDB — SQL star/marts + tests (run from repo root)
.\.venv\Scripts\dbt.exe run --project-dir dbt --profiles-dir dbt
.\.venv\Scripts\dbt.exe test --project-dir dbt --profiles-dir dbt

# 6) Read-only API (filtered marts + daily drill-down)
uvicorn src.api.main:app --reload --port 8080
# Open http://127.0.0.1:8080/docs
```


Data lands under `data/` (gitignored payloads). DuckDB file: `data/gold/climate_record.duckdb`. Run manifests under `data/meta/`.

**Requires:** activate venv first; packages in `requirements.txt` include `duckdb`, `dbt-core`, `dbt-duckdb`.

### Useful extras

```powershell
python -m src.ingest.download_station_days --list-only
python -m src.transform.silver_quality_check
python -m src.transform.export_qc_fails
python -m src.transform.export_qc_fails --reason range_temp
```

---

## Docs

| File | Role |
|------|------|
| [`PROJECT_PLAN.md`](PROJECT_PLAN.md) | Phases, YOU ARE HERE |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | System design + Mermaid + QC/gold methods |
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
data/silver/stations/ parsed daily rows
data/silver/stations_qc/  + qc_pass / qc_reasons
data/gold/dims|facts|marts/
src/ingest/           downloads
src/transform/        parse, QC, gold
```
