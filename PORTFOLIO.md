# Climate Record Platform — Portfolio case study

**Status:** In progress (Phase 1)  
**Live URL:** TBD (Dunleavy page after Phase 4)  
**Role:** Solo data engineer / builder  

---

## Problem

Public daily weather observations (NOAA GHCNd) are large, station-oriented, and quality-flagged. Using them well requires a real pipeline and model — not a single spreadsheet — if the goal is transparent, reproducible climate **records** analytics (degree-days, freeze season, extremes frequency, network coverage).

---

## Solution (target)

End-to-end platform:

1. Bronze ingest from NOAA public bulk HTTPS  
2. Silver parse retaining quality flags  
3. Gold dimensional model + analytic marts  
4. Tests and documented methods  
5. Public explorer (planned)

---

## Architecture summary

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## Phases shipped

| Phase | Status |
|-------|--------|
| Repo + bronze ingest scripts | 🔄 |
| Silver / gold / public site | ⬜ |

---

## Challenges (fill as you hit them)

- Station ID selection and volume control  
- Missing data and flag interpretation  
- SCD for station metadata  

---

## What this demonstrates

- Medallion lakehouse-style layout on real public data  
- Reproducible ingest  
- Path to enterprise modeling practices (dims/facts, tests, incremental)  

**Honest scale:** multi-year daily data for a regional station set — **enterprise patterns**, not FAANG petabyte claims.
