#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/roadmap.py
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
# File: src/roadmap.py
# Purpose: Provide the module 'roadmap'.
# Invoked by / imported from:
#   - src/brainctl.py
#   - src/incidents.py
#   - src/maintenance.py
#   - src/scary_sweep.py
#   - src/sr_cycle.py
#   - src/ssr_cycle.py
#   - src/surgeon_auto.py
#   - src/toolproxy.py
# Public API / entry functions:
#   - load_role_roadmaps
#   - record_signal
#   - list_signals_since
#   - list_items
#   - export_report
# Inputs:
#   - Environment: NOEMAFORGE_ROADMAP_DB
#   - Common path inputs: /var/lib/noemaforge/roadmaps/roadmap.sqlite, /var/lib/noemaforge/roadmaps/exports
#   - Imports: __future__, datetime, json, os, sqlite3, uuid, typing, yaml
# Output formats / side effects:
#   - SQLite databases
#   - JSON files
#   - YAML files
#   - Markdown files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""roadmap.py (v0.12.7)

Roadmap aggregation + export.

Goal:
- Remove "magical" SR/SSR: development routes become explicit artifacts.
- Provide a simple queue where many streams/processes can request improvements,
  especially for Solution Architect (and other roles).
- Repetition increases priority: score depends on total events and unique sources.

This module is intentionally offline, local-first, and dependency-light.
"""


import datetime as dt
import json
import os
import sqlite3
import uuid
from typing import Any, Dict, List, Optional, Tuple

import yaml

DEFAULT_DB_PATH = os.environ.get("NOEMAFORGE_ROADMAP_DB", "/var/lib/noemaforge/roadmaps/roadmap.sqlite")
DEFAULT_EXPORT_DIR = "/var/lib/noemaforge/roadmaps/exports"


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
# Function: _connect(db_path: str = DEFAULT_DB_PATH)
# Purpose: Implement the routine ' connect'.
# Inputs:
#   - db_path: str = DEFAULT_DB_PATH
# Called by:
#   - src/casebase.py
#   - src/dream_cycle.py
#   - src/knowledge/store.py
#   - src/memory_system.py
#   - src/pipelines/finance_budget.py
#   - src/task_tools.py
#   - src/taskqueue.py
#   - src/vstore.py
# Calls:
#   - _ensure_parent, connect, execute, _init_schema
# Returns / emits: sqlite3.Connection
# Side effects:
#   - opens a database or socket connection
#   - executes SQL or shell-like commands
# Key locals:
#   - con
# === End NoemaForge Autodoc Function Header ===
def _connect(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    _ensure_parent(db_path)
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA synchronous=NORMAL;")
    _init_schema(con)
    return con


# === NoemaForge Autodoc Function Header ===
# Function: _init_schema(con: sqlite3.Connection)
# Purpose: Implement the routine ' init schema'.
# Inputs:
#   - con: sqlite3.Connection
# Called by:
#   - src/taskqueue.py
#   - tools/prep/scan_library.py
#   - tools/prep/scan_vault.py
# Calls:
#   - execute, commit
# Returns / emits: None
# Side effects:
#   - executes SQL or shell-like commands
# === End NoemaForge Autodoc Function Header ===
def _init_schema(con: sqlite3.Connection) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS signals (
          signal_id TEXT PRIMARY KEY,
          created_at TEXT NOT NULL,
          target_role TEXT NOT NULL,
          key TEXT NOT NULL,
          title TEXT,
          description TEXT,
          source_stream TEXT NOT NULL,
          source_role TEXT NOT NULL,
          project_id TEXT,
          run_id TEXT,
          process_id TEXT
        );
        """
    )
    con.execute("CREATE INDEX IF NOT EXISTS idx_signals_target_key ON signals(target_role, key);")
    con.execute("CREATE INDEX IF NOT EXISTS idx_signals_created_at ON signals(created_at);")
    con.commit()


