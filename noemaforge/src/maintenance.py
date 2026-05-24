#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/maintenance.py
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
# File: src/maintenance.py
# Purpose: Run idle-cycle maintenance, scheduling, resource recovery, and background system housekeeping.
# Invoked by / imported from:
#   - No inbound Python import detected; treat as library leaf or direct entrypoint.
# Public API / entry functions:
#   - is_busy
#   - daily_sla_enqueue
#   - dispatch_domain
#   - dispatch_one_task
#   - idle_cycle
#   - auto_cycle_step
#   - tick
#   - main
# Inputs:
#   - Common path inputs: /var/lib/noemaforge, /opt/noemaforge/configs/maintenance-policy.yaml, /workspace/outbox/system/auto_cycle, /opt/noemaforge/src/surgeon_auto.py, /opt/noemaforge/src/scary_sweep.py, /opt/noemaforge/src/planned_sweep.py
#   - Imports: __future__, datetime, os, subprocess, sys, typing, yaml, seclog
# Output formats / side effects:
#   - JSON files
#   - YAML files
#   - Markdown files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""maintenance.py (v0.12.7)

Maintenance tick (spine).

Trigger:
- Runs periodically (systemd timer).

Lifecycle (v0.11.8):
- When the system becomes idle, we "arm" the idle timer.
- Once idle for > idle_trigger_sec, we enter an AUTO_CYCLE:
    1) SR (deterministic SR-lite + roadmap artifacts + handoffs)
    2) SSR (deterministic safety reflection + roadmap artifacts + handoff)
    3) Resource recovery (cleanup tokens/workdirs; optionally stop extra LLM backends)
    4) Dispatch ONE queued task (TaskQueue)
- While AUTO_CYCLE is active, *each tick* dispatches ONE queued task without
  requiring another idle wait window.

v0.12.7:
- Roadmap cursor bridge: all new roadmap signals (including those emitted by
  Incidents/ToolProxy outside SR/SSR) are translated into TaskQueue tasks.

Additionally:
- SLA guard for daily tasks: ensure must-run daily tasks start no later than
  deadline - (mean + sigma).

