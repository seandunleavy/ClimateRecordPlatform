# Climate Record Platform — Project Plan

**Last updated:** 2026-07-21  
**Status:** **v1.1 complete** — explorer chart pack; next is v1.2 (public Dunleavy)  
**Git tags:** `v1.0.0` (platform), `v1.1.0` (explorer charts)  
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
| **v1.2** | Dunleavy public link + deploy polish | ⬜ |
| **v2.0** | Nationwide long-record USW/USC (planned; same repo) | ⬜ |

---

## Goals

| # | Goal | Status |
|---|------|--------|
| 1 | Bronze ingest of GHCNd meta + regional station days | ✅ v1 |
| 2 | Silver parse + quality flags retained + row QC | ✅ v1 |
| 3 | Gold dims/facts + marts (HDD/CDD, freeze, extremes, coverage) | ✅ v1 |
| 4 | dbt tests (+ later incremental patterns) | ✅ v1 tests; incremental later |
| 5 | Public pages on Dunleavy | 🔄 Draft explorer; production link = v1.2 |
| 6 | PORTFOLIO case study complete | 🔄 Updated for v1.0 |

---

## YOU ARE HERE

```
v1.0 CLOSED — Regional long-record climate platform
  ✅ Bronze → silver → QC → gold star + marts
  ✅ ~323 long-record USW/USC stations (SC, NC, GA; 50+y TMAX/TMIN/PRCP)
  ✅ ~28M qc_pass daily fact rows
  ✅ dbt + DuckDB (29 schema/relationship tests)
  ✅ Per-station mart JSON + draft Dunleavy explorer (fast charts)
  ✅ Optional read-only FastAPI over gold Parquet
v1.1 CLOSED — richer explorer (~10 charts + thematic map + ranks)
  ✅ Multi-chart pack from existing marts
  ✅ Thematic station map (hot/freeze marker colors); rank table
  ✅ Completeness chart renamed for clarity
NEXT (v1.2): Dunleavy public link / deploy polish
  (Optional later: map year selector; more polish)
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

### Phase 4 — Serve 🔄

- [x] Mart → web JSON (per-station for performance at scale)  
- [x] Draft Dunleavy explorer + methods  
- [x] Read-only FastAPI (DuckDB on gold Parquet)  
- [ ] Promote/deploy + link from projects.html (v1.2)  
- [ ] Freshness badge  

### Phase 5 — Portfolio polish 🔄

- [x] Architecture + PORTFOLIO for v1.0  
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
| Web demo | Static mart JSON + Chart.js (Dunleavy draft) |

---

## Geographic scope (v1)

**South Carolina, North Carolina, Georgia** — all USW/USC stations with ≥50 years overlapping TMAX + TMIN + PRCP in inventory.  
Expandable later (nationwide long-record = v2).

---

## Last session

**2026-07-21 — Close v1.1**

- Explorer: multi-chart pack, rank table, thematic Leaflet map (hot/freeze)  
- Tagged **`v1.1.0`** (minor: same warehouse, richer product surface)  
- Next: **v1.2** public Dunleavy when ready; map year control optional later  

**Earlier — v1.0**

- Tagged `v1.0.0`; ~323 stations, ~28M qc_pass rows, dbt, API, per-station serve  



---

## Locked product principles

- **Best practices first** (medallion, star schema, explicit QC, documented metric methods).  
- **Modern tools when justified** (Parquet, dbt, DuckDB, FastAPI).  
- **Fast viz from marts** (per-station loads at scale); atomic fact for drill-down / API.  
- **Honest scale** — regional complete long-record in v1; nationwide planned as v2.  
- **Same repo** for all versions; tags mark milestones.  

---

## Open decisions (post-v1)

- Dunleavy production link timing (v1.2)  
- Chart set for v1.1 (wet days, max/min, completeness, map, …)  
- Nationwide download strategy and serving (API-first) for v2  
