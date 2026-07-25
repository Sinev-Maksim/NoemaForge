#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/sr_lite.py
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
"""
from __future__ import annotations


# === NoemaForge Autodoc File Header ===
# File: src/sr_lite.py
# Purpose: Provide the module 'sr_lite'.
# Invoked by / imported from:
#   - src/sr_cycle.py
# Public API / entry functions:
#   - run
# Inputs:
#   - Common path inputs: /var/lib/noemaforge
#   - Imports: __future__, datetime, json, os, typing, seclog
# Output formats / side effects:
#   - JSON files
#   - Markdown files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""sr_lite.py (v0.11.4)

SR-lite: deterministic self-reflection pass.

Goal:
- When the system is idle for >N minutes, do a quick audit of "what just happened":
  - errors / denies / quarantines
  - missing daily tasks
  - repeated failures
- Produce small artifacts for Surgeon/Scary and for the user.

This is intentionally LLM-free in MVP: it must be safe, offline, and reproducible.
"""


import datetime as dt
import json
import os
from typing import Any, Dict, List, Tuple

from seclog import verify as sel_verify
from platform_paths import DEFAULT_PATHS as _pp

BASE = str(_pp.data_root)
SEL_DIR = os.path.join(BASE, "sel", "segments")
ROUTINES_DIR = os.path.join(BASE, "routines")
OUT_DIR = os.path.join(BASE, "sr")


# === NoemaForge Autodoc Function Header ===
# Function: _nowz()
# Purpose: Implement the routine ' nowz'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - src/audit_remediation.py
#   - src/noemaforge_core.py
#   - src/bundles.py
#   - src/caps.py
#   - src/casebase.py
#   - src/coordinator_fanout.py
#   - src/dream_cycle.py
#   - src/fixture_bundle.py
# Calls:
#   - isoformat, utcnow
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _nowz() -> str:
    return dt.datetime.now(dt.UTC).replace(tzinfo=None).isoformat() + "Z"


# === NoemaForge Autodoc Function Header ===
# Function: _today()
# Purpose: Implement the routine ' today'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - src/planned_sweep.py
#   - src/scary_sweep.py
#   - src/seclog.py
#   - src/ssr_cycle.py
# Calls:
#   - strftime, utcnow
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _today() -> str:
    return dt.datetime.now(dt.UTC).replace(tzinfo=None).strftime("%Y-%m-%d")


# === NoemaForge Autodoc Function Header ===
# Function: _read_last_events(day: str, limit: int = 500)
# Purpose: Implement the routine ' read last events'.
# Inputs:
#   - day: str
#   - limit: int = 500
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - join, exists, open, rstrip, append, strip, loads
# Returns / emits: List[Dict[str, Any]]
# Side effects:
#   - reads or writes files
#   - appends to logs or files
# Key locals:
#   - f, lines, ln, out, path
# === End NoemaForge Autodoc Function Header ===
def _read_last_events(day: str, limit: int = 500) -> List[Dict[str, Any]]:
    path = os.path.join(SEL_DIR, f"{day}.jsonl")
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = [ln.rstrip("\n") for ln in f if ln.strip()]
        lines = lines[-limit:]
        out: List[Dict[str, Any]] = []
        for ln in lines:
            try:
                out.append(json.loads(ln))
            except Exception:
                continue
        return out
    except Exception:
        return []


# === NoemaForge Autodoc Function Header ===
# Function: _count_types(events: List[Dict[str, Any]], prefix: str)
# Purpose: Implement the routine ' count types'.
# Inputs:
#   - events: List[Dict[str, Any]]
#   - prefix: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - startswith, str, get
# Returns / emits: int
# Key locals:
#   - c, e
# === End NoemaForge Autodoc Function Header ===
def _count_types(events: List[Dict[str, Any]], prefix: str) -> int:
    c = 0
    for e in events:
        if str(e.get("type") or "").startswith(prefix):
            c += 1
    return c


# === NoemaForge Autodoc Function Header ===
# Function: _daily_missing(today: str)
# Purpose: Implement the routine ' daily missing'.
# Inputs:
#   - today: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - join, exists, load, get, str, open, bool, append
# Returns / emits: List[str]
# Side effects:
#   - reads or writes files
#   - appends to logs or files
# Key locals:
#   - missing, plan, plan_path, run_path, t, tid
# === End NoemaForge Autodoc Function Header ===
def _daily_missing(today: str) -> List[str]:
    plan_path = os.path.join(ROUTINES_DIR, "plans", f"{today}.json")
    if not os.path.exists(plan_path):
        return []
    try:
        plan = json.load(open(plan_path, "r", encoding="utf-8"))
    except Exception:
        return []

    missing: List[str] = []
    for t in plan.get("tasks") or []:
        tid = str(t.get("task_id") or "")
        if not tid:
            continue
        if not bool(t.get("must_run")):
            continue
        run_path = os.path.join(ROUTINES_DIR, "runs", f"{today}_{tid}.json")
        if not os.path.exists(run_path):
            missing.append(tid)
    return missing