# === NoemaForge Autodoc Function Header ===
# Function: load_role_roadmaps(epoch_dir: str)
# Purpose: Load role-roadmaps.yaml from an epoch directory.
# Inputs:
#   - epoch_dir: str
# Called by:
#   - src/surgeon_auto.py
# Calls:
#   - join, exists, open, safe_load
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads or writes files
# Key locals:
#   - f, path
# === End NoemaForge Autodoc Function Header ===
def load_role_roadmaps(epoch_dir: str) -> Dict[str, Any]:
    """Load role-roadmaps.yaml from an epoch directory."""
    path = os.path.join(epoch_dir, "role-roadmaps.yaml")
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# === NoemaForge Autodoc Function Header ===
# Function: _priority_model(roadmaps_obj: Dict[str, Any])
# Purpose: Implement the routine ' priority model'.
# Inputs:
#   - roadmaps_obj: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - float, get
# Returns / emits: Dict[str, float]
# Key locals:
#   - base, d, repeat_w, uniq_w
# === End NoemaForge Autodoc Function Header ===
def _priority_model(roadmaps_obj: Dict[str, Any]) -> Dict[str, float]:
    d = (roadmaps_obj.get("defaults") or {}).get("priority_model") or {}
    base = float(d.get("base") or 0.0)
    repeat_w = float(d.get("repeat_weight") or 1.0)
    uniq_w = float(d.get("unique_source_weight") or 5.0)
    return {"base": base, "repeat_weight": repeat_w, "unique_source_weight": uniq_w}


