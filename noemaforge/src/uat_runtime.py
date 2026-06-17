#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/uat_runtime.py
Zone: src/runtime
Version: 0.33.0
Purpose: One-command UAT orchestration ("the UAT button"). Sequentially:
           1. starts event recording (a dedicated event-log dir for the session),
           2. (optionally) launches the Admin GUI, display-safe, pointed at the
              same event log,
           3. runs every pipeline in the catalog in turn, saving each run's
              artifacts into the logging folder,
           4. stops the GUI and the event recording,
         then writes a self-describing evidence bundle (manifest + summary +
         per-pipeline artifacts + recorded events) and prints its path so the
         operator gets the artifacts back, not just side effects.
Inputs: pipeline catalog (configs/pipelines.json), CLI flags.
Outputs: a UAT evidence bundle under --out (events/, pipelines/<id>/,
         gui/, commands.log, manifest.json, summary.md).
Side effects: spawns pipeline runs (and optionally the GUI) as subprocesses,
              writing under --out and the per-session state dir only.
Tests: noemaforge/tests/test_uat_runtime.py
Notes: stdlib only. Cross-platform: pipeline/GUI are launched via sys.executable
       (no bash). Per the display-safety rule the GUI keeps the display alive.
       Code comments are English-only.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

_SRC = Path(__file__).resolve().parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from noemaforge_version import RUNTIME_VERSION  # noqa: E402


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_catalog(package_root: Path) -> Dict[str, Dict[str, Any]]:
    """Pipeline ids -> definition, via the pipeline runtime's own loader."""
    import pipeline_runtime  # imported lazily so --help works without the catalog
    return pipeline_runtime.load_pipeline_catalog(package_root)


def _append_event(events_dir: Path, event_type: str, data: Dict[str, Any]) -> None:
    import event_log
    event_log.EventLog(events_dir).append(event_type, data, actor="uat")


def _run_pipeline(
    pipeline_id: str,
    *,
    package_root: Path,
    bundle: Path,
    env: Dict[str, str],
    request: str,
    dry_run: bool,
    timeout: int,
) -> Dict[str, Any]:
    """Run one pipeline as a subprocess; collect its artifacts into the bundle."""
    run_id = f"uat_{pipeline_id}_{int(time.time())}"
    cmd = [
        sys.executable, str(package_root / "src" / "pipeline_runtime.py"),
        "run", pipeline_id,
        "--task-id", f"uat_{pipeline_id}",
        "--request", request,
        "--run-id", run_id,
        "--allow-degraded",
    ]
    if dry_run:
        cmd.append("--dry-run")
    record: Dict[str, Any] = {"pipeline": pipeline_id, "run_id": run_id, "cmd": cmd}
    try:
        proc = subprocess.run(
            cmd, cwd=str(package_root), env=env, text=True,
            capture_output=True, timeout=timeout,
        )
        record["returncode"] = proc.returncode
        record["status"] = "ok" if proc.returncode == 0 else "failed"
        out_dir = bundle / "pipelines" / pipeline_id
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "stdout.txt").write_text(proc.stdout or "", encoding="utf-8")
        (out_dir / "stderr.txt").write_text(proc.stderr or "", encoding="utf-8")
        run_dir = ""
        try:
            run_dir = str(json.loads(proc.stdout).get("run_dir", ""))
        except Exception:  # noqa: BLE001 - non-JSON output is captured as-is
            pass
        if run_dir and Path(run_dir).is_dir():
            shutil.copytree(run_dir, out_dir / "run_dir", dirs_exist_ok=True)
            record["artifact_count"] = sum(
                1 for _ in (out_dir / "run_dir").rglob("*") if _.is_file()
            )
        else:
            record["artifact_count"] = 0
    except subprocess.TimeoutExpired:
        record["status"] = "timeout"
        record["returncode"] = None
    except Exception as exc:  # noqa: BLE001 - a pipeline crash is captured, not fatal
        record["status"] = "error"
        record["error"] = repr(exc)
    return record


def _launch_gui(package_root: Path, bundle: Path, env: Dict[str, str], keep_display: bool):
    """Best-effort: launch the Admin GUI as a background subprocess."""
    gui_dir = bundle / "gui"
    gui_dir.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(package_root / "src" / "admin_gui_server.py")]
    if keep_display:
        cmd.append("--keep-display")
    log = open(gui_dir / "gui.log", "w", encoding="utf-8")
    try:
        proc = subprocess.Popen(cmd, cwd=str(package_root), env=env, stdout=log, stderr=log)
    except Exception as exc:  # noqa: BLE001
        (gui_dir / "gui.json").write_text(
            json.dumps({"launched": False, "error": repr(exc)}, indent=2), encoding="utf-8"
        )
        return None
    time.sleep(2)  # give it a moment to bind / fail fast
    (gui_dir / "gui.json").write_text(
        json.dumps({"launched": proc.poll() is None, "pid": proc.pid, "cmd": cmd}, indent=2),
        encoding="utf-8",
    )
    return proc


