#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/plan_mode.py
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
# File: src/plan_mode.py
# Purpose: Provide the module 'plan_mode'.
# Invoked by / imported from:
#   - src/toolproxy.py
# Public API / entry functions:
#   - load_state
#   - save_state
#   - enter
#   - approve
#   - exit
#   - status
#   - main
# Inputs:
#   - project_id
#   - --actor
#   - --objective
#   - --notes
#   - --checkpoint
#   - --note
#   - Common path inputs: /var/lib/noemaforge/projects
#   - Imports: __future__, argparse, datetime, json, os, uuid, typing
# Output formats / side effects:
#   - JSON files
#   - Markdown files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===


import argparse
import datetime as dt
import json
import os
import uuid
from typing import Any, Dict, List, Optional

BASE_DIR = "/var/lib/noemaforge/projects"


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
# Function: _project_dir(project_id: str)
# Purpose: Implement the routine ' project dir'.
# Inputs:
#   - project_id: str
# Called by:
#   - src/worktree_manager.py
# Calls:
#   - join, strip, str
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _project_dir(project_id: str) -> str:
    return os.path.join(BASE_DIR, str(project_id).strip())


# === NoemaForge Autodoc Function Header ===
# Function: _plan_dir(project_id: str)
# Purpose: Implement the routine ' plan dir'.
# Inputs:
#   - project_id: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - join, _project_dir
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _plan_dir(project_id: str) -> str:
    return os.path.join(_project_dir(project_id), "plan_mode")


# === NoemaForge Autodoc Function Header ===
# Function: _state_path(project_id: str)
# Purpose: Implement the routine ' state path'.
# Inputs:
#   - project_id: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - join, _plan_dir
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _state_path(project_id: str) -> str:
    return os.path.join(_plan_dir(project_id), "state.json")


# === NoemaForge Autodoc Function Header ===
# Function: _history_path(project_id: str)
# Purpose: Implement the routine ' history path'.
# Inputs:
#   - project_id: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - join, _plan_dir
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _history_path(project_id: str) -> str:
    return os.path.join(_plan_dir(project_id), "history.jsonl")


# === NoemaForge Autodoc Function Header ===
# Function: _plan_md_path(project_id: str)
# Purpose: Implement the routine ' plan md path'.
# Inputs:
#   - project_id: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - join, _plan_dir
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _plan_md_path(project_id: str) -> str:
    return os.path.join(_plan_dir(project_id), "latest-plan.md")


# === NoemaForge Autodoc Function Header ===
# Function: _ensure(project_id: str)
# Purpose: Implement the routine ' ensure'.
# Inputs:
#   - project_id: str
# Called by:
#   - src/notifier.py
#   - src/worktree_manager.py
# Calls:
#   - _plan_dir, makedirs
# Returns / emits: str
# Side effects:
#   - creates directories
# Key locals:
#   - pdir
# === End NoemaForge Autodoc Function Header ===
def _ensure(project_id: str) -> str:
    pdir = _plan_dir(project_id)
    os.makedirs(pdir, exist_ok=True)
    return pdir


# === NoemaForge Autodoc Function Header ===
# Function: _append_history(project_id: str, event: Dict[str, Any])
# Purpose: Implement the routine ' append history'.
# Inputs:
#   - project_id: str
#   - event: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _ensure, _history_path, open, write, dumps
# Returns / emits: None
# Side effects:
#   - reads or writes files
#   - serializes structured data
# Key locals:
#   - f, path
# === End NoemaForge Autodoc Function Header ===
def _append_history(project_id: str, event: Dict[str, Any]) -> None:
    _ensure(project_id)
    path = _history_path(project_id)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


# === NoemaForge Autodoc Function Header ===
# Function: load_state(project_id: str)
# Purpose: Implement the routine 'load state'.
# Inputs:
#   - project_id: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - open, load, isinstance, _state_path
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads or writes files
# Key locals:
#   - f, obj
# === End NoemaForge Autodoc Function Header ===
def load_state(project_id: str) -> Dict[str, Any]:
    try:
        with open(_state_path(project_id), "r", encoding="utf-8") as f:
            obj = json.load(f)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


