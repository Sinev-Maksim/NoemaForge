#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/task_tools.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-14
Modified: 2026-05-14
Purpose: Manage NoemaForge task queue and task execution surfaces.
Inputs: Command-line arguments, environment variables, package files and local NoemaForge runtime state as applicable.
Outputs: Structured command output, files, service state or UI state as documented by the caller.
Side effects: Limited to the documented NoemaForge paths, runtime state directories or systemd units used by this file.
Tests: Syntax validation plus the release setup selftest, consistency-audit and targeted smoke checks.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

# === NoemaForge Autodoc File Header ===
# File: src/task_tools.py
# Purpose: Provide the module 'task_tools'.
# Invoked by / imported from:
#   - src/coordinator_fanout.py
#   - src/dream_cycle.py
#   - src/session_memory_extractor.py
#   - src/skills_registry.py
#   - src/toolproxy.py
#   - tools/migrate/migrate_taskqueue_v26.py
# Public API / entry functions:
#   - init_v26_schema
#   - create_user_task
#   - list_user_tasks
#   - get_user_task
#   - update_user_task
#   - stop_user_task
#   - add_output
#   - main
# Inputs:
#   - --project-id
#   - --status
#   - --limit
#   - user_task_id
#   - Common path inputs: /var/lib/noemaforge/projects
#   - Imports: __future__, argparse, datetime, hashlib, json, os, sqlite3, uuid
# Output formats / side effects:
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
import uuid
from typing import Any, Dict, List, Optional

import taskqueue
from platform_paths import DEFAULT_PATHS as _pp

PROJECTS_BASE = str(_pp.data_root / "projects")
LIST_USER_TASKS_SQL = (
    "SELECT user_task_id, created_at, updated_at, project_id, session_id, title, description, kind, status, owner, "
    "priority_class, engine_task_id, worktree_id, plan_required, last_error, payload_json, metadata_json "
    "FROM user_tasks {where_clause} ORDER BY created_at DESC LIMIT ?"
)
UPDATE_USER_TASK_COLUMNS = {
    "title": "title",
    "description": "description",
    "kind": "kind",
    "status": "status",
    "owner": "owner",
    "priority_class": "priority_class",
    "worktree_id": "worktree_id",
    "last_error": "last_error",
    "session_id": "session_id",
    "plan_required": "plan_required",
    "payload_json": "payload_json",
    "metadata_json": "metadata_json",
    "updated_at": "updated_at",
}

USER_TO_ENGINE = {
    "queued": "TODO",
    "planning": "TODO",
    "blocked": "TODO",
    "running": "IN_PROGRESS",
    "done": "DONE",
    "failed": "DEADLETTER",
    "stopped": "DEADLETTER",
}
ENGINE_TO_USER = {
    "TODO": "queued",
    "IN_PROGRESS": "running",
    "DONE": "done",
    "DEADLETTER": "failed",
}


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
# Function: _ensure_parent(path: str)
# Purpose: Implement the routine ' ensure parent'.
# Inputs:
#   - path: str
# Called by:
#   - src/dream_cycle.py
#   - src/roadmap.py
#   - src/session_memory_extractor.py
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
# Function: _projects_task_dir(project_id: str, user_task_id: str)
# Purpose: Implement the routine ' projects task dir'.
# Inputs:
#   - project_id: str
#   - user_task_id: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - join, strip, str
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _projects_task_dir(project_id: str, user_task_id: str) -> str:
    return os.path.join(PROJECTS_BASE, str(project_id).strip(), "tasks", str(user_task_id).strip(), "outputs")


# === NoemaForge Autodoc Function Header ===
# Function: _sha256_bytes(b: bytes)
# Purpose: Implement the routine ' sha256 bytes'.
# Inputs:
#   - b: bytes
# Called by:
#   - src/quarantine.py
#   - src/quarantine_samples.py
# Calls:
#   - hexdigest, sha256
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