No network access is required. No canaries are executed at runtime.
"""


import datetime as dt
import os
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

import yaml

from seclog import append as sel_append

import runtime_state
from daily_stats import mean_sigma
from resource_recovery import cleanup as recovery_cleanup
from sr_cycle import run as sr_cycle_run
from ssr_cycle import run as ssr_cycle_run

import roadmap

import taskqueue
import task_runner
import daily_scheduler

BASE = "/var/lib/noemaforge"
SYS_DIR = os.path.join(BASE, ".sys")
LOCKS_DIR = os.path.join(SYS_DIR, "locks")
PROJECTS_DIR = os.path.join(BASE, "projects")
ROUTINES_DIR = os.path.join(BASE, "routines")
CONFIG_PATH = "/opt/noemaforge/configs/maintenance-policy.yaml"

OUTBOX_AUTO_CYCLE = "/workspace/outbox/system/auto_cycle"



# === NoemaForge Autodoc Function Header ===
# Function: _save_text(path: str, text: str)
# Purpose: Implement the routine ' save text'.
# Inputs:
#   - path: str
#   - text: str
# Called by:
#   - src/audit_remediation.py
#   - src/noemaforge_core.py
# Calls:
#   - makedirs, replace, dirname, open, write
# Returns / emits: None
# Side effects:
#   - reads or writes files
#   - creates directories
# Key locals:
#   - f, tmp
# === End NoemaForge Autodoc Function Header ===
def _save_text(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


# === NoemaForge Autodoc Function Header ===
# Function: _write_autocycle_summary(reason: str, details: Dict[str, Any], st: Dict[str, Any])
# Purpose: Write a human-readable + machine-readable summary when AUTO_CYCLE ends.
# Inputs:
#   - reason: str
#   - details: Dict[str, Any]
#   - st: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - strftime, replace, join, makedirs, append, items, _save_text, _nowz, open, dump, sel_append, utcnow
# Returns / emits: Dict[str, str]
# Side effects:
#   - reads or writes files
#   - serializes structured data
#   - creates directories
#   - appends to logs or files
# Key locals:
#   - f, jpath, md, mpath, obj, out_dir, safe_reason, tmp, ts
# === End NoemaForge Autodoc Function Header ===
def _write_autocycle_summary(*, reason: str, details: Dict[str, Any], st: Dict[str, Any]) -> Dict[str, str]:
    """Write a human-readable + machine-readable summary when AUTO_CYCLE ends."""
    ts = dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    safe_reason = (reason or "unknown").replace("/", "_").replace(" ", "_")
    out_dir = os.path.join(ROUTINES_DIR, "maintenance", "auto_cycle")
    os.makedirs(out_dir, exist_ok=True)
    jpath = os.path.join(out_dir, f"{ts}_{safe_reason}.json")
    mpath = os.path.join(OUTBOX_AUTO_CYCLE, f"{ts}_{safe_reason}.md")

    obj = {
        "schema_version": "v1",
        "kind": "AutoCycleEnd",
        "ended_at": _nowz(),
        "reason": reason,
        "details": details,
        "state": {
            "auto_cycle_started_ts": st.get("auto_cycle_started_ts"),
            "auto_cycle_last_step_ts": st.get("auto_cycle_last_step_ts"),
            "auto_cycle_last_sr_ts": st.get("auto_cycle_last_sr_ts"),
            "auto_cycle_steps": int(st.get("auto_cycle_steps") or 0),
            "last_domain": st.get("last_domain"),
            "last_actor": st.get("last_actor"),
        },
    }
    tmp = jpath + ".tmp"
    import json
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, jpath)

    md = []
    md.append(f"# AUTO_CYCLE ended ({ts})\n\n")
    md.append(f"- reason: **{reason}**\n")
    md.append(f"- steps: **{obj['state']['auto_cycle_steps']}**\n")
    md.append(f"- started: {obj['state']['auto_cycle_started_ts']}\n")
    md.append(f"- last step: {obj['state']['auto_cycle_last_step_ts']}\n")
    md.append(f"- last SR: {obj['state']['auto_cycle_last_sr_ts']}\n")
    md.append(f"- last domain: {obj['state']['last_domain']}\n\n")
    md.append("## Details\n")
    for k, v in (details or {}).items():
        md.append(f"- {k}: {v}\n")
    _save_text(mpath, "".join(md))

    try:
        sel_append(
            {
                "evt_id": os.urandom(8).hex(),
                "ts": obj["ended_at"],
                "severity": "S1",
                "type": "AUTO_CYCLE_ENDED",
                "actor": {"subsystem": "maintenance"},
                "decision": "end",
                "trace_id": os.urandom(8).hex(),
                "reason": reason,
                "details": details,
                "artifact": {"json": jpath, "md": mpath},
            }
        )
    except Exception:
        pass

    return {"json": jpath, "md": mpath}


# === NoemaForge Autodoc Function Header ===
# Function: _end_auto_cycle(reason: str, details: Dict[str, Any], arm_idle: bool)
# Purpose: End AUTO_CYCLE with an explicit reason + artifacts.
# Inputs:
#   - reason: str
#   - details: Dict[str, Any]
#   - arm_idle: bool
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - load, _write_autocycle_summary, end_auto_cycle, arm_idle, touch_activity
# Returns / emits: Dict[str, Any]
# Key locals:
#   - art, st
# === End NoemaForge Autodoc Function Header ===
def _end_auto_cycle(*, reason: str, details: Dict[str, Any], arm_idle: bool) -> Dict[str, Any]:
    """End AUTO_CYCLE with an explicit reason + artifacts."""
    st = runtime_state.load()
    art = _write_autocycle_summary(reason=reason, details=details, st=st)
    try:
        runtime_state.end_auto_cycle(reason=reason, actor="maintenance", details={"artifacts": art, **(details or {})})
    except Exception:
        pass
    if arm_idle:
        runtime_state.arm_idle(actor="maintenance.auto_end")
    else:
        runtime_state.touch_activity(actor="maintenance.auto_end", note={"auto_cycle_end": {"reason": reason}})
    return {"ok": True, "reason": reason, "artifacts": art}

# === NoemaForge Autodoc Function Header ===
# Function: _save_state(st: Dict[str, Any])
# Purpose: Directly persist runtime_state (we need to update auto-cycle fields).
# Inputs:
#   - st: Dict[str, Any]
# Called by:
#   - src/knowledge_maintainer.py
#   - src/localgateway.py
#   - src/nids_lite.py
# Calls:
#   - save
# Returns / emits: None
# === End NoemaForge Autodoc Function Header ===
def _save_state(st: Dict[str, Any]) -> None:
    """Directly persist runtime_state (we need to update auto-cycle fields)."""
    try:
        runtime_state.save(st)
    except Exception:
        # Best-effort only.
        pass


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
# Function: _load_yaml(path: str)
# Purpose: Implement the routine ' load yaml'.
# Inputs:
#   - path: str
# Called by:
#   - src/brainctl.py
#   - src/noemaforge_core.py
#   - src/canary_runner.py
#   - src/daily_scheduler.py
#   - src/fixture_bundle.py
#   - src/flow_metrics.py
#   - src/incidents.py
#   - src/knowledge/policy.py
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
#   - src/daily_scheduler.py
# Calls:
#   - split, len, int, strip
# Returns / emits: Tuple[int, int]
# Key locals:
#   - parts
# === End NoemaForge Autodoc Function Header ===
def _parse_hhmm(s: str) -> Tuple[int, int]:
    parts = (s or "").strip().split(":")
    if len(parts) != 2:
        return 0, 0
    return int(parts[0]), int(parts[1])


# === NoemaForge Autodoc Function Header ===
# Function: _tz_now(tz: str)
# Purpose: Implement the routine ' tz now'.
# Inputs:
#   - tz: str
# Called by:
#   - src/daily_scheduler.py
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
# Function: _list_projects()
# Purpose: Implement the routine ' list projects'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - src/noemaforge_core.py
# Calls:
#   - sorted, isdir, listdir, join, exists, append
# Returns / emits: List[str]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - name, out, p
# === End NoemaForge Autodoc Function Header ===
def _list_projects() -> List[str]:
    if not os.path.isdir(PROJECTS_DIR):
        return []
    out = []
    for name in sorted(os.listdir(PROJECTS_DIR)):
        p = os.path.join(PROJECTS_DIR, name)
        if os.path.isdir(p) and os.path.exists(os.path.join(p, "project.yaml")):
            out.append(name)
    return out


# === NoemaForge Autodoc Function Header ===
# Function: _has_pending_wakes(project_id: str)
# Purpose: Implement the routine ' has pending wakes'.
# Inputs:
#   - project_id: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - join, any, endswith, listdir
# Returns / emits: bool
# Key locals:
#   - wq
# === End NoemaForge Autodoc Function Header ===
def _has_pending_wakes(project_id: str) -> bool:
    wq = os.path.join(PROJECTS_DIR, project_id, "team", "wakeq")
    try:
        return any(fn.endswith(".json") for fn in os.listdir(wq))
    except Exception:
        return False


# === NoemaForge Autodoc Function Header ===
# Function: _semaphore_active(project_id: str, now: dt.datetime)
# Purpose: Implement the routine ' semaphore active'.
# Inputs:
#   - project_id: str
#   - now: dt.datetime
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - join, exists, load, get, fromisoformat, open, replace, str
# Returns / emits: bool
# Side effects:
#   - reads or writes files
# Key locals:
#   - lease, lease_dt, obj, sp
# === End NoemaForge Autodoc Function Header ===
def _semaphore_active(project_id: str, now: dt.datetime) -> bool:
    sp = os.path.join(PROJECTS_DIR, project_id, "team", "semaphore.json")
    if not os.path.exists(sp):
        return False
    try:
        import json

        obj = json.load(open(sp, "r", encoding="utf-8"))
        if not obj.get("active"):
            return False
        lease = obj.get("lease_until")
        if not lease:
            return True
        lease_dt = dt.datetime.fromisoformat(str(lease).replace("Z", "+00:00"))
        return lease_dt > now.replace(tzinfo=lease_dt.tzinfo)
    except Exception:
        return False


# === NoemaForge Autodoc Function Header ===
# Function: _locks_present()
# Purpose: Implement the routine ' locks present'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - listdir, isdir, endswith
# Returns / emits: bool
# Key locals:
#   - fn
# === End NoemaForge Autodoc Function Header ===
def _locks_present() -> bool:
    try:
        if not os.path.isdir(LOCKS_DIR):
            return False
        for fn in os.listdir(LOCKS_DIR):
            if fn.endswith(".lock"):
                return True
        return False
    except Exception:
        return False


# === NoemaForge Autodoc Function Header ===
# Function: is_busy()
# Purpose: Implement the routine 'is busy'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _locks_present, replace, _list_projects, exists, append, _has_pending_wakes, _semaphore_active, join, utcnow, len
# Returns / emits: Tuple[bool, List[str]]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - now, pid, reasons
# === End NoemaForge Autodoc Function Header ===
def is_busy() -> Tuple[bool, List[str]]:
    reasons: List[str] = []

    if _locks_present():
        reasons.append("locks")

    now = dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc)
    for pid in _list_projects():
        if _has_pending_wakes(pid):
            reasons.append(f"wakeq:{pid}")
            break
    for pid in _list_projects():
        if _semaphore_active(pid, now):
            reasons.append(f"semaphore:{pid}")
            break

    if os.path.exists(os.path.join(SYS_DIR, "memergency.checkpoint")):
        reasons.append("memergency")

    return (len(reasons) > 0), reasons


# === NoemaForge Autodoc Function Header ===
# Function: daily_sla_enqueue(cfg: Dict[str, Any])
# Purpose: Enqueue due daily recurring + daily audit checks.
# Inputs:
#   - cfg: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - load_policy, enqueue_due_recurring, enqueue_due_audits, list, get, sel_append, hex, _nowz, urandom
# Returns / emits: Dict[str, Any]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - missed, qpol, rep_aud, rep_rec
# === End NoemaForge Autodoc Function Header ===
def daily_sla_enqueue(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Enqueue due daily recurring + daily audit checks.

    Daily tasks must be executed before their deadlines. We implement this by
    enqueuing them as high-priority TaskQueue items (priority_class=daily_sla)
    as soon as start-by time is reached.

    Verification is also explicit: daily auditor checks are enqueued as
    core.run_audit tasks at their scheduled times.

    NOTE: We do not execute tasks here; we only enqueue and emit alerts.
    """

    qpol = taskqueue.load_policy()
    rep_rec = daily_scheduler.enqueue_due_recurring(maintenance_cfg=cfg, taskqueue_policy=qpol)
    rep_aud = daily_scheduler.enqueue_due_audits(maintenance_cfg=cfg, taskqueue_policy=qpol)

    missed = list(rep_rec.get("missed") or [])
    if missed:
        try:
            sel_append(
                {
                    "evt_id": os.urandom(8).hex(),
                    "ts": _nowz(),
                    "severity": "S2",
                    "type": "DAILY_SLA_MISSED",
                    "actor": {"subsystem": "maintenance"},
                    "decision": "alert",
                    "trace_id": os.urandom(8).hex(),
                    "missed": missed,
                }
            )
        except Exception:
            pass

    return {"recurring": rep_rec, "audit": rep_aud}


