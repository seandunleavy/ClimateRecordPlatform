"""
Automated refresh pipeline for Climate Record Platform.

Pulls latest NOAA GHCNd files for the locked station cohort, reprocesses
changed stations through silver + QC, optionally rebuilds gold/dbt/web export.

Production (full cohort — long run):
  python run_refresh.py --full

Smoke (safe for daytime — does NOT rebuild nationwide gold):
  python run_refresh.py --smoke --limit 3

Force downstream even when bronze size unchanged:
  python run_refresh.py --full --reprocess-all

Skip expensive stages:
  python run_refresh.py --full --skip-gold --skip-dbt --skip-export
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
try:
    os.chdir(ROOT)
except OSError:
    pass

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.common.paths import META  # noqa: E402

LOGS = ROOT / "logs"
LOGS.mkdir(exist_ok=True)


def _setup_logging() -> logging.Logger:
    log_path = LOGS / "refresh.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    return logging.getLogger("refresh")


def _run(cmd: list[str], logger: logging.Logger) -> None:
    pretty = " ".join(cmd)
    logger.info("RUN: %s", pretty)
    print(f"\n>>> {pretty}", flush=True)
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed ({result.returncode}): {pretty}")


def _python() -> str:
    return sys.executable


def _load_bronze_manifest() -> dict:
    path = META / "bronze_stations_manifest.json"
    if not path.exists():
        raise SystemExit(
            f"Missing {path}. Complete a full nationwide download before refresh."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def _station_ids_from_manifest(limit: int | None) -> list[str]:
    data = _load_bronze_manifest()
    ids = [s["id"] for s in data.get("stations", []) if s.get("id")]
    if not ids:
        raise SystemExit("bronze_stations_manifest.json has no station ids")
    if limit is not None:
        ids = ids[:limit]
    return ids


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Refresh Climate Record from NOAA GHCNd (automated pipeline)"
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--full",
        action="store_true",
        help="Refresh entire locked cohort; rebuild gold + dbt + export by default",
    )
    mode.add_argument(
        "--smoke",
        action="store_true",
        help="Small subset: bronze/silver/qc only (never overwrites full gold marts)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max stations to re-download/reprocess (default: 3 with --smoke, all with --full)",
    )
    parser.add_argument(
        "--reprocess-all",
        action="store_true",
        help="Re-run silver/QC for all pulled stations even if .dly size unchanged",
    )
    parser.add_argument("--skip-meta", action="store_true")
    parser.add_argument("--skip-bronze", action="store_true")
    parser.add_argument("--skip-silver", action="store_true")
    parser.add_argument("--skip-qc", action="store_true")
    parser.add_argument(
        "--skip-gold",
        action="store_true",
        help="Skip gold rebuild (default for --smoke)",
    )
    parser.add_argument(
        "--skip-dbt",
        action="store_true",
        help="Skip dbt run/test (default for --smoke)",
    )
    parser.add_argument(
        "--skip-export",
        action="store_true",
        help="Skip web JSON export (default for --smoke)",
    )
    parser.add_argument(
        "--skip-fact",
        action="store_true",
        help="When building gold, skip atomic fact (faster marts-only rebuild)",
    )
    parser.add_argument(
        "--copy-to-dunleavy",
        action="store_true",
        help="Pass through to export_web_json (local Dunleavy data/climate-record copy)",
    )
    parser.add_argument(
        "--deploy-phenom",
        action="store_true",
        help=(
            "After export, scp climate-record JSON to phenom unattended "
            "(Dunleavy deploy/deploy-climate-data.ps1; no sudo). "
            "Implies need for --copy-to-dunleavy first (auto-enabled if export runs)."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print plan only; no downloads or transforms",
    )
    args = parser.parse_args()

    if args.deploy_phenom and not args.skip_export:
        # Publish path needs local Dunleavy tree populated
        args.copy_to_dunleavy = True
    if args.deploy_phenom and args.skip_export:
        print(
            "warning: --deploy-phenom with --skip-export will still try phenom sync "
            "from existing local Dunleavy data/climate-record/"
        )

    if not args.full and not args.smoke:
        # Default to smoke when no mode — safer for casual runs
        args.smoke = True
        print("note: no --full/--smoke; defaulting to --smoke (safe subset)")

    if args.smoke:
        if args.limit is None:
            args.limit = 3
        # Protect nationwide gold by default
        if not args.skip_gold and not args.full:
            args.skip_gold = True
        args.skip_dbt = True if not args.full else args.skip_dbt
        args.skip_export = True if not args.full else args.skip_export
        # smoke always skips dbt/export unless user later wants; enforce:
        args.skip_dbt = True
        args.skip_export = True

    if args.full and args.limit is not None:
        print(
            "warning: --full with --limit will only re-pull N stations; "
            "gold rebuild (if enabled) still uses ALL QC files on disk"
        )

    logger = _setup_logging()
    started = datetime.now(timezone.utc)
    logger.info("=== REFRESH START mode=%s limit=%s ===", "full" if args.full else "smoke", args.limit)
    print("=== Climate Record refresh ===")
    print(f"mode={'full' if args.full else 'smoke'}  limit={args.limit}  dry_run={args.dry_run}")
    print(f"started_utc={started.isoformat()}")

    plan = {
        "meta": not args.skip_meta,
        "bronze": not args.skip_bronze,
        "silver": not args.skip_silver,
        "qc": not args.skip_qc,
        "gold": not args.skip_gold,
        "dbt": not args.skip_dbt,
        "export": not args.skip_export,
    }
    print("stages:", {k: v for k, v in plan.items() if v})

    if args.dry_run:
        ids = _station_ids_from_manifest(args.limit)
        print(f"would touch stations ({len(ids)}): {ids[:10]}{'…' if len(ids) > 10 else ''}")
        logger.info("dry-run exit")
        return 0

    py = _python()
    exit_code = 1
    changed_ids: list[str] = []
    reprocess_ids: list[str] = []
    stage_results: dict = {}

    try:
        # 1) Meta
        if plan["meta"]:
            _run([py, "-m", "src.ingest.download_ghcnd_meta", "--force"], logger)
            stage_results["meta"] = "ok"

        # 2) Bronze refresh for cohort
        if plan["bronze"]:
            cmd = [
                py,
                "-m",
                "src.ingest.download_station_days",
                "--from-manifest",
                "--force",
                "--quiet-list",
            ]
            if args.limit is not None:
                cmd.extend(["--limit", str(args.limit)])
            _run(cmd, logger)
            man = _load_bronze_manifest()
            changed_ids = list(man.get("last_pull_changed_station_ids") or [])
            unchanged_ids = list(man.get("last_pull_unchanged_station_ids") or [])
            pulled_ids = changed_ids + unchanged_ids
            if not pulled_ids and args.limit:
                pulled_ids = _station_ids_from_manifest(args.limit)
            stage_results["bronze"] = {
                "changed": len(changed_ids),
                "unchanged": len(man.get("last_pull_unchanged_station_ids") or []),
                "errors": len(man.get("errors") or []),
            }
            logger.info(
                "bronze changed=%s unchanged=%s",
                len(changed_ids),
                len(man.get("last_pull_unchanged_station_ids") or []),
            )
        else:
            pulled_ids = _station_ids_from_manifest(args.limit)

        if args.reprocess_all:
            reprocess_ids = pulled_ids if plan["bronze"] else _station_ids_from_manifest(args.limit)
            logger.info("reprocess-all: %s stations", len(reprocess_ids))
        else:
            reprocess_ids = list(changed_ids)
            if not reprocess_ids and plan["bronze"]:
                logger.info("No bronze size changes; silver/qc will skip unless --reprocess-all")
            elif not plan["bronze"]:
                reprocess_ids = _station_ids_from_manifest(args.limit)

        # 3) Silver (changed or forced subset only)
        if plan["silver"]:
            if not reprocess_ids:
                logger.info("silver: skip (no stations to reprocess)")
                stage_results["silver"] = "skipped_no_changes"
            else:
                joined = ",".join(reprocess_ids)
                _run(
                    [py, "-m", "src.transform.bronze_to_silver", "--stations", joined],
                    logger,
                )
                stage_results["silver"] = {"stations": len(reprocess_ids)}

        # 4) QC
        if plan["qc"]:
            if not reprocess_ids:
                logger.info("qc: skip (no stations to reprocess)")
                stage_results["qc"] = "skipped_no_changes"
            else:
                joined = ",".join(reprocess_ids)
                _run(
                    [py, "-m", "src.transform.apply_qc", "--stations", joined],
                    logger,
                )
                stage_results["qc"] = {"stations": len(reprocess_ids)}

        # 5) Gold — full QC set on disk (protects marts integrity)
        if plan["gold"]:
            if args.smoke:
                raise RuntimeError("internal: gold must not run in smoke mode")
            if not reprocess_ids and not args.reprocess_all:
                logger.info("gold: skip (no bronze changes)")
                stage_results["gold"] = "skipped_no_changes"
            else:
                gold_cmd = [py, "-m", "src.transform.silver_to_gold"]
                if args.skip_fact:
                    gold_cmd.append("--skip-fact")
                _run(gold_cmd, logger)
                stage_results["gold"] = "ok"

        # 6) dbt
        if plan["dbt"]:
            dbt_exe = ROOT / ".venv" / "Scripts" / "dbt.exe"
            dbt = str(dbt_exe) if dbt_exe.exists() else "dbt"
            _run([dbt, "run", "--project-dir", "dbt", "--profiles-dir", "dbt"], logger)
            _run([dbt, "test", "--project-dir", "dbt", "--profiles-dir", "dbt"], logger)
            stage_results["dbt"] = "ok"

        # 7) Export
        if plan["export"]:
            exp = [py, "-m", "src.serve.export_web_json"]
            if args.copy_to_dunleavy:
                exp.append("--copy-to-dunleavy")
            _run(exp, logger)
            stage_results["export"] = "ok"

        # 8) Unattended live JSON to phenom (no sudo; sean owns data/climate-record)
        if args.deploy_phenom:
            dunleavy_deploy = (
                ROOT.parent
                / "dunleavyorganization.com"
                / "deploy"
                / "deploy-climate-data.ps1"
            )
            if not dunleavy_deploy.exists():
                raise RuntimeError(f"Missing phenom data deploy script: {dunleavy_deploy}")
            _run(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(dunleavy_deploy),
                ],
                logger,
            )
            stage_results["deploy_phenom"] = "ok"

        exit_code = 0
        logger.info("=== REFRESH OK ===")
        print("\n✅ Refresh completed successfully")
    except Exception as e:  # noqa: BLE001
        logger.exception("REFRESH FAILED: %s", e)
        print(f"\n❌ Refresh failed: {e}")
        exit_code = 1

    finished = datetime.now(timezone.utc)
    duration_s = (finished - started).total_seconds()
    summary = {
        "started_at_utc": started.isoformat(),
        "finished_at_utc": finished.isoformat(),
        "duration_seconds": duration_s,
        "mode": "full" if args.full else "smoke",
        "limit": args.limit,
        "reprocess_all": args.reprocess_all,
        "changed_station_ids": changed_ids,
        "reprocess_station_ids": reprocess_ids,
        "copy_to_dunleavy": bool(args.copy_to_dunleavy),
        "deploy_phenom": bool(args.deploy_phenom),
        "stages": stage_results,
        "exit_code": exit_code,
        "plan": plan,
    }
    META.mkdir(parents=True, exist_ok=True)
    out = META / "refresh_manifest.json"
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"manifest: {out}")
    print(f"duration: {duration_s:.1f}s | exit_code={exit_code}")
    logger.info("=== REFRESH END exit=%s duration=%.1fs ===", exit_code, duration_s)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
