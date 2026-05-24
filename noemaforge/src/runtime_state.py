#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/runtime_state.py
Zone: release/package
Version: 0.31.13.alpha-patched1
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
# File: src/runtime_state.py
# Purpose: Provide the module 'runtime_state'.
# Invoked by / imported from:
#   - src/noemaforge_core.py
#   - src/maintenance.py
# Public API / entry functions:
#   - load
#   - save
#   - touch_activity
#   - mark_completed
#   - arm_idle
#   - end_auto_cycle
#   - set_state
# Inputs:
#   - Common path inputs: /var/lib/noemaforge
#   - Imports: __future__, datetime, json, os, typing
# Output formats / side effects:
#   - JSON files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""runtime_state.py (v0.12.7)

Tiny shared state for NoemaForge spine.

Why this exists:
- The spine is multi-process (teamworker timer, recurring timers, maintenance tick).
- We need a *minimal*, deterministic place to coordinate:
  - last activity timestamp
  - last completed domain
  - idle arming ("idle > 5 minutes" maintenance trigger)

This is NOT a general memory system. It's a single JSON file with atomic updates.
"""


import datetime as dt
import json
import os
from typing import Any, Dict, Optional

BASE = "/var/lib/noemaforge"
SYS_DIR = os.path.join(BASE, ".sys")
STATE_PATH = os.path.join(SYS_DIR, "runtime_state.json")


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
# Function: _default()
# Purpose: Implement the routine ' default'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Returns / emits: Dict[str, Any]
# === End NoemaForge Autodoc Function Header ===
def _default() -> Dict[str, Any]:
    return {
        "state": "ACTIVE",  # ACTIVE | IDLE_ARMED | MAINTENANCE | AUTO_CYCLE
        "last_activity_ts": None,
        "last_completed_ts": None,
        "idle_since_ts": None,
        "last_domain": "WORK",  # WORK | SELF_IMPROVE | SECURITY | PLANNED
        "last_actor": None,
        "notes": {},

        # v0.11.8: "auto cycle" mode.
        # Idea: once the idle trigger fires, we can keep dispatching queued tasks
        # (one step per maintenance tick) without waiting another idle window.
        "auto_cycle_active": False,
        "auto_cycle_started_ts": None,
        "auto_cycle_last_sr_ts": None,
        "auto_cycle_last_step_ts": None,
        "auto_cycle_steps": 0,
        "auto_cycle_last_end_ts": None,
        "auto_cycle_last_end_reason": None,
        "auto_cycle_last_end_details": {},

        # v0.12.7: cursor for translating roadmap signals -> TaskQueue tasks.
        # Stored as ISO-8601 Z timestamp.
        "roadmap_cursor_ts": None,
    }


# === NoemaForge Autodoc Function Header ===
# Function: load(path: str = STATE_PATH)
# Purpose: Implement the routine 'load'.
# Inputs:
#   - path: str = STATE_PATH
# Called by:
#   - src/brainctl.py
#   - src/noemaforge_core.py
#   - src/bundles.py
#   - src/caps.py
#   - src/daily_stats.py
#   - src/doctor.py
#   - src/fixture_bundle.py
#   - src/glove_agent.py
# Calls:
#   - _default, update, open, load
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads or writes files
# Key locals:
#   - base, f, obj
# === End NoemaForge Autodoc Function Header ===
def load(path: str = STATE_PATH) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f) or {}
        base = _default()
        base.update(obj)
        return base
    except Exception:
        return _default()


# === NoemaForge Autodoc Function Header ===
# Function: save(state: Dict[str, Any], path: str = STATE_PATH)
# Purpose: Implement the routine 'save'.
# Inputs:
#   - state: Dict[str, Any]
#   - path: str = STATE_PATH
# Called by:
#   - src/maintenance.py
# Calls:
#   - makedirs, replace, dirname, open, dump, chmod
# Returns / emits: None
# Side effects:
#   - reads or writes files
#   - serializes structured data
#   - creates directories
# Key locals:
#   - f, tmp
# === End NoemaForge Autodoc Function Header ===
def save(state: Dict[str, Any], path: str = STATE_PATH) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass


# === NoemaForge Autodoc Function Header ===
# Function: touch_activity(domain: Optional[str] = None, actor: Optional[str] = None, note: Optional[Dict[str, Any]] = None)
# Purpose: Implement the routine 'touch activity'.
# Inputs:
#   - domain: Optional[str] = None
#   - actor: Optional[str] = None
#   - note: Optional[Dict[str, Any]] = None
# Called by:
#   - src/noemaforge_core.py
#   - src/maintenance.py
# Calls:
#   - load, _nowz, save, str, setdefault, update
# Returns / emits: Dict[str, Any]
# Key locals:
#   - st
# === End NoemaForge Autodoc Function Header ===
def touch_activity(domain: Optional[str] = None, actor: Optional[str] = None, note: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    st = load()
    st["state"] = "ACTIVE"
    st["last_activity_ts"] = _nowz()
    if domain:
        st["last_domain"] = str(domain)
    if actor:
        st["last_actor"] = str(actor)
    if note:
        st.setdefault("notes", {})
        st["notes"].update(note)
    # If we are active, we are not "armed" for idle maintenance.
    st["idle_since_ts"] = None

    # Any observed activity stops auto-cycle.
    st["auto_cycle_active"] = False
    st["auto_cycle_started_ts"] = None
    st["auto_cycle_last_step_ts"] = None
    save(st)
    return st


# === NoemaForge Autodoc Function Header ===
# Function: mark_completed(domain: Optional[str] = None, actor: Optional[str] = None, note: Optional[Dict[str, Any]] = None)
# Purpose: Implement the routine 'mark completed'.
# Inputs:
#   - domain: Optional[str] = None
#   - actor: Optional[str] = None
#   - note: Optional[Dict[str, Any]] = None
# Called by:
#   - src/noemaforge_core.py
#   - src/maintenance.py
# Calls:
#   - touch_activity, _nowz, save
# Returns / emits: Dict[str, Any]
# Key locals:
#   - st
# === End NoemaForge Autodoc Function Header ===
def mark_completed(domain: Optional[str] = None, actor: Optional[str] = None, note: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    st = touch_activity(domain=domain, actor=actor, note=note)
    st["last_completed_ts"] = _nowz()
    save(st)
    return st


# === NoemaForge Autodoc Function Header ===
# Function: arm_idle(actor: str = 'system')
# Purpose: Implement the routine 'arm idle'.
# Inputs:
#   - actor: str = 'system'
# Called by:
#   - src/noemaforge_core.py
#   - src/maintenance.py
# Calls:
#   - load, save, get, _nowz
# Returns / emits: Dict[str, Any]
# Key locals:
#   - st
# === End NoemaForge Autodoc Function Header ===
def arm_idle(actor: str = "system") -> Dict[str, Any]:
    st = load()
    if st.get("state") != "IDLE_ARMED":
        st["state"] = "IDLE_ARMED"
    if not st.get("idle_since_ts"):
        st["idle_since_ts"] = _nowz()
    st["last_actor"] = actor

    # Idle arming ends auto-cycle.
    st["auto_cycle_active"] = False
    st["auto_cycle_started_ts"] = None
    st["auto_cycle_last_step_ts"] = None
    save(st)
    return st



# === NoemaForge Autodoc Function Header ===
# Function: end_auto_cycle(reason: str, actor: str = 'system', details: Optional[Dict[str, Any]] = None)
# Purpose: Record end of an AUTO_CYCLE without modifying contracts/policies.
# Inputs:
#   - reason: str
#   - actor: str = 'system'
#   - details: Optional[Dict[str, Any]] = None
# Called by:
#   - src/maintenance.py
# Calls:
#   - load, _nowz, str, save
# Returns / emits: Dict[str, Any]
# Key locals:
#   - st
# === End NoemaForge Autodoc Function Header ===
def end_auto_cycle(reason: str, actor: str = "system", details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Record end of an AUTO_CYCLE without modifying contracts/policies.

    This only records the reason/details in runtime_state for later diagnosis.
    Callers (maintenance) decide whether to arm idle or mark activity.
    """
    st = load()
    st["auto_cycle_active"] = False
    st["auto_cycle_last_end_ts"] = _nowz()
    st["auto_cycle_last_end_reason"] = str(reason or "unknown")
    st["auto_cycle_last_end_details"] = details or {}
    st["last_actor"] = actor
    save(st)
    return st

# === NoemaForge Autodoc Function Header ===
# Function: set_state(new_state: str, actor: str = 'system', note: Optional[Dict[str, Any]] = None)
# Purpose: Implement the routine 'set state'.
# Inputs:
#   - new_state: str
#   - actor: str = 'system'
#   - note: Optional[Dict[str, Any]] = None
# Called by:
#   - src/maintenance.py
# Calls:
#   - load, str, save, setdefault, update
# Returns / emits: Dict[str, Any]
# Key locals:
#   - st
# === End NoemaForge Autodoc Function Header ===
def set_state(new_state: str, actor: str = "system", note: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    st = load()
    st["state"] = str(new_state)
    st["last_actor"] = actor
    if note:
        st.setdefault("notes", {})
        st["notes"].update(note)
    save(st)
    return st
