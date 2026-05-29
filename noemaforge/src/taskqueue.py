#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/taskqueue.py
Zone: release/package
Version: 0.32.2
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
# File: src/taskqueue.py
# Purpose: Persist and dispatch scheduled work with SQLite-backed queue state and audit metadata.
# Invoked by / imported from:
#   - src/audit_remediation.py
#   - src/daily_scheduler.py
#   - src/maintenance.py
#   - src/scary_sweep.py
#   - src/task_runner.py
#   - src/task_tools.py
# Public API / entry functions:
#   - load_policy
#   - enqueue_task
#   - ensure_default_tasks
#   - enqueue_from_signal
#   - claim_next_task
#   - complete_task
#   - list_tasks
#   - has_todo_with_priority_classes
# Inputs:
#   - Common path inputs: /opt/noemaforge/configs/taskqueue-policy.yaml, /var/lib/noemaforge/taskqueue/stamps, /var/lib/noemaforge/taskqueue/taskqueue.sqlite
#   - Imports: __future__, datetime, json, os, sqlite3, uuid, hashlib, fnmatch
# Output formats / side effects:
#   - SQLite databases
#   - JSON files
#   - YAML files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""taskqueue.py (v0.12.7)

System task queue (spine).

Why this exists
--------------
NoemaForge has multiple *domains* of background work:
  - WORK         (project execution via teamworker)
  - SELF_IMPROVE (surgeon, solution architect, SR outputs)
  - SECURITY     (scary sweep, quarantine flows)
  - PLANNED      (scheduled/offline pipelines)

Historically, maintenance.py executed a fixed rotation. That works, but it makes
SR/SSR feel "magical": they emit ideas, but not actionable, queued tasks.

This module provides a small, local-first task queue:
  - deterministic
  - auditable (SEL can consume outcomes)
  - repeat-aware (same group_key repeats -> priority boost)
  - safe offline (sqlite only)

It is *not* a general-purpose workflow engine. It's just enough for:
  - enqueue tasks in SR/SSR
  - claim ONE task during idle-cycle
  - run it (via task_runner)

v0.11.8 notes:
  - Default tasks may specify cooldown_sec in policy; we enforce it via
    lightweight filesystem stamps (no schema expansion required).