# === NoemaForge Autodoc Function Header ===
# Function: record_signal(target_role: str, key: str, requested_by: Dict[str, Any], title: str = '', description: str = '', db_path: str = DEFAULT_DB_PATH)
# Purpose: Append a roadmap signal. Repetition increases priority via aggregation.
# Inputs:
#   - target_role: str
#   - key: str
#   - requested_by: Dict[str, Any]
#   - title: str = ''
#   - description: str = ''
#   - db_path: str = DEFAULT_DB_PATH
# Called by:
#   - src/brainctl.py
#   - src/scary_sweep.py
#   - src/sr_cycle.py
#   - src/ssr_cycle.py
#   - src/toolproxy.py
# Calls:
#   - str, _connect, execute, commit, close, _nowz, strip, ValueError, uuid4, get
# Returns / emits: Dict[str, Any]
# Side effects:
#   - opens a database or socket connection
#   - executes SQL or shell-like commands
# Key locals:
#   - con, process_id, project_id, run_id, sig, src_role, src_stream
# === End NoemaForge Autodoc Function Header ===
def record_signal(
    *,
    target_role: str,
    key: str,
    requested_by: Dict[str, Any],
    title: str = "",
    description: str = "",
    db_path: str = DEFAULT_DB_PATH,
) -> Dict[str, Any]:
    """Append a roadmap signal. Repetition increases priority via aggregation."""
    sig = {
        "schema_version": "v1",
        "signal_id": uuid.uuid4().hex,
        "created_at": _nowz(),
        "target_role": str(target_role).strip() or "solution_architect",
        "key": str(key).strip(),
        "title": str(title).strip(),
        "description": str(description).strip(),
        "requested_by": requested_by or {},
    }
    if not sig["key"]:
        raise ValueError("missing_key")

    src_stream = str((requested_by or {}).get("stream_id") or "unknown")
    src_role = str((requested_by or {}).get("role") or "unknown")
    project_id = str((requested_by or {}).get("project_id") or "")
    run_id = str((requested_by or {}).get("run_id") or "")
    process_id = str((requested_by or {}).get("process_id") or "")

    con = _connect(db_path)
    con.execute(
        """
        INSERT INTO signals(signal_id, created_at, target_role, key, title, description, source_stream, source_role, project_id, run_id, process_id)
        VALUES(?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            sig["signal_id"],
            sig["created_at"],
            sig["target_role"],
            sig["key"],
            sig["title"],
            sig["description"],
            src_stream,
            src_role,
            project_id,
            run_id,
            process_id,
        ),
    )
    con.commit()
    con.close()
    return sig


# === NoemaForge Autodoc Function Header ===
# Function: list_signals_since(since_ts: str, limit: int = 500, target_roles: Optional[List[str]] = None, db_path: str = DEFAULT_DB_PATH)
# Purpose: Return raw roadmap signals since a timestamp.
# Inputs:
#   - since_ts: str
#   - limit: int = 500
#   - target_roles: Optional[List[str]] = None
#   - db_path: str = DEFAULT_DB_PATH
# Called by:
#   - src/maintenance.py
# Calls:
#   - strip, max, _connect, min, close, append, str, int, join, fetchall, len, execute
# Returns / emits: Dict[str, Any]
# Side effects:
#   - opens a database or socket connection
#   - executes SQL or shell-like commands
#   - appends to logs or files
# Key locals:
#   - con, lim, newest, qs, r, roles, rows, sigs, since
# === End NoemaForge Autodoc Function Header ===
def list_signals_since(
    *,
    since_ts: str,
    limit: int = 500,
    target_roles: Optional[List[str]] = None,
    db_path: str = DEFAULT_DB_PATH,
) -> Dict[str, Any]:
    """Return raw roadmap signals since a timestamp.

    Why this exists:
    - SR/SSR write signals into the roadmap DB.
    - Other spine modules (Incidents, ToolProxy) can also write signals.
    - Maintenance needs a cursor-based way to translate *new* signals into
      executable TaskQueue items without replaying the entire history.

    Notes:
    - created_at is ISO-8601 Z; lexical order matches chronological order.
    - This returns raw events (not aggregated priority items).
    """

    since = str(since_ts or "").strip()
    if not since:
        # Safe default: treat as "very old".
        since = "1970-01-01T00:00:00Z"

    lim = max(1, min(int(limit or 500), 5000))
    roles = [str(r).strip() for r in (target_roles or []) if str(r).strip()]

    con = _connect(db_path)
    try:
        if roles:
            qs = ",".join(["?"] * len(roles))
            rows = con.execute(
                f"""
                SELECT signal_id, created_at, target_role, key, title, description,
                       source_stream, source_role, project_id, run_id, process_id
                FROM signals
                WHERE created_at > ? AND target_role IN ({qs})
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (since, *roles, lim),
            ).fetchall()
        else:
            rows = con.execute(
                """
                SELECT signal_id, created_at, target_role, key, title, description,
                       source_stream, source_role, project_id, run_id, process_id
                FROM signals
                WHERE created_at > ?
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (since, lim),
            ).fetchall()
    finally:
        con.close()

    sigs: List[Dict[str, Any]] = []
    for r in rows:
        sigs.append(
            {
                "signal_id": str(r[0] or ""),
                "created_at": str(r[1] or ""),
                "target_role": str(r[2] or ""),
                "key": str(r[3] or ""),
                "title": str(r[4] or ""),
                "description": str(r[5] or ""),
                "source_stream": str(r[6] or ""),
                "source_role": str(r[7] or ""),
                "project_id": str(r[8] or ""),
                "run_id": str(r[9] or ""),
                "process_id": str(r[10] or ""),
            }
        )

    newest = sigs[-1]["created_at"] if sigs else since
    return {"ok": True, "since": since, "newest": newest, "signals": sigs}


# === NoemaForge Autodoc Function Header ===
# Function: list_items(epoch_dir: str, target_role: Optional[str] = None, limit: int = 50, db_path: str = DEFAULT_DB_PATH)
# Purpose: Return prioritized roadmap items (aggregated).
# Inputs:
#   - epoch_dir: str
#   - target_role: Optional[str] = None
#   - limit: int = 50
#   - db_path: str = DEFAULT_DB_PATH
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - strip, _connect, close, _priority_model, sort, fetchall, load_role_roadmaps, append, execute, float, str, int
# Returns / emits: Dict[str, Any]
# Side effects:
#   - opens a database or socket connection
#   - executes SQL or shell-like commands
#   - appends to logs or files
# Key locals:
#   - con, items, pm, rm, role, rows, score
# === End NoemaForge Autodoc Function Header ===
def list_items(
    *,
    epoch_dir: str,
    target_role: Optional[str] = None,
    limit: int = 50,
    db_path: str = DEFAULT_DB_PATH,
) -> Dict[str, Any]:
    """Return prioritized roadmap items (aggregated)."""
    role = (target_role or "").strip()
    con = _connect(db_path)
    if role:
        rows = con.execute(
            """
            SELECT target_role, key,
                   MAX(COALESCE(title,'')) AS title,
                   COUNT(*) AS total_events,
                   COUNT(DISTINCT COALESCE(source_stream,'') || '|' || COALESCE(project_id,'')) AS unique_sources,
                   MAX(created_at) AS last_seen
            FROM signals
            WHERE target_role=?
            GROUP BY target_role, key
            """,
            (role,),
        ).fetchall()
    else:
        rows = con.execute(
            """
            SELECT target_role, key,
                   MAX(COALESCE(title,'')) AS title,
                   COUNT(*) AS total_events,
                   COUNT(DISTINCT COALESCE(source_stream,'') || '|' || COALESCE(project_id,'')) AS unique_sources,
                   MAX(created_at) AS last_seen
            FROM signals
            GROUP BY target_role, key
            """
        ).fetchall()
    con.close()

    rm = load_role_roadmaps(epoch_dir) or {}
    pm = _priority_model(rm)

    items: List[Dict[str, Any]] = []
    for (trole, key, title, total, uniq, last_seen) in rows:
        score = pm["base"] + pm["repeat_weight"] * float(total) + pm["unique_source_weight"] * float(uniq)
        items.append(
            {
                "target_role": str(trole),
                "key": str(key),
                "title": str(title or ""),
                "total_events": int(total or 0),
                "unique_sources": int(uniq or 0),
                "last_seen": str(last_seen or ""),
                "score": float(score),
            }
        )

    items.sort(key=lambda x: (x["score"], x["unique_sources"], x["total_events"], x["last_seen"]), reverse=True)
    return {"ok": True, "items": items[: max(1, int(limit))], "priority_model": pm}


# === NoemaForge Autodoc Function Header ===
# Function: export_report(epoch_dir: str, target_role: Optional[str] = None, include_role_roadmaps: bool = True, limit: int = 100, export_dir: str = DEFAULT_EXPORT_DIR, db_path: str = DEFAULT_DB_PATH)
# Purpose: Generate a RoadmapReport artifact.
# Inputs:
#   - epoch_dir: str
#   - target_role: Optional[str] = None
#   - include_role_roadmaps: bool = True
#   - limit: int = 100
#   - export_dir: str = DEFAULT_EXPORT_DIR
#   - db_path: str = DEFAULT_DB_PATH
# Called by:
#   - src/scary_sweep.py
#   - src/sr_cycle.py
#   - src/ssr_cycle.py
#   - src/surgeon_auto.py
# Calls:
#   - makedirs, _nowz, list_items, join, replace, append, enumerate, uuid4, get, load_role_roadmaps, bool, open
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads or writes files
#   - creates directories
#   - appends to logs or files
# Key locals:
#   - created_at, f, items, lines, listing, obj, p_json, p_md, report_id, rm
# === End NoemaForge Autodoc Function Header ===
def export_report(
    *,
    epoch_dir: str,
    target_role: Optional[str] = None,
    include_role_roadmaps: bool = True,
    limit: int = 100,
    export_dir: str = DEFAULT_EXPORT_DIR,
    db_path: str = DEFAULT_DB_PATH,
) -> Dict[str, Any]:
    """Generate a RoadmapReport artifact."""
    os.makedirs(export_dir, exist_ok=True)
    report_id = uuid.uuid4().hex
    created_at = _nowz()

    listing = list_items(epoch_dir=epoch_dir, target_role=target_role, limit=limit, db_path=db_path)
    items = listing.get("items") or []

    rm = load_role_roadmaps(epoch_dir) if include_role_roadmaps else {}
    obj: Dict[str, Any] = {
        "schema_version": "v1",
        "report_id": report_id,
        "created_at": created_at,
        "generated_by": {"subsystem": "roadmap", "epoch_dir": epoch_dir},
        "role_roadmaps_included": bool(include_role_roadmaps),
        "target_role": (target_role or "").strip() or "",
        "priority_model": listing.get("priority_model") or {},
        "items": items,
    }
    if include_role_roadmaps:
        obj["role_roadmaps"] = rm

    # Write JSON + a small Markdown summary.
    p_json = os.path.join(export_dir, f"roadmap_report_{created_at.replace(':','').replace('.','')}_{report_id}.json")
    with open(p_json, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

    p_md = p_json.replace(".json", ".md")
    lines = []
    lines.append(f"# Roadmap report\n")
    lines.append(f"- created_at: {created_at}\n- target_role: {obj.get('target_role') or 'ALL'}\n")
    lines.append("\n## Top items\n")
    for i, it in enumerate(items[: min(len(items), 25)], 1):
        lines.append(f"{i}. **{it.get('target_role')}** :: `{it.get('key')}` (score={it.get('score'):.1f}, uniq={it.get('unique_sources')}, total={it.get('total_events')})\n")
        if it.get("title"):
            lines.append(f"   - {it.get('title')}\n")
    with open(p_md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return {"ok": True, "report_path": p_json, "markdown_path": p_md, "report_id": report_id, "created_at": created_at}