# === NoemaForge Autodoc Function Header ===
# Function: _seconds_since(ts_z: Optional[str])
# Purpose: Implement the routine ' seconds since'.
# Inputs:
#   - ts_z: Optional[str]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - fromisoformat, replace, total_seconds, utcnow
# Returns / emits: Optional[float]
# Key locals:
#   - now, t
# === End NoemaForge Autodoc Function Header ===
def _seconds_since(ts_z: Optional[str]) -> Optional[float]:
    if not ts_z:
        return None
    try:
        t = dt.datetime.fromisoformat(ts_z.replace("Z", "+00:00"))
        now = dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc)
        return (now - t).total_seconds()
    except Exception:
        return None


# === NoemaForge Autodoc Function Header ===
# Function: _next_domain(last: str, order: List[str])
# Purpose: Implement the routine ' next domain'.
# Inputs:
#   - last: str
#   - order: List[str]
# Called by:
#   - src/taskqueue.py
# Calls:
#   - upper, index, str, len
# Returns / emits: str
# Key locals:
#   - i, last_u, order, order_u
# === End NoemaForge Autodoc Function Header ===
def _next_domain(last: str, order: List[str]) -> str:
    if not order:
        order = ["WORK", "SELF_IMPROVE", "SECURITY", "PLANNED"]
    order_u = [str(x).upper() for x in order]
    last_u = str(last or "WORK").upper()
    if last_u not in order_u:
        return order_u[0]
    i = order_u.index(last_u)
    return order_u[(i + 1) % len(order_u)]