"""


import datetime as dt
import json
import os
import sqlite3
import uuid
import hashlib
import fnmatch
from typing import Any, Dict, Iterable, List, Optional, Tuple

import yaml


DEFAULT_POLICY_PATH = "/opt/noemaforge/configs/taskqueue-policy.yaml"

# Cooldown stamps for default background tasks.
# We keep them outside the DB schema so they survive light DB maintenance and
# remain trivial to inspect.
STAMPS_DIR = "/var/lib/noemaforge/taskqueue/stamps"


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
#   - src/session_memory_extractor.py
#   - src/task_tools.py
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
# Function: _stamp_path(group_key: str)
# Purpose: Return a filesystem stamp path for a group_key.
# Inputs:
#   - group_key: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - strip, makedirs, join, hexdigest, sha256, encode
# Returns / emits: str
# Side effects:
#   - creates directories
# Key locals:
#   - gk, h
# === End NoemaForge Autodoc Function Header ===
def _stamp_path(group_key: str) -> str:
    """Return a filesystem stamp path for a group_key."""
    gk = (group_key or "").strip()
    h = hashlib.sha256(gk.encode("utf-8", errors="ignore")).hexdigest()[:20]
    os.makedirs(STAMPS_DIR, exist_ok=True)
    return os.path.join(STAMPS_DIR, f"{h}.stamp")


# === NoemaForge Autodoc Function Header ===
# Function: _stamp_age_sec(group_key: str)
# Purpose: Implement the routine ' stamp age sec'.
# Inputs:
#   - group_key: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _stamp_path, stat, timestamp, max, exists, utcnow, float
# Returns / emits: Optional[float]
# Key locals:
#   - now, p, st
# === End NoemaForge Autodoc Function Header ===
def _stamp_age_sec(group_key: str) -> Optional[float]:
    try:
        p = _stamp_path(group_key)
        if not os.path.exists(p):
            return None
        st = os.stat(p)
        now = dt.datetime.utcnow().timestamp()
        return max(0.0, float(now) - float(st.st_mtime))
    except Exception:
        return None


# === NoemaForge Autodoc Function Header ===
# Function: _write_stamp(group_key: str)
# Purpose: Implement the routine ' write stamp'.
# Inputs:
#   - group_key: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _stamp_path, replace, open, write, chmod, _nowz, strip
# Returns / emits: None
# Side effects:
#   - reads or writes files
# Key locals:
#   - f, p, tmp
# === End NoemaForge Autodoc Function Header ===
def _write_stamp(group_key: str) -> None:
    try:
        p = _stamp_path(group_key)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(_nowz() + "\n")
            f.write(group_key.strip() + "\n")
        os.replace(tmp, p)
        try:
            os.chmod(p, 0o600)
        except Exception:
            pass
    except Exception:
        return


# === NoemaForge Autodoc Function Header ===
# Function: load_policy(path: str = DEFAULT_POLICY_PATH)
# Purpose: Implement the routine 'load policy'.
# Inputs:
#   - path: str = DEFAULT_POLICY_PATH
# Called by:
#   - src/audit_remediation.py
#   - src/bootdoctor.py
#   - src/brainctl.py
#   - src/daily_scheduler.py
#   - src/lsm.py
#   - src/maintenance.py
#   - src/resource_policy.py
#   - src/role_runner.py
# Calls:
#   - open, safe_load
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads or writes files
# Key locals:
#   - f
# === End NoemaForge Autodoc Function Header ===
def load_policy(path: str = DEFAULT_POLICY_PATH) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


# === NoemaForge Autodoc Function Header ===
# Function: _priority_order(policy: Dict[str, Any])
# Purpose: Implement the routine ' priority order'.
# Inputs:
#   - policy: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - lower, strip, get, str
# Returns / emits: List[str]
# === End NoemaForge Autodoc Function Header ===
def _priority_order(policy: Dict[str, Any]) -> List[str]:
    return [str(x).strip().lower() for x in ((policy.get("selection") or {}).get("priority_order") or [])] or [
        "critical",
        "urgent",
        "daily_sla",
        "high",
        "normal",
        "background",
    ]


# === NoemaForge Autodoc Function Header ===
# Function: _prio_index(policy: Dict[str, Any], priority_class: str)
# Purpose: Implement the routine ' prio index'.
# Inputs:
#   - policy: Dict[str, Any]
#   - priority_class: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _priority_order, lower, int, strip, index
# Returns / emits: int
# Key locals:
#   - order, p
# === End NoemaForge Autodoc Function Header ===
def _prio_index(policy: Dict[str, Any], priority_class: str) -> int:
    order = _priority_order(policy)
    p = (priority_class or "normal").strip().lower()
    try:
        return int(order.index(p))
    except Exception:
        return int(order.index("normal")) if "normal" in order else 3


# === NoemaForge Autodoc Function Header ===
# Function: _domain_cycle(policy: Dict[str, Any])
# Purpose: Implement the routine ' domain cycle'.
# Inputs:
#   - policy: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - get, upper, strip, str
# Returns / emits: List[str]
# Key locals:
#   - cyc, out
# === End NoemaForge Autodoc Function Header ===
def _domain_cycle(policy: Dict[str, Any]) -> List[str]:
    cyc = ((policy.get("selection") or {}).get("domain_cycle") or [])
    out = [str(x).strip().upper() for x in cyc if str(x).strip()]
    return out or ["WORK", "SELF_IMPROVE", "SECURITY", "PLANNED"]


# === NoemaForge Autodoc Function Header ===
# Function: _next_domain(last: str, order: List[str])
# Purpose: Implement the routine ' next domain'.
# Inputs:
#   - last: str
#   - order: List[str]
# Called by:
#   - src/maintenance.py
# Calls:
#   - upper, index, strip, len, str
# Returns / emits: str
# Key locals:
#   - i, last_u, order
# === End NoemaForge Autodoc Function Header ===
def _next_domain(last: str, order: List[str]) -> str:
    if not order:
        order = ["WORK", "SELF_IMPROVE", "SECURITY", "PLANNED"]
    last_u = str(last or "WORK").strip().upper()
    if last_u not in order:
        return order[0]
    i = order.index(last_u)
    return order[(i + 1) % len(order)]


# === NoemaForge Autodoc Function Header ===
# Function: _connect(db_path: str)
# Purpose: Implement the routine ' connect'.
# Inputs:
#   - db_path: str
# Called by:
#   - src/casebase.py
#   - src/dream_cycle.py
#   - src/knowledge/store.py
#   - src/memory_system.py
#   - src/pipelines/finance_budget.py
#   - src/roadmap.py
#   - src/task_tools.py
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
def _connect(db_path: str) -> sqlite3.Connection:
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
#   - src/roadmap.py
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
        CREATE TABLE IF NOT EXISTS tasks (
          task_id TEXT PRIMARY KEY,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          domain TEXT NOT NULL,
          priority_class TEXT NOT NULL,
          prio_index INTEGER NOT NULL,
          status TEXT NOT NULL,
          kind TEXT NOT NULL,
          module TEXT,
          title TEXT,
          description TEXT,
          payload_json TEXT,
          group_key TEXT,
          repeats INTEGER NOT NULL DEFAULT 0,
          attempts INTEGER NOT NULL DEFAULT 0,
          claimed_by TEXT,
          claimed_at TEXT,
          lease_until TEXT,
          last_error TEXT
        );
        """
    )
    con.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status_prio ON tasks(status, prio_index, created_at);")
    con.execute("CREATE INDEX IF NOT EXISTS idx_tasks_domain_status ON tasks(domain, status);")
    con.execute("CREATE INDEX IF NOT EXISTS idx_tasks_group_key ON tasks(group_key);")
    con.commit()