# === NoemaForge Autodoc Function Header ===
# Function: _con(policy: Optional[Dict[str, Any]] = None)
# Purpose: Implement the routine ' con'.
# Inputs:
#   - policy: Optional[Dict[str, Any]] = None
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _db_path, _connect, init_v26_schema, load_policy
# Returns / emits: sqlite3.Connection
# Side effects:
#   - opens a database or socket connection
# Key locals:
#   - con, db_path, policy
# === End NoemaForge Autodoc Function Header ===
def _con(policy: Optional[Dict[str, Any]] = None) -> sqlite3.Connection:
    policy = policy or taskqueue.load_policy()
    db_path = taskqueue._db_path(policy)  # type: ignore[attr-defined]
    con = taskqueue._connect(db_path)  # type: ignore[attr-defined]
    init_v26_schema(policy=policy, con=con)
    return con


def _where_clause(parts: List[str]) -> str:
    if not parts:
        return ""
    allowed = {"project_id=?", "status=?"}
    for part in parts:
        if part not in allowed:
            raise ValueError("unsupported_where_clause")
    return "WHERE " + " AND ".join(parts)


def _assignment(column: str) -> str:
    safe = UPDATE_USER_TASK_COLUMNS.get(str(column))
    if not safe:
        raise ValueError("unsupported_update_column")
    return f"{safe}=?"


