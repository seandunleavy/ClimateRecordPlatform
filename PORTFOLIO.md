# Climate Record Platform — Portfolio case study

**Status:** **v1.1 complete** (v1.0 platform + multi-chart explorer)  
**Version tags:** `v1.0.0` (platform), `v1.1.0` (explorer charts)  
**Live URL:** Draft explorer locally / Dunleavy draft page (production link TBD — v1.2)  
**Role:** Solo data engineer / builder  
**Repo:** https://github.com/seandunleavy/ClimateRecordPlatform  

---

## Problem

Public daily weather observations (NOAA GHCNd) are large, station-oriented, and quality-flagged. Using them well requires a real pipeline and model — not a single spreadsheet — if the goal is transparent, reproducible climate **records** analytics (degree-days, freeze season, extremes frequency, network coverage).

---

## Solution (v1.0)

End-to-end medallion platform on a **complete regional long-record sample**:

1. **Bronze** — HTTPS bulk land of station meta, inventory, and per-station `.dly` files  
2. **Smart station pick** — all USW/USC in SC/NC/GA with ≥50-year TMAX+TMIN+PRCP inventory overlap (~**323 stations**)  
3. **Silver** — fixed-width `.dly` → daily typed Parquet; retain M/Q/S flags; scale units  
4. **QC** — `qc_pass` / `qc_reasons` (missing, NOAA qflag, physical ranges, TMAX&lt;TMIN); no silent deletes  
5. **Gold star + marts** — dims + daily fact; monthly climate, heating/cooling degree-days, extremes, freeze season, coverage  
6. **dbt + DuckDB** — SQL models + uniqueness / relationship tests  
7. **Serve** — per-station mart JSON for a fast multi-chart explorer (degree-days, extremes, precip, completeness, ranks, thematic station map); optional read-only FastAPI  


---

## Architecture summary

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

```text
NOAA GHCNd → bronze → silver → stations_qc → gold (star + marts)
                              → dbt/DuckDB tests
                              → per-station JSON / FastAPI → explorer
```

---

## Scale (honest)

| Metric | v1.0 |
|--------|------|
| Stations | ~**323** long-record USW/USC (SC, NC, GA) |
| Quality-pass daily rows | ~**28 million** |
| History | Multi-decade to ~150+ years on some series |
| Web performance approach | Load **only selected station** mart files (not full daily fact or giant all-station JSON) |

Enterprise **patterns** at portfolio-honest volume — not petabyte claims.

---

## Phases shipped (v1.0)

| Phase | Status |
|-------|--------|
| Repo + bronze ingest (long-record regional set) | ✅ |
| Silver parse + quality profile | ✅ |
| Row-level QC + fail export | ✅ |
| Gold star schema + marts | ✅ |
| dbt + DuckDB tests | ✅ |
| Fast mart-based explorer + optional API | ✅ v1.0 |
| Multi-chart explorer + thematic map | ✅ v1.1 |
| Production Dunleavy link | ⬜ v1.2 |
| Nationwide sample | ⬜ v2 |

---

## Challenges (real ones hit)

- **Station ID selection** — first-N by ID yielded short CoCoRaHS-style gauges; inventory + USW/USC fixed it  
- **`.dly` layout** — month-wide fixed-width lines; scale factors (tenths °C / mm)  
- **Bad historical values** — rare extremes (e.g. 1470 °C TMAX); range QC + NOAA qflags  
- **Missing vs wrong** — most QC fails are missing days or NOAA flags  
- **Serve at scale** — all-station multi-decade JSON grew to tens of MB; switched to **per-station** mart loads so charts stay fast  
- **Sparse stations** — inventory span ≠ every year filled after QC (showed honestly in explorer)  

---

## What this demonstrates

- Medallion layout on real public data  
- Reproducible ingest + manifests  
- Quality-aware silver and explicit product QC  
- Dimensional modeling (star) + analytic marts  
- dbt testing culture  
- Performance-aware serving (marts / per-station slices / optional API)  
- Transparent climate metric methods  

---

## Roadmap (same repo)

- **v1.1** — more charts / ranks / thematic map ✅  
- **v1.2** — public Dunleavy case study link  
- **v2** — nationwide long-record expansion (planned)  

---

## How to run

See [`README.md`](README.md) quick start.