# === NoemaForge Autodoc Function Header ===
# Function: dispatch_domain(domain: str)
# Purpose: Implement the routine 'dispatch domain'.
# Inputs:
#   - domain: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - upper, mark_completed, touch_activity, sel_append, str, run, repr, hex, _nowz, urandom
# Returns / emits: Dict[str, Any]
# Side effects:
#   - spawns subprocesses or workers
#   - appends to logs or files
# Key locals:
#   - domain, err, ok, p
# === End NoemaForge Autodoc Function Header ===
def dispatch_domain(domain: str) -> Dict[str, Any]:
    domain = str(domain).upper()
    ok = True
    err = None

    try:
        if domain == "SELF_IMPROVE":
            p = subprocess.run(["/usr/bin/python3", "/opt/noemaforge/src/surgeon_auto.py"], capture_output=True, text=True)
            ok = p.returncode == 0
        elif domain == "SECURITY":
            p = subprocess.run(["/usr/bin/python3", "/opt/noemaforge/src/scary_sweep.py"], capture_output=True, text=True)
            ok = p.returncode == 0
        elif domain == "PLANNED":
            p = subprocess.run(["/usr/bin/python3", "/opt/noemaforge/src/planned_sweep.py"], capture_output=True, text=True)
            ok = p.returncode == 0
        else:
            ok = True
    except Exception as e:
        ok = False
        err = repr(e)

    if ok:
        runtime_state.mark_completed(domain=domain, actor="maintenance.dispatch", note={"domain": domain})
    else:
        runtime_state.touch_activity(domain=domain, actor="maintenance.dispatch", note={"domain": domain, "error": err})

    try:
        sel_append(
            {
                "evt_id": os.urandom(8).hex(),
                "ts": _nowz(),
                "severity": "S1" if ok else "S2",
                "type": "MAINTENANCE_DISPATCH",
                "actor": {"subsystem": "maintenance"},
                "decision": "dispatch",
                "trace_id": os.urandom(8).hex(),
                "domain": domain,
                "ok": ok,
                "error": err,
            }
        )
    except Exception:
        pass

    return {"domain": domain, "ok": ok, "error": err}


