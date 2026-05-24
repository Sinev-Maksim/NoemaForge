#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/audit_remediation.py
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
# File: src/audit_remediation.py
# Purpose: Provide the module 'audit_remediation'.
# Invoked by / imported from:
#   - src/noemaforge_core.py
# Public API / entry functions:
#   - apply_on_missing_actions
# Inputs:
#   - Common path inputs: /var/lib/noemaforge, /workspace/outbox/notifications/daily_audit
#   - Imports: __future__, datetime, json, os, typing, seclog, yaml, taskqueue
# Output formats / side effects:
#   - JSON files
#   - Markdown files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""audit_remediation.py (v0.11.10)

Daily audit remediation helpers.

Purpose
-------
The daily auditor (noemaforge_core.py run-audit) produces verification signals.
In the intended NoemaForge design, verification must not end at "missing" logs.

This module turns audit failures into explicit, auditable actions:
  - enqueue remediation tasks into TaskQueue (idempotent via group_key)
  - open incidents (for scary) when configured
  - notify user via outbox markdown
  - create handoff packets for surgeon/scary

Constraints
-----------
  - No network access.
  - No runtime contract/policy changes.
  - Deterministic, best-effort, safe defaults.
"""


import datetime as dt
import json
import os
from typing import Any, Dict, List, Optional

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None

from seclog import append as sel_append

try:
    import taskqueue
except Exception:  # pragma: no cover
    taskqueue = None  # type: ignore

try:
    import incidents
except Exception:  # pragma: no cover
    incidents = None  # type: ignore


BASE = "/var/lib/noemaforge"
PACKETS_SURGEON = os.path.join(BASE, "packets", "surgeon")
PACKETS_SCARY = os.path.join(BASE, "packets", "scary")
INCIDENTS_DIR = os.path.join(BASE, "incidents", "daily_audit")
OUTBOX_NOTIF = "/workspace/outbox/notifications/daily_audit"


# === NoemaForge Autodoc Function Header ===
# Function: _nowz()
# Purpose: Implement the routine ' nowz'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - src/noemaforge_core.py
#   - src/bundles.py
#   - src/caps.py
#   - src/casebase.py
#   - src/coordinator_fanout.py
#   - src/dream_cycle.py
#   - src/fixture_bundle.py
#   - src/glove_agent.py
# Calls:
#   - isoformat, utcnow
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _nowz() -> str:
    return dt.datetime.utcnow().isoformat() + "Z"


# === NoemaForge Autodoc Function Header ===
# Function: _save_json(path: str, obj)
# Purpose: Implement the routine ' save json'.
# Inputs:
#   - path: str
#   - obj
# Called by:
#   - src/noemaforge_core.py
#   - src/fixture_bundle.py
#   - src/model_registry.py
#   - src/model_scorecards.py
#   - src/prestart.py
#   - src/roles/role_entry.py
#   - src/scary_sweep.py
#   - src/sr_cycle.py
# Calls:
#   - makedirs, dirname, open, dump
# Returns / emits: None
# Side effects:
#   - reads or writes files
#   - serializes structured data
#   - creates directories
# Key locals:
#   - f
# === End NoemaForge Autodoc Function Header ===
def _save_json(path: str, obj: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


# === NoemaForge Autodoc Function Header ===
# Function: _save_text(path: str, text: str)
# Purpose: Implement the routine ' save text'.
# Inputs:
#   - path: str
#   - text: str
# Called by:
#   - src/noemaforge_core.py
#   - src/maintenance.py
# Calls:
#   - makedirs, dirname, open, write
# Returns / emits: None
# Side effects:
#   - reads or writes files
#   - creates directories
# Key locals:
#   - f
# === End NoemaForge Autodoc Function Header ===
def _save_text(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


# === NoemaForge Autodoc Function Header ===
# Function: _find_check(aud_cfg: Dict[str, Any], check_id: str)
# Purpose: Implement the routine ' find check'.
# Inputs:
#   - aud_cfg: Dict[str, Any]
#   - check_id: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - get, isinstance, strip, str
# Returns / emits: Optional[Dict[str, Any]]
# Key locals:
#   - c
# === End NoemaForge Autodoc Function Header ===
def _find_check(aud_cfg: Dict[str, Any], check_id: str) -> Optional[Dict[str, Any]]:
    for c in aud_cfg.get("checks") or []:
        if not isinstance(c, dict):
            continue
        if str(c.get("id") or "").strip() == check_id:
            return c
    return None


# === NoemaForge Autodoc Function Header ===
# Function: _enqueue_remediation_tasks(day: str, check_id: str, missing: List[str])
# Purpose: Implement the routine ' enqueue remediation tasks'.
# Inputs:
#   - day: str
#   - check_id: str
#   - missing: List[str]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - load_policy, strip, enqueue_task, append, str
# Returns / emits: List[Dict[str, Any]]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - desc, gk, out, pol, r, tid, tid_s, title
# === End NoemaForge Autodoc Function Header ===
def _enqueue_remediation_tasks(*, day: str, check_id: str, missing: List[str]) -> List[Dict[str, Any]]:
    if not taskqueue:
        return []
    pol = taskqueue.load_policy()
    out: List[Dict[str, Any]] = []
    for tid in missing:
        tid_s = str(tid).strip()
        if not tid_s:
            continue
        gk = f"daily_sla.{day}.{tid_s}"
        title = f"Remediate daily task: {tid_s}"
        desc = f"remediation from daily audit {check_id} day={day}"
        try:
            r = taskqueue.enqueue_task(
                policy=pol,
                domain="PLANNED",
                kind="core.run_recurring",
                priority_class="daily_sla",
                title=title,
                description=desc,
                payload={"task_id": tid_s, "day": day, "source": f"audit:{check_id}"},
                group_key=gk,
            )
            out.append(r)
        except Exception:
            continue
    return out


# === NoemaForge Autodoc Function Header ===
# Function: _open_incident(day: str, check_id: str, tz: str, missing: List[str], in_progress: List[str], report_path: str = '')
# Purpose: Open (or dedupe) a daily audit incident.
# Inputs:
#   - day: str
#   - check_id: str
#   - tz: str
#   - missing: List[str]
#   - in_progress: List[str]
#   - report_path: str = ''
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - open_incident, str, makedirs, join, _save_json, list, _nowz, get
# Returns / emits: str
# Side effects:
#   - reads or writes files
#   - creates directories
# Key locals:
#   - details, meta, obj, p, title
# === End NoemaForge Autodoc Function Header ===
def _open_incident(*, day: str, check_id: str, tz: str, missing: List[str], in_progress: List[str], report_path: str = "") -> str:
    """Open (or dedupe) a daily audit incident.

    Uses incidents.py to create a first-class incident object with lifecycle.
    """
    if not incidents:
        # Fallback: legacy JSON file (best-effort).
        os.makedirs(INCIDENTS_DIR, exist_ok=True)
        p = os.path.join(INCIDENTS_DIR, f"{day}_{check_id}.json")
        obj = {
            "schema_version": "v1",
            "kind": "DailyAuditIncident",
            "created_at": _nowz(),
            "date": day,
            "timezone": tz,
            "check_id": check_id,
            "severity": "S2",
            "missing": list(missing),
            "in_progress": list(in_progress),
            "report_path": report_path,
            "notes": ["Incident opened by daily auditor remediation (legacy)."],
        }
        _save_json(p, obj)
        return p

    title = f"Daily audit missing tasks: {check_id} ({day})"
    details = {"date": day, "timezone": tz, "check_id": check_id, "missing": list(missing), "in_progress": list(in_progress), "report_path": report_path}
    meta = incidents.open_incident(
        kind="daily_audit",
        severity="S2",
        title=title,
        details=details,
        source={"subsystem": "auditor", "check_id": check_id},
        tags=["daily", "audit", "sla"],
        artifacts={"audit_report_path": report_path},
        dedupe_key=f"daily_audit:{day}:{check_id}",
    )
    return str(meta.get("path") or "")


# === NoemaForge Autodoc Function Header ===
# Function: _create_packet(to_role: str, payload: Dict[str, Any])
# Purpose: Implement the routine ' create packet'.
# Inputs:
#   - to_role: str
#   - payload: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - strftime, lower, makedirs, join, _save_json, utcnow, strip
# Returns / emits: str
# Side effects:
#   - creates directories
# Key locals:
#   - out_dir, p, safe_to, ts
# === End NoemaForge Autodoc Function Header ===
def _create_packet(*, to_role: str, payload: Dict[str, Any]) -> str:
    ts = dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    safe_to = (to_role or "").strip().lower()
    if safe_to == "surgeon":
        out_dir = PACKETS_SURGEON
    else:
        out_dir = PACKETS_SCARY
    os.makedirs(out_dir, exist_ok=True)
    p = os.path.join(out_dir, f"{ts}_daily_audit_{safe_to}.json")
    _save_json(p, payload)
    return p


# === NoemaForge Autodoc Function Header ===
# Function: _notify_user(day: str, check_id: str, missing: List[str], in_progress: List[str], actions: Dict[str, Any])
# Purpose: Implement the routine ' notify user'.
# Inputs:
#   - day: str
#   - check_id: str
#   - missing: List[str]
#   - in_progress: List[str]
#   - actions: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - makedirs, join, append, items, _save_text, len
# Returns / emits: str
# Side effects:
#   - creates directories
#   - appends to logs or files
# Key locals:
#   - md, p, t
# === End NoemaForge Autodoc Function Header ===
def _notify_user(*, day: str, check_id: str, missing: List[str], in_progress: List[str], actions: Dict[str, Any]) -> str:
    os.makedirs(OUTBOX_NOTIF, exist_ok=True)
    p = os.path.join(OUTBOX_NOTIF, f"{day}_{check_id}.md")
    md: List[str] = []
    md.append(f"# Daily audit notification: {check_id} ({day})\n\n")
    md.append(f"Missing tasks: **{len(missing)}**\n\n")
    if missing:
        for t in missing:
            md.append(f"- {t}\n")
        md.append("\n")
    if in_progress:
        md.append("## In progress\n")
        for t in in_progress:
            md.append(f"- {t}\n")
        md.append("\n")
    md.append("## Actions taken\n")
    for k, v in (actions or {}).items():
        md.append(f"- **{k}**: {v}\n")
    md.append("\n")
    md.append("Notes: This is a spine-generated notification; contracts/policies are not modified at runtime.\n")
    _save_text(p, "".join(md))
    return p


# === NoemaForge Autodoc Function Header ===
# Function: apply_on_missing_actions(aud_cfg: Dict[str, Any], check_id: str, day: str, tz: str, missing: List[str], in_progress: List[str], report_path: str = '')
# Purpose: Apply configured on_missing actions.
# Inputs:
#   - aud_cfg: Dict[str, Any]
#   - check_id: str
#   - day: str
#   - tz: str
#   - missing: List[str]
#   - in_progress: List[str]
#   - report_path: str = ''
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _find_check, isinstance, strip, append, _create_packet, get, _enqueue_remediation_tasks, len, setdefault, str, sel_append, _open_incident
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads or writes files
#   - appends to logs or files
# Key locals:
#   - a, act, actions_taken, chk, incident_path, notif_path, on_missing, p_scary, p_surgeon, remediation_tasks, rep
# === End NoemaForge Autodoc Function Header ===
def apply_on_missing_actions(
    *,
    aud_cfg: Dict[str, Any],
    check_id: str,
    day: str,
    tz: str,
    missing: List[str],
    in_progress: List[str],
    report_path: str = "",
) -> Dict[str, Any]:
    """Apply configured on_missing actions.

    Returns a report dict describing actions taken and artifact paths.
    """

    rep: Dict[str, Any] = {"ok": True, "check_id": check_id, "day": day, "actions": [], "artifacts": {}}
    chk = _find_check(aud_cfg or {}, check_id)
    on_missing = (chk.get("on_missing") or []) if isinstance(chk, dict) else []

    actions_taken: Dict[str, Any] = {}

    # Always create handoff packets when missing exists; content differs per action.
    remediation_tasks: List[Dict[str, Any]] = []
    incident_path = ""
    notif_path = ""

    for a in on_missing:
        if not isinstance(a, dict):
            continue
        act = str(a.get("action") or "").strip()
        if not act:
            continue
        rep["actions"].append(act)

        if act == "create_remediation_tasks":
            remediation_tasks = _enqueue_remediation_tasks(day=day, check_id=check_id, missing=missing)
            actions_taken["remediation_tasks_enqueued"] = len(remediation_tasks)
            rep["artifacts"].setdefault("remediation", {})["tasks"] = remediation_tasks
            try:
                sel_append(
                    {
                        "evt_id": os.urandom(8).hex(),
                        "ts": _nowz(),
                        "severity": "S1",
                        "type": "DAILY_AUDIT_REMEDIATION_ENQUEUED",
                        "actor": {"subsystem": "auditor"},
                        "decision": "enqueue",
                        "trace_id": os.urandom(8).hex(),
                        "check_id": check_id,
                        "day": day,
                        "missing": missing,
                        "enqueued": remediation_tasks,
                    }
                )
            except Exception:
                pass

        elif act == "open_incident":
            incident_path = _open_incident(day=day, check_id=check_id, tz=tz, missing=missing, in_progress=in_progress, report_path=report_path)
            actions_taken["incident"] = incident_path
            rep["artifacts"].setdefault("incident", {})["path"] = incident_path
            try:
                sel_append(
                    {
                        "evt_id": os.urandom(8).hex(),
                        "ts": _nowz(),
                        "severity": "S2",
                        "type": "DAILY_AUDIT_INCIDENT_OPENED",
                        "actor": {"subsystem": "auditor"},
                        "decision": "open_incident",
                        "trace_id": os.urandom(8).hex(),
                        "check_id": check_id,
                        "day": day,
                        "incident": incident_path,
                    }
                )
            except Exception:
                pass

        elif act == "notify_user":
            notif_path = _notify_user(day=day, check_id=check_id, missing=missing, in_progress=in_progress, actions=actions_taken)
            actions_taken["user_notification"] = notif_path
            rep["artifacts"].setdefault("notification", {})["path"] = notif_path
            try:
                sel_append(
                    {
                        "evt_id": os.urandom(8).hex(),
                        "ts": _nowz(),
                        "severity": "S1" if not missing else "S2",
                        "type": "DAILY_AUDIT_USER_NOTIFIED",
                        "actor": {"subsystem": "auditor"},
                        "decision": "notify",
                        "trace_id": os.urandom(8).hex(),
                        "check_id": check_id,
                        "day": day,
                        "path": notif_path,
                    }
                )
            except Exception:
                pass

    # Handoff packets (always when missing exists; do not depend on explicit actions)
    try:
        p_surgeon = _create_packet(
            to_role="surgeon",
            payload={
                "schema_version": "v1",
                "kind": "DailyAuditHandoff",
                "created_at": _nowz(),
                "from": {"subsystem": "auditor"},
                "to": {"role": "surgeon"},
                "date": day,
                "check_id": check_id,
                "missing": list(missing),
                "in_progress": list(in_progress),
                "remediation_tasks": remediation_tasks,
                "notification": notif_path,
                "notes": [
                    "This is a deterministic spine artifact.",
                    "Surgeon may propose pre-start improvements (no runtime contract changes).",
                ],
            },
        )
        rep["artifacts"].setdefault("handoff", {})["surgeon"] = p_surgeon
    except Exception:
        pass

    try:
        p_scary = _create_packet(
            to_role="scary",
            payload={
                "schema_version": "v1",
                "kind": "DailyAuditHandoff",
                "created_at": _nowz(),
                "from": {"subsystem": "auditor"},
                "to": {"role": "scary"},
                "date": day,
                "check_id": check_id,
                "missing": list(missing),
                "in_progress": list(in_progress),
                "incident": incident_path,
                "notification": notif_path,
                "notes": [
                    "If an incident is opened, treat it as an operational-security signal and review for anomalies.",
                    "Prefer sterile review via gloves when inspecting untrusted artifacts.",
                ],
            },
        )
        rep["artifacts"].setdefault("handoff", {})["scary"] = p_scary
    except Exception:
        pass

    rep["actions_taken"] = actions_taken
    return rep