# === NoemaForge Autodoc Function Header ===
# Function: init_v26_schema(policy: Optional[Dict[str, Any]] = None, con: Optional[sqlite3.Connection] = None)
# Purpose: Implement the routine 'init v26 schema'.
# Inputs:
#   - policy: Optional[Dict[str, Any]] = None
#   - con: Optional[sqlite3.Connection] = None
# Called by:
#   - tools/migrate/migrate_taskqueue_v26.py
# Calls:
#   - execute, commit, _con_without_init, close
# Returns / emits: Dict[str, Any]
# Side effects:
#   - executes SQL or shell-like commands
# Key locals:
#   - con, own
# === End NoemaForge Autodoc Function Header ===
def init_v26_schema(*, policy: Optional[Dict[str, Any]] = None, con: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
    own = False
    if con is None:
        con = _con_without_init(policy)
        own = True
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS user_tasks (
          user_task_id TEXT PRIMARY KEY,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          project_id TEXT NOT NULL,
          session_id TEXT,
          title TEXT NOT NULL,
          description TEXT,
          kind TEXT NOT NULL,
          status TEXT NOT NULL,
          owner TEXT,
          priority_class TEXT NOT NULL DEFAULT 'normal',
          payload_json TEXT,
          metadata_json TEXT,
          engine_task_id TEXT,
          worktree_id TEXT,
          plan_required INTEGER NOT NULL DEFAULT 0,
          last_error TEXT
        );
        """
    )
    con.execute("CREATE INDEX IF NOT EXISTS idx_user_tasks_project_status ON user_tasks(project_id, status, created_at);")
    con.execute("CREATE INDEX IF NOT EXISTS idx_user_tasks_engine ON user_tasks(engine_task_id);")
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS user_task_deps (
          user_task_id TEXT NOT NULL,
          depends_on_task_id TEXT NOT NULL,
          PRIMARY KEY(user_task_id, depends_on_task_id)
        );
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS user_task_artifacts (
          artifact_id TEXT PRIMARY KEY,
          user_task_id TEXT NOT NULL,
          created_at TEXT NOT NULL,
          kind TEXT NOT NULL,
          path TEXT NOT NULL,
          sha256 TEXT,
          meta_json TEXT
        );
        """
    )
    con.execute("CREATE INDEX IF NOT EXISTS idx_user_task_artifacts_task ON user_task_artifacts(user_task_id, created_at);")
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS user_task_events (
          event_id TEXT PRIMARY KEY,
          user_task_id TEXT NOT NULL,
          created_at TEXT NOT NULL,
          actor TEXT,
          event_kind TEXT NOT NULL,
          detail_json TEXT
        );
        """
    )
    con.execute("CREATE INDEX IF NOT EXISTS idx_user_task_events_task ON user_task_events(user_task_id, created_at);")
    con.commit()
    if own:
        con.close()
    return {"ok": True}


# === NoemaForge Autodoc Function Header ===
# Function: _con_without_init(policy: Optional[Dict[str, Any]] = None)
# Purpose: Implement the routine ' con without init'.
# Inputs:
#   - policy: Optional[Dict[str, Any]] = None
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _db_path, _connect, load_policy
# Returns / emits: sqlite3.Connection
# Side effects:
#   - opens a database or socket connection
# Key locals:
#   - con, db_path, policy
# === End NoemaForge Autodoc Function Header ===
def _con_without_init(policy: Optional[Dict[str, Any]] = None) -> sqlite3.Connection:
    policy = policy or taskqueue.load_policy()
    db_path = taskqueue._db_path(policy)  # type: ignore[attr-defined]
    con = taskqueue._connect(db_path)  # type: ignore[attr-defined]
    return con


# === NoemaForge Autodoc Function Header ===
# Function: _row_to_task(con: sqlite3.Connection, row: sqlite3.Row)
# Purpose: Implement the routine ' row to task'.
# Inputs:
#   - con: sqlite3.Connection
#   - row: sqlite3.Row
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - str, fetchall, bool, loads, append, int, execute
# Returns / emits: Dict[str, Any]
# Side effects:
#   - executes SQL or shell-like commands
#   - appends to logs or files
# Key locals:
#   - art_rows, arts, dep_rows, detail, engine_task_id, ev_rows, evs, meta, out, r, user_task_id
# === End NoemaForge Autodoc Function Header ===
def _row_to_task(con: sqlite3.Connection, row: sqlite3.Row) -> Dict[str, Any]:
    user_task_id = str(row[0])
    engine_task_id = str(row[11] or "")
    out = {
        "user_task_id": user_task_id,
        "created_at": str(row[1]),
        "updated_at": str(row[2]),
        "project_id": str(row[3]),
        "session_id": str(row[4] or ""),
        "title": str(row[5]),
        "description": str(row[6] or ""),
        "kind": str(row[7]),
        "status": str(row[8]),
        "owner": str(row[9] or ""),
        "priority_class": str(row[10] or "normal"),
        "engine_task_id": engine_task_id,
        "worktree_id": str(row[12] or ""),
        "plan_required": bool(int(row[13] or 0)),
        "last_error": str(row[14] or ""),
        "payload": {},
        "metadata": {},
        "depends_on": [],
        "artifacts": [],
        "events": [],
    }
    try:
        out["payload"] = json.loads(str(row[15] or "{}"))
    except Exception:
        out["payload"] = {}
    try:
        out["metadata"] = json.loads(str(row[16] or "{}"))
    except Exception:
        out["metadata"] = {}
    dep_rows = con.execute("SELECT depends_on_task_id FROM user_task_deps WHERE user_task_id=? ORDER BY depends_on_task_id ASC", (user_task_id,)).fetchall()
    out["depends_on"] = [str(r[0]) for r in dep_rows]
    art_rows = con.execute(
        "SELECT artifact_id, created_at, kind, path, sha256, meta_json FROM user_task_artifacts WHERE user_task_id=? ORDER BY created_at DESC",
        (user_task_id,),
    ).fetchall()
    arts = []
    for r in art_rows:
        try:
            meta = json.loads(str(r[5] or "{}"))
        except Exception:
            meta = {}
        arts.append({"artifact_id": str(r[0]), "created_at": str(r[1]), "kind": str(r[2]), "path": str(r[3]), "sha256": str(r[4] or ""), "meta": meta})
    out["artifacts"] = arts
    ev_rows = con.execute(
        "SELECT event_id, created_at, actor, event_kind, detail_json FROM user_task_events WHERE user_task_id=? ORDER BY created_at DESC LIMIT 50",
        (user_task_id,),
    ).fetchall()
    evs = []
    for r in ev_rows:
        try:
            detail = json.loads(str(r[4] or "{}"))
        except Exception:
            detail = {}
        evs.append({"event_id": str(r[0]), "created_at": str(r[1]), "actor": str(r[2] or ""), "event_kind": str(r[3]), "detail": detail})
    out["events"] = evs
    return out


# === NoemaForge Autodoc Function Header ===
# Function: _sync_engine_statuses(con: sqlite3.Connection)
# Purpose: Implement the routine ' sync engine statuses'.
# Inputs:
#   - con: sqlite3.Connection
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - fetchall, commit, fetchone, get, str, execute, upper, _record_event, _nowz
# Returns / emits: None
# Side effects:
#   - executes SQL or shell-like commands
# Key locals:
#   - last_error, new_status, r, rows
# === End NoemaForge Autodoc Function Header ===
def _sync_engine_statuses(con: sqlite3.Connection) -> None:
    rows = con.execute("SELECT user_task_id, engine_task_id, status FROM user_tasks WHERE engine_task_id IS NOT NULL AND engine_task_id != ''").fetchall()
    for user_task_id, engine_task_id, cur_status in rows:
        r = con.execute("SELECT status, last_error FROM tasks WHERE task_id=?", (str(engine_task_id),)).fetchone()
        if not r:
            continue
        new_status = ENGINE_TO_USER.get(str(r[0] or "").upper(), str(cur_status or "queued"))
        last_error = str(r[1] or "")
        if new_status != str(cur_status):
            con.execute(
                "UPDATE user_tasks SET status=?, updated_at=?, last_error=? WHERE user_task_id=?",
                (new_status, _nowz(), last_error[:4000], str(user_task_id)),
            )
            _record_event(con, str(user_task_id), "engine_status_sync", {"engine_task_id": engine_task_id, "status": new_status, "last_error": last_error}, actor="engine")
    con.commit()


# === NoemaForge Autodoc Function Header ===
# Function: _record_event(con: sqlite3.Connection, user_task_id: str, event_kind: str, detail: Dict[str, Any], actor: str = '')
# Purpose: Implement the routine ' record event'.
# Inputs:
#   - con: sqlite3.Connection
#   - user_task_id: str
#   - event_kind: str
#   - detail: Dict[str, Any]
#   - actor: str = ''
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - execute, uuid4, _nowz, dumps
# Returns / emits: str
# Side effects:
#   - serializes structured data
#   - executes SQL or shell-like commands
# Key locals:
#   - event_id
# === End NoemaForge Autodoc Function Header ===
def _record_event(con: sqlite3.Connection, user_task_id: str, event_kind: str, detail: Dict[str, Any], actor: str = "") -> str:
    event_id = uuid.uuid4().hex
    con.execute(
        "INSERT OR REPLACE INTO user_task_events(event_id, user_task_id, created_at, actor, event_kind, detail_json) VALUES(?,?,?,?,?,?)",
        (event_id, user_task_id, _nowz(), actor or None, event_kind, json.dumps(detail or {}, ensure_ascii=False)),
    )
    return event_id


# === NoemaForge Autodoc Function Header ===
# Function: create_user_task(policy: Optional[Dict[str, Any]] = None, project_id: str, title: str, description: str = '', kind: str = 'generic', status: str = 'queued', owner: str = '', priority_class: str = 'normal', payload: Optional[Dict[str, Any]] = None, metadata: Optional[Dict[str, Any]] = None, depends_on: Optional[List[str]] = None, session_id: str = '', background_module: str = '', group_key: str = '', plan_required: bool = False, worktree_id: str = '', actor: str = 'toolproxy')
# Purpose: Implement the routine 'create user task'.
# Inputs:
#   - policy: Optional[Dict[str, Any]] = None
#   - project_id: str
#   - title: str
#   - description: str = ''
#   - kind: str = 'generic'
#   - status: str = 'queued'
#   - owner: str = ''
#   - priority_class: str = 'normal'
#   - payload: Optional[Dict[str, Any]] = None
#   - metadata: Optional[Dict[str, Any]] = None
#   - depends_on: Optional[List[str]] = None
#   - session_id: str = ''
#   - background_module: str = ''
#   - group_key: str = ''
#   - plan_required: bool = False
#   - worktree_id: str = ''
#   - actor: str = 'toolproxy'
# Called by:
#   - src/coordinator_fanout.py
#   - src/skills_registry.py
#   - src/toolproxy.py
# Calls:
#   - _con, strip, ValueError, execute, _record_event, commit, fetchone, close, isinstance, uuid4, enqueue_task, str
# Returns / emits: Dict[str, Any]
# Side effects:
#   - executes SQL or shell-like commands
# Key locals:
#   - con, dep, depends_on, engine_task_id, enq, metadata, payload, row, user_task_id
# === End NoemaForge Autodoc Function Header ===
def create_user_task(
    *,
    policy: Optional[Dict[str, Any]] = None,
    project_id: str,
    title: str,
    description: str = "",
    kind: str = "generic",
    status: str = "queued",
    owner: str = "",
    priority_class: str = "normal",
    payload: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    depends_on: Optional[List[str]] = None,
    session_id: str = "",
    background_module: str = "",
    group_key: str = "",
    plan_required: bool = False,
    worktree_id: str = "",
    actor: str = "toolproxy",
) -> Dict[str, Any]:
    if not str(project_id).strip():
        raise ValueError("missing_project_id")
    if not str(title).strip():
        raise ValueError("missing_title")
    con = _con(policy)
    try:
        payload = payload if isinstance(payload, dict) else {}
        metadata = metadata if isinstance(metadata, dict) else {}
        depends_on = [str(x).strip() for x in (depends_on or []) if str(x).strip()]
        user_task_id = uuid.uuid4().hex
        engine_task_id = ""
        if background_module:
            enq = taskqueue.enqueue_task(
                policy=policy,
                domain="WORK",
                kind="module",
                module=str(background_module).strip(),
                title=title,
                description=description,
                payload={"project_id": project_id, "user_task_id": user_task_id, **payload},
                priority_class=priority_class,
                group_key=group_key or f"user.{project_id}.{kind}.{title[:48]}",
            )
            engine_task_id = str(enq.get("task_id") or "")
        con.execute(
            """
            INSERT INTO user_tasks(
              user_task_id, created_at, updated_at, project_id, session_id, title, description, kind, status, owner,
              priority_class, engine_task_id, worktree_id, plan_required, last_error, payload_json, metadata_json
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                user_task_id,
                _nowz(),
                _nowz(),
                project_id,
                session_id or None,
                title.strip(),
                description.strip() or None,
                kind.strip() or "generic",
                status.strip() or "queued",
                owner.strip() or None,
                priority_class.strip() or "normal",
                engine_task_id or None,
                worktree_id or None,
                1 if plan_required else 0,
                None,
                json.dumps(payload, ensure_ascii=False),
                json.dumps(metadata, ensure_ascii=False),
            ),
        )
        for dep in depends_on:
            con.execute("INSERT OR IGNORE INTO user_task_deps(user_task_id, depends_on_task_id) VALUES(?,?)", (user_task_id, dep))
        _record_event(con, user_task_id, "created", {"title": title, "background_module": background_module, "engine_task_id": engine_task_id}, actor=actor)
        con.commit()
        row = con.execute(
            "SELECT user_task_id, created_at, updated_at, project_id, session_id, title, description, kind, status, owner, priority_class, engine_task_id, worktree_id, plan_required, last_error, payload_json, metadata_json FROM user_tasks WHERE user_task_id=?",
            (user_task_id,),
        ).fetchone()
        return {"ok": True, "task": _row_to_task(con, row)}
    finally:
        con.close()


