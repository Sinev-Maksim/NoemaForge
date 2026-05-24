#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/first_start_summary.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-14
Modified: 2026-05-14
Purpose: Provide NoemaForge release functionality for the packaged local runtime.
Inputs: Command-line arguments, environment variables, package files and local NoemaForge runtime state as applicable.
Outputs: Structured command output, files, service state or UI state as documented by the caller.
Side effects: Limited to the documented NoemaForge paths, runtime state directories or systemd units used by this file.
Tests: Syntax validation plus the release setup selftest, consistency-audit and targeted smoke checks.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===

Existing module notes:
Readable NoemaForge first-start summary with color and grouped runs.
"""
from __future__ import annotations
import argparse, json, os, sys
from pathlib import Path
from typing import Any

RUNTIME_VERSION = "0.32.1"
BOOT = Path(os.environ.get("NOEMAFORGE_BOOTSTRAP", "/var/lib/noemaforge/bootstrap"))

COLORS = {
    "green":"\033[32m", "red":"\033[31m", "yellow":"\033[33m", "blue":"\033[36m", "bold":"\033[1m", "reset":"\033[0m"
}

def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return default

def load_events(path: Path) -> list[dict[str, Any]]:
    out=[]
    if not path.exists(): return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            obj=json.loads(line)
            if isinstance(obj, dict): out.append(obj)
        except Exception:
            pass
    return out

def group_runs(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    runs=[]; cur=None
    for ev in events:
        if ev.get("step") == "start":
            if cur: runs.append(cur)
            cur={"start":ev,"events":[ev]}
        elif cur:
            cur["events"].append(ev)
    if cur: runs.append(cur)
    return runs

def status_kind(state: str|None) -> str:
    s=str(state or "")
    if s in {"complete","selection_ready_no_apply","applied_no_reboot","applied_reboot_scheduled"} or s.startswith("applied"):
        return "PASS"
    if s.startswith("blocked") or s in {"failed","error","unstaffed"}:
        return "FAIL"
    if s in {"warning","degraded_selected"} or "warn" in s or "degraded" in s:
        return "WARN"
    return "INFO"

def badge(kind: str, color: bool=True) -> str:
    if not color: return f"[{kind}]"
    c = {"PASS":"green","FAIL":"red","WARN":"yellow","INFO":"blue"}.get(kind,"blue")
    return f"{COLORS[c]}[{kind}]{COLORS['reset']}"

def b(text: str, color: bool=True) -> str:
    return f"{COLORS['bold']}{text}{COLORS['reset']}" if color else text

def run_final(run: dict[str, Any]) -> dict[str, Any]:
    evs=run.get("events") or []
    return next((e for e in reversed(evs) if e.get("step") == "complete"), evs[-1] if evs else {})

def main(argv=None) -> int:
    ap=argparse.ArgumentParser(prog="noemaforge first-start summary")
    ap.add_argument("--bootstrap", default=str(BOOT))
    ap.add_argument("--latest", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-color", action="store_true")
    args=ap.parse_args(argv)
    boot=Path(args.bootstrap)
    events=load_events(boot/"firstboot-events.jsonl")
    runs=group_runs(events)
    staff=load_json(boot/"firstboot-staffing-summary.json", {})
    status=load_json(boot/"firstboot-status.json", {})
    decision=load_json(boot/"model-selection-decision.json", {})
    if args.json:
        print(json.dumps({"ok": True, "version": RUNTIME_VERSION, "run_count": len(runs), "latest_status": status, "staffing": staff, "decision": decision, "runs": runs}, ensure_ascii=False, indent=2))
        return 0
    color = not args.no_color
    print(b("NOEMAFORGE FIRST-START SUMMARY", color))
    print()
    if not runs:
        print(f"{badge('WARN', color)} no first-start events found in {boot}")
        return 0
    show_runs = runs if args.all else runs[-1:]
    if args.all:
        print(b("Runs", color))
    else:
        print(b("Latest run", color))
    for run in show_runs:
        st=run.get("start",{})
        fn=run_final(run)
        extra=st.get("extra") or {}
        fextra=fn.get("extra") or {}
        mode=fextra.get("selection_mode")
        if not mode:
            for ev in run.get("events",[]):
                ex=ev.get("extra") or {}
                if ex.get("selection_mode"):
                    mode=ex.get("selection_mode"); break
        state=fn.get("state") or "unknown"
        kind=status_kind(state)
        print(f"{badge(kind, color)} {st.get('ts','-')}  run={extra.get('run_id','-')}  mode={mode or '-'}  final={state}")
        print(f"      {fn.get('message','')}")
    print()
    print(b("Timeline", color))
    latest = runs[-1]
    for ev in latest.get("events",[]):
        kind=status_kind(ev.get("state"))
        print(f"{badge(kind, color)} {ev.get('ts','-')}  {str(ev.get('step','-')):<18} {str(ev.get('state','-')):<34} {ev.get('message','')}")
    print()
    print(b("Staffing", color))
    sstate=staff.get("staffing_state") or "unknown"
    missing=staff.get("missing_mandatory_core_roles") or []
    selected=staff.get("selected_model_count") or 0
    degraded=staff.get("degraded_roles") or []
    unstaffed=staff.get("unstaffed_roles") or []
    print(f"{badge(status_kind(sstate), color)} staffing_state={sstate}")
    print(f"{badge('PASS' if not missing else 'FAIL', color)} mandatory_core_missing={missing}")
    print(f"{badge('PASS' if selected else 'FAIL', color)} selected_model_count={selected}")
    print(f"{badge('WARN' if degraded else 'PASS', color)} degraded_roles={degraded}")
    print(f"{badge('INFO', color)} unstaffed_roles_count={len(unstaffed)}")
    print()
    final_state=status.get("state") or run_final(latest).get("state") or "unknown"
    final_kind=status_kind(final_state)
    print(b("Final", color))
    print(f"{badge(final_kind, color)} {b(str(final_state), color)}")
    if final_kind == "PASS":
        print(b("**PASS: first-start selection/recovery state is acceptable for this stage.**", color))
    elif final_kind == "WARN":
        print(b("**WARN: mandatory core may be usable, but degraded roles require review.**", color))
    else:
        print(b("**FAIL: do not treat this run as successful until blocker is reviewed.**", color))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())


