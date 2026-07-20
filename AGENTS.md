# Climate Record Platform — Agent rules

## Product

- **Enterprise DE platform** on NOAA **GHCNd** daily observations.  
- Public viz later on Dunleavy.  
- **Out of scope:** work-window / crew scheduling; political slogan framing.

## Stack

- Python ingest under `src/ingest/`  
- Data under `data/` (bronze/silver/gold) — **do not commit large raw payloads**  
- dbt + DuckDB planned under `dbt/`  

## Commands

```powershell
cd C:\Users\seand\GitProjects\ClimateRecordPlatform
.\.venv\Scripts\Activate.ps1
python -m src.ingest.download_ghcnd_meta
python -m src.ingest.download_station_days --states SC,NC,GA --max-stations 25
```

## Docs on change

Update `PROJECT_PLAN.md` (YOU ARE HERE), `docs/ARCHITECTURE.md` if flows change, `PORTFOLIO.md` when milestones ship.

## Secrets

None for GHCNd public bulk.
