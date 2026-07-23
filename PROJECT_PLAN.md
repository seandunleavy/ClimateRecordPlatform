# Climate Record Platform — Project Plan

**Last updated:** 2026-07-23  
**Status:** **v2.1 complete (code)** — refresh automation shipped; weekly schedule optional next  
**Git tags:** `v1.0.0`, `v1.1.0`, `v1.2.0`, `v2.0.0`, `v2.1.0`  
**Live:** https://www.dunleavyorganization.com/project-climate-record.html  
**Purpose:** Enterprise DE portfolio platform on NOAA GHCNd + public analytics.

---

## Vision

A reproducible **observational climate data warehouse** from public station daily data: clean models, tests, lineage, and public visualizations that answer defined questions (degree-days, freeze season, extremes rates, network quality) with transparent methods.

**Not:** work-window / crew scheduling product (rejected).  
**Not:** political slogan product.  
**Is:** DE system + honest viz.

---

## Version roadmap (same repo)

| Version | Scope | Status |
|---------|--------|--------|
| **v1.0** | Regional long-record platform (SC/NC/GA) + marts + dbt + serve/API | ✅ **Closed** |
| **v1.1** | More charts / explorer interactions from existing marts | ✅ **Closed** |
| **v1.2** | Dunleavy public link + deploy polish | ✅ **Closed** |
| **v2.0** | Nationwide long-record — **same rules as v1**, all states + DC | ✅ **Closed** |
| **v2.1** | Automated refresh (force re-pull + change detect + schedule helper) | ✅ **Code closed** |

---

## Goals

| # | Goal | Status |
|---|------|--------|
| 1 | Bronze ingest of GHCNd meta + regional station days | ✅ v1 |
| 2 | Silver parse + quality flags retained + row QC | ✅ v1 |
| 3 | Gold dims/facts + marts (HDD/CDD, freeze, extremes, coverage) | ✅ v1 |
| 4 | dbt tests (+ later incremental patterns) | ✅ v1 tests; incremental later |
| 5 | Public pages on Dunleavy | ✅ Live nationwide explorer + site shell |
| 6 | PORTFOLIO case study complete | ✅ Updated through v2.0 |

---

## YOU ARE HERE

```
v1.0–v1.2 CLOSED — Regional platform + public Dunleavy case study
v2.0 CLOSED — Nationwide long-record (SAME rules as v1)
  LOCKED: USW+USC · ≥50y TMAX+TMIN+PRCP · all states+DC
  COUNT: 6,265 stations · ~514M qc_pass fact rows · ~528M silver rows
  ✅ Bronze → silver → QC → gold (stream_per_station) → dbt PASS
  ✅ Dunleavy live; tagged v2.0.0

v2.1 CLOSED (code) — Automated refresh pipeline
  ✅ force re-download (meta + .dly)
  ✅ --from-manifest preserves locked 6,265-station cohort
  ✅ change detection (byte size) → silver/QC only changed stations
  ✅ run_refresh.py + bats + scripts/register_refresh_task.ps1
  ✅ smoke OK 2026-07-23; tagged v2.1.0
OPS: Task ClimateRecord-WeeklyRefresh = Sunday 2:00 AM
  → run_refresh.bat → --full --copy-to-dunleavy --deploy-phenom
  → LogonType Password + Highest + WakeToRun (match MassiveStock reliability; weekly schedule)
NEXT: observe first Sunday run (logs/refresh.log + live explorer); optional search polish
```



---

## v1.0 scope (what “done” means)

**Included**
- Medallion pipeline on public NOAA GHCNd  
- Long-record station selection (not first-ID junk samples)  
- Full history for selected stations in gold  
- Star schema + analytic marts  
- Quality control with audit trail (`qc_pass` / reasons)  
- dbt models + tests  
- Fast web explorer pattern (marts, not daily facts in the browser)  
- Optional API for on-demand slices  

**Explicitly out of v1.0**
- Nationwide station network  
- Production Dunleavy nav link / formal deploy  
- Full set of ~10 chart types  
- SCD2 station history, warehouse in the cloud  

---

## Phases

### Phase 1 — Bronze ✅

- [x] Repo + docs skeleton  
- [x] `download_ghcnd_meta` — stations, inventory, readme  
- [x] `download_station_days` — `.dly` per station  
- [x] Long-record USW/USC, inventory span, state balance  
- [x] Full regional long-record set (~323 stations, SC/NC/GA)  

### Phase 2 — Silver ✅

