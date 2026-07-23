# Session handoff — Climate Record Platform

**Purpose:** Durable context so work continues in **this repo’s session**, not the career folder.  
**Written:** 2026-07-23 (moved out of `GitProjects/career` chat)  
**Repo:** `C:\Users\seand\GitProjects\ClimateRecordPlatform`  
**Live:** https://www.dunleavyorganization.com/project-climate-record.html  

**Agents:** On session start, read this file + `PROJECT_PLAN.md` (YOU ARE HERE) + `docs/ARCHITECTURE.md` refresh section.

---

## What is locked (do not re-debate)

| Decision | Choice |
|----------|--------|
| Product | Enterprise-style DE warehouse on **NOAA GHCNd** + public explorer on Dunleavy |
| Scale | **v2.0** nationwide long-record: **~6,265** stations (USW/USC, ≥50y TMAX+TMIN+PRCP), ~514M qc_pass fact rows |
| Ingest source | **Bulk HTTPS** `.dly` + meta — **not** NOAA CDO API for ongoing |
| Why bulk for refresh | Same format as historical load; weekly NOAA reconstruct; archive replacements rewrite history in files; API better for tiny recent pulls |
| Cohort on refresh | **Locked** via `data/meta/bronze_stations_manifest.json` (`--from-manifest`) — do not re-select every week |
| Gold rebuild | Still **all-or-nothing** from all QC files on disk (partial station list would wipe national marts) |
| Cadence | **Weekly** full refresh matches NCEI daily station updates + **usually weekly** dataset reconstruct; archive-quality often 45–60 days after month end |
| Career positioning | Practical builder / DE **patterns** — not “fake senior DE” brand (career PROFILE) |

---

## v2.1 status (automated refresh) — done today

### Shipped code

| Path | Role |
|------|------|
| `src/common/http.py` | `download_file(..., force=)` returns skip/bytes/changed |
| `src/ingest/download_ghcnd_meta.py` | `--force` |
| `src/ingest/download_station_days.py` | `--from-manifest`, `--force`, `--limit`; change id lists on manifest |
| `src/transform/bronze_to_silver.py` | `--stations a,b,c`; **merge** partial into silver manifest |
| `src/transform/apply_qc.py` | `--stations`; **merge** partial into QC manifest |
| `run_refresh.py` | Orchestrator: meta → bronze → silver → QC → optional gold/dbt/export |
| `run_refresh.bat` | Full weekly-style entry (`--full --copy-to-dunleavy`) |
| `run_refresh_smoke.bat` | Safe daytime: 3 stations, **no gold** |
| `scripts/register_refresh_task.ps1` | Windows Task Scheduler helper (not registered yet) |

### Smoke test (2026-07-23)

```text
python run_refresh.py --smoke --limit 3 --reprocess-all
→ OK ~15s: meta force + 3 .dly force + silver + QC
→ gold/dbt/export skipped by design
→ logs/refresh.log + data/meta/refresh_manifest.json
```

### How refresh works (plain language)

```text
NOAA bulk files
  → force re-download locked cohort
  → if .dly size changed (or --reprocess-all): silver + QC for those stations
  → --full: rebuild gold from ALL stations_qc on disk + optional dbt + export_web_json
  → --copy-to-dunleavy: local folder → dunleavyorganization.com/data/climate-record/
  → --deploy-phenom: unattended scp of that tree to phenom (no sudo)
```

---

## Automation honesty (important)

| Stage | Automated? | Password / sudo? |
|-------|------------|------------------|
| Warehouse refresh (local) | Yes — Task **ClimateRecord-WeeklyRefresh** (Sunday 2 AM) | No |
| Copy JSON into local Dunleavy repo | Yes with `--copy-to-dunleavy` | No |
| Live climate **JSON** on **phenom** | Yes — `deploy/deploy-climate-data.ps1` (BatchMode scp) | No |
| Full Dunleavy **HTML/CSS** site deploy | Manual when pages change | `deploy.ps1` may still prompt sudo |

Weekly bat: `run_refresh.py --full --copy-to-dunleavy --deploy-phenom`

Requires: SSH key to `phenom` + `sean` owns `/var/www/dunleavyorganization.com/data/climate-record` (already true after full site deploys).

---

## Commands (copy-paste)

```powershell
cd C:\Users\seand\GitProjects\ClimateRecordPlatform
.\.venv\Scripts\Activate.ps1

# Safe smoke (no gold, no phenom)
.\run_refresh_smoke.bat

# Full weekly-style (warehouse + local copy + live JSON)
python run_refresh.py --full --copy-to-dunleavy --deploy-phenom
# or: .\run_refresh.bat

# Phenom data-only only (after export already copied locally)
cd ..\dunleavyorganization.com
.\deploy\deploy-climate-data.ps1
```

---

## Open next actions (priority order)

1. First Sunday / overnight full run (PC on at 2 AM).  
2. Optional: incremental gold patch; station search polish.

---

## Explicitly out of scope for this handoff

- Career bids, resume, Upwork, LinkedIn → `GitProjects/career` only  
- AI-Native Backend Lab → parked in career `projects/AI-NATIVE-BACKEND-LAB.md`  
- Do not re-open WWI / work-window product  

---

## Files to read first in a Climate session

1. This handoff  
2. `PROJECT_PLAN.md` — YOU ARE HERE + Last session  
3. `docs/ARCHITECTURE.md` — refresh + medallion  
4. `run_refresh.py` — orchestrator flags  
5. If deploy work: `../dunleavyorganization.com/deploy/deploy.ps1` + SPG `deploy/install-passwordless-deploy.sh` as template  

---

## Career session note

Work on 2026-07-23 was discussed in a **career** Grok session by mistake. Code and docs live only in this repo. Career `NOTES.md` points here. Continue climate engineering **only** with cwd `ClimateRecordPlatform`.
