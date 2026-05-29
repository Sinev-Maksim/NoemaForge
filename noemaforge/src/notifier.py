#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/notifier.py
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
# File: src/notifier.py
# Purpose: Provide the module 'notifier'.
# Invoked by / imported from:
#   - src/toolproxy.py
# Public API / entry functions:
#   - emit
#   - list_notifications
#   - ack
# Inputs:
#   - severity
#   - message
#   - --project-id
#   - --limit
#   - --only-unacked
#   - notification_id
#   - Common path inputs: /var/lib/noemaforge/outbox
#   - Imports: __future__, datetime, json, os, uuid, typing, argparse
# Output formats / side effects:
#   - JSON files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===


import datetime as dt
import json
import os
import uuid
from typing import Any, Dict, List, Optional

BASE = "/var/lib/noemaforge/outbox"
NOTIFICATIONS = os.path.join(BASE, "notifications.jsonl")
ACKS = os.path.join(BASE, "notifications.acks.json")


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
# Function: _ensure()
# Purpose: Implement the routine ' ensure'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - src/plan_mode.py
#   - src/worktree_manager.py
# Calls:
#   - makedirs
# Returns / emits: None
# Side effects:
#   - creates directories
# === End NoemaForge Autodoc Function Header ===
def _ensure() -> None:
    os.makedirs(BASE, exist_ok=True)


# === NoemaForge Autodoc Function Header ===
# Function: _load_acks()
# Purpose: Implement the routine ' load acks'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - open, load
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads or writes files
# Key locals:
#   - f
# === End NoemaForge Autodoc Function Header ===
def _load_acks() -> Dict[str, Any]:
    try:
        with open(ACKS, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


# === NoemaForge Autodoc Function Header ===
# Function: _save_acks(doc: Dict[str, Any])
# Purpose: Implement the routine ' save acks'.
# Inputs:
#   - doc: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _ensure, replace, open, dump
# Returns / emits: None
# Side effects:
#   - reads or writes files
#   - serializes structured data
# Key locals:
#   - f, tmp
# === End NoemaForge Autodoc Function Header ===
def _save_acks(doc: Dict[str, Any]) -> None:
    _ensure()
    tmp = ACKS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    os.replace(tmp, ACKS)


# === NoemaForge Autodoc Function Header ===
# Function: emit(severity: str, message: str, project_id: str = '', links: Optional[List[Dict[str, Any]]] = None, topic: str = '', actor: str = 'toolproxy')
# Purpose: Implement the routine 'emit'.
# Inputs:
#   - severity: str
#   - message: str
#   - project_id: str = ''
#   - links: Optional[List[Dict[str, Any]]] = None
#   - topic: str = ''
#   - actor: str = 'toolproxy'
# Called by:
#   - src/toolproxy.py
# Calls:
#   - _ensure, strip, ValueError, _nowz, lower, open, write, uuid4, str, dumps
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads or writes files
#   - serializes structured data
# Key locals:
#   - f, obj
# === End NoemaForge Autodoc Function Header ===
def emit(
    *,
    severity: str,
    message: str,
    project_id: str = "",
    links: Optional[List[Dict[str, Any]]] = None,
    topic: str = "",
    actor: str = "toolproxy",
) -> Dict[str, Any]:
    if not str(message).strip():
        raise ValueError("missing_message")
    _ensure()
    obj = {
        "notification_id": uuid.uuid4().hex,
        "created_at": _nowz(),
        "project_id": str(project_id or "").strip(),
        "severity": str(severity or "info").strip().lower(),
        "message": str(message).strip(),
        "topic": str(topic or "").strip(),
        "links": links or [],
        "actor": actor,
    }
    with open(NOTIFICATIONS, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")
    return {"ok": True, "notification": obj}


# === NoemaForge Autodoc Function Header ===
# Function: list_notifications(limit: int = 50, only_unacked: bool = False)
# Purpose: Implement the routine 'list notifications'.
# Inputs:
#   - limit: int = 50
#   - only_unacked: bool = False
# Called by:
#   - src/toolproxy.py
# Calls:
#   - _ensure, _load_acks, exists, reverse, open, strip, str, bool, append, max, loads, get
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads or writes files
#   - appends to logs or files
# Key locals:
#   - acks, f, ln, nid, obj, rows
# === End NoemaForge Autodoc Function Header ===
def list_notifications(limit: int = 50, only_unacked: bool = False) -> Dict[str, Any]:
    _ensure()
    acks = _load_acks()
    rows = []
    if os.path.exists(NOTIFICATIONS):
        with open(NOTIFICATIONS, "r", encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    obj = json.loads(ln)
                except Exception:
                    continue
                nid = str(obj.get("notification_id") or "")
                obj["acked"] = bool(acks.get(nid))
                if only_unacked and obj["acked"]:
                    continue
                rows.append(obj)
    rows = rows[-max(1, int(limit)) :]
    rows.reverse()
    return {"ok": True, "notifications": rows}


# === NoemaForge Autodoc Function Header ===
# Function: ack(notification_id: str, actor: str = 'toolproxy')
# Purpose: Implement the routine 'ack'.
# Inputs:
#   - notification_id: str
#   - actor: str = 'toolproxy'
# Called by:
#   - src/toolproxy.py
# Calls:
#   - _load_acks, _save_acks, str, _nowz
# Returns / emits: Dict[str, Any]
# Key locals:
#   - acks
# === End NoemaForge Autodoc Function Header ===
def ack(notification_id: str, actor: str = "toolproxy") -> Dict[str, Any]:
    acks = _load_acks()
    acks[str(notification_id)] = {"acked_at": _nowz(), "actor": actor}
    _save_acks(acks)
    return {"ok": True, "notification_id": notification_id, "ack": acks[str(notification_id)]}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("emit")
    p.add_argument("severity")
    p.add_argument("message")
    p.add_argument("--project-id", default="")
    p = sub.add_parser("list")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--only-unacked", action="store_true")
    p = sub.add_parser("ack")
    p.add_argument("notification_id")
    ns = ap.parse_args()
    if ns.cmd == "emit":
        out = emit(severity=ns.severity, message=ns.message, project_id=ns.project_id)
    elif ns.cmd == "list":
        out = list_notifications(limit=ns.limit, only_unacked=ns.only_unacked)
    else:
        out = ack(ns.notification_id)
    print(json.dumps(out, ensure_ascii=False, indent=2))