# === NoemaForge Autodoc Function Header ===
# Function: _enqueue_signal_tasks(policy: Dict[str, Any], rep: Dict[str, Any], source: str)
# Purpose: Convert selected SR/SSR signals into executable queue tasks.
# Inputs:
#   - policy: Dict[str, Any]
#   - rep: Dict[str, Any]
#   - source: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - get, strip, isinstance, enqueue_from_signal, str, append
# Returns / emits: List[Dict[str, Any]]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - key, out, r, s
# === End NoemaForge Autodoc Function Header ===
def _enqueue_signal_tasks(policy: Dict[str, Any], rep: Dict[str, Any], source: str) -> List[Dict[str, Any]]:
    """Convert selected SR/SSR signals into executable queue tasks.

    The mapping lives in taskqueue-policy.yaml (epoch-scoped).
    """
    out: List[Dict[str, Any]] = []
    for s in (rep.get("signals_emitted") or []):
        if not isinstance(s, dict):
            continue
        key = str(s.get("key") or "").strip()
        if not key:
            continue
        # Use the signal key as group_key so repeats boost priority.
        try:
            r = taskqueue.enqueue_from_signal(
                policy=policy,
                signal_key=key,
                title=str(s.get("key") or ""),
                description=f"from:{source} signal_id={s.get('signal_id')}",
            )
            if r:
                out.append(r)
        except Exception:
            continue
    return out


# === NoemaForge Autodoc Function Header ===
# Function: _enqueue_roadmap_since_cursor(policy: Dict[str, Any], epoch_dir: str, cursor_ts: str, limit: int = 1000)
# Purpose: Translate new Roadmap signals into TaskQueue work items.
# Inputs:
#   - policy: Dict[str, Any]
#   - epoch_dir: str
#   - cursor_ts: str
#   - limit: int = 1000
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - strip, list_signals_since, str, get, len, isoformat, int, isinstance, enqueue_from_signal, append, utcnow, timedelta
# Returns / emits: Dict[str, Any]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - desc, enq, key, newest, r, rep, s, sigs, since, src, ttl
# === End NoemaForge Autodoc Function Header ===
def _enqueue_roadmap_since_cursor(
    *,
    policy: Dict[str, Any],
    epoch_dir: str,
    cursor_ts: str,
    limit: int = 1000,
) -> Dict[str, Any]:
    """Translate new Roadmap signals into TaskQueue work items.

    This is the missing glue for:
    - Incident-driven roadmap signals (ToolProxy/Incidents)
    - SR/SSR signals (already in the roadmap DB)

    Without this, only SR/SSR "signals_emitted" are turned into tasks.
    With this cursor-based bridge, we process *all* new signals deterministically
    and only once.
    """

    since = str(cursor_ts or "").strip()
    if not since:
        # First-run safety: don't replay entire history.
        # We only ingest the last 24h worth of signals.
        since = (dt.datetime.utcnow() - dt.timedelta(days=1)).isoformat() + "Z"

    rep = roadmap.list_signals_since(since_ts=since, limit=int(limit or 1000))
    sigs = rep.get("signals") or []
    enq: List[Dict[str, Any]] = []

    for s in sigs:
        if not isinstance(s, dict):
            continue
        key = str(s.get("key") or "").strip()
        if not key:
            continue
        ttl = str(s.get("title") or key)
        desc = str(s.get("description") or "")
        src = f"roadmap:{s.get('target_role')}:{s.get('source_stream')}:{s.get('source_role')}"
        try:
            r = taskqueue.enqueue_from_signal(policy=policy, signal_key=key, title=ttl, description=f"{src} {desc}".strip())
            if r:
                enq.append(r)
        except Exception:
            continue

    newest = str(rep.get("newest") or since)
    return {"ok": True, "since": since, "newest": newest, "count": len(sigs), "enqueued": enq}


