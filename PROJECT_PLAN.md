# Climate Record Platform — Project Plan

**Last updated:** 2026-07-21  
**Status:** Active — Phase 3 (gold v1 shipped; dbt still planned)  
**Purpose:** Enterprise DE portfolio platform on NOAA GHCNd + public analytics later.

---

## Vision

A reproducible **observational climate data warehouse** from public station daily data: clean models, tests, lineage, and public visualizations that answer defined questions (degree-days, freeze season, extremes rates, network quality) with transparent methods.

**Not:** work-window / crew scheduling product (rejected).  
**Not:** political slogan product.  
**Is:** DE system + honest viz.

---

## Goals

| # | Goal | Status |
|---|------|--------|
| 1 | Bronze ingest of GHCNd meta + SE station days | ✅ |
| 2 | Silver parse + quality flags retained + row QC | ✅ |
| 3 | Gold dims/facts + marts (HDD/CDD, coverage; freeze/extremes next) | 🔄 Partial (v1) |
| 4 | dbt tests + incremental patterns | ⬜ |
| 5 | Public pages on Dunleavy | ⬜ |
| 6 | PORTFOLIO case study complete | 🔄 Draft updated |

---

## YOU ARE HERE

```
PHASE 3 — Gold (v1)
  ✅ Bronze: meta + long-record USW/USC (SC/NC/GA), inventory-based pick
  ✅ Silver: .dly → daily Parquet (TMAX/TMIN/PRCP)
  ✅ QC: qc_pass / qc_reasons on silver; export fails to CSV
  ✅ Gold v1: dim_station, fact_observation_daily, monthly climate,
     monthly HDD/CDD, yearly coverage, freeze season, extremes
NEXT: dbt + DuckDB tests; then serve / Dunleavy
```


---

## Phases

### Phase 1 — Bronze

- [x] Repo + docs skeleton  
- [x] `download_ghcnd_meta` — stations, inventory, readme  
- [x] `download_station_days` — `.dly` per station  
- [x] Long-record sampling: USW/USC, TMAX+TMIN+PRCP span, state balance  
- [x] Bronze verified (~15 SE stations; multi‑MB long records)

### Phase 2 — Silver

- [x] Parse fixed-width `.dly` into typed daily rows  
- [x] Retain MFLAGS / QFLAGS / SFLAGS  
- [x] Scale values (e.g. tenths °C → °C, tenths mm → mm)  
- [x] Parquet under `data/silver/stations/`  
- [x] Light quality profile (`silver_quality_check`)  
- [x] Row QC flags (`apply_qc` → `data/silver/stations_qc/`)  
- [x] Export QC fails to CSV for review  

### Phase 3 — Gold + dbt

- [x] `dim_station` (current attributes; SCD2 later if needed)  
- [x] `fact_observation_daily` (qc_pass only)  
- [x] Marts: monthly climate, monthly HDD/CDD, yearly coverage  
- [x] Marts: freeze season (yearly), extremes (yearly)  
- [ ] `dim_date` / richer dims as needed  
- [ ] dbt + DuckDB models + tests  


### Phase 4 — Serve

- [ ] Publish subset for web  
- [ ] Dunleavy explorer pages + methodology  
- [ ] Freshness badge  

### Phase 5 — Portfolio polish

- [ ] Architecture diagrams final  
- [x] PORTFOLIO.md kept current with milestones  
- [ ] Optional Snowflake/Tableau as **consumers only**  

---

## Stack

| Layer | Choice |
|-------|--------|
| Language | Python 3.11+ (dev currently 3.14 OK) |
| Bronze | Raw NOAA `.txt` / `.dly` under `data/bronze` |
| Silver | Parquet daily rows + QC-flagged copy |
| Gold | Parquet dims/facts/marts under `data/gold` (Python first) |
| Transform next | **dbt + DuckDB** planned under `dbt/` |
| Serve | Dunleavy static/API later |
| Optional | Snowflake / Tableau as extra consumers of gold |

---

## Geographic MVP scope

**Default:** SC, NC, GA (CLI expandable).  
Station pick: long-record **USW** / **USC** with inventory overlap on TMAX, TMIN, PRCP (default min span 50 years), balanced across states.

---

## Last session

**2026-07-21 (docs catch-up)**

- Documented full path: bronze → silver → stations_qc → gold v1  
- Updated PROJECT_PLAN, ARCHITECTURE, README, PORTFOLIO, AGENTS  

**Prior work (same effort arc)**

- Long-record station download; silver parse (all 15)  
- QC rules + fail export; gold dims/facts/marts including HDD/CDD  

---

## Open decisions

- Exact public product name on Dunleavy (working: **Climate Record Platform**)  
- DuckDB vs Postgres for gold serve  
- Full SE vs SC-only for first public demo  
- Whether to tighten temp gates further for gold-only rules vs keep silver_qc as source of truth  
