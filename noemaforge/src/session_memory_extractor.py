#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/session_memory_extractor.py
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
# File: src/session_memory_extractor.py
# Purpose: Provide the module 'session_memory_extractor'.
# Invoked by / imported from:
#   - src/dream_cycle.py
#   - tools/migrate/migrate_memory_v26.py
# Public API / entry functions:
#   - extract_project
#   - extract_all_projects
#   - main
# Inputs:
#   - --project-id
#   - --limit
#   - Common path inputs: /var/lib/noemaforge/memory/session, /var/lib/noemaforge/memory/longterm.sqlite
#   - Imports: __future__, argparse, datetime, json, os, sqlite3, typing, task_tools
# Output formats / side effects:
#   - SQLite databases
#   - JSON files
#   - Markdown files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===


import argparse
import datetime as dt
import json
import os
import sqlite3
from typing import Any, Dict, List, Optional

import task_tools

MEMORY_DIR = "/var/lib/noemaforge/memory/session"
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
#   - src/dream_cycle.py
#   - src/fixture_bundle.py
# Calls:
#   - isoformat, utcnow
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _nowz() -> str:
    return dt.datetime.utcnow().isoformat() + "Z"


# === NoemaForge Autodoc Function Header ===
# Function: _ensure_parent(path: str)
# Purpose: Implement the routine ' ensure parent'.
# Inputs:
#   - path: str
# Called by:
#   - src/dream_cycle.py
#   - src/roadmap.py
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
# Function: _session_md_path(project_id: str)
# Purpose: Implement the routine ' session md path'.
# Inputs:
#   - project_id: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - join, strip, str
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _session_md_path(project_id: str) -> str:
    return os.path.join(MEMORY_DIR, str(project_id).strip(), "session_memory.md")