# === NoemaForge Autodoc Function Header ===
# Function: list_user_tasks(policy: Optional[Dict[str, Any]] = None, project_id: str = '', status: str = '', limit: int = 50)
# Purpose: Implement the routine 'list user tasks'.
# Inputs:
#   - policy: Optional[Dict[str, Any]] = None
#   - project_id: str = ''
#   - status: str = ''
#   - limit: int = 50
# Called by:
#   - src/dream_cycle.py
#   - src/session_memory_extractor.py
#   - src/toolproxy.py
# Calls:
#   - _con, _sync_engine_statuses, fetchall, close, append, join, execute, _row_to_task, tuple, max, int
# Returns / emits: Dict[str, Any]
# Side effects:
#   - executes SQL or shell-like commands
#   - appends to logs or files
# Key locals:
#   - con, rows, where
# === End NoemaForge Autodoc Function Header ===
def list_user_tasks(
    *,
    policy: Optional[Dict[str, Any]] = None,
    project_id: str = "",
    status: str = "",
    limit: int = 50,
) -> Dict[str, Any]:
    con = _con(policy)
    con.row_factory = sqlite3.Row
    try:
        _sync_engine_statuses(con)
        wh, args = [], []
        if project_id:
            wh.append("project_id=?")
            args.append(project_id)
        if status:
            wh.append("status=?")
            args.append(status)
        where = _where_clause(wh)
        rows = con.execute(
            LIST_USER_TASKS_SQL.format(where_clause=where),
            tuple(args + [max(1, int(limit))]),
        ).fetchall()
        return {"ok": True, "tasks": [_row_to_task(con, r) for r in rows]}
    finally:
        con.close()