# === NoemaForge Autodoc Function Header ===
# Function: _db_path(policy: Dict[str, Any])
# Purpose: Implement the routine ' db path'.
# Inputs:
#   - policy: Dict[str, Any]
# Called by:
#   - src/task_tools.py
# Calls:
#   - str, get
# Returns / emits: str
# Key locals:
#   - q
# === End NoemaForge Autodoc Function Header ===
def _db_path(policy: Dict[str, Any]) -> str:
    q = policy.get("queue") or {}
    return str(q.get("db_path") or "/var/lib/noemaforge/taskqueue/taskqueue.sqlite")


# === NoemaForge Autodoc Function Header ===
# Function: _claim_lease_sec(policy: Dict[str, Any])
# Purpose: Implement the routine ' claim lease sec'.
# Inputs:
#   - policy: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - int, get
# Returns / emits: int
# Key locals:
#   - q
# === End NoemaForge Autodoc Function Header ===
def _claim_lease_sec(policy: Dict[str, Any]) -> int:
    q = policy.get("queue") or {}
    return int(q.get("claim_lease_sec", 900) or 900)


# === NoemaForge Autodoc Function Header ===
# Function: _repeat_boost(policy: Dict[str, Any])
# Purpose: Implement the routine ' repeat boost'.
# Inputs:
#   - policy: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - get, isinstance
# Returns / emits: Dict[str, Any]
# Key locals:
#   - rb
# === End NoemaForge Autodoc Function Header ===
def _repeat_boost(policy: Dict[str, Any]) -> Dict[str, Any]:
    rb = ((policy.get("selection") or {}).get("repeat_boost") or {})
    if not isinstance(rb, dict):
        return {"enabled": False}
    return rb


# === NoemaForge Autodoc Function Header ===
# Function: _promote_priority(policy: Dict[str, Any], current: str, repeats: int)
# Purpose: Implement the routine ' promote priority'.
# Inputs:
#   - policy: Dict[str, Any]
#   - current: str
#   - repeats: int
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _repeat_boost, lower, bool, get, strip, isinstance, int, _prio_index, str
# Returns / emits: str
# Key locals:
#   - best, cur, rb, t, thr, thresholds
# === End NoemaForge Autodoc Function Header ===
def _promote_priority(policy: Dict[str, Any], current: str, repeats: int) -> str:
    rb = _repeat_boost(policy)
    if not bool(rb.get("enabled", True)):
        return current

    cur = (current or "normal").strip().lower()
    thresholds = rb.get("thresholds") or []
    best = cur
    for t in thresholds:
        if not isinstance(t, dict):
            continue
        try:
            thr = int(t.get("repeats") or 0)
        except Exception:
            thr = 0
        if repeats >= thr and thr > 0:
            best = str(t.get("promote_to") or best).strip().lower()
    # Ensure we only promote "up" (lower index = higher priority)
    try:
        if _prio_index(policy, best) < _prio_index(policy, cur):
            return best
    except Exception:
        pass
    return cur