# === NoemaForge Autodoc Function Header ===
# Function: _connect_longterm()
# Purpose: Implement the routine ' connect longterm'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - tools/migrate/migrate_memory_v26.py
# Calls:
#   - _ensure_parent, connect, execute, commit
# Returns / emits: sqlite3.Connection
# Side effects:
#   - opens a database or socket connection
#   - executes SQL or shell-like commands
# Key locals:
#   - con
# === End NoemaForge Autodoc Function Header ===
def _connect_longterm() -> sqlite3.Connection:
    _ensure_parent(LONGTERM_SQLITE)
    con = sqlite3.connect(LONGTERM_SQLITE)
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS session_summaries (
          summary_id TEXT PRIMARY KEY,
          generated_at TEXT NOT NULL,
          project_id TEXT NOT NULL,
          source_count INTEGER NOT NULL DEFAULT 0,
          path TEXT NOT NULL,
          facts_json TEXT,
          decisions_json TEXT,
          open_items_json TEXT
        );
        """
    )
    con.commit()
    return con


# === NoemaForge Autodoc Function Header ===
# Function: _facts_from_tasks(tasks: List[Dict[str, Any]])
# Purpose: Implement the routine ' facts from tasks'.
# Inputs:
#   - tasks: List[Dict[str, Any]]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - str, int, append, get
# Returns / emits: Dict[str, Any]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - art, facts, kd, st, t
# === End NoemaForge Autodoc Function Header ===
def _facts_from_tasks(tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
    facts: Dict[str, Any] = {"counts_by_status": {}, "counts_by_kind": {}, "recent_artifacts": []}
    for t in tasks:
        st = str(t.get("status") or "unknown")
        facts["counts_by_status"][st] = int(facts["counts_by_status"].get(st, 0)) + 1
        kd = str(t.get("kind") or "generic")
        facts["counts_by_kind"][kd] = int(facts["counts_by_kind"].get(kd, 0)) + 1
        for art in (t.get("artifacts") or [])[:2]:
            facts["recent_artifacts"].append({"task": t.get("user_task_id"), "kind": art.get("kind"), "path": art.get("path")})
    facts["recent_artifacts"] = facts["recent_artifacts"][:12]
    return facts


# === NoemaForge Autodoc Function Header ===
# Function: _decisions_from_tasks(tasks: List[Dict[str, Any]])
# Purpose: Implement the routine ' decisions from tasks'.
# Inputs:
#   - tasks: List[Dict[str, Any]]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - str, append, get
# Returns / emits: List[str]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - out, t
# === End NoemaForge Autodoc Function Header ===
def _decisions_from_tasks(tasks: List[Dict[str, Any]]) -> List[str]:
    out: List[str] = []
    for t in tasks:
        if str(t.get("status") or "") == "done":
            out.append(f"{t.get('title')}: выполнено")
        elif str(t.get("status") or "") == "running":
            out.append(f"{t.get('title')}: в работе")
    return out[:12]


# === NoemaForge Autodoc Function Header ===
# Function: _open_items_from_tasks(tasks: List[Dict[str, Any]])
# Purpose: Implement the routine ' open items from tasks'.
# Inputs:
#   - tasks: List[Dict[str, Any]]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - str, strip, append, get
# Returns / emits: List[str]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - out, t, ttl
# === End NoemaForge Autodoc Function Header ===
def _open_items_from_tasks(tasks: List[Dict[str, Any]]) -> List[str]:
    out: List[str] = []
    for t in tasks:
        if str(t.get("status") or "") not in ("done", "stopped"):
            ttl = str(t.get("title") or "").strip()
            if ttl:
                out.append(ttl)
    return out[:20]


# === NoemaForge Autodoc Function Header ===
# Function: extract_project(project_id: str, limit: int = 40)
# Purpose: Implement the routine 'extract project'.
# Inputs:
#   - project_id: str
#   - limit: int = 40
# Called by:
#   - src/dream_cycle.py
# Calls:
#   - list_user_tasks, list, _facts_from_tasks, _decisions_from_tasks, _open_items_from_tasks, append, _session_md_path, _ensure_parent, _connect_longterm, sorted, strip, open
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads or writes files
#   - opens a database or socket connection
#   - appends to logs or files
# Key locals:
#   - art, con, decisions, f, facts, item, lines, md, open_items, path, res, t
# === End NoemaForge Autodoc Function Header ===
def extract_project(project_id: str, *, limit: int = 40) -> Dict[str, Any]:
    res = task_tools.list_user_tasks(project_id=project_id, limit=limit)
    tasks = list(res.get("tasks") or [])
    facts = _facts_from_tasks(tasks)
    decisions = _decisions_from_tasks(tasks)
    open_items = _open_items_from_tasks(tasks)

    lines: List[str] = []
    lines.append(f"# Session Memory — {project_id}")
    lines.append("")
    lines.append(f"- Generated at: `{_nowz()}`")
    lines.append(f"- Tasks observed: `{len(tasks)}`")
    lines.append("")
    lines.append("## Facts")
    if facts["counts_by_status"]:
        for k, v in sorted(facts["counts_by_status"].items()):
            lines.append(f"- status `{k}`: {v}")
    else:
        lines.append("- no task facts yet")
    if facts["recent_artifacts"]:
        lines.append("")
        lines.append("## Recent artifacts")
        for art in facts["recent_artifacts"]:
            lines.append(f"- {art.get('kind')}: `{art.get('path')}`")
    lines.append("")
    lines.append("## Decisions / progress")
    if decisions:
        for item in decisions:
            lines.append(f"- {item}")
    else:
        lines.append("- no stable decisions captured yet")
    lines.append("")
    lines.append("## Open items")
    if open_items:
        for item in open_items:
            lines.append(f"- {item}")
    else:
        lines.append("- no open items")
    lines.append("")
    lines.append("## Recent tasks")
    for t in tasks[:15]:
        lines.append(f"- [{t.get('status')}] {t.get('title')} ({t.get('kind')})")
    md = "\n".join(lines).strip() + "\n"

    path = _session_md_path(project_id)
    _ensure_parent(path)
    with open(path, "w", encoding="utf-8") as f:
        f.write(md)

    con = _connect_longterm()
    try:
        con.execute(
            "INSERT OR REPLACE INTO session_summaries(summary_id, generated_at, project_id, source_count, path, facts_json, decisions_json, open_items_json) VALUES(?,?,?,?,?,?,?,?)",
            (
                f"{project_id}:latest",
                _nowz(),
                project_id,
                len(tasks),
                path,
                json.dumps(facts, ensure_ascii=False),
                json.dumps(decisions, ensure_ascii=False),
                json.dumps(open_items, ensure_ascii=False),
            ),
        )
        con.commit()
    finally:
        con.close()

    return {"ok": True, "project_id": project_id, "path": path, "facts": facts, "decisions": decisions, "open_items": open_items, "source_count": len(tasks)}


# === NoemaForge Autodoc Function Header ===
# Function: extract_all_projects(limit: int = 40)
# Purpose: Implement the routine 'extract all projects'.
# Inputs:
#   - limit: int = 40
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - list_user_tasks, list, sorted, append, len, get, strip, extract_project, str
# Returns / emits: Dict[str, Any]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - all_tasks, out, project_id, project_ids, res
# === End NoemaForge Autodoc Function Header ===
def extract_all_projects(limit: int = 40) -> Dict[str, Any]:
    res = task_tools.list_user_tasks(limit=500)
    all_tasks = list(res.get("tasks") or [])
    project_ids = sorted({str(t.get("project_id") or "").strip() for t in all_tasks if str(t.get("project_id") or "").strip()})
    out = []
    for project_id in project_ids:
        out.append(extract_project(project_id, limit=limit))
    return {"ok": True, "projects": out, "count": len(out)}


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
#   - src/dream_cycle.py
# Calls:
#   - ArgumentParser, add_argument, parse_args, print, extract_project, extract_all_projects, dumps
# Returns / emits: int
# Side effects:
#   - serializes structured data
# Key locals:
#   - ap, ns, out
# === End NoemaForge Autodoc Function Header ===
def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-id", default="")
    ap.add_argument("--limit", type=int, default=40)
    ns = ap.parse_args(argv)
    out = extract_project(ns.project_id, limit=ns.limit) if ns.project_id else extract_all_projects(limit=ns.limit)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
