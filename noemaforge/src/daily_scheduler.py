#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/daily_scheduler.py
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
# File: src/daily_scheduler.py
# Purpose: Provide the module 'daily_scheduler'.
# Invoked by / imported from:
#   - src/maintenance.py
# Public API / entry functions:
#   - enqueue_due_recurring
#   - enqueue_due_audits
# Inputs:
#   - Common path inputs: /opt/noemaforge/configs/recurring-tasks.yaml, /opt/noemaforge/configs/daily-auditor.yaml, /var/lib/noemaforge/routines, /var/lib/noemaforge/.sys/locks, Europe/Lisbon
#   - Imports: __future__, datetime, os, typing, yaml, daily_stats, taskqueue, zoneinfo
# Output formats / side effects:
#   - JSON files
#   - YAML files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""daily_scheduler.py (v0.11.9)

Enqueue daily recurring tasks and audit checks into TaskQueue.

Why
---
Historically, maintenance.py executed must-run daily tasks directly (run-recurring).
That ensured deadlines, but bypassed the explicit TaskQueue that SR/SSR use.

v0.11.9 changes this:
  - must-run recurring tasks are *enqueued* as TaskQueue tasks (kind=core.run_recurring)
  - daily auditor checks are also *enqueued* (kind=core.run_audit)

Benefits
--------
  - daily work is visible/auditable as backlog items
  - the same one-step-per-tick engine runs them (AUTO_CYCLE or direct preemption)
  - verification becomes an explicit task (audit checks)