# === NoemaForge Autodoc Function Header ===
# Function: enqueue_task(policy: Optional[Dict[str, Any]] = None, domain: str, kind: str, priority_class: str = 'normal', module: str = '', title: str = '', description: str = '', payload: Optional[Dict[str, Any]] = None, group_key: str = '')
# Purpose: Insert a task. If group_key matches an existing runnable task, increment repeats.
# Inputs:
#   - policy: Optional[Dict[str, Any]] = None
#   - domain: str
#   - kind: str
#   - priority_class: str = 'normal'
#   - module: str = ''
#   - title: str = ''
#   - description: str = ''
#   - payload: Optional[Dict[str, Any]] = None
#   - group_key: str = ''
# Called by:
#   - src/audit_remediation.py
#   - src/daily_scheduler.py
#   - src/scary_sweep.py
#   - src/task_runner.py
#   - src/task_tools.py
# Calls:
#   - _db_path, upper, lower, strip, _connect, _nowz, dumps, execute, commit, close, load_policy, ValueError
# Returns / emits: Dict[str, Any]
# Side effects:
#   - serializes structured data
#   - opens a database or socket connection
#   - executes SQL or shell-like commands
# Key locals:
#   - con, db_path, dom, gk, k, new_pr, now, payload_json, policy, pr, reps, row
# === End NoemaForge Autodoc Function Header ===
def enqueue_task(
    *,
    policy: Optional[Dict[str, Any]] = None,
    domain: str,
    kind: str,
    priority_class: str = "normal",
    module: str = "",
    title: str = "",
    description: str = "",
    payload: Optional[Dict[str, Any]] = None,
    group_key: str = "",
) -> Dict[str, Any]:
    """Insert a task. If group_key matches an existing runnable task, increment repeats."""
    policy = policy or load_policy()
    db_path = _db_path(policy)

    dom = str(domain).strip().upper()
    if not dom:
        dom = "SELF_IMPROVE"

    pr = (priority_class or "normal").strip().lower()
    if not pr:
        pr = "normal"

    k = str(kind).strip()
    if not k:
        raise ValueError("missing_kind")

    gk = (group_key or "").strip() or ""

    con = _connect(db_path)
    now = _nowz()

    # De-dupe / repeat boost
    if gk:
        row = con.execute(
            """
            SELECT task_id, priority_class, repeats
            FROM tasks
            WHERE group_key=? AND status IN ('TODO','IN_PROGRESS')
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (gk,),
        ).fetchone()
        if row:
            task_id, cur_pr, reps = row
            reps = int(reps or 0) + 1
            new_pr = _promote_priority(policy, str(cur_pr or pr), reps)
            con.execute(
                """
                UPDATE tasks
                SET repeats=?, priority_class=?, prio_index=?, updated_at=?
                WHERE task_id=?
                """,
                (reps, new_pr, _prio_index(policy, new_pr), now, str(task_id)),
            )
            con.commit()
            con.close()
            return {
                "ok": True,
                "deduped": True,
                "task_id": str(task_id),
                "group_key": gk,
                "repeats": reps,
                "priority_class": new_pr,
            }

    task_id = uuid.uuid4().hex
    payload_json = json.dumps(payload or {}, ensure_ascii=False)

    con.execute(
        """
        INSERT INTO tasks(task_id, created_at, updated_at, domain, priority_class, prio_index, status, kind, module, title, description, payload_json, group_key, repeats, attempts)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            task_id,
            now,
            now,
            dom,
            pr,
            _prio_index(policy, pr),
            "TODO",
            k,
            (module or "").strip() or None,
            (title or "").strip() or None,
            (description or "").strip() or None,
            payload_json,
            gk or None,
            0,
            0,
        ),
    )
    con.commit()
    con.close()
    return {"ok": True, "deduped": False, "task_id": task_id, "domain": dom, "priority_class": pr, "group_key": gk}