def run_uat(args: argparse.Namespace) -> int:
    package_root = Path(args.root).resolve()
    bundle = Path(args.out).resolve()
    bundle.mkdir(parents=True, exist_ok=True)
    events_dir = bundle / "events"
    events_dir.mkdir(parents=True, exist_ok=True)
    state_dir = bundle / "state"

    env = dict(os.environ)
    env["NOEMAFORGE_ROOT"] = str(package_root)
    env["NOEMAFORGE_EVENT_LOG_DIR"] = str(events_dir)      # step 1: record here
    env["NOEMAFORGE_PIPELINE_STATE"] = str(state_dir)
    env["NOEMAFORGE_ALLOW_DEGRADED_MUTATION"] = "1"

    catalog = _load_catalog(package_root)
    selected = (
        [p for p in args.pipelines.split(",") if p.strip()]
        if args.pipelines else sorted(catalog)
    )
    selected = [p for p in selected if p in catalog]

    # Step 1 — start recording.
    _append_event(events_dir, "uat_session_start", {
        "version": RUNTIME_VERSION, "pipelines": selected,
        "dry_run": args.dry_run, "gui": args.gui, "started_at": _now(),
    })

    # Step 2 — launch the GUI (display-safe, best-effort).
    gui_proc = _launch_gui(package_root, bundle, env, args.keep_display) if args.gui else None

    # Step 3 — run every pipeline, saving artifacts.
    results: List[Dict[str, Any]] = []
    for pid in selected:
        results.append(_run_pipeline(
            pid, package_root=package_root, bundle=bundle, env=env,
            request=args.request, dry_run=args.dry_run, timeout=args.timeout,
        ))

    # Step 4 — stop the GUI, then stop recording.
    if gui_proc is not None and gui_proc.poll() is None:
        gui_proc.terminate()
        try:
            gui_proc.wait(timeout=10)
        except Exception:  # noqa: BLE001
            gui_proc.kill()
    _append_event(events_dir, "uat_session_stop", {
        "stopped_at": _now(),
        "ok": sum(1 for r in results if r.get("status") == "ok"),
        "total": len(results),
    })

    event_count = 0
    events_file = events_dir / "events.jsonl"
    if events_file.is_file():
        event_count = sum(1 for line in events_file.read_text(encoding="utf-8").splitlines() if line.strip())

    manifest = {
        "kind": "NoemaForgeUATBundle",
        "version": RUNTIME_VERSION,
        "generated_at": _now(),
        "gui_launched": gui_proc is not None,
        "dry_run": args.dry_run,
        "event_count": event_count,
        "pipelines": results,
        "summary": {
            "total": len(results),
            "ok": sum(1 for r in results if r.get("status") == "ok"),
            "failed": sum(1 for r in results if r.get("status") not in ("ok",)),
            "artifacts": sum(int(r.get("artifact_count", 0)) for r in results),
        },
    }
    (bundle / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    s = manifest["summary"]
    lines = [
        f"# NoemaForge UAT run — {manifest['generated_at']}",
        "",
        f"- version: {RUNTIME_VERSION}",
        f"- pipelines: {s['ok']}/{s['total']} ok · artifacts: {s['artifacts']} · events: {event_count}",
        f"- gui launched: {manifest['gui_launched']} · dry_run: {args.dry_run}",
        "",
        "| pipeline | status | rc | artifacts |",
        "|---|---|---|---|",
    ]
    for r in results:
        lines.append(f"| {r['pipeline']} | {r.get('status')} | {r.get('returncode')} | {r.get('artifact_count', 0)} |")
    (bundle / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps({"ok": True, "bundle": str(bundle), "summary": s, "events": event_count}, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="noemaforge uat", description="One-command UAT runner.")
    sub = p.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="record events, (launch GUI,) run all pipelines, bundle artifacts")
    run.add_argument("--root", default="noemaforge", help="package root (contains src/, configs/)")
    run.add_argument("--out", required=True, help="logging/evidence bundle directory")
    run.add_argument("--request", default="UAT smoke run", help="request text passed to each pipeline")
    run.add_argument("--pipelines", default="", help="comma-separated pipeline ids (default: all in catalog)")
    run.add_argument("--timeout", type=int, default=300, help="per-pipeline timeout (seconds)")
    run.add_argument("--dry-run", action="store_true", help="plan pipelines without executing side effects")
    gui = run.add_mutually_exclusive_group()
    gui.add_argument("--gui", dest="gui", action="store_true", help="launch the Admin GUI (default)")
    gui.add_argument("--no-gui", dest="gui", action="store_false", help="headless: do not launch the GUI")
    run.set_defaults(gui=True)
    run.add_argument("--keep-display", action="store_true", default=True, help="keep the display alive (display-safety rule)")
    run.set_defaults(func=run_uat)
    return p


def main(argv: List[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