# === NoemaForge Autodoc Function Header ===
# Function: run(max_events: int = 500)
# Purpose: Implement the routine 'run'.
# Inputs:
#   - max_events: int = 500
# Called by:
#   - src/bootdoctor.py
#   - src/brainctl.py
#   - src/firstboot_eval.py
#   - src/hwscan.py
#   - src/knowledge_maintainer.py
#   - src/lan_discovery.py
#   - src/localgateway.py
#   - src/localgw_connectors/ipp.py
# Calls:
#   - makedirs, _today, _read_last_events, bool, _count_types, _daily_missing, items, join, sel_verify, _nowz, append, open
# Returns / emits: Tuple[str, Dict[str, Any]]
# Side effects:
#   - reads or writes files
#   - creates directories
#   - appends to logs or files
# Key locals:
#   - denies, events, f, findings, md_lines, mem_crit, missing_daily, out_json, out_md, quarantines, r, recs
# === End NoemaForge Autodoc Function Header ===
def run(max_events: int = 500) -> Tuple[str, Dict[str, Any]]:
    os.makedirs(OUT_DIR, exist_ok=True)

    today = _today()
    events = _read_last_events(today, limit=max_events)

    sel_ok = bool(sel_verify(today))

    denies = _count_types(events, "TOOLPROXY_DENY")
    quarantines = _count_types(events, "TOOLPROXY_QUARANTINE")
    mem_crit = _count_types(events, "MEM_PRESSURE_M2") + _count_types(events, "MEM_PRESSURE_M3")
    recurring_fail = _count_types(events, "RECURRING_RUN_FAILED")

    missing_daily = _daily_missing(today)

    findings: Dict[str, Any] = {
        "ts": _nowz(),
        "day": today,
        "sel_ok": sel_ok,
        "counts": {
            "tool_denies": denies,
            "tool_quarantines": quarantines,
            "mem_critical": mem_crit,
            "recurring_failed": recurring_fail,
            "missing_daily": len(missing_daily),
        },
        "missing_daily_tasks": missing_daily,
        "recommendations": [],
    }

    recs: List[Dict[str, Any]] = []
    if not sel_ok:
        recs.append({"priority": "critical", "action": "investigate_sel_integrity", "why": "SEL verify() failed for today"})
    if mem_crit > 0:
        recs.append({"priority": "critical", "action": "memory_spill_and_recovery", "why": "M2/M3 memory pressure events detected"})
    if quarantines > 0:
        recs.append({"priority": "urgent", "action": "review_quarantine_incidents", "why": "ToolProxy quarantined actions"})
    if denies > 0:
        recs.append({"priority": "high", "action": "review_tool_policy_denies", "why": "ToolProxy denies indicate missing capabilities or policy"})
    if missing_daily:
        recs.append({"priority": "urgent", "action": "run_missing_daily_tasks", "why": "Daily SLA tasks missing"})

    findings["recommendations"] = recs

    md_lines = [
        f"# SR-lite report {today}\n",
        f"Generated: {findings['ts']}\n\n",
        f"SEL integrity: {'OK' if sel_ok else '**FAIL**'}\n\n",
        "## Counters\n",
    ]
    for k, v in (findings.get("counts") or {}).items():
        md_lines.append(f"- {k}: {v}\n")

    if missing_daily:
        md_lines.append("\n## Missing daily tasks\n")
        for tid in missing_daily:
            md_lines.append(f"- {tid}\n")

    if recs:
        md_lines.append("\n## Recommendations\n")
        for r in recs:
            md_lines.append(f"- **{r['priority']}**: {r['action']} — {r['why']}\n")

    out_md = os.path.join(OUT_DIR, "sr_lite_last.md")
    out_json = os.path.join(OUT_DIR, "sr_lite_last.json")

    with open(out_md, "w", encoding="utf-8") as f:
        f.write("".join(md_lines))

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(findings, f, ensure_ascii=False, indent=2)

    return out_md, findings


if __name__ == "__main__":
    p, _ = run()
    print(p)