# === NoemaForge Autodoc Function Header ===
# Function: dispatch_one_task(last_domain: str)
# Purpose: Claim and execute ONE task from the system TaskQueue.
# Inputs:
#   - last_domain: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - load_policy, ensure_default_tasks, claim_next_task, run_task, bool, complete_task, get, str, mark_completed, touch_activity
# Returns / emits: Dict[str, Any]
# Side effects:
#   - spawns subprocesses or workers
# Key locals:
#   - err, ok, pol, run, t
# === End NoemaForge Autodoc Function Header ===
def dispatch_one_task(last_domain: str) -> Dict[str, Any]:
    """Claim and execute ONE task from the system TaskQueue."""
    pol = taskqueue.load_policy()
    taskqueue.ensure_default_tasks(pol)
    t = taskqueue.claim_next_task(policy=pol, last_domain=last_domain, claimed_by="maintenance")
    if not t:
        return {"mode": "taskqueue", "ok": True, "skipped": True, "reason": "no_tasks"}

    run = task_runner.run_task(t)
    ok = bool(run.get("ok"))
    err = ""
    if not ok:
        err = str(run.get("error") or run.get("stderr_tail") or "")
    taskqueue.complete_task(policy=pol, task_id=str(t.get("task_id")), ok=ok, error=err)

    # Mirror into runtime_state
    if ok:
        runtime_state.mark_completed(domain=str(t.get("domain") or ""), actor="maintenance.taskqueue", note={"task": t, "run": {"rc": run.get("rc")}})
    else:
        runtime_state.touch_activity(domain=str(t.get("domain") or ""), actor="maintenance.taskqueue", note={"task": t, "run": {"rc": run.get("rc"), "error": err}})

    return {"mode": "taskqueue", "ok": ok, "task": t, "run": run}


