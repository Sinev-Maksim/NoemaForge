#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/dream_cycle.py
Zone: release/package
Version: 0.32.2
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
# File: src/dream_cycle.py
# Purpose: Provide the module 'dream_cycle'.
# Invoked by / imported from:
#   - tools/migrate/migrate_memory_v26.py
# Public API / entry functions:
#   - run_project
#   - run_all_projects
#   - main
# Inputs:
#   - --project-id
#   - Common path inputs: /var/lib/noemaforge/outbox/dream, /var/lib/noemaforge/memory/longterm.sqlite
#   - Imports: __future__, argparse, datetime, hashlib, json, os, sqlite3, typing
# Output formats / side effects:
#   - SQLite databases
#   - JSON files
#   - Markdown files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===


import argparse
import datetime as dt
import hashlib
import json
import os
import sqlite3
from typing import Any, Dict, List, Optional

import session_memory_extractor
import task_tools

OUTBOX_BASE = "/var/lib/noemaforge/outbox/dream"
LONGTERM_SQLITE = "/var/lib/noemaforge/memory/longterm.sqlite"


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
#   - src/fixture_bundle.py
#   - src/glove_agent.py
# Calls:
#   - isoformat, utcnow
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _nowz() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


# === NoemaForge Autodoc Function Header ===
# Function: _slug_ts()
# Purpose: Implement the routine ' slug ts'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - strftime, utcnow
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _slug_ts() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


# === NoemaForge Autodoc Function Header ===
# Function: _ensure_parent(path: str)
# Purpose: Implement the routine ' ensure parent'.
# Inputs:
#   - path: str
# Called by:
#   - src/roadmap.py
#   - src/session_memory_extractor.py
#   - src/task_tools.py
#   - src/taskqueue.py
#   - src/telemetry.py
#   - tools/prep/scan_tabs.py
#   - tools/prep/scan_tg.py
# Calls:
#   - makedirs, dirname
# Returns / emits: None
# Side effects:
#   - creates directories
# === End NoemaForge Autodoc Function Header ===
def _ensure_parent(path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)