# === NoemaForge Autodoc Function Header ===
# Function: save_state(project_id: str, state: Dict[str, Any])
# Purpose: Implement the routine 'save state'.
# Inputs:
#   - project_id: str
#   - state: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _ensure, replace, _state_path, open, dump
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads or writes files
#   - serializes structured data
# Key locals:
#   - f, tmp
# === End NoemaForge Autodoc Function Header ===
def save_state(project_id: str, state: Dict[str, Any]) -> Dict[str, Any]:
    _ensure(project_id)
    tmp = _state_path(project_id) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _state_path(project_id))
    return state


# === NoemaForge Autodoc Function Header ===
# Function: _write_plan_markdown(project_id: str, state: Dict[str, Any])
# Purpose: Implement the routine ' write plan markdown'.
# Inputs:
#   - project_id: str
#   - state: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _ensure, append, get, _plan_md_path, isinstance, open, write, strip, str, join
# Returns / emits: str
# Side effects:
#   - reads or writes files
#   - appends to logs or files
# Key locals:
#   - cp, cps, f, md, path
# === End NoemaForge Autodoc Function Header ===
def _write_plan_markdown(project_id: str, state: Dict[str, Any]) -> str:
    _ensure(project_id)
    md = []
    md.append(f"# Plan Mode — {project_id}")
    md.append("")
    md.append(f"- Session: `{state.get('session_id', '')}`")
    md.append(f"- Status: `{state.get('status', 'inactive')}`")
    md.append(f"- Entered at: `{state.get('entered_at', '')}`")
    if state.get("approved_at"):
        md.append(f"- Approved at: `{state.get('approved_at', '')}`")
    md.append("")
    md.append("## Objective")
    md.append(str(state.get("objective") or "").strip() or "_not specified_")
    md.append("")
    md.append("## Notes")
    md.append(str(state.get("notes") or "").strip() or "_none_")
    md.append("")
    md.append("## Checkpoints")
    cps = state.get("checkpoints") or []
    if isinstance(cps, list) and cps:
        for cp in cps:
            md.append(f"- {str(cp).strip()}")
    else:
        md.append("- Explore relevant code paths")
        md.append("- Choose implementation approach")
        md.append("- Define verification criteria")
    md.append("")
    if state.get("approval_note"):
        md.append("## Approval")
        md.append(str(state.get("approval_note") or "").strip())
        md.append("")
    path = _plan_md_path(project_id)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(md).strip() + "\n")
    return path


# === NoemaForge Autodoc Function Header ===
# Function: enter(project_id: str, actor: str = 'toolproxy', objective: str = '', notes: str = '', checkpoints: Optional[List[str]] = None)
# Purpose: Implement the routine 'enter'.
# Inputs:
#   - project_id: str
#   - actor: str = 'toolproxy'
#   - objective: str = ''
#   - notes: str = ''
#   - checkpoints: Optional[List[str]] = None
# Called by:
#   - src/toolproxy.py
#   - src/worktree_manager.py
# Calls:
#   - load_state, save_state, _write_plan_markdown, _append_history, strip, ValueError, _nowz, uuid4, str
# Returns / emits: Dict[str, Any]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - plan_path, prev, state
# === End NoemaForge Autodoc Function Header ===
def enter(
    *,
    project_id: str,
    actor: str = "toolproxy",
    objective: str = "",
    notes: str = "",
    checkpoints: Optional[List[str]] = None,
) -> Dict[str, Any]:
    if not str(project_id).strip():
        raise ValueError("missing_project_id")
    prev = load_state(project_id)
    state = {
        "kind": "NoemaForgePlanModeState",
        "version": "0.26.0",
        "project_id": project_id,
        "session_id": uuid.uuid4().hex,
        "status": "plan",
        "objective": str(objective or "").strip(),
        "notes": str(notes or "").strip(),
        "checkpoints": [str(x).strip() for x in (checkpoints or []) if str(x).strip()],
        "entered_at": _nowz(),
        "approved_at": None,
        "approval_note": "",
        "exited_at": None,
        "actor": actor,
        "previous_state": prev or None,
    }
    save_state(project_id, state)
    plan_path = _write_plan_markdown(project_id, state)
    _append_history(project_id, {"at": _nowz(), "event": "enter", "actor": actor, "session_id": state["session_id"]})
    return {"ok": True, "state": state, "plan_path": plan_path}