# === NoemaForge Autodoc Function Header ===
# Function: get_user_task(policy: Optional[Dict[str, Any]] = None, user_task_id: str)
# Purpose: Implement the routine 'get user task'.
# Inputs:
#   - policy: Optional[Dict[str, Any]] = None
#   - user_task_id: str
# Called by:
#   - src/toolproxy.py
# Calls:
#   - _con, _sync_engine_statuses, fetchone, close, ValueError, _row_to_task, execute
# Returns / emits: Dict[str, Any]
# Side effects:
#   - executes SQL or shell-like commands
# Key locals:
#   - con, row
# === End NoemaForge Autodoc Function Header ===
def get_user_task(*, policy: Optional[Dict[str, Any]] = None, user_task_id: str) -> Dict[str, Any]:
    con = _con(policy)
    con.row_factory = sqlite3.Row
    try:
        _sync_engine_statuses(con)
        row = con.execute(
            "SELECT user_task_id, created_at, updated_at, project_id, session_id, title, description, kind, status, owner, priority_class, engine_task_id, worktree_id, plan_required, last_error, payload_json, metadata_json FROM user_tasks WHERE user_task_id=?",
            (user_task_id,),
        ).fetchone()
        if not row:
            raise ValueError("unknown_user_task")
        return {"ok": True, "task": _row_to_task(con, row)}
    finally:
        con.close()


