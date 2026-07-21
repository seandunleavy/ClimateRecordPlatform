# Climate Record Platform — Portfolio case study

**Status:** In progress (gold v1 shipped; public site TBD)  
**Live URL:** TBD (Dunleavy page after Phase 4)  
**Role:** Solo data engineer / builder  

---

## Problem

Public daily weather observations (NOAA GHCNd) are large, station-oriented, and quality-flagged. Using them well requires a real pipeline and model — not a single spreadsheet — if the goal is transparent, reproducible climate **records** analytics (degree-days, freeze season, extremes frequency, network coverage).

---

## Solution (built so far)

End-to-end medallion path on a regional sample (SC / NC / GA):

1. **Bronze** — HTTPS bulk land of station meta, inventory, and per-station `.dly` files  
2. **Smart station pick** — long-record USW/USC via inventory (TMAX+TMIN+PRCP span), not first IDs in sort  
3. **Silver** — fixed-width `.dly` → daily typed Parquet; retain M/Q/S flags; scale units  
4. **QC** — explicit `qc_pass` / `qc_reasons` (missing, NOAA qflag, physical ranges, TMAX&lt;TMIN); no silent deletes  
5. **Gold marts** — `dim_station`, daily fact, monthly climate, HDD/CDD (base 18 °C), coverage, freeze season, yearly extremes  
6. **Tests / public site** — dbt + Dunleavy planned  

---

## Architecture summary

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

```text
NOAA GHCNd → bronze (.dly) → silver (rows) → stations_qc (flags) → gold (marts)
```

---

## Phases shipped

| Phase | Status |
|-------|--------|
| Repo + bronze ingest (meta + long-record sample) | ✅ |
| Silver parse + quality profile | ✅ |
| Row-level QC + fail export | ✅ |
| Gold dims / facts / marts (HDD/CDD, coverage, freeze, extremes) | ✅ |
| dbt + DuckDB tests | ⬜ |
| Public Dunleavy explorer | ⬜ |

---

## Challenges (real ones hit)

- **Station ID selection** — first-N by ID yielded short CoCoRaHS-style gauges; inventory + USW/USC fixed it  
- **`.dly` layout** — month-wide fixed-width lines, not one day per row; scale factors (tenths °C / mm)  
- **Bad historical values** — rare but extreme (e.g. 1470 °C TMAX); caught by range QC + NOAA qflags  
- **Missing vs wrong** — most QC fails are missing days or NOAA flags, not only absurd temps  

---

## What this demonstrates

- Medallion layout on real public data  
- Reproducible ingest + manifests  
- Quality-aware silver (flags retained, product rules explicit)  
- Analytic marts (degree-days, coverage) with documented methods  
- Path to enterprise modeling (dbt/tests, serve layer)  

**Honest scale:** multi-decade daily data for ~15 regional stations (~1.8M qc_pass rows into gold) — **enterprise patterns**, not petabyte claims.

---

## How to run

See [`README.md`](README.md) quick start.
