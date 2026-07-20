# Climate Record Platform — Project Plan

**Last updated:** 2026-07-20  
**Status:** Active — Phase 1 (bronze ingest)  
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
| 1 | Bronze ingest of GHCNd meta + SE station days | 🔄 In progress |
| 2 | Silver parse + quality flags retained | ⬜ |
| 3 | Gold dims/facts + marts (HDD/CDD, freeze, extremes, coverage) | ⬜ |
| 4 | dbt tests + incremental patterns | ⬜ |
| 5 | Public pages on Dunleavy | ⬜ |
| 6 | PORTFOLIO case study complete | ⬜ |

---

## YOU ARE HERE

```
PHASE 1 — Bronze
  ✅ Repo scaffold + docs
  ✅ Meta download (stations ~11MB, inventory ~36MB, readme)
  ✅ Sample station .dly files (15 x SC/NC/GA subset — actually first US* in sort = GA Coop)
NEXT: Prefer USW/USC long-record stations; silver .dly parser
```

---

## Phases

### Phase 1 — Bronze (now)

- [x] Repo + docs skeleton  
- [x] `download_ghcnd_meta` — stations, inventory, readme  
- [x] `download_station_days` — `.dly` per station (states + max)  
- [x] Bronze run verified 2026-07-20 (15 stations)  
- [ ] Improve station sampling (long-record USW/USC, not only first IDs)

### Phase 2 — Silver

- [ ] Parse fixed-width / CSV station days into typed tables  
- [ ] Retain QFLAGS / MFLAGS  
- [ ] Dedup keys: station_id + date + element  

### Phase 3 — Gold + dbt

- [ ] `dim_station` (SCD2 where history allows)  
- [ ] `dim_date`, `fact_observation_daily`  
- [ ] Marts: HDD/CDD, freeze dates, extreme-day rates, missingness  
- [ ] dbt tests  

### Phase 4 — Serve

- [ ] Publish subset for web  
- [ ] Dunleavy explorer pages + methodology  
- [ ] Freshness badge  

### Phase 5 — Portfolio polish

- [ ] Architecture diagrams final  
- [ ] PORTFOLIO.md  
- [ ] Optional Snowflake/Tableau as **consumers only**  

---

## Stack (locked for start)

| Layer | Choice |
|-------|--------|
| Language | Python 3.11+ |
| Bronze | Local Parquet/CSV under `data/bronze` |
| Transform | Python → later **dbt + DuckDB** |
| Serve | Dunleavy static/API later |
| Optional | Snowflake / Tableau as extra consumers of gold |

---

## Geographic MVP scope

**Default:** SC, NC, GA (expandable via CLI).  
Enough stations for real volume without downloading the entire planet on day one.

---

## Last session

**2026-07-20**

- Project created under `GitProjects\ClimateRecordPlatform`  
- Docs + Phase 1 ingest scripts added  
- WWI / work-window product explicitly out of scope  

---

## Open decisions

- Exact public product name on Dunleavy (working: **Climate Record Platform**)  
- DuckDB vs Postgres for gold serve  
- Full SE vs SC-only for first public demo  