# === NoemaForge Autodoc Function Header ===
# Function: update_user_task(policy: Optional[Dict[str, Any]] = None, user_task_id: str, patch: Dict[str, Any], actor: str = 'toolproxy')
# Purpose: Implement the routine 'update user task'.
# Inputs:
#   - policy: Optional[Dict[str, Any]] = None
#   - user_task_id: str
#   - patch: Dict[str, Any]
#   - actor: str = 'toolproxy'
# Called by:
#   - src/toolproxy.py
# Calls:
#   - _con, fetchone, append, execute, _record_event, commit, close, ValueError, get_user_task, _nowz, tuple, _row_to_task
# Returns / emits: Dict[str, Any]
# Side effects:
#   - executes SQL or shell-like commands
#   - appends to logs or files
# Key locals:
#   - args, con, fields, key, row, row2, simple
# === End NoemaForge Autodoc Function Header ===
def update_user_task(
    *,
    policy: Optional[Dict[str, Any]] = None,
    user_task_id: str,
    patch: Dict[str, Any],
    actor: str = "toolproxy",
) -> Dict[str, Any]:
    con = _con(policy)
    con.row_factory = sqlite3.Row
    try:
        row = con.execute("SELECT payload_json, metadata_json FROM user_tasks WHERE user_task_id=?", (user_task_id,)).fetchone()
        if not row:
            raise ValueError("unknown_user_task")
        fields = []
        args: List[Any] = []
        simple = ["title", "description", "kind", "status", "owner", "priority_class", "worktree_id", "last_error", "session_id"]
        for key in simple:
            if key in patch:
                fields.append(_assignment(key))
                args.append((str(patch.get(key) or "").strip() or None) if key not in ("status", "priority_class") else str(patch.get(key) or "").strip())
        if "plan_required" in patch:
            fields.append(_assignment("plan_required"))
            args.append(1 if bool(patch.get("plan_required")) else 0)
        if "payload" in patch:
            fields.append(_assignment("payload_json"))
            args.append(json.dumps(patch.get("payload") or {}, ensure_ascii=False))
        if "metadata" in patch:
            fields.append(_assignment("metadata_json"))
            args.append(json.dumps(patch.get("metadata") or {}, ensure_ascii=False))
        if not fields:
            return get_user_task(policy=policy, user_task_id=user_task_id)
        fields.append(_assignment("updated_at"))
        args.append(_nowz())
        args.append(user_task_id)
        con.execute(f"UPDATE user_tasks SET {', '.join(fields)} WHERE user_task_id=?", tuple(args))
        _record_event(con, user_task_id, "updated", {"patch_keys": sorted(list((patch or {}).keys()))}, actor=actor)
        con.commit()
        row2 = con.execute(
            "SELECT user_task_id, created_at, updated_at, project_id, session_id, title, description, kind, status, owner, priority_class, engine_task_id, worktree_id, plan_required, last_error, payload_json, metadata_json FROM user_tasks WHERE user_task_id=?",
            (user_task_id,),
        ).fetchone()
        return {"ok": True, "task": _row_to_task(con, row2)}
    finally:
        con.close()