# === NoemaForge Autodoc Function Header ===
# Function: _connect()
# Purpose: Implement the routine ' connect'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - src/casebase.py
#   - src/knowledge/store.py
#   - src/memory_system.py
#   - src/pipelines/finance_budget.py
#   - src/roadmap.py
#   - src/task_tools.py
#   - src/taskqueue.py
#   - src/vstore.py
# Calls:
#   - _ensure_parent, connect, execute, commit
# Returns / emits: sqlite3.Connection
# Side effects:
#   - opens a database or socket connection
#   - executes SQL or shell-like commands
# Key locals:
#   - con
# === End NoemaForge Autodoc Function Header ===
def _connect() -> sqlite3.Connection:
    _ensure_parent(LONGTERM_SQLITE)
    con = sqlite3.connect(LONGTERM_SQLITE)
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS dream_cycles (
          dream_id TEXT PRIMARY KEY,
          created_at TEXT NOT NULL,
          project_id TEXT NOT NULL,
          report_path TEXT NOT NULL,
          report_sha256 TEXT,
          meta_json TEXT
        );
        """
    )
    con.commit()
    return con


# === NoemaForge Autodoc Function Header ===
# Function: run_project(project_id: str)
# Purpose: Implement the routine 'run project'.
# Inputs:
#   - project_id: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - extract_project, get, append, join, _ensure_parent, hexdigest, _connect, strip, open, write, execute, commit
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads or writes files
#   - opens a database or socket connection
#   - executes SQL or shell-like commands
#   - appends to logs or files
# Key locals:
#   - active, con, d, done, f, lines, path, report, sha, sm, t, tasks
# === End NoemaForge Autodoc Function Header ===
def run_project(project_id: str) -> Dict[str, Any]:
    sm = session_memory_extractor.extract_project(project_id)
    tasks = task_tools.list_user_tasks(project_id=project_id, limit=100).get("tasks") or []
    done = [t for t in tasks if str(t.get("status")) == "done"]
    active = [t for t in tasks if str(t.get("status")) in ("queued", "running", "planning", "blocked")]
    lines = [
        f"# Dream Cycle — {project_id}",
        "",
        f"- Generated at: `{_nowz()}`",
        f"- Completed tasks: `{len(done)}`",
        f"- Active tasks: `{len(active)}`",
        "",
        "## Consolidated signals",
    ]
    if sm.get("decisions"):
        for d in sm.get("decisions")[:12]:
            lines.append(f"- {d}")
    else:
        lines.append("- no stable decisions yet")
    lines += ["", "## Suggested next moves"]
    if active:
        for t in active[:8]:
            lines.append(f"- Finish: {t.get('title')}")
    elif done:
        lines.append("- Convert latest completed work into reusable knowledge / casebase entries")
    else:
        lines.append("- Capture first task or plan before starting execution")
    lines += ["", "## Memory hygiene"]
    lines.append("- Keep the current session summary as the short-term memory anchor")
    lines.append("- Revisit blocked tasks and attach missing artifacts")
    report = "\n".join(lines).strip() + "\n"

    path = os.path.join(OUTBOX_BASE, project_id, f"{_slug_ts()}-dream.md")
    _ensure_parent(path)
    with open(path, "w", encoding="utf-8") as f:
        f.write(report)
    sha = hashlib.sha256(report.encode("utf-8")).hexdigest()

    con = _connect()
    try:
        con.execute(
            "INSERT OR REPLACE INTO dream_cycles(dream_id, created_at, project_id, report_path, report_sha256, meta_json) VALUES(?,?,?,?,?,?)",
            (f"{project_id}:{_slug_ts()}", _nowz(), project_id, path, sha, json.dumps({"active_count": len(active), "done_count": len(done)}, ensure_ascii=False)),
        )
        con.commit()
    finally:
        con.close()
    return {"ok": True, "project_id": project_id, "report_path": path, "sha256": sha, "active_count": len(active), "done_count": len(done)}


# === NoemaForge Autodoc Function Header ===
# Function: run_all_projects()
# Purpose: Implement the routine 'run all projects'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - sorted, get, len, strip, run_project, list_user_tasks, str
# Returns / emits: Dict[str, Any]
# Side effects:
#   - spawns subprocesses or workers
# Key locals:
#   - project_ids, tasks
# === End NoemaForge Autodoc Function Header ===
def run_all_projects() -> Dict[str, Any]:
    tasks = task_tools.list_user_tasks(limit=500).get("tasks") or []
    project_ids = sorted({str(t.get("project_id") or "").strip() for t in tasks if str(t.get("project_id") or "").strip()})
    return {"ok": True, "projects": [run_project(pid) for pid in project_ids], "count": len(project_ids)}


# === NoemaForge Autodoc Function Header ===
# Function: main(argv: Optional[List[str]] = None)
# Purpose: Implement the routine 'main'.
# Inputs:
#   - argv: Optional[List[str]] = None
# Called by:
#   - bootstrap/microvm/noemaforge-microvm-run.py
#   - src/bootdoctor.py
#   - src/brainctl.py
#   - src/noemaforge_core.py
#   - src/brainui.py
#   - src/canary_runner.py
#   - src/doctor.py
#   - src/firstboot_eval.py
# Calls:
#   - ArgumentParser, add_argument, parse_args, print, run_project, run_all_projects, dumps
# Returns / emits: int
# Side effects:
#   - serializes structured data
#   - spawns subprocesses or workers
# Key locals:
#   - ap, ns, out
# === End NoemaForge Autodoc Function Header ===
def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-id", default="")
    ns = ap.parse_args(argv)
    out = run_project(ns.project_id) if ns.project_id else run_all_projects()
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
