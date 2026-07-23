# Climate Record Platform — Portfolio case study

**Status:** **v2.0 complete** (nationwide long-record + public Dunleavy explorer)  
**Version tags:** `v1.0.0`, `v1.1.0`, `v1.2.0`, `v2.0.0`  
**Live URL:** https://www.dunleavyorganization.com/project-climate-record.html  
**Role:** Solo data engineer / builder  
**Repo:** https://github.com/seandunleavy/ClimateRecordPlatform *(public)*  

---

## Problem

Public daily weather observations (NOAA GHCNd) are large, station-oriented, and quality-flagged. Using them well requires a real pipeline and model — not a single spreadsheet — if the goal is transparent, reproducible climate **records** analytics (degree-days, freeze season, extremes frequency, network coverage).

---

## Solution

End-to-end medallion platform on **nationwide long-record** public stations (v2; regional v1 first):

1. **Bronze** — HTTPS bulk land of station meta, inventory, and per-station `.dly` files  
2. **Station pick** — all USW/USC with ≥50-year TMAX+TMIN+PRCP inventory overlap — **~6,265 stations** (all states + D.C.; same rules as the SC/NC/GA pilot)  
3. **Silver** — fixed-width `.dly` → daily typed Parquet; retain M/Q/S flags; scale units (~**528M** rows)  
4. **QC** — `qc_pass` / `qc_reasons` (missing, NOAA qflag, physical ranges, TMAX&lt;TMIN); no silent deletes (~**97.3%** pass)  
5. **Gold star + marts** — dims + daily fact (~**514M** qc_pass rows) built **station-at-a-time** to avoid OOM; monthly climate, HDD/CDD, extremes, freeze, coverage  
6. **dbt + DuckDB** — SQL models + uniqueness / relationship tests (**29 PASS**)  
7. **Serve** — one combined mart JSON per station; multi-chart explorer + map on Dunleavy; optional read-only FastAPI  
8. **Refresh (v2.1)** — scheduled re-pull of the locked cohort (`run_refresh.py`): force-download → change detection → silver/QC for changed stations → optional full gold + dbt + web export  


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

| Metric | v1 (regional) | v2 (nationwide) |
|--------|---------------|-----------------|
| Stations | ~**323** (SC, NC, GA) | ~**6,265** (all states + D.C.) |
| Quality-pass daily rows | ~**28 million** | ~**514 million** |
| History | Multi-decade to 150+ years | Same rules; some series from mid-1800s |
| Web serve | One JSON file per station select | Same pattern at national station count |

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
| Production Dunleavy case study page + cards | ✅ v1.2 |
| Nationwide long-record (same rules) + live explorer | ✅ v2.0 |

---

## Challenges (real ones hit)

- **Station ID selection** — first-N by ID yielded short CoCoRaHS-style gauges; inventory + USW/USC fixed it  
- **`.dly` layout** — month-wide fixed-width lines; scale factors (tenths °C / mm)  
- **Bad historical values** — rare extremes (e.g. 1470 °C TMAX); range QC + NOAA qflags  
- **Missing vs wrong** — most QC fails are missing days or NOAA flags  
- **Serve at scale** — all-station multi-decade JSON grew to tens of MB; switched to **per-station** loads, then **one combined JSON** per station for fewer round trips  
- **Gold at 500M+ rows** — full in-memory concat would OOM; **streamed gold** (one station QC file at a time + ParquetWriter for the fact)  
- **Sparse / closed stations** — map network metrics use each station’s **own latest extremes year**, not only calendar-year max  
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
- **v1.2** — public Dunleavy case study ✅  
- **v2.0** — nationwide long-record + live explorer ✅  
- **Later** — optional search / map polish; incremental refresh patterns  

---

## How to run

See [`README.md`](README.md) quick start.