# === NoemaForge Autodoc Function Header ===
# Function: stop_user_task(policy: Optional[Dict[str, Any]] = None, user_task_id: str, actor: str = 'toolproxy')
# Purpose: Implement the routine 'stop user task'.
# Inputs:
#   - policy: Optional[Dict[str, Any]] = None
#   - user_task_id: str
#   - actor: str = 'toolproxy'
# Called by:
#   - src/toolproxy.py
# Calls:
#   - _con, fetchone, str, execute, _record_event, commit, close, ValueError, _row_to_task, _nowz
# Returns / emits: Dict[str, Any]
# Side effects:
#   - executes SQL or shell-like commands
# Key locals:
#   - con, eng, row, row2
# === End NoemaForge Autodoc Function Header ===
def stop_user_task(*, policy: Optional[Dict[str, Any]] = None, user_task_id: str, actor: str = "toolproxy") -> Dict[str, Any]:
    con = _con(policy)
    con.row_factory = sqlite3.Row
    try:
        row = con.execute(
            "SELECT engine_task_id FROM user_tasks WHERE user_task_id=?",
            (user_task_id,),
        ).fetchone()
        if not row:
            raise ValueError("unknown_user_task")
        eng = str(row[0] or "")
        con.execute("UPDATE user_tasks SET status='stopped', updated_at=? WHERE user_task_id=?", (_nowz(), user_task_id))
        if eng:
            con.execute("UPDATE tasks SET status='DEADLETTER', updated_at=?, last_error=? WHERE task_id=?", (_nowz(), "stopped_by_user", eng))
        _record_event(con, user_task_id, "stopped", {"engine_task_id": eng}, actor=actor)
        con.commit()
        row2 = con.execute(
            "SELECT user_task_id, created_at, updated_at, project_id, session_id, title, description, kind, status, owner, priority_class, engine_task_id, worktree_id, plan_required, last_error, payload_json, metadata_json FROM user_tasks WHERE user_task_id=?",
            (user_task_id,),
        ).fetchone()
        return {"ok": True, "task": _row_to_task(con, row2)}
    finally:
        con.close()