# === NoemaForge Autodoc Function Header ===
# Function: approve(project_id: str, actor: str = 'toolproxy', note: str = '')
# Purpose: Implement the routine 'approve'.
# Inputs:
#   - project_id: str
#   - actor: str = 'toolproxy'
#   - note: str = ''
# Called by:
#   - src/toolproxy.py
# Calls:
#   - load_state, _nowz, strip, save_state, _write_plan_markdown, _append_history, ValueError, str, get
# Returns / emits: Dict[str, Any]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - plan_path, state
# === End NoemaForge Autodoc Function Header ===
def approve(*, project_id: str, actor: str = "toolproxy", note: str = "") -> Dict[str, Any]:
    state = load_state(project_id)
    if not state:
        raise ValueError("plan_state_missing")
    state["status"] = "approved"
    state["approved_at"] = _nowz()
    state["approval_note"] = str(note or "").strip()
    save_state(project_id, state)
    plan_path = _write_plan_markdown(project_id, state)
    _append_history(project_id, {"at": _nowz(), "event": "approve", "actor": actor, "session_id": state.get("session_id")})
    return {"ok": True, "state": state, "plan_path": plan_path}


# === NoemaForge Autodoc Function Header ===
# Function: exit(project_id: str, actor: str = 'toolproxy', note: str = '')
# Purpose: Implement the routine 'exit'.
# Inputs:
#   - project_id: str
#   - actor: str = 'toolproxy'
#   - note: str = ''
# Called by:
#   - src/localgw_uplink_agent.py
#   - src/toolproxy.py
#   - src/worktree_manager.py
#   - tools/sim/simulate_prestart.py
# Calls:
#   - load_state, strip, _nowz, save_state, _append_history, str, get
# Returns / emits: Dict[str, Any]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - state
# === End NoemaForge Autodoc Function Header ===
def exit(*, project_id: str, actor: str = "toolproxy", note: str = "") -> Dict[str, Any]:
    state = load_state(project_id)
    if not state:
        return {"ok": True, "state": {"project_id": project_id, "status": "inactive"}}
    state["status"] = "inactive"
    state["exit_note"] = str(note or "").strip()
    state["exited_at"] = _nowz()
    save_state(project_id, state)
    _append_history(project_id, {"at": _nowz(), "event": "exit", "actor": actor, "session_id": state.get("session_id")})
    return {"ok": True, "state": state}


# === NoemaForge Autodoc Function Header ===
# Function: status(project_id: str)
# Purpose: Implement the routine 'status'.
# Inputs:
#   - project_id: str
# Called by:
#   - src/toolproxy.py
#   - src/worktree_manager.py
# Calls:
#   - load_state, _plan_md_path, _history_path
# Returns / emits: Dict[str, Any]
# Key locals:
#   - st
# === End NoemaForge Autodoc Function Header ===
def status(project_id: str) -> Dict[str, Any]:
    st = load_state(project_id)
    if st:
        st["plan_path"] = _plan_md_path(project_id)
        st["history_path"] = _history_path(project_id)
        return {"ok": True, "state": st}
    return {"ok": True, "state": {"project_id": project_id, "status": "inactive"}}


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
#   - ArgumentParser, add_subparsers, add_parser, add_argument, parse_args, print, enter, dumps, approve, exit, status
# Returns / emits: int
# Side effects:
#   - serializes structured data
# Key locals:
#   - ap, ns, out, p, sub
# === End NoemaForge Autodoc Function Header ===
def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("enter")
    p.add_argument("project_id")
    p.add_argument("--actor", default="cli")
    p.add_argument("--objective", default="")
    p.add_argument("--notes", default="")
    p.add_argument("--checkpoint", action="append", default=[])

    p = sub.add_parser("approve")
    p.add_argument("project_id")
    p.add_argument("--actor", default="cli")
    p.add_argument("--note", default="")

    p = sub.add_parser("exit")
    p.add_argument("project_id")
    p.add_argument("--actor", default="cli")
    p.add_argument("--note", default="")

    p = sub.add_parser("status")
    p.add_argument("project_id")

    ns = ap.parse_args(argv)
    if ns.cmd == "enter":
        out = enter(project_id=ns.project_id, actor=ns.actor, objective=ns.objective, notes=ns.notes, checkpoints=ns.checkpoint)
    elif ns.cmd == "approve":
        out = approve(project_id=ns.project_id, actor=ns.actor, note=ns.note)
    elif ns.cmd == "exit":
        out = exit(project_id=ns.project_id, actor=ns.actor, note=ns.note)
    else:
        out = status(ns.project_id)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