# === NoemaForge Autodoc Function Header ===
# Function: ensure_default_tasks(policy: Optional[Dict[str, Any]] = None)
# Purpose: Ensure minimal default tasks exist for empty domains.
# Inputs:
#   - policy: Optional[Dict[str, Any]] = None
# Called by:
#   - src/maintenance.py
# Calls:
#   - _db_path, _connect, items, close, load_policy, get, isinstance, upper, fetchone, int, strip, _stamp_age_sec
# Returns / emits: Dict[str, Any]
# Side effects:
#   - opens a database or socket connection
# Key locals:
#   - age, cnt, con, cooldown, db_path, defaults, dom_u, gk, inserted, policy, res, t
# === End NoemaForge Autodoc Function Header ===
def ensure_default_tasks(policy: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Ensure minimal default tasks exist for empty domains."""
    policy = policy or load_policy()
    db_path = _db_path(policy)
    defaults = policy.get("default_tasks") or {}
    if not isinstance(defaults, dict):
        return {"ok": True, "inserted": []}

    inserted: List[Dict[str, Any]] = []
    con = _connect(db_path)
    for dom, tasks in defaults.items():
        dom_u = str(dom).strip().upper()
        if not dom_u:
            continue
        # Runnable means TODO
        cnt = con.execute("SELECT COUNT(*) FROM tasks WHERE domain=? AND status='TODO'", (dom_u,)).fetchone()[0]
        if int(cnt or 0) > 0:
            continue
        if not isinstance(tasks, list):
            continue
        for t in tasks:
            if not isinstance(t, dict):
                continue
            # v0.11.8: default-task cooldown, to avoid endless loops.
            gk = str(t.get("group_key") or "").strip()
            cooldown = int(t.get("cooldown_sec", 0) or 0)
            if cooldown > 0 and gk:
                age = _stamp_age_sec(gk)
                if age is not None and age < float(cooldown):
                    continue
            try:
                res = enqueue_task(
                    policy=policy,
                    domain=dom_u,
                    kind=str(t.get("kind") or "module"),
                    module=str(t.get("module") or "").strip(),
                    priority_class=str(t.get("priority_class") or "background"),
                    title=str(t.get("title") or "").strip(),
                    description=str(t.get("description") or "").strip(),
                    payload=dict(t.get("payload") or {}) if isinstance(t.get("payload"), dict) else {},
                    group_key=gk,
                )
                inserted.append(res)
            except Exception:
                continue
    con.close()
    return {"ok": True, "inserted": inserted}


# === NoemaForge Autodoc Function Header ===
# Function: enqueue_from_signal(policy: Optional[Dict[str, Any]] = None, signal_key: str, title: str = '', description: str = '')
# Purpose: Implement the routine 'enqueue from signal'.
# Inputs:
#   - policy: Optional[Dict[str, Any]] = None
#   - signal_key: str
#   - title: str = ''
#   - description: str = ''
# Called by:
#   - src/maintenance.py
# Calls:
#   - strip, enqueue_task, load_policy, get, items, isinstance, str, fnmatchcase, any, len, dict
# Returns / emits: Dict[str, Any]
# Key locals:
#   - best, best_pat, best_spec, key, m, mapping, matched, p, policy, spec
# === End NoemaForge Autodoc Function Header ===
def enqueue_from_signal(
    *,
    policy: Optional[Dict[str, Any]] = None,
    signal_key: str,
    title: str = "",
    description: str = "",
) -> Dict[str, Any]:
    policy = policy or load_policy()
    key = str(signal_key or "").strip()
    mapping = policy.get("signal_to_task") or {}

    if not key or not isinstance(mapping, dict):
        return {"ok": False, "skipped": True, "reason": "no_mapping"}

    # Support wildcard mappings (fnmatch) to avoid enumerating dynamic keys
    # like: security.toolproxy.deny.repeat.3 / .6 / .12.
    # Exact match always wins.
    m = None
    matched = ""
    if key in mapping:
        m = mapping.get(key)
        matched = key
    else:
        best = None
        best_pat = ""
        best_spec = -1
        for pat, val in mapping.items():
            if not isinstance(pat, str):
                continue
            p = pat.strip()
            if not p:
                continue
            # Only treat patterns containing wildcard syntax as patterns.
            if not any(ch in p for ch in ("*", "?", "[")):
                continue
            if fnmatch.fnmatchcase(key, p):
                # Specificity heuristic: more non-wildcard characters = more specific.
                spec = len([c for c in p if c not in "*?[]"])  # coarse but deterministic
                if spec > best_spec:
                    best_spec = spec
                    best = val
                    best_pat = p
        if best is not None:
            m = best
            matched = best_pat

    if not isinstance(m, dict):
        return {"ok": False, "skipped": True, "reason": "no_mapping"}

    return enqueue_task(
        policy=policy,
        domain=str(m.get("domain") or "SELF_IMPROVE"),
        kind=str(m.get("kind") or "module"),
        module=str(m.get("module") or "").strip(),
        priority_class=str(m.get("priority_class") or "normal"),
        title=title or str(m.get("title") or ""),
        description=description or str(m.get("description") or ""),
        payload=dict(m.get("payload") or {}) if isinstance(m.get("payload"), dict) else {},
        group_key=key,
    )


# === NoemaForge Autodoc Function Header ===
# Function: _choose_domain_for_tie(last_domain: str, domains: Iterable[str], policy: Dict[str, Any])
# Purpose: Implement the routine ' choose domain for tie'.
# Inputs:
#   - last_domain: str
#   - domains: Iterable[str]
#   - policy: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _domain_cycle, _next_domain, index, range, upper, len, strip, sorted, list, str
# Returns / emits: str
# Key locals:
#   - d, doms, i0, k, order, start
# === End NoemaForge Autodoc Function Header ===
def _choose_domain_for_tie(last_domain: str, domains: Iterable[str], policy: Dict[str, Any]) -> str:
    doms = {str(d).strip().upper() for d in domains if str(d).strip()}
    order = _domain_cycle(policy)
    start = _next_domain(last_domain, order)
    # Traverse cycle starting from "start".
    if start not in order:
        start = order[0]
    i0 = order.index(start)
    for k in range(len(order)):
        d = order[(i0 + k) % len(order)]
        if d in doms:
            return d
    # Fallback: any domain
    return sorted(list(doms))[0] if doms else "SELF_IMPROVE"


# === NoemaForge Autodoc Function Header ===
# Function: claim_next_task(policy: Optional[Dict[str, Any]] = None, last_domain: str = 'WORK', claimed_by: str = 'maintenance')
# Purpose: Pick and claim the next runnable task.
# Inputs:
#   - policy: Optional[Dict[str, Any]] = None
#   - last_domain: str = 'WORK'
#   - claimed_by: str = 'maintenance'
# Called by:
#   - src/maintenance.py
# Calls:
#   - _db_path, _claim_lease_sec, _nowz, _connect, load_policy, isoformat, fetchall, min, _choose_domain_for_tie, str, execute, fetchone
# Returns / emits: Optional[Dict[str, Any]]
# Side effects:
#   - opens a database or socket connection
#   - executes SQL or shell-like commands
# Key locals:
#   - attempts, best, cand, cand_all, chosen_dom, con, created, cur, db_path, dom, domains, eligible
# === End NoemaForge Autodoc Function Header ===
def claim_next_task(
    *,
    policy: Optional[Dict[str, Any]] = None,
    last_domain: str = "WORK",
    claimed_by: str = "maintenance",
) -> Optional[Dict[str, Any]]:
    """Pick and claim the next runnable task.

    Selection (v0.12.8):
    - Lowest prio_index first
    - Domain tie-break via cycle (relative to last_domain)
    - Within domain: repeats desc, created_at asc

    Additional gate:
    - If a task payload specifies requires_invite: <scope>, it is *ineligible*
      until that invite scope is active.

    Rationale:
    - Tasks that must never run automatically (e.g. surgeon LIVE) should not
      be endlessly retried/failed. They should simply wait.
    """
    policy = policy or load_policy()
    db_path = _db_path(policy)

    lease_sec = _claim_lease_sec(policy)
    now = _nowz()
    lease_until = (dt.datetime.utcnow() + dt.timedelta(seconds=int(lease_sec))).isoformat() + "Z"

    # Optional invite checker (spine-only).
    try:
        import invites  # type: ignore
    except Exception:
        invites = None  # type: ignore

    # === NoemaForge Autodoc Function Header ===
    # Function: invite_ok(payload: Dict[str, Any])
    # Purpose: Implement the routine 'invite ok'.
    # Inputs:
    #   - payload: Dict[str, Any]
    # Called by:
    #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
    # Calls:
    #   - strip, bool, is_active, str, get
    # Returns / emits: bool
    # Key locals:
    #   - scope
    # === End NoemaForge Autodoc Function Header ===
    def invite_ok(payload: Dict[str, Any]) -> bool:
        try:
            scope = str((payload or {}).get("requires_invite") or "").strip()
            if not scope:
                return True
            if invites is None:
                return False
            return bool(invites.is_active(scope))
        except Exception:
            return False

    con = _connect(db_path)
    try:
        # Pull a candidate set ordered by priority so we can skip invite-locked tasks
        # and still make progress on the next eligible priority.
        cand_all = con.execute(
            """
            SELECT task_id, created_at, domain, priority_class, prio_index, kind, module, title, description, payload_json, group_key, repeats, attempts
            FROM tasks
            WHERE status='TODO'
            ORDER BY prio_index ASC, created_at ASC
            LIMIT 400
            """
        ).fetchall()
        if not cand_all:
            return None

        eligible = []  # list of tuples (row, payload)
        for r in cand_all:
            payload = {}
            try:
                payload = json.loads(r[9] or "{}") if r[9] else {}
            except Exception:
                payload = {}
            if not isinstance(payload, dict):
                payload = {}
            if not invite_ok(payload):
                continue
            eligible.append((r, payload))

        if not eligible:
            return None

        min_prio = min(int(r[0][4] or 0) for r in eligible)
        cand = [(r, p) for (r, p) in eligible if int(r[4] or 0) == min_prio]
        if not cand:
            return None

        domains = [str(r[2] or "").strip().upper() for (r, _) in cand]
        chosen_dom = _choose_domain_for_tie(last_domain, domains, policy)

        # Choose best task inside domain: repeats desc, created_at asc
        best = None
        for (r, payload) in cand:
            dom = str(r[2] or "").strip().upper()
            if dom != chosen_dom:
                continue
            reps = int(r[11] or 0)
            created = str(r[1] or "")
            key = (-reps, created)
            if best is None or key < best[0]:
                best = (key, r, payload)
        if best is None:
            return None

        r = best[1]
        payload = best[2]
        task_id = str(r[0])

        # Claim atomically
        con.execute("BEGIN IMMEDIATE;")
        cur = con.execute("SELECT status, attempts FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        if not cur or str(cur[0]) != "TODO":
            con.execute("ROLLBACK;")
            return None
        attempts = int(cur[1] or 0) + 1

        con.execute(
            """
            UPDATE tasks
            SET status='IN_PROGRESS', claimed_by=?, claimed_at=?, lease_until=?, updated_at=?, attempts=?
            WHERE task_id=?
            """,
            (claimed_by, now, lease_until, now, attempts, task_id),
        )
        con.execute("COMMIT;")

        return {
            "task_id": task_id,
            "created_at": str(r[1] or ""),
            "domain": str(r[2] or "").strip().upper(),
            "priority_class": str(r[3] or ""),
            "prio_index": int(r[4] or 0),
            "kind": str(r[5] or ""),
            "module": str(r[6] or ""),
            "title": str(r[7] or ""),
            "description": str(r[8] or ""),
            "payload": payload,
            "group_key": str(r[10] or ""),
            "repeats": int(r[11] or 0),
            "attempts": attempts,
            "claimed_by": claimed_by,
            "claimed_at": now,
            "lease_until": lease_until,
        }
    finally:
        con.close()


# === NoemaForge Autodoc Function Header ===
# Function: complete_task(policy: Optional[Dict[str, Any]] = None, task_id: str, ok: bool, error: str = '', max_attempts: int = 3)
# Purpose: Implement the routine 'complete task'.
# Inputs:
#   - policy: Optional[Dict[str, Any]] = None
#   - task_id: str
#   - ok: bool
#   - error: str = ''
#   - max_attempts: int = 3
# Called by:
#   - src/maintenance.py
# Calls:
#   - _db_path, _connect, _nowz, load_policy, fetchone, commit, close, int, str, execute, startswith, _write_stamp
# Returns / emits: None
# Side effects:
#   - opens a database or socket connection
#   - executes SQL or shell-like commands
# Key locals:
#   - attempts, con, db_path, group_key, now, policy, row, status
# === End NoemaForge Autodoc Function Header ===
def complete_task(
    *,
    policy: Optional[Dict[str, Any]] = None,
    task_id: str,
    ok: bool,
    error: str = "",
    max_attempts: int = 3,
) -> None:
    policy = policy or load_policy()
    db_path = _db_path(policy)
    con = _connect(db_path)
    now = _nowz()
    try:
        row = con.execute("SELECT attempts, group_key FROM tasks WHERE task_id=?", (str(task_id),)).fetchone()
        attempts = int(row[0] or 0) if row else 0
        group_key = str(row[1] or "") if row and row[1] is not None else ""
        if ok:
            con.execute(
                """
                UPDATE tasks
                SET status='DONE', updated_at=?, last_error=NULL
                WHERE task_id=?
                """,
                (now, str(task_id)),
            )
            # Write a cooldown stamp for default tasks.
            if group_key.startswith("default."):
                _write_stamp(group_key)
        else:
            # Retry a few times; then deadletter.
            status = "TODO" if attempts < int(max_attempts) else "DEADLETTER"
            con.execute(
                """
                UPDATE tasks
                SET status=?, updated_at=?, last_error=?
                WHERE task_id=?
                """,
                (status, now, (error or "").strip()[:4000], str(task_id)),
            )
        con.commit()
    finally:
        con.close()


# === NoemaForge Autodoc Function Header ===
# Function: list_tasks(policy: Optional[Dict[str, Any]] = None, domain: str = '', status: str = '', limit: int = 50)
# Purpose: Implement the routine 'list tasks'.
# Inputs:
#   - policy: Optional[Dict[str, Any]] = None
#   - domain: str = ''
#   - status: str = ''
#   - limit: int = 50
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _db_path, _connect, load_policy, fetchall, close, append, upper, join, execute, tuple, str, int
# Returns / emits: List[Dict[str, Any]]
# Side effects:
#   - opens a database or socket connection
#   - executes SQL or shell-like commands
#   - appends to logs or files
# Key locals:
#   - args, con, db_path, out, policy, r, rows, wh, where
# === End NoemaForge Autodoc Function Header ===
def list_tasks(
    *,
    policy: Optional[Dict[str, Any]] = None,
    domain: str = "",
    status: str = "",
    limit: int = 50,
) -> List[Dict[str, Any]]:
    policy = policy or load_policy()
    db_path = _db_path(policy)
    con = _connect(db_path)
    try:
        wh = []
        args: List[Any] = []
        if domain:
            wh.append("domain=?")
            args.append(str(domain).strip().upper())
        if status:
            wh.append("status=?")
            args.append(str(status).strip().upper())
        where = ("WHERE " + " AND ".join(wh)) if wh else ""
        rows = con.execute(
            f"""
            SELECT task_id, created_at, updated_at, domain, priority_class, status, kind, module, title, group_key, repeats, attempts, last_error
            FROM tasks
            {where}
            ORDER BY created_at DESC
            LIMIT ?
            """,
            tuple(args + [max(1, int(limit))]),
        ).fetchall()
        out: List[Dict[str, Any]] = []
        for r in rows:
            out.append(
                {
                    "task_id": str(r[0]),
                    "created_at": str(r[1]),
                    "updated_at": str(r[2]),
                    "domain": str(r[3]),
                    "priority_class": str(r[4]),
                    "status": str(r[5]),
                    "kind": str(r[6]),
                    "module": str(r[7] or ""),
                    "title": str(r[8] or ""),
                    "group_key": str(r[9] or ""),
                    "repeats": int(r[10] or 0),
                    "attempts": int(r[11] or 0),
                    "last_error": str(r[12] or ""),
                }
            )
        return out
    finally:
        con.close()


# === NoemaForge Autodoc Function Header ===
# Function: has_todo_with_priority_classes(policy: Optional[Dict[str, Any]] = None, priority_classes: Optional[List[str]] = None)
# Purpose: Fast check: any runnable TODO task with any of the given priority classes.
# Inputs:
#   - policy: Optional[Dict[str, Any]] = None
#   - priority_classes: Optional[List[str]] = None
# Called by:
#   - src/maintenance.py
# Calls:
#   - _db_path, _connect, load_policy, lower, join, fetchone, bool, close, strip, len, execute, str
# Returns / emits: bool
# Side effects:
#   - opens a database or socket connection
#   - executes SQL or shell-like commands
# Key locals:
#   - con, db_path, policy, prios, qmarks, row
# === End NoemaForge Autodoc Function Header ===
def has_todo_with_priority_classes(
    *,
    policy: Optional[Dict[str, Any]] = None,
    priority_classes: Optional[List[str]] = None,
) -> bool:
    """Fast check: any runnable TODO task with any of the given priority classes."""
    policy = policy or load_policy()
    prios = [str(x).strip().lower() for x in (priority_classes or []) if str(x).strip()]
    if not prios:
        return False
    db_path = _db_path(policy)
    con = _connect(db_path)
    try:
        qmarks = ",".join(["?"] * len(prios))
        row = con.execute(
            f"SELECT 1 FROM tasks WHERE status='TODO' AND lower(priority_class) IN ({qmarks}) LIMIT 1",
            tuple(prios),
        ).fetchone()
        return bool(row)
    except Exception:
        return False
    finally:
        con.close()