# === NoemaForge Autodoc Function Header ===
# Function: add_output(policy: Optional[Dict[str, Any]] = None, user_task_id: str, kind: str, text: str = '', path: str = '', meta: Optional[Dict[str, Any]] = None, actor: str = 'toolproxy')
# Purpose: Implement the routine 'add output'.
# Inputs:
#   - policy: Optional[Dict[str, Any]] = None
#   - user_task_id: str
#   - kind: str
#   - text: str = ''
#   - path: str = ''
#   - meta: Optional[Dict[str, Any]] = None
#   - actor: str = 'toolproxy'
# Called by:
#   - src/toolproxy.py
# Calls:
#   - _con, fetchone, str, strip, execute, _record_event, commit, close, ValueError, uuid4, isinstance, _ensure_parent
# Returns / emits: Dict[str, Any]
# Side effects:
#   - executes SQL or shell-like commands
# Key locals:
#   - artifact_id, con, data, ext, f, final_path, meta, project_id, row, sha
# === End NoemaForge Autodoc Function Header ===
def add_output(
    *,
    policy: Optional[Dict[str, Any]] = None,
    user_task_id: str,
    kind: str,
    text: str = "",
    path: str = "",
    meta: Optional[Dict[str, Any]] = None,
    actor: str = "toolproxy",
) -> Dict[str, Any]:
    con = _con(policy)
    try:
        row = con.execute("SELECT project_id FROM user_tasks WHERE user_task_id=?", (user_task_id,)).fetchone()
        if not row:
            raise ValueError("unknown_user_task")
        project_id = str(row[0])
        artifact_id = uuid.uuid4().hex
        meta = meta if isinstance(meta, dict) else {}
        final_path = str(path or "").strip()
        sha = ""
        if text:
            ext = ".md" if str(kind).endswith("md") or str(kind) in ("markdown", "report", "summary") else ".txt"
            final_path = final_path or os.path.join(_projects_task_dir(project_id, user_task_id), f"{artifact_id}{ext}")
            _ensure_parent(final_path)
            data = text.encode("utf-8")
            with open(final_path, "wb") as f:
                f.write(data)
            sha = _sha256_bytes(data)
        elif final_path and os.path.exists(final_path):
            with open(final_path, "rb") as f:
                sha = _sha256_bytes(f.read())
        else:
            raise ValueError("missing_output_content")
        con.execute(
            "INSERT INTO user_task_artifacts(artifact_id, user_task_id, created_at, kind, path, sha256, meta_json) VALUES(?,?,?,?,?,?,?)",
            (artifact_id, user_task_id, _nowz(), str(kind or 'artifact'), final_path, sha or None, json.dumps(meta, ensure_ascii=False)),
        )
        _record_event(con, user_task_id, "output_added", {"artifact_id": artifact_id, "path": final_path, "kind": kind}, actor=actor)
        con.commit()
        return {"ok": True, "artifact": {"artifact_id": artifact_id, "user_task_id": user_task_id, "kind": kind, "path": final_path, "sha256": sha, "meta": meta}}
    finally:
        con.close()


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
#   - ArgumentParser, add_subparsers, add_parser, add_argument, parse_args, print, init_v26_schema, dumps, list_user_tasks, get_user_task
# Returns / emits: int
# Side effects:
#   - serializes structured data
# Key locals:
#   - ap, ns, out, p, sub
# === End NoemaForge Autodoc Function Header ===
def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init")
    p = sub.add_parser("list")
    p.add_argument("--project-id", default="")
    p.add_argument("--status", default="")
    p.add_argument("--limit", type=int, default=20)
    p = sub.add_parser("get")
    p.add_argument("user_task_id")

    ns = ap.parse_args(argv)
    if ns.cmd == "init":
        out = init_v26_schema()
    elif ns.cmd == "list":
        out = list_user_tasks(project_id=ns.project_id, status=ns.status, limit=ns.limit)
    else:
        out = get_user_task(user_task_id=ns.user_task_id)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