- [x] Parse fixed-width `.dly` into typed daily rows  
- [x] Retain MFLAGS / QFLAGS / SFLAGS  
- [x] Scale values (e.g. tenths °C → °C, tenths mm → mm)  
- [x] Parquet under `data/silver/stations/`  
- [x] Light quality profile (`silver_quality_check`)  
- [x] Row QC flags (`apply_qc` → `data/silver/stations_qc/`)  
- [x] Export QC fails to CSV for review  

### Phase 3 — Gold + dbt ✅ (v1)

- [x] Star dims: `dim_station`, `dim_date`, `dim_element`  
- [x] Atomic fact: `fact_observation_daily`  
- [x] Marts: monthly climate, HDD/CDD, coverage, freeze, extremes  
- [x] dbt + DuckDB models + tests  
- [ ] SCD2 on stations if needed (later)  
- [ ] Incremental dbt patterns (later)  

### Phase 4 — Serve ✅ (v1.2)

- [x] Mart → web JSON (one file per station for fewer HTTP requests)  
- [x] Dunleavy explorer + methods (multi-chart + map)  
- [x] Read-only FastAPI (DuckDB on gold Parquet)  
- [x] Production case study + home/projects cards  
- [ ] Freshness badge (optional later)  

### Phase 5 — Portfolio polish ✅ (v1.2)

- [x] Architecture + PORTFOLIO + live URL  
- [ ] Optional Snowflake/Tableau as consumers only  

---

## Stack (v1 locked)

| Layer | Choice |
|-------|--------|
| Language | Python 3.11+ |
| Bronze | Raw NOAA `.txt` / `.dly` under `data/bronze` |
| Silver | Parquet daily rows + QC-flagged copy |
| Gold | Parquet dims/facts/marts under `data/gold` |
| SQL / tests | **dbt + DuckDB** |
| API | FastAPI (read-only) |
| Web demo | Static mart JSON + Chart.js + Leaflet (Dunleavy live) |

---

## Geographic scope

| Version | Geography | Station rules |
|---------|-----------|---------------|
| **v1** | SC, NC, GA | USW/USC · ≥50y TMAX+TMIN+PRCP inventory overlap · ~323 stations |
| **v2** | **All US states + DC** | **Same rules as v1** · ~6,265 stations |

```powershell
# v2 bronze (resume-safe; skips .dly already on disk)
python -m src.ingest.download_station_days --nationwide
python -m src.ingest.download_station_days --nationwide --list-only --quiet-list
```

---

## Last session

**2026-07-23 — Refresh automation live as scheduled job; wrap**

- **v2.1.0** on GitHub: `run_refresh.py`, force pull, change detect, cohort lock  
- Unattended phenom climate JSON: `--deploy-phenom` + Dunleavy `deploy/deploy-climate-data.ps1`  
- Task **ClimateRecord-WeeklyRefresh**: Sunday 2 AM; Password / Highest / WakeToRun (like MassiveStock)  
- First real proof: **next Sunday** — check `logs/refresh.log` + live explorer after  
- Context: [`docs/SESSION-HANDOFF.md`](docs/SESSION-HANDOFF.md)  

**Earlier 2026-07-23 — Close v2.1 code + commit/tag**  

- Force download + orchestrator + smoke; tagged **`v2.1.0`**  



**2026-07-22 — Close v2.0 (nationwide live)**

- Same station rules as v1, all states+DC: **6,265** stations  
- Full pipeline: bronze → silver (~528M rows) → QC (97.3% pass) → gold stream (~514M fact) → dbt 29 PASS  
- Serve: combined per-station JSON; map uses per-station latest extremes year; hide zero-day markers  
- Dunleavy case study updated + site shell aligned; deployed; desktop + mobile OK  
- Tagged **`v2.0.0`**  

**2026-07-22 — Close v1.2** — public Dunleavy case study; **`v1.2.0`**  





**2026-07-21 — Close v1.1** — multi-chart explorer; tag `v1.1.0`  

**Earlier — v1.0** — tag `v1.0.0`; regional platform  





---

## Locked product principles

- **Best practices first** (medallion, star schema, explicit QC, documented metric methods).  
- **Modern tools when justified** (Parquet, dbt, DuckDB, FastAPI).  
- **Fast viz from marts** (per-station loads at scale); atomic fact for drill-down / API.  
- **Honest scale** — regional complete long-record in v1; nationwide planned as v2.  
- **Same repo** for all versions; tags mark milestones.  

---

## Open decisions (post-v1)

- ~~Dunleavy production link timing (v1.2)~~ — wire-up done; deploy when ready  
- Nationwide download strategy and serving (API-first) for v2  
- Optional map year selector / more explorer polish
