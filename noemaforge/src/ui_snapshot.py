#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/ui_snapshot.py
Zone: release/package
Version: 0.31.13.alpha
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
# File: src/ui_snapshot.py
# Purpose: Provide the module 'ui_snapshot'.
# Invoked by / imported from:
#   - src/brainui.py
# Public API / entry functions:
#   - resolve_paths
#   - load_taskqueue
#   - load_projects
#   - load_sel_events
#   - load_telemetry
#   - load_inboxes
#   - load_user_tasks
#   - load_notifications
#   - load_memory
#   - load_worktrees
#   - load_skills
#   - build_snapshot
# Inputs:
#   - Environment: NOEMAFORGE_INBOX_CACHE_TTL_SEC
#   - Common path inputs: noemaforge.ui.snapshot/v1, /var/lib/noemaforge, /var/lib/noemaforge/taskqueue/taskqueue.sqlite, /var/lib/noemaforge/sel/segments, /var/lib/noemaforge/telemetry, /var/lib/noemaforge/projects
#   - Imports: __future__, datetime, glob, json, os, sqlite3, typing, yaml
# Output formats / side effects:
#   - SQLite databases
#   - JSON files
#   - YAML files
#   - Markdown files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""ui_snapshot.py (v0.25.1)

Builds a *safe*, read-only runtime snapshot for UI visualization.

