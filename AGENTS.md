# Climate Record Platform — Agent rules

## Product

- **Enterprise DE platform** on NOAA **GHCNd** daily observations.  
- Public viz later on Dunleavy.  
- **Out of scope:** work-window / crew scheduling; political slogan framing.

## Stack

- Python under `src/ingest/` and `src/transform/`  
- Data under `data/` (bronze / silver / silver_qc / gold) — **do not commit large raw payloads**  
- dbt + DuckDB planned under `dbt/`  

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

# optional review
python -m src.transform.silver_quality_check
python -m src.transform.export_qc_fails
```

## Docs on change

Update `PROJECT_PLAN.md` (YOU ARE HERE), `docs/ARCHITECTURE.md` if flows change, `PORTFOLIO.md` when milestones ship.

## Secrets

None for GHCNd public bulk.