This module is deterministic, offline-only, and safe for the spine.
"""


import datetime as dt
import os
from typing import Any, Dict, List, Optional, Tuple

import yaml

from daily_stats import mean_sigma
import taskqueue


REC_CFG = "/opt/noemaforge/configs/recurring-tasks.yaml"
AUD_CFG = "/opt/noemaforge/configs/daily-auditor.yaml"

ROUTINES_DIR = "/var/lib/noemaforge/routines"
LOCKS_DIR = "/var/lib/noemaforge/.sys/locks"


# === NoemaForge Autodoc Function Header ===
# Function: _load_yaml(path: str)
# Purpose: Implement the routine ' load yaml'.
# Inputs:
#   - path: str
# Called by:
#   - src/brainctl.py
#   - src/noemaforge_core.py
#   - src/canary_runner.py
#   - src/fixture_bundle.py
#   - src/flow_metrics.py
#   - src/incidents.py
#   - src/knowledge/policy.py
#   - src/llm_backends_manager.py
# Calls:
#   - open, safe_load
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads or writes files
# Key locals:
#   - f
# === End NoemaForge Autodoc Function Header ===
def _load_yaml(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


# === NoemaForge Autodoc Function Header ===
# Function: _parse_hhmm(s: str)
# Purpose: Implement the routine ' parse hhmm'.
# Inputs:
#   - s: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - split, len, int, strip
# Returns / emits: Tuple[int, int]
# Key locals:
#   - parts
# === End NoemaForge Autodoc Function Header ===
def _parse_hhmm(s: str) -> Tuple[int, int]:
    parts = (s or "").strip().split(":")
    if len(parts) < 2:
        return 0, 0
    return int(parts[0]), int(parts[1])


# === NoemaForge Autodoc Function Header ===
# Function: _parse_oncalendar_time(s: str)
# Purpose: Parse schedule_oncalendar like '*-*-* 09:00:00' -> (9,0).
# Inputs:
#   - s: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - strip, split, _parse_hhmm
# Returns / emits: Optional[Tuple[int, int]]
# Key locals:
#   - tail, txt
# === End NoemaForge Autodoc Function Header ===
def _parse_oncalendar_time(s: str) -> Optional[Tuple[int, int]]:
    """Parse schedule_oncalendar like '*-*-* 09:00:00' -> (9,0)."""
    txt = (s or "").strip()
    if not txt or " " not in txt:
        return None
    tail = txt.split()[-1]
    if ":" not in tail:
        return None
    try:
        hh, mm = _parse_hhmm(tail)
        return hh, mm
    except Exception:
        return None


# === NoemaForge Autodoc Function Header ===
# Function: _tz_now(tz: str)
# Purpose: Implement the routine ' tz now'.
# Inputs:
#   - tz: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - now, ZoneInfo
# Returns / emits: dt.datetime
# === End NoemaForge Autodoc Function Header ===
def _tz_now(tz: str) -> dt.datetime:
    try:
        from zoneinfo import ZoneInfo

        return dt.datetime.now(ZoneInfo(tz))
    except Exception:
        return dt.datetime.now()


# === NoemaForge Autodoc Function Header ===
# Function: _today_str(now: dt.datetime)
# Purpose: Implement the routine ' today str'.
# Inputs:
#   - now: dt.datetime
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - strftime
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _today_str(now: dt.datetime) -> str:
    return now.strftime("%Y-%m-%d")


# === NoemaForge Autodoc Function Header ===
# Function: _run_marker_for_audit(day: str, check_id: str)
# Purpose: Implement the routine ' run marker for audit'.
# Inputs:
#   - day: str
#   - check_id: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - join
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _run_marker_for_audit(day: str, check_id: str) -> str:
    return os.path.join(ROUTINES_DIR, "audit", "runs", f"{day}_{check_id}.json")


# === NoemaForge Autodoc Function Header ===
# Function: _rec_run_marker(day: str, task_id: str)
# Purpose: Implement the routine ' rec run marker'.
# Inputs:
#   - day: str
#   - task_id: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - join
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _rec_run_marker(day: str, task_id: str) -> str:
    return os.path.join(ROUTINES_DIR, "runs", f"{day}_{task_id}.json")


# === NoemaForge Autodoc Function Header ===
# Function: _rec_lock(task_id: str)
# Purpose: Implement the routine ' rec lock'.
# Inputs:
#   - task_id: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - join
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _rec_lock(task_id: str) -> str:
    return os.path.join(LOCKS_DIR, f"recurring_{task_id}.lock")


# === NoemaForge Autodoc Function Header ===
# Function: enqueue_due_recurring(maintenance_cfg: Optional[Dict[str, Any]] = None, taskqueue_policy: Optional[Dict[str, Any]] = None, now_local: Optional[dt.datetime] = None)
# Purpose: Enqueue due must-run recurring tasks.
# Inputs:
#   - maintenance_cfg: Optional[Dict[str, Any]] = None
#   - taskqueue_policy: Optional[Dict[str, Any]] = None
#   - now_local: Optional[dt.datetime] = None
# Called by:
#   - src/maintenance.py
# Calls:
#   - _load_yaml, str, _today_str, float, load_policy, _tz_now, get, strip, _parse_hhmm, replace, _parse_oncalendar_time, mean_sigma
# Returns / emits: Dict[str, Any]
# Key locals:
#   - day, deadline, deadline_s, desc, enqueue_at, enqueued, fallback_mean, fallback_sigma, gk, in_progress, maintenance_cfg, mean
# === End NoemaForge Autodoc Function Header ===
def enqueue_due_recurring(
    *,
    maintenance_cfg: Optional[Dict[str, Any]] = None,
    taskqueue_policy: Optional[Dict[str, Any]] = None,
    now_local: Optional[dt.datetime] = None,
) -> Dict[str, Any]:
    """Enqueue due must-run recurring tasks.

    Trigger rule:
      enqueue_at = max(schedule_oncalendar_time, deadline - (mean + sigma))

    We enqueue (not execute) as TaskQueue tasks:
      kind = core.run_recurring
      payload.task_id = <id>
      group_key = daily_sla.<day>.<id>
    """

    maintenance_cfg = maintenance_cfg or {}
    taskqueue_policy = taskqueue_policy or taskqueue.load_policy()

    rec = _load_yaml(REC_CFG)
    tz = str(rec.get("timezone") or (maintenance_cfg.get("daily_sla") or {}).get("timezone") or "Europe/Lisbon")

    now = now_local or _tz_now(tz)
    day = _today_str(now)

    fallback_mean = float(((maintenance_cfg.get("daily_sla") or {}).get("fallback_mean_sec", 1800)) or 1800)
    fallback_sigma = float(((maintenance_cfg.get("daily_sla") or {}).get("fallback_sigma_sec", 600)) or 600)

    enqueued: List[Dict[str, Any]] = []
    missed: List[str] = []
    in_progress: List[str] = []

    for t in rec.get("tasks") or []:
        tid = str(t.get("id") or "").strip()
        if not tid:
            continue
        if not bool(t.get("must_run")):
            continue

        pr = str(t.get("priority_class") or "daily_sla").strip().lower() or "daily_sla"

        deadline_s = str(t.get("deadline_local") or "").strip()
        if not deadline_s:
            continue
        hh, mm = _parse_hhmm(deadline_s)
        deadline = now.replace(hour=hh, minute=mm, second=0, microsecond=0)

        # Earliest schedule time if present
        sched = None
        st = _parse_oncalendar_time(str(t.get("schedule_oncalendar") or ""))
        if st is not None:
            sh, sm = st
            sched = now.replace(hour=sh, minute=sm, second=0, microsecond=0)

        mean, sigma, n = mean_sigma(tid)
        if n < 2:
            mean = mean if mean > 0 else fallback_mean
            sigma = sigma if sigma > 0 else fallback_sigma

        start_by = deadline - dt.timedelta(seconds=(mean + sigma))
        enqueue_at = start_by
        if sched is not None and sched > enqueue_at:
            enqueue_at = sched

        # Done today?
        run_marker = _rec_run_marker(day, tid)
        if os.path.exists(run_marker):
            continue

        # In progress?
        if os.path.exists(_rec_lock(tid)):
            in_progress.append(tid)
            continue

        if now >= deadline:
            missed.append(tid)

        if now < enqueue_at:
            continue

        title = str(t.get("title") or tid)
        desc = f"daily_sla day={day} deadline={deadline_s} enqueue_at={enqueue_at.strftime('%H:%M')}"

        gk = f"daily_sla.{day}.{tid}"
        try:
            r = taskqueue.enqueue_task(
                policy=taskqueue_policy,
                domain="PLANNED",
                kind="core.run_recurring",
                priority_class=pr,
                title=title,
                description=desc,
                payload={"task_id": tid, "day": day},
                group_key=gk,
            )
            enqueued.append(r)
        except Exception:
            continue

    return {"ok": True, "day": day, "timezone": tz, "enqueued": enqueued, "missed": missed, "in_progress": in_progress}


# === NoemaForge Autodoc Function Header ===
# Function: enqueue_due_audits(maintenance_cfg: Optional[Dict[str, Any]] = None, taskqueue_policy: Optional[Dict[str, Any]] = None, now_local: Optional[dt.datetime] = None)
# Purpose: Enqueue due daily auditor checks as explicit verification tasks.
# Inputs:
#   - maintenance_cfg: Optional[Dict[str, Any]] = None
#   - taskqueue_policy: Optional[Dict[str, Any]] = None
#   - now_local: Optional[dt.datetime] = None
# Called by:
#   - src/maintenance.py
# Calls:
#   - _load_yaml, str, _today_str, load_policy, _tz_now, get, strip, _parse_oncalendar_time, replace, _run_marker_for_audit, exists, isinstance
# Returns / emits: Dict[str, Any]
# Side effects:
#   - spawns subprocesses or workers
# Key locals:
#   - aud, chk, cid, day, desc, enqueued, gk, maintenance_cfg, marker, now, r, scheduled
# === End NoemaForge Autodoc Function Header ===
def enqueue_due_audits(
    *,
    maintenance_cfg: Optional[Dict[str, Any]] = None,
    taskqueue_policy: Optional[Dict[str, Any]] = None,
    now_local: Optional[dt.datetime] = None,
) -> Dict[str, Any]:
    """Enqueue due daily auditor checks as explicit verification tasks."""
    maintenance_cfg = maintenance_cfg or {}
    taskqueue_policy = taskqueue_policy or taskqueue.load_policy()

    aud = _load_yaml(AUD_CFG)
    tz = str(aud.get("timezone") or (maintenance_cfg.get("daily_sla") or {}).get("timezone") or "Europe/Lisbon")
    now = now_local or _tz_now(tz)
    day = _today_str(now)

    enqueued: List[Dict[str, Any]] = []

    for chk in aud.get("checks") or []:
        if not isinstance(chk, dict):
            continue
        cid = str(chk.get("id") or "").strip()
        if not cid:
            continue
        st = _parse_oncalendar_time(str(chk.get("schedule_oncalendar") or ""))
        if st is None:
            continue
        hh, mm = st
        scheduled = now.replace(hour=hh, minute=mm, second=0, microsecond=0)

        marker = _run_marker_for_audit(day, cid)
        if os.path.exists(marker):
            continue

        if now < scheduled:
            continue

        gk = f"audit.{day}.{cid}"
        title = f"Daily audit: {cid}"
        desc = f"audit_check day={day} scheduled={scheduled.strftime('%H:%M')}"
        try:
            r = taskqueue.enqueue_task(
                policy=taskqueue_policy,
                domain="PLANNED",
                kind="core.run_audit",
                priority_class="daily_sla",
                title=title,
                description=desc,
                payload={"check_id": cid, "day": day},
                group_key=gk,
            )
            enqueued.append(r)
        except Exception:
            continue

    return {"ok": True, "day": day, "timezone": tz, "enqueued": enqueued}