Why this exists
--------------
NoemaForge has several "truth sources":
  - runtime_state.json (idle/auto-cycle state machine)
  - TaskQueue (sqlite)
  - projects/* (team batons + wakeq + roster)
  - SEL/WORM (security + orchestration events)
  - telemetry (metadata-only LLM/tool call traces)

Common multi-agent orchestration stacks expose a live view of:
  - what's running now
  - what's next
  - what happened recently (trace)

This module produces exactly that *without* requiring the rest of the NoemaForge
runtime to be up, and without importing Linux-only modules at import time.

Cross-platform note
-------------------
This module is designed to run on Windows as a "lab viewer" as well.
It avoids importing linux-only modules (fcntl, systemd, etc.).
"""


import datetime as dt
import glob
import json
import os
import sqlite3
from typing import Any, Dict, List, Optional


try:  # pragma: no cover
    import yaml
except Exception:  # pragma: no cover
    yaml = None  # type: ignore

try:  # pragma: no cover
    import profile_manager
except Exception:  # pragma: no cover
    profile_manager = None  # type: ignore


SCHEMA = "noemaforge.ui.snapshot/v1"

# Inbox snapshot caching: avoid rescanning inbox trees on every UI poll.
INBOX_CACHE_TTL_SEC = float(os.environ.get("NOEMAFORGE_INBOX_CACHE_TTL_SEC", "10"))
_INBOX_CACHE: Dict[str, Any] = {"ts": 0.0, "state_root": "", "data": None}


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
# Function: _safe_load_yaml(path: str)
# Purpose: Implement the routine ' safe load yaml'.
# Inputs:
#   - path: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - open, isinstance, safe_load
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads or writes files
# Key locals:
#   - f, obj
# === End NoemaForge Autodoc Function Header ===
def _safe_load_yaml(path: str) -> Dict[str, Any]:
    if yaml is None:
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = yaml.safe_load(f) or {}
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


# === NoemaForge Autodoc Function Header ===
# Function: _safe_load_json(path: str)
# Purpose: Implement the routine ' safe load json'.
# Inputs:
#   - path: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - open, load, isinstance
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads or writes files
# Key locals:
#   - f, obj
# === End NoemaForge Autodoc Function Header ===
def _safe_load_json(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


# === NoemaForge Autodoc Function Header ===
# Function: _tail_lines(path: str, max_lines: int = 200)
# Purpose: Read last N lines efficiently-ish (good enough for JSONL logs).
# Inputs:
#   - path: str
#   - max_lines: int = 200
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - open, seek, tell, splitlines, append, count, read, decode, str
# Returns / emits: List[str]
# Side effects:
#   - reads or writes files
#   - appends to logs or files
# Key locals:
#   - block, data, f, lines, ln, out, pos, read, size
# === End NoemaForge Autodoc Function Header ===
def _tail_lines(path: str, max_lines: int = 200) -> List[str]:
    """Read last N lines efficiently-ish (good enough for JSONL logs)."""
    if max_lines <= 0:
        return []
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            block = 64 * 1024
            data = b""
            pos = size
            while pos > 0 and data.count(b"\n") <= max_lines + 1:
                read = block if pos >= block else pos
                pos -= read
                f.seek(pos)
                data = f.read(read) + data
            lines = data.splitlines()[-max_lines:]
        out = []
        for ln in lines:
            try:
                out.append(ln.decode("utf-8", errors="replace"))
            except Exception:
                out.append(str(ln))
        return out
    except Exception:
        return []


# === NoemaForge Autodoc Function Header ===
# Function: _posix_to_host_path(state_root: str, p: str)
# Purpose: Map canonical NoemaForge POSIX paths into a host-local state_root.
# Inputs:
#   - state_root: str
#   - p: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - strip, startswith, lstrip, join, isabs, str, split, len
# Returns / emits: str
# Key locals:
#   - p, parts, rel
# === End NoemaForge Autodoc Function Header ===
def _posix_to_host_path(state_root: str, p: str) -> str:
    """Map canonical NoemaForge POSIX paths into a host-local state_root.

    NoemaForge uses /var/lib/noemaforge as canonical "state root".
    For lab/dev the user may point to a copied directory (e.g., Windows path).
    We remap only when the path begins with /var/lib/noemaforge.
    """
    p = str(p or "").strip()
    if not p:
        return p
    if p.startswith("/var/lib/noemaforge"):
        rel = p[len("/var/lib/noemaforge") :].lstrip("/")
        parts = [x for x in rel.split("/") if x]
        return os.path.join(state_root, *parts)
    if not os.path.isabs(p):
        return os.path.join(state_root, p)
    return p


# === NoemaForge Autodoc Function Header ===
# Function: resolve_paths(state_root: str, configs_dir: str)
# Purpose: Resolve key storage paths using configs + state_root mapping.
# Inputs:
#   - state_root: str
#   - configs_dir: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - abspath, join, _safe_load_yaml, str, _posix_to_host_path, isinstance, get
# Returns / emits: Dict[str, str]
# Key locals:
#   - base, configs_dir, files, llm_calls, obs_pol, projects_dir, runtime_state_path, sel_segments_dir, st, state_root, taskqueue_db, tele_base
# === End NoemaForge Autodoc Function Header ===
def resolve_paths(*, state_root: str, configs_dir: str) -> Dict[str, str]:
    """Resolve key storage paths using configs + state_root mapping."""
    state_root = os.path.abspath(state_root)
    configs_dir = os.path.abspath(configs_dir)

    runtime_state_path = os.path.join(state_root, ".sys", "runtime_state.json")

    # TaskQueue DB
    tq_pol = _safe_load_yaml(os.path.join(configs_dir, "taskqueue-policy.yaml"))
    tq_sql = tq_pol.get("sqlite") if isinstance(tq_pol.get("sqlite"), dict) else {}
    tq_db = str((tq_sql or {}).get("path") or "/var/lib/noemaforge/taskqueue/taskqueue.sqlite")
    taskqueue_db = _posix_to_host_path(state_root, tq_db)

    # SEL/WORM segments
    sel_segments_dir = _posix_to_host_path(state_root, "/var/lib/noemaforge/sel/segments")

    # Telemetry
    obs_pol = _safe_load_yaml(os.path.join(configs_dir, "observability-policy.yaml"))
    st = obs_pol.get("storage") if isinstance(obs_pol.get("storage"), dict) else {}
    base = str((st or {}).get("base_dir") or "/var/lib/noemaforge/telemetry")
    tele_base = _posix_to_host_path(state_root, base)
    files = (st or {}).get("files") if isinstance((st or {}).get("files"), dict) else {}
    llm_calls = os.path.join(tele_base, str((files or {}).get("llm_calls") or "llm_calls.jsonl"))
    tool_calls = os.path.join(tele_base, str((files or {}).get("tool_calls") or "tool_calls.jsonl"))

    projects_dir = _posix_to_host_path(state_root, "/var/lib/noemaforge/projects")

    return {
        "state_root": state_root,
        "configs_dir": configs_dir,
        "runtime_state": runtime_state_path,
        "taskqueue_db": taskqueue_db,
        "sel_segments_dir": sel_segments_dir,
        "telemetry_llm_calls": llm_calls,
        "telemetry_tool_calls": tool_calls,
        "projects_dir": projects_dir,
        "library_dir": os.path.join(state_root, "Library"),
        "vault_dir": os.path.join(state_root, "Vault"),
        "workspace_dir": os.path.join(state_root, "Workspace"),
        "library_inbox": os.path.join(state_root, "Library", "inbox"),
        "vault_inbox": os.path.join(state_root, "Vault", "inbox"),
        "workspace_inbox": os.path.join(state_root, "Workspace", "inbox"),
    }


# === NoemaForge Autodoc Function Header ===
# Function: _load_runtime_state(path: str)
# Purpose: Implement the routine ' load runtime state'.
# Inputs:
#   - path: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _safe_load_json, exists, get
# Returns / emits: Optional[Dict[str, Any]]
# Key locals:
#   - k, keep, obj, out
# === End NoemaForge Autodoc Function Header ===
def _load_runtime_state(path: str) -> Optional[Dict[str, Any]]:
    if not os.path.exists(path):
        return None
    obj = _safe_load_json(path)
    if not obj:
        return None
    keep = {
        "schema_version",
        "state",
        "last_activity_ts",
        "last_activity_domain",
        "last_activity_actor",
        "idle_armed_ts",
        "idle_trigger_sec",
        "idle_triggered_ts",
        "auto_cycle_active",
        "auto_cycle_started_ts",
        "auto_cycle_last_step_ts",
        "auto_cycle_steps",
        "auto_cycle_last_sr_ts",
        "auto_cycle_reason",
        "note",
        "last_error",
    }
    out: Dict[str, Any] = {}
    for k in keep:
        if k in obj:
            out[k] = obj.get(k)
    return out


# === NoemaForge Autodoc Function Header ===
# Function: _tq_connect(db_path: str)
# Purpose: Implement the routine ' tq connect'.
# Inputs:
#   - db_path: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - connect, exists
# Returns / emits: Optional[sqlite3.Connection]
# Side effects:
#   - opens a database or socket connection
# Key locals:
#   - con
# === End NoemaForge Autodoc Function Header ===
def _tq_connect(db_path: str) -> Optional[sqlite3.Connection]:
    if not db_path or not os.path.exists(db_path):
        return None
    try:
        con = sqlite3.connect(db_path)
        con.row_factory = sqlite3.Row
        return con
    except Exception:
        return None


# === NoemaForge Autodoc Function Header ===
# Function: _tq_summary(con: sqlite3.Connection)
# Purpose: Implement the routine ' tq summary'.
# Inputs:
#   - con: sqlite3.Connection
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - fetchall, upper, int, execute, str
# Returns / emits: Dict[str, int]
# Side effects:
#   - executes SQL or shell-like commands
# Key locals:
#   - out, r, rows, st
# === End NoemaForge Autodoc Function Header ===
def _tq_summary(con: sqlite3.Connection) -> Dict[str, int]:
    out = {"TODO": 0, "IN_PROGRESS": 0, "DONE": 0, "DEADLETTER": 0}
    try:
        rows = con.execute("SELECT status, COUNT(*) as n FROM tasks GROUP BY status").fetchall()
        for r in rows:
            st = str(r[0] or "").upper()
            out[st] = int(r[1] or 0)
    except Exception:
        pass
    return out


# === NoemaForge Autodoc Function Header ===
# Function: _tq_pick_fields(r: sqlite3.Row)
# Purpose: Implement the routine ' tq pick fields'.
# Inputs:
#   - r: sqlite3.Row
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - keys
# Returns / emits: Dict[str, Any]
# Key locals:
#   - fields, k, out
# === End NoemaForge Autodoc Function Header ===
def _tq_pick_fields(r: sqlite3.Row) -> Dict[str, Any]:
    fields = [
        "task_id",
        "created_at",
        "updated_at",
        "domain",
        "priority_class",
        "prio_index",
        "status",
        "kind",
        "module",
        "title",
        "group_key",
        "repeats",
        "attempts",
        "claimed_by",
        "claimed_at",
        "lease_until",
        "last_error",
    ]
    out: Dict[str, Any] = {}
    for k in fields:
        if k in r.keys():
            out[k] = r[k]
    return out


# === NoemaForge Autodoc Function Header ===
# Function: _tq_fetch(con: sqlite3.Connection, status: str, limit: int, order_sql: str)
# Purpose: Implement the routine ' tq fetch'.
# Inputs:
#   - con: sqlite3.Connection
#   - status: str
#   - limit: int
#   - order_sql: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - fetchall, _tq_pick_fields, execute, upper, max, int
# Returns / emits: List[Dict[str, Any]]
# Side effects:
#   - executes SQL or shell-like commands
# Key locals:
#   - rows
# === End NoemaForge Autodoc Function Header ===
def _tq_fetch(con: sqlite3.Connection, *, status: str, limit: int, order_sql: str) -> List[Dict[str, Any]]:
    try:
        rows = con.execute(
            f"""
            SELECT task_id, created_at, updated_at, domain, priority_class, prio_index, status, kind,
                   module, title, group_key, repeats, attempts, claimed_by, claimed_at, lease_until, last_error
            FROM tasks
            WHERE status=?
            ORDER BY {order_sql}
            LIMIT ?
            """,
            (status.upper(), max(1, int(limit))),
        ).fetchall()
        return [_tq_pick_fields(r) for r in rows]
    except Exception:
        return []


# === NoemaForge Autodoc Function Header ===
# Function: load_taskqueue(db_path: str)
# Purpose: Implement the routine 'load taskqueue'.
# Inputs:
#   - db_path: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _tq_connect, _tq_summary, _tq_fetch, close
# Returns / emits: Dict[str, Any]
# Side effects:
#   - opens a database or socket connection
# Key locals:
#   - con, current, deadletters, next_tasks, recent_done, summary
# === End NoemaForge Autodoc Function Header ===
def load_taskqueue(db_path: str) -> Dict[str, Any]:
    con = _tq_connect(db_path)
    if con is None:
        return {
            "db_path": db_path,
            "available": False,
            "summary": {},
            "current": None,
            "next": [],
            "recent_done": [],
            "deadletters": [],
        }
    try:
        summary = _tq_summary(con)
        current = _tq_fetch(con, status="IN_PROGRESS", limit=5, order_sql="claimed_at DESC, created_at DESC")
        next_tasks = _tq_fetch(con, status="TODO", limit=20, order_sql="prio_index ASC, created_at ASC")
        recent_done = _tq_fetch(con, status="DONE", limit=20, order_sql="updated_at DESC")
        deadletters = _tq_fetch(con, status="DEADLETTER", limit=20, order_sql="updated_at DESC")
        return {
            "db_path": db_path,
            "available": True,
            "summary": summary,
            "current": current[0] if current else None,
            "in_progress": current,
            "next": next_tasks,
            "recent_done": recent_done,
            "deadletters": deadletters,
        }
    finally:
        try:
            con.close()
        except Exception:
            pass


# === NoemaForge Autodoc Function Header ===
# Function: _project_dirs(projects_dir: str)
# Purpose: Implement the routine ' project dirs'.
# Inputs:
#   - projects_dir: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - sorted, isdir, glob, join, append
# Returns / emits: List[str]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - out, p
# === End NoemaForge Autodoc Function Header ===
def _project_dirs(projects_dir: str) -> List[str]:
    if not os.path.isdir(projects_dir):
        return []
    out: List[str] = []
    for p in sorted(glob.glob(os.path.join(projects_dir, "*"))):
        if os.path.isdir(p):
            out.append(p)
    return out


# === NoemaForge Autodoc Function Header ===
# Function: _count_backlog(backlog: Dict[str, Any])
# Purpose: Implement the routine ' count backlog'.
# Inputs:
#   - backlog: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - isinstance, get, lower, strip, str
# Returns / emits: Dict[str, Any]
# Key locals:
#   - it, items, next_item, s, st
# === End NoemaForge Autodoc Function Header ===
def _count_backlog(backlog: Dict[str, Any]) -> Dict[str, Any]:
    items = backlog.get("items") if isinstance(backlog.get("items"), list) else []
    st = {"todo": 0, "doing": 0, "done": 0, "other": 0}
    next_item = None
    for it in items:
        if not isinstance(it, dict):
            continue
        s = str(it.get("status") or "").strip().lower()
        if s in st:
            st[s] += 1
        else:
            st["other"] += 1
        if next_item is None and s == "todo":
            next_item = {
                "id": it.get("id"),
                "title": it.get("title"),
                "priority_class": it.get("priority_class"),
                "assigned_role": it.get("assigned_role"),
            }
    return {"counts": st, "next": next_item}


# === NoemaForge Autodoc Function Header ===
# Function: _read_wake(path: str)
# Purpose: Implement the routine ' read wake'.
# Inputs:
#   - path: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _safe_load_json, isinstance, get
# Returns / emits: Dict[str, Any]
# Key locals:
#   - baton, k, keep, obj, out
# === End NoemaForge Autodoc Function Header ===
def _read_wake(path: str) -> Dict[str, Any]:
    obj = _safe_load_json(path)
    if not obj:
        return {"path": path}
    keep = {
        "wake_id",
        "ts",
        "project_id",
        "from_role",
        "to_role",
        "baton_id",
        "stream_id",
    }
    out: Dict[str, Any] = {"path": path}
    for k in keep:
        if k in obj:
            out[k] = obj.get(k)
    baton = obj.get("baton") if isinstance(obj.get("baton"), dict) else {}
    if baton:
        for k in ("task_id", "objective", "priority_class"):
            if k in baton:
                out[k] = baton.get(k)
    return out


# === NoemaForge Autodoc Function Header ===
# Function: load_projects(projects_dir: str, configs_dir: str)
# Purpose: Implement the routine 'load projects'.
# Inputs:
#   - projects_dir: str
#   - configs_dir: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _safe_load_yaml, isinstance, _project_dirs, sort, join, strip, get, basename, str, _count_backlog, _safe_load_json, append
# Returns / emits: Dict[str, Any]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - active, ar, backlog, backlog_sum, cursor, default_stream, flow, flow_cat, flows, items, lease_until, n
# === End NoemaForge Autodoc Function Header ===
def load_projects(*, projects_dir: str, configs_dir: str) -> Dict[str, Any]:
    streams = _safe_load_yaml(os.path.join(configs_dir, "streams.yaml"))
    default_stream = ""
    if isinstance(streams, dict):
        default_stream = str(streams.get("default_stream") or "").strip()

    flow_cat = _safe_load_yaml(os.path.join(configs_dir, "flow-catalog.yaml"))
    flows = flow_cat.get("flows") if isinstance(flow_cat.get("flows"), dict) else {}

    items: List[Dict[str, Any]] = []
    for pd in _project_dirs(projects_dir):
        pid = os.path.basename(pd)
        proj = _safe_load_yaml(os.path.join(pd, "project.yaml"))
        title = str(proj.get("title") or "")
        status = str(proj.get("status") or "")
        try:
            prio = int(proj.get("priority") or 0)
        except Exception:
            prio = 0

        stream_id = str(proj.get("default_stream") or "").strip() or default_stream

        backlog = _safe_load_yaml(os.path.join(pd, "backlog.yaml"))
        backlog_sum = _count_backlog(backlog)

        team_dir = os.path.join(pd, "team")
        roster = _safe_load_yaml(os.path.join(team_dir, "roster.yaml"))
        roles = []
        if isinstance(roster.get("roles"), list):
            for r in roster.get("roles"):
                if isinstance(r, dict) and r.get("id"):
                    roles.append({"id": str(r.get("id")), "route": r.get("route"), "description": r.get("description")})

        semaphore = _safe_load_json(os.path.join(team_dir, "semaphore.json"))
        active = semaphore.get("active") if isinstance(semaphore.get("active"), dict) else None
        lease_until = semaphore.get("lease_until")

        wakeq = os.path.join(team_dir, "wakeq")
        pending = sorted(glob.glob(os.path.join(wakeq, "*.json"))) if os.path.isdir(wakeq) else []
        next_wake = _read_wake(pending[0]) if pending else None

        flow = flows.get(stream_id) if isinstance(flows, dict) else None
        nodes = []
        if isinstance(flow, dict) and isinstance(flow.get("nodes"), list):
            for n in flow.get("nodes"):
                if isinstance(n, dict) and n.get("id") and n.get("role"):
                    nodes.append({"id": n.get("id"), "role": n.get("role"), "expandable": bool(n.get("expandable"))})

        cursor = None
        if active and isinstance(active, dict):
            ar = str(active.get("role_id") or "")
            if ar and nodes:
                for i, n in enumerate(nodes):
                    if str(n.get("role") or "") == ar or str(n.get("id") or "") == ar:
                        cursor = {"index": i, "role": ar}
                        break

        items.append(
            {
                "project_id": pid,
                "title": title,
                "status": status,
                "priority": prio,
                "stream_id": stream_id,
                "backlog": backlog_sum,
                "team": {
                    "roles": roles,
                    "semaphore": {"active": active, "lease_until": lease_until},
                    "wakeq": {"pending": len(pending), "next": next_wake},
                },
                "flow": {"nodes": nodes, "cursor": cursor, "description": (flow or {}).get("description") if isinstance(flow, dict) else ""},
            }
        )

    items.sort(key=lambda x: (int(x.get("priority") or 0), str(x.get("project_id") or "")))
    return {"count": len(items), "items": items}


# === NoemaForge Autodoc Function Header ===
# Function: load_sel_events(sel_segments_dir: str, limit: int = 50)
# Purpose: Implement the routine 'load sel events'.
# Inputs:
#   - sel_segments_dir: str
#   - limit: int = 50
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - sorted, reversed, list, isdir, glob, join, _tail_lines, len, loads, isinstance, append, get
# Returns / emits: Dict[str, Any]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - ln, obj, recent, seg, segs
# === End NoemaForge Autodoc Function Header ===
def load_sel_events(sel_segments_dir: str, limit: int = 50) -> Dict[str, Any]:
    if not os.path.isdir(sel_segments_dir):
        return {"available": False, "recent": []}

    segs = sorted(glob.glob(os.path.join(sel_segments_dir, "*.jsonl")))
    if not segs:
        return {"available": False, "recent": []}

    recent: List[Dict[str, Any]] = []
    for seg in reversed(segs[-7:]):
        for ln in reversed(_tail_lines(seg, max_lines=400)):
            try:
                obj = json.loads(ln)
                if isinstance(obj, dict):
                    recent.append(
                        {
                            "ts": obj.get("ts"),
                            "severity": obj.get("severity"),
                            "type": obj.get("type") or obj.get("event_type"),
                            "decision": obj.get("decision"),
                            "actor": obj.get("actor"),
                            "trace_id": obj.get("trace_id"),
                        }
                    )
            except Exception:
                continue
            if len(recent) >= limit:
                break
        if len(recent) >= limit:
            break

    recent = list(reversed(recent))
    return {"available": True, "recent": recent, "segments_dir": sel_segments_dir}


# === NoemaForge Autodoc Function Header ===
# Function: load_telemetry(llm_calls_path: str, limit: int = 50)
# Purpose: Implement the routine 'load telemetry'.
# Inputs:
#   - llm_calls_path: str
#   - limit: int = 50
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - reversed, list, _tail_lines, exists, loads, append, len, isinstance, get
# Returns / emits: Dict[str, Any]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - ln, obj, recent
# === End NoemaForge Autodoc Function Header ===
def load_telemetry(llm_calls_path: str, limit: int = 50) -> Dict[str, Any]:
    if not llm_calls_path or not os.path.exists(llm_calls_path):
        return {"available": False, "recent_llm_calls": []}
    recent: List[Dict[str, Any]] = []
    for ln in reversed(_tail_lines(llm_calls_path, max_lines=400)):
        try:
            obj = json.loads(ln)
            if not isinstance(obj, dict):
                continue
            recent.append(
                {
                    "ts": obj.get("ts"),
                    "kind": obj.get("kind"),
                    "actor": obj.get("actor"),
                    "trace_id": obj.get("trace_id"),
                    "model": obj.get("model"),
                    "latency_ms": obj.get("latency_ms"),
                    "usage": obj.get("usage"),
                    "input_hash": obj.get("input_hash"),
                    "output_hash": obj.get("output_hash"),
                }
            )
        except Exception:
            continue
        if len(recent) >= limit:
            break
    recent = list(reversed(recent))
    return {"available": True, "recent_llm_calls": recent, "llm_calls_path": llm_calls_path}



# === NoemaForge Autodoc Function Header ===
# Function: _iso_ts(ts: float)
# Purpose: Implement the routine ' iso ts'.
# Inputs:
#   - ts: float
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - isoformat, utcfromtimestamp, float
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _iso_ts(ts: float) -> str:
    try:
        return dt.datetime.utcfromtimestamp(float(ts)).isoformat() + "Z"
    except Exception:
        return ""


# === NoemaForge Autodoc Function Header ===
# Function: _scan_inbox_dir(base_dir: str, max_recent: int = 25)
# Purpose: Return a safe summary of an inbox directory.
# Inputs:
#   - base_dir: str
#   - max_recent: int = 25
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - abspath, walk, items, sort, isdir, append, int, join, replace, max, stat, get
# Returns / emits: Dict[str, Any]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - b, base_dir, bucket, bucket_list, by_bucket, fn, full, recent, rel, st, sz, total_bytes
# === End NoemaForge Autodoc Function Header ===
def _scan_inbox_dir(base_dir: str, *, max_recent: int = 25) -> Dict[str, Any]:
    """Return a safe summary of an inbox directory.

    Safety rules:
      - never read file contents
      - only emit metadata (path, size, mtime)
    """
    base_dir = os.path.abspath(base_dir)
    if not os.path.isdir(base_dir):
        return {
            "available": False,
            "base_dir": base_dir,
            "total_files": 0,
            "total_bytes": 0,
            "by_bucket": [],
            "recent": [],
        }

    total_files = 0
    total_bytes = 0
    by_bucket: Dict[str, Dict[str, int]] = {}
    recent: List[Dict[str, Any]] = []

    for root, _dirs, files in os.walk(base_dir):
        for fn in files:
            full = os.path.join(root, fn)
            try:
                st = os.stat(full)
            except Exception:
                continue
            rel = os.path.relpath(full, base_dir).replace("\\", "/")
            bucket = rel.split("/", 1)[0] if "/" in rel else ""
            total_files += 1
            try:
                sz = int(st.st_size)
            except Exception:
                sz = 0
            total_bytes += sz

            b = by_bucket.get(bucket) or {"files": 0, "bytes": 0}
            b["files"] = int(b.get("files") or 0) + 1
            b["bytes"] = int(b.get("bytes") or 0) + sz
            by_bucket[bucket] = b

            recent.append(
                {"path": rel, "bucket": bucket, "size": sz, "mtime": _iso_ts(getattr(st, "st_mtime", 0.0))}
            )

    bucket_list = []
    for k, v in by_bucket.items():
        bucket_list.append({"bucket": k, "files": int(v.get("files") or 0), "bytes": int(v.get("bytes") or 0)})
    bucket_list.sort(
        key=lambda x: (-int(x.get("files") or 0), -int(x.get("bytes") or 0), str(x.get("bucket") or ""))
    )

    recent.sort(key=lambda x: str(x.get("mtime") or ""), reverse=True)
    recent = recent[: max(0, int(max_recent))]

    return {
        "available": True,
        "base_dir": base_dir,
        "total_files": int(total_files),
        "total_bytes": int(total_bytes),
        "by_bucket": bucket_list[:40],
        "recent": recent,
    }


# === NoemaForge Autodoc Function Header ===
# Function: load_inboxes(state_root: str)
# Purpose: Load inbox stats for Library/Vault/Workspace.
# Inputs:
#   - state_root: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - abspath, time, get, join, float, _scan_inbox_dir, str
# Returns / emits: Dict[str, Any]
# Key locals:
#   - _INBOX_CACHE, cached, data, lib, now, state_root, ttl, vault, ws
# === End NoemaForge Autodoc Function Header ===
def load_inboxes(*, state_root: str) -> Dict[str, Any]:
    """Load inbox stats for Library/Vault/Workspace.

    Note: the dashboard polls often; we cache this snapshot for a short TTL
    to avoid heavy rescans when inboxes contain many files.
    """
    state_root = os.path.abspath(state_root)

    now = time.time()
    try:
        ttl = float(INBOX_CACHE_TTL_SEC)
    except Exception:
        ttl = 10.0

    global _INBOX_CACHE
    cached = _INBOX_CACHE.get("data")
    if (
        cached is not None
        and str(_INBOX_CACHE.get("state_root") or "") == state_root
        and (now - float(_INBOX_CACHE.get("ts") or 0.0)) < ttl
    ):
        return cached

    lib = os.path.join(state_root, "Library", "inbox")
    vault = os.path.join(state_root, "Vault", "inbox")
    ws = os.path.join(state_root, "Workspace", "inbox")

    data = {
        "available": True,
        "library": _scan_inbox_dir(lib, max_recent=20),
        "vault": _scan_inbox_dir(vault, max_recent=20),
        "workspace": _scan_inbox_dir(ws, max_recent=25),
    }
    _INBOX_CACHE = {"ts": now, "state_root": state_root, "data": data}
    return data



# === NoemaForge Autodoc Function Header ===
# Function: load_user_tasks(db_path: str, limit: int = 50)
# Purpose: Implement the routine 'load user tasks'.
# Inputs:
#   - db_path: str
#   - limit: int = 50
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - exists, connect, fetchall, close, append, execute, str, max, int
# Returns / emits: Dict[str, Any]
# Side effects:
#   - opens a database or socket connection
#   - executes SQL or shell-like commands
#   - appends to logs or files
# Key locals:
#   - con, out, r, rows
# === End NoemaForge Autodoc Function Header ===
def load_user_tasks(db_path: str, limit: int = 50) -> Dict[str, Any]:
    if not os.path.exists(db_path):
        return {"available": False, "tasks": []}
    try:
        con = sqlite3.connect(db_path)
        rows = con.execute(
            """
            SELECT user_task_id, created_at, updated_at, project_id, title, kind, status, owner, priority_class, engine_task_id
            FROM user_tasks
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (max(1, int(limit)),),
        ).fetchall()
        out = []
        for r in rows:
            out.append(
                {
                    "user_task_id": str(r[0]),
                    "created_at": str(r[1]),
                    "updated_at": str(r[2]),
                    "project_id": str(r[3]),
                    "title": str(r[4]),
                    "kind": str(r[5]),
                    "status": str(r[6]),
                    "owner": str(r[7] or ""),
                    "priority_class": str(r[8] or ""),
                    "engine_task_id": str(r[9] or ""),
                }
            )
        con.close()
        return {"available": True, "tasks": out}
    except Exception as e:
        return {"available": False, "error": str(e), "tasks": []}


# === NoemaForge Autodoc Function Header ===
# Function: load_notifications(state_root: str, limit: int = 50)
# Purpose: Implement the routine 'load notifications'.
# Inputs:
#   - state_root: str
#   - limit: int = 50
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - join, exists, _tail_lines, reverse, _safe_load_json, max, loads, str, bool, append, int, get
# Returns / emits: Dict[str, Any]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - acks, acks_path, ln, nid, obj, path, rows
# === End NoemaForge Autodoc Function Header ===
def load_notifications(*, state_root: str, limit: int = 50) -> Dict[str, Any]:
    path = os.path.join(state_root, "outbox", "notifications.jsonl")
    acks_path = os.path.join(state_root, "outbox", "notifications.acks.json")
    acks = {}
    if os.path.exists(acks_path):
        try:
            acks = _safe_load_json(acks_path)
        except Exception:
            acks = {}
    rows = []
    for ln in _tail_lines(path, max_lines=max(1, int(limit))):
        try:
            obj = json.loads(ln)
            nid = str(obj.get("notification_id") or "")
            obj["acked"] = bool((acks or {}).get(nid))
            rows.append(obj)
        except Exception:
            continue
    rows.reverse()
    return {"available": os.path.exists(path), "notifications": rows}


# === NoemaForge Autodoc Function Header ===
# Function: load_memory(state_root: str, limit: int = 12)
# Purpose: Implement the routine 'load memory'.
# Inputs:
#   - state_root: str
#   - limit: int = 12
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - join, isdir, sorted, exists, listdir, glob, append, max, read, int, open
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads or writes files
#   - appends to logs or files
# Key locals:
#   - dream_root, fp, items, out, p, proj, sess_root, txt
# === End NoemaForge Autodoc Function Header ===
def load_memory(*, state_root: str, limit: int = 12) -> Dict[str, Any]:
    sess_root = os.path.join(state_root, "memory", "session")
    out = {"available": os.path.isdir(sess_root), "session": [], "dream": []}
    if os.path.isdir(sess_root):
        for proj in sorted(os.listdir(sess_root))[:50]:
            p = os.path.join(sess_root, proj, "session_memory.md")
            if os.path.exists(p):
                try:
                    txt = open(p, "r", encoding="utf-8").read()
                    out["session"].append({"project_id": proj, "path": p, "preview": txt[:800]})
                except Exception:
                    continue
    dream_root = os.path.join(state_root, "outbox", "dream")
    if os.path.isdir(dream_root):
        items = []
        for proj in sorted(os.listdir(dream_root)):
            for fp in sorted(glob.glob(os.path.join(dream_root, proj, "*.md")), reverse=True):
                items.append({"project_id": proj, "path": fp})
        out["dream"] = items[: max(1, int(limit))]
    return out


# === NoemaForge Autodoc Function Header ===
# Function: load_worktrees(projects_dir: str, limit: int = 50)
# Purpose: Implement the routine 'load worktrees'.
# Inputs:
#   - projects_dir: str
#   - limit: int = 50
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - isdir, sorted, listdir, join, max, exists, int, _safe_load_json, append
# Returns / emits: Dict[str, Any]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - meta, obj, out, proj, wid, wroot
# === End NoemaForge Autodoc Function Header ===
def load_worktrees(*, projects_dir: str, limit: int = 50) -> Dict[str, Any]:
    out = []
    if os.path.isdir(projects_dir):
        for proj in sorted(os.listdir(projects_dir)):
            wroot = os.path.join(projects_dir, proj, "worktrees")
            if not os.path.isdir(wroot):
                continue
            for wid in sorted(os.listdir(wroot)):
                meta = os.path.join(wroot, wid, ".noemaforge-worktree.json")
                if os.path.exists(meta):
                    try:
                        obj = _safe_load_json(meta)
                        if obj:
                            out.append(obj)
                    except Exception:
                        continue
    out = out[: max(1, int(limit))]
    return {"available": True, "worktrees": out}


# === NoemaForge Autodoc Function Header ===
# Function: load_skills(configs_dir: str)
# Purpose: Implement the routine 'load skills'.
# Inputs:
#   - configs_dir: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - join, _safe_load_yaml, get, append, bool, isinstance, str
# Returns / emits: Dict[str, Any]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - doc, path, rows, s
# === End NoemaForge Autodoc Function Header ===
def load_skills(*, configs_dir: str) -> Dict[str, Any]:
    path = os.path.join(configs_dir, "skills.yaml")
    doc = _safe_load_yaml(path)
    rows = []
    for s in doc.get("skills", []) or []:
        if not isinstance(s, dict):
            continue
        rows.append({"id": str(s.get("id") or ""), "title": str(s.get("title") or ""), "type": str(s.get("type") or ""), "description": str(s.get("description") or "")})
    return {"available": bool(rows), "skills": rows}



# === NoemaForge Autodoc Function Header ===
# Function: build_snapshot(state_root: str, configs_dir: Optional[str] = None)
# Purpose: Implement the routine 'build snapshot'.
# Inputs:
#   - state_root: str
#   - configs_dir: Optional[str] = None
# Called by:
#   - src/brainui.py
#   - src/metrics_snapshot.py
# Calls:
#   - resolve_paths, _load_runtime_state, load_taskqueue, load_projects, load_sel_events, load_telemetry, load_inboxes, load_user_tasks, load_notifications, load_memory, load_worktrees, load_skills
# Returns / emits: Dict[str, Any]
# Side effects:
#   - spawns subprocesses or workers
# Key locals:
#   - configs_dir, ev, ib, mem, nt, paths, pr, rt, skl, tl, tq, ut
# === End NoemaForge Autodoc Function Header ===


def load_firstboot_status(state_root: str) -> Dict[str, Any]:
    path = os.path.join(state_root, 'bootstrap', 'firstboot-status.json')
    try:
        with open(path, 'r', encoding='utf-8') as f:
            obj = json.load(f)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    return {}

def build_snapshot(*, state_root: str, configs_dir: Optional[str] = None) -> Dict[str, Any]:
    if not configs_dir:
        configs_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "configs"))

    paths = resolve_paths(state_root=state_root, configs_dir=configs_dir)
    rt = _load_runtime_state(paths["runtime_state"])
    tq = load_taskqueue(paths["taskqueue_db"])
    pr = load_projects(projects_dir=paths["projects_dir"], configs_dir=paths["configs_dir"])
    ev = load_sel_events(paths["sel_segments_dir"], limit=80)
    tl = load_telemetry(paths["telemetry_llm_calls"], limit=80)
    ib = load_inboxes(state_root=paths["state_root"])
    ut = load_user_tasks(paths["taskqueue_db"], limit=80)
    nt = load_notifications(state_root=paths["state_root"], limit=80)
    mem = load_memory(state_root=paths["state_root"], limit=20)
    wt = load_worktrees(projects_dir=paths["projects_dir"], limit=80)
    skl = load_skills(configs_dir=paths["configs_dir"])
    operator = profile_manager.operator_status_snapshot(paths["configs_dir"]) if profile_manager is not None else {"profiles": {}, "enabled_profiles": [], "disabled_profiles": [], "ready_count": 0, "total_count": 0}
    fb = load_firstboot_status(paths["state_root"])

    return {
        "schema_version": SCHEMA,
        "generated_at": _nowz(),
        "paths": {k: v for k, v in paths.items() if k not in ("telemetry_tool_calls",)},
        "runtime_state": rt,
        "taskqueue": tq,
        "user_tasks": ut,
        "projects": pr,
        "events": ev,
        "telemetry": tl,
        "inboxes": ib,
        "notifications": nt,
        "memory": mem,
        "worktrees": wt,
        "skills": skl,
        "operator": operator,
        "firstboot": fb,
        "administrator": {"mode": fb.get("step") or "idle", "state": fb.get("state") or "unknown"},
    }