# === NoemaForge Autodoc Function Header ===
# Function: idle_cycle(cfg: Dict[str, Any])
# Purpose: Start an AUTO_CYCLE.
# Inputs:
#   - cfg: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - set_state, int, sr_cycle_run, bool, recovery_cleanup, load_policy, load, strip, _enqueue_roadmap_since_cursor, str, dispatch_one_task, get
# Returns / emits: Dict[str, Any]
# Side effects:
#   - spawns subprocesses or workers
# Key locals:
#   - auto_cfg, auto_enabled, cursor, disp, enq_bus, export_limit, export_roles, last_dom, max_events, next_dom, nowz, order
# === End NoemaForge Autodoc Function Header ===
def idle_cycle(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Start an AUTO_CYCLE.

    Runs SR/SSR/recovery once, then dispatches ONE task.
    """
    runtime_state.set_state("MAINTENANCE", actor="maintenance")

    max_events = int(((cfg.get("sr") or {}).get("max_events_scan", 500)) or 500)
    export_roles = (cfg.get("sr") or {}).get("export_roles") or None
    export_limit = int(((cfg.get("sr") or {}).get("export_limit", 100)) or 100)

    sr_rep = sr_cycle_run(max_events=max_events, export_roles=export_roles, export_limit=export_limit)

    # SSR is separate from "scary sweep". It emits a route; scary executes.
    ssr_cfg = cfg.get("ssr") or {}
    ssr_enable = bool(ssr_cfg.get("enabled", True))
    ssr_rep: Dict[str, Any] = {"ok": True, "skipped": True, "reason": "disabled"}
    if ssr_enable:
        ssr_rep = ssr_cycle_run(max_events=int(ssr_cfg.get("max_events_scan", max_events) or max_events))

    # Resource recovery: tokens/workdirs; optional model unload
    rec_cfg = cfg.get("recovery") or {}
    rep = recovery_cleanup(
        max_work_age_sec=int(rec_cfg.get("max_work_age_sec", 3600) or 3600),
        max_token_age_sec=int(rec_cfg.get("max_token_age_sec", 24 * 3600) or (24 * 3600)),
        stop_extra_backends=bool(rec_cfg.get("stop_extra_backends", False)),
    )

    # Translate ALL new Roadmap signals -> TaskQueue items, cursor-based.
    # This includes Incident-driven signals emitted outside SR/SSR.
    qpol = taskqueue.load_policy()
    st0 = runtime_state.load()
    cursor = str(st0.get("roadmap_cursor_ts") or "").strip()
    enq_bus = _enqueue_roadmap_since_cursor(policy=qpol, epoch_dir=e_dir, cursor_ts=cursor, limit=max(1000, int(max_events) * 2))
    try:
        if enq_bus.get("count"):
            st0["roadmap_cursor_ts"] = str(enq_bus.get("newest") or cursor)
            _save_state(st0)
    except Exception:
        pass

    try:
        sel_append(
            {
                "evt_id": os.urandom(8).hex(),
                "ts": _nowz(),
                "severity": "S1",
                "type": "ROADMAP_TASKQUEUE_SYNC",
                "actor": {"subsystem": "maintenance"},
                "decision": "enqueue",
                "trace_id": os.urandom(8).hex(),
                "since": enq_bus.get("since"),
                "newest": enq_bus.get("newest"),
                "signals": int(enq_bus.get("count") or 0),
                "tasks": len(enq_bus.get("enqueued") or []),
            }
        )
    except Exception:
        pass

    # Choose next step.
    st = runtime_state.load()
    last_dom = str(st.get("last_domain") or "WORK")

    disp = dispatch_one_task(last_domain=last_dom)
    if disp.get("skipped"):
        # Fallback: legacy domain rotation if queue is empty.
        order = (cfg.get("dispatch") or {}).get("domain_cycle") or ["WORK", "SELF_IMPROVE", "SECURITY", "PLANNED"]
        next_dom = _next_domain(last_dom, order)
        disp = {"mode": "legacy", **dispatch_domain(next_dom)}

    # Enter AUTO_CYCLE (epoch policy can disable it).
    auto_cfg = (cfg.get("auto_cycle") or {}) if isinstance(cfg.get("auto_cycle"), dict) else {}
    auto_enabled = bool(auto_cfg.get("enabled", True))

    st2 = runtime_state.load()
    nowz = _nowz()
    st2["state"] = "AUTO_CYCLE" if auto_enabled else "ACTIVE"
    st2["auto_cycle_active"] = bool(auto_enabled)
    if auto_enabled:
        st2["auto_cycle_steps"] = 0
        st2["auto_cycle_started_ts"] = st2.get("auto_cycle_started_ts") or nowz
        # Reset step counter on first entry.
        if int(st2.get("auto_cycle_steps") or 0) <= 0:
            st2["auto_cycle_steps"] = 0
        st2["auto_cycle_last_sr_ts"] = nowz
        st2["auto_cycle_last_step_ts"] = nowz
        st2["auto_cycle_steps"] = int(st2.get("auto_cycle_steps") or 0)
    st2.setdefault("notes", {})
    st2["notes"].update(
        {
            "last_sr": nowz,
            "sr_report": sr_rep.get("sr_report"),
            "ssr_report": ssr_rep.get("ssr_report"),
        }
    )
    _save_state(st2)

    return {"sr": sr_rep, "ssr": ssr_rep, "recovery": rep, "dispatch": disp}


# === NoemaForge Autodoc Function Header ===
# Function: auto_cycle_step(cfg: Dict[str, Any])
# Purpose: Perform ONE step while AUTO_CYCLE is active.
# Inputs:
#   - cfg: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - load, str, int, dispatch_one_task, get, _nowz, _save_state, isinstance, _seconds_since, _end_auto_cycle, idle_cycle, float
# Returns / emits: Dict[str, Any]
# Key locals:
#   - age, auto_cfg, disp, last_dom, last_sr, sr_every, st, st2
# === End NoemaForge Autodoc Function Header ===
def auto_cycle_step(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Perform ONE step while AUTO_CYCLE is active.

    - Does NOT re-run SR/SSR by default.
    - Claims and executes ONE TaskQueue task.
    - If the queue is empty, ends AUTO_CYCLE and arms idle.
    """

    st = runtime_state.load()
    last_dom = str(st.get("last_domain") or "WORK")

    # Optional SR cadence for long unattended runs.
    auto_cfg = (cfg.get("auto_cycle") or {}) if isinstance(cfg.get("auto_cycle"), dict) else {}
    sr_every = int(auto_cfg.get("sr_every_sec", 0) or 0)

    if sr_every > 0:
        last_sr = st.get("auto_cycle_last_sr_ts")
        age = _seconds_since(last_sr)
        if age is not None and age >= float(sr_every):
            # Re-run SR/SSR/recovery before continuing.
            idle_cycle(cfg)
            st = runtime_state.load()
            last_dom = str(st.get("last_domain") or "WORK")

    disp = dispatch_one_task(last_domain=last_dom)
    if disp.get("skipped"):
        _end_auto_cycle(reason="no_tasks", details={"queue": "empty"}, arm_idle=True)
        return {"mode": "auto", "ok": True, "ended": True, "reason": "no_tasks"}

    st2 = runtime_state.load()
    st2["state"] = "AUTO_CYCLE"
    st2["auto_cycle_active"] = True
    st2["auto_cycle_last_step_ts"] = _nowz()
    st2["auto_cycle_steps"] = int(st2.get("auto_cycle_steps") or 0) + 1
    _save_state(st2)
    return {"mode": "auto", "ok": True, "ended": False, "dispatch": disp}


# === NoemaForge Autodoc Function Header ===
# Function: tick()
# Purpose: Implement the routine 'tick'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - src/memsentinel.py
# Calls:
#   - makedirs, _load_yaml, int, bool, load, is_busy, load_policy, _seconds_since, idle_cycle, get, daily_sla_enqueue, touch_activity
# Returns / emits: int
# Side effects:
#   - creates directories
# Key locals:
#   - cfg, dq, dq_dispatch, dq_enabled, idle_for, idle_sec, qpol, rep, sla, sr_counts, st
# === End NoemaForge Autodoc Function Header ===
def tick() -> int:
    os.makedirs(LOCKS_DIR, exist_ok=True)

    cfg = _load_yaml(CONFIG_PATH)
    idle_sec = int(cfg.get("idle_trigger_sec", 300) or 300)

    # Enqueue daily recurring tasks + audits first (even if busy), unless disabled.
    dq = cfg.get("daily_queue") or {}
    dq_enabled = bool(dq.get("enabled", True))
    sla = daily_sla_enqueue(cfg) if dq_enabled else {"ok": True, "skipped": True, "reason": "disabled"}

    st = runtime_state.load()

    busy, reasons = is_busy()
    if busy:
        # If we were in AUTO_CYCLE, end it explicitly for diagnostics.
        if st.get("state") == "AUTO_CYCLE" and bool(st.get("auto_cycle_active")):
            _end_auto_cycle(reason="became_busy", details={"busy": reasons}, arm_idle=False)
        runtime_state.touch_activity(actor="maintenance", note={"busy": reasons, "sla": sla})
        return 0

    # Preemptive daily execution: if any daily_sla tasks are queued, run one step
    # even outside the idle-trigger cycle.
    # This keeps must-run daily tasks on-time.
    qpol = taskqueue.load_policy()
    dq_dispatch = bool(dq.get("dispatch_outside_idle", True))
    if dq_enabled and dq_dispatch and taskqueue.has_todo_with_priority_classes(policy=qpol, priority_classes=["daily_sla"]) and not (
        st.get("state") == "AUTO_CYCLE" and bool(st.get("auto_cycle_active"))
    ):
        rep = dispatch_one_task(last_domain=str(st.get("last_domain") or "WORK"))
        try:
            sel_append(
                {
                    "evt_id": os.urandom(8).hex(),
                    "ts": _nowz(),
                    "severity": "S1" if rep.get("ok") else "S2",
                    "type": "DAILY_SLA_STEP",
                    "actor": {"subsystem": "maintenance"},
                    "decision": "dispatch",
                    "trace_id": os.urandom(8).hex(),
                    "summary": {"sla": sla, "dispatch": rep},
                }
            )
        except Exception:
            pass
        return 0

    # If we are in AUTO_CYCLE, take one step per tick.
    if st.get("state") == "AUTO_CYCLE" and bool(st.get("auto_cycle_active")):
        rep = auto_cycle_step(cfg)
        try:
            sel_append(
                {
                    "evt_id": os.urandom(8).hex(),
                    "ts": _nowz(),
                    "severity": "S1",
                    "type": "AUTO_CYCLE_STEP",
                    "actor": {"subsystem": "maintenance"},
                    "decision": "step",
                    "trace_id": os.urandom(8).hex(),
                    "summary": {"sla": sla, "rep": rep},
                }
            )
        except Exception:
            pass
        return 0

    if st.get("state") != "IDLE_ARMED":
        runtime_state.arm_idle(actor="maintenance")
        return 0

    idle_for = _seconds_since(st.get("idle_since_ts"))
    if idle_for is None or idle_for < idle_sec:
        return 0

    rep = idle_cycle(cfg)

    try:
        sr_counts = ((rep.get("sr") or {}).get("counts") or {}) if isinstance(rep.get("sr"), dict) else {}
        sel_append(
            {
                "evt_id": os.urandom(8).hex(),
                "ts": _nowz(),
                "severity": "S1",
                "type": "MAINTENANCE_CYCLE",
                "actor": {"subsystem": "maintenance"},
                "decision": "complete",
                "trace_id": os.urandom(8).hex(),
                "summary": {
                    "sla": sla,
                    "dispatch": rep.get("dispatch"),
                    "sr": rep.get("sr"),
                    "ssr": rep.get("ssr"),
                    "counts": sr_counts,
                },
            }
        )
    except Exception:
        pass

    return 0


# === NoemaForge Autodoc Function Header ===
# Function: main(argv: List[str])
# Purpose: Implement the routine 'main'.
# Inputs:
#   - argv: List[str]
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
#   - lower, print, tick, strip, len
# Returns / emits: int
# Key locals:
#   - cmd
# === End NoemaForge Autodoc Function Header ===
def main(argv: List[str]) -> int:
    cmd = (argv[1] if len(argv) > 1 else "tick").strip().lower()
    if cmd in ("tick", "run"):
        return tick()
    print("Usage: maintenance.py tick", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
