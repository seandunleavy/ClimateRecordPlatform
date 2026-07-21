# Climate Record Platform — Agent rules

## Product

- **Enterprise DE platform** on NOAA **GHCNd** daily observations.  
- Public viz later on Dunleavy.  
- **Out of scope:** work-window / crew scheduling; political slogan framing.

## Portfolio standard (locked)

This repo must showcase **best practices first**, with **modern tools when they earn their place**.

| Practice | How we do it here |
|----------|-------------------|
| Medallion | bronze → silver → silver_qc → gold |
| Star schema | `dim_station`, `dim_date`, `dim_element` + `fact_observation_daily` |
| QC without silent deletes | `qc_pass` / `qc_reasons`; gold uses pass only |
| Fast viz | charts from **marts** → small JSON under `data/serve/web` → Dunleavy page |
| Documented methods | HDD base, freeze defs, extremes thresholds in ARCHITECTURE |
| Modern stack | Python + Parquet now; **dbt + DuckDB** next when it adds SQL/tests/speed |
| Honest scale | regional long-record sample — enterprise *patterns*, not petabyte claims |

When choosing next work: prefer changes that strengthen the portfolio story (tests, dbt, clearer star, serve from marts) over one-off hacks.

## Stack

- Python under `src/ingest/` and `src/transform/`  
- Data under `data/` (bronze / silver / silver_qc / gold) — **do not commit large raw payloads**  
- dbt + DuckDB under `dbt/` (SQL layer + tests over gold Parquet)  


## Code style (readability)

- Module docstring: purpose + how to run  
- Comment **business/QC rules** and NOAA format quirks, not obvious lines  
- Prefer clear names over comment spam  

## Commands

```powershell
cd C:\Users\seand\GitProjects\ClimateRecordPlatform
.\.venv\Scripts\Activate.ps1

python -m src.ingest.download_ghcnd_meta
python -m src.ingest.download_station_days --states SC,NC,GA --max-stations 15

python -m src.transform.bronze_to_silver --from-manifest
python -m src.transform.apply_qc --all
python -m src.transform.silver_to_gold

# dbt (always from repo root)
.\.venv\Scripts\dbt.exe run --project-dir dbt --profiles-dir dbt
.\.venv\Scripts\dbt.exe test --project-dir dbt --profiles-dir dbt

# optional review
python -m src.transform.silver_quality_check
python -m src.transform.export_qc_fails

# static web export (optional copy into Dunleavy data/)
python -m src.serve.export_web_json --copy-to-dunleavy
# full multi-decade mart JSON (default). Single year: --single-year 2020
```




## Docs on change

Update `PROJECT_PLAN.md` (YOU ARE HERE), `docs/ARCHITECTURE.md` if flows change, `PORTFOLIO.md` when milestones ship.

## Secrets

None for GHCNd public bulk.
