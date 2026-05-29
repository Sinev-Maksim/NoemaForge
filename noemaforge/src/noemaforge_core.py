#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/noemaforge_core.py
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
# File: src/noemaforge_core.py
# Purpose: Boot the core runtime, coordinate projects/tasks, and enforce role-facing runtime rules.
# Invoked by / imported from:
#   - No inbound Python import detected; treat as library leaf or direct entrypoint.
# Public API / entry functions:
#   - ensure_dirs
#   - project_path
#   - project_file
#   - backlog_file
#   - team_roster_file
#   - semaphore_file
#   - batons_dir
#   - wakeq_dir
#   - artifacts_dir
#   - checkpoints_dir
#   - freeze_dir
#   - snapshots_dir
# Inputs:
#   - project_id
#   - --title
#   - --priority
#   - --team-template
#   - --default-stream
#   - --priority-class
#   - --stream
#   - --reason
#   - --actor
#   - --include-artifacts
# Output formats / side effects:
#   - JSON files
#   - YAML files
#   - Markdown files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""noemaforge_core.py (v0.9 MVP)

NoemaForge "BCA spine" + Serial Team runtime.

What changed in v0.9 vs v0.8:
- Roles are executed via **RoleRunner** (podman if available, host fallback).
- Roles are *pure compute*: they receive a context snapshot and return a RoleResult.
- NoemaForge core remains deterministic and writes artifacts / updates backlog / creates batons.
- Tool access (LLM/tools) goes through **ToolProxy** with short-lived capability tokens.
- Contracts/policies are immutable at runtime (Contract Epochs); changes happen pre-start.

Still included:
- Projects registry: /var/lib/noemaforge/projects/<project_id>/
- Backlog per project: backlog.yaml
- Artifacts per project: artifacts/
- DailyPlan + recurring tasks + auditor
- MemSentinel integration (critical memory pressure -> checkpoint flag)

Design principle:
"Spinal cord" (core) is deterministic, auditable, policy-governed.
"Cortex" (roles/LLMs) is ephemeral and only returns structured proposals.
"""



# Lazy MemorySystem (optional).
_MEMSYS = None


# === NoemaForge Autodoc Function Header ===
# Function: _memsys()
# Purpose: Implement the routine ' memsys'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - MemorySystem, current_epoch_dir
# Returns / emits: value from '_MEMSYS', NoneType
# Key locals:
#   - _MEMSYS
# === End NoemaForge Autodoc Function Header ===
def _memsys():
    global _MEMSYS
    if _MEMSYS is not None:
        return _MEMSYS
    try:
        from epoch import current_epoch_dir
        from memory_system import MemorySystem

        _MEMSYS = MemorySystem(epoch_dir=current_epoch_dir())
        return _MEMSYS
    except Exception:
        _MEMSYS = False
        return None
import argparse
import datetime as dt
import glob
import json
import os
import re
import subprocess
import sys
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple
from project_snapshot import freeze_project as snapshot_freeze_project, thaw_project as snapshot_thaw_project, latest_snapshot as snapshot_latest_snapshot

# v0.11.4: shared state + daily duration stats
try:
    import runtime_state
except Exception:  # pragma: no cover
    runtime_state = None  # type: ignore

try:
    from daily_stats import record as record_daily_stat
except Exception:  # pragma: no cover
    record_daily_stat = None  # type: ignore

try:
    import yaml
except Exception:
    yaml = None

from seclog import append as sel_append

from caps import issue_token
from role_runner import RunSpec, run_role

# v0.11.10: daily auditor remediation actions -> explicit TaskQueue tasks + packets
try:
    from audit_remediation import apply_on_missing_actions as audit_apply_on_missing_actions
except Exception:  # pragma: no cover
    audit_apply_on_missing_actions = None  # type: ignore


BASE = "/var/lib/noemaforge"
PROJECTS_DIR = os.path.join(BASE, "projects")
ROUTINES_DIR = os.path.join(BASE, "routines")
SYS_DIR = os.path.join(BASE, ".sys")
CONFIG_DIR = "/opt/noemaforge/configs"

# Streams catalog (v0.9.0)
STREAMS_CFG = os.path.join(CONFIG_DIR, "streams.yaml")


# === NoemaForge Autodoc Function Header ===
# Function: _load_streams_catalog()
# Purpose: Implement the routine ' load streams catalog'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _load_yaml
# Returns / emits: Dict[str, Any]
# === End NoemaForge Autodoc Function Header ===
def _load_streams_catalog() -> Dict[str, Any]:
    try:
        return _load_yaml(STREAMS_CFG)
    except Exception:
        return {}


# === NoemaForge Autodoc Function Header ===
# Function: _default_stream_id()
# Purpose: Implement the routine ' default stream id'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _load_streams_catalog, str, get
# Returns / emits: str
# Key locals:
#   - cat, s
# === End NoemaForge Autodoc Function Header ===
def _default_stream_id() -> str:
    cat = _load_streams_catalog()
    s = str(cat.get("default_stream") or "dev.work")
    return s or "dev.work"


# === NoemaForge Autodoc Function Header ===
# Function: _project_default_stream(project_id: str)
# Purpose: Implement the routine ' project default stream'.
# Inputs:
#   - project_id: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _load_yaml, str, project_file, _default_stream_id, get
# Returns / emits: str
# Key locals:
#   - proj
# === End NoemaForge Autodoc Function Header ===
def _project_default_stream(project_id: str) -> str:
    try:
        proj = _load_yaml(project_file(project_id))
        return str(proj.get("default_stream") or _default_stream_id())
    except Exception:
        return _default_stream_id()

TEMPLATES_DIR = "/opt/noemaforge/templates"

PRIORITY_ORDER = ["critical", "urgent", "daily_sla", "high", "normal", "background"]
PRIO_INDEX = {p: i for i, p in enumerate(PRIORITY_ORDER)}


# -------------------------
# Helpers
# -------------------------

# === NoemaForge Autodoc Function Header ===
# Function: _nowz()
# Purpose: Implement the routine ' nowz'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - src/audit_remediation.py
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
# Function: _today_local(tz: str = 'Europe/Lisbon')
# Purpose: Local date in the configured timezone (fallback: naive local).
# Inputs:
#   - tz: str = 'Europe/Lisbon'
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - date, now, ZoneInfo
# Returns / emits: dt.date
# === End NoemaForge Autodoc Function Header ===
def _today_local(tz: str = "Europe/Lisbon") -> dt.date:
    """Local date in the configured timezone (fallback: naive local)."""
    try:
        from zoneinfo import ZoneInfo  # py3.9+
        return dt.datetime.now(ZoneInfo(tz)).date()
    except Exception:
        return dt.datetime.now().date()


# === NoemaForge Autodoc Function Header ===
# Function: _prio_idx(p: Optional[str])
# Purpose: Implement the routine ' prio idx'.
# Inputs:
#   - p: Optional[str]
# Called by:
#   - src/roles/role_entry.py
# Calls:
#   - get
# Returns / emits: int
# === End NoemaForge Autodoc Function Header ===
def _prio_idx(p: Optional[str]) -> int:
    if not p:
        return PRIO_INDEX["normal"]
    return PRIO_INDEX.get(p, PRIO_INDEX["normal"])


# === NoemaForge Autodoc Function Header ===
# Function: _load_yaml(path: str)
# Purpose: Implement the routine ' load yaml'.
# Inputs:
#   - path: str
# Called by:
#   - src/brainctl.py
#   - src/canary_runner.py
#   - src/daily_scheduler.py
#   - src/fixture_bundle.py
#   - src/flow_metrics.py
#   - src/incidents.py
#   - src/knowledge/policy.py
#   - src/llm_backends_manager.py
# Calls:
#   - RuntimeError, open, safe_load
# Returns / emits: Any
# Side effects:
#   - reads or writes files
# Key locals:
#   - f
# === End NoemaForge Autodoc Function Header ===
def _load_yaml(path: str) -> Any:
    if yaml is None:
        raise RuntimeError("PyYAML missing. Install python3-yaml.")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# === NoemaForge Autodoc Function Header ===
# Function: _save_yaml(path: str, obj)
# Purpose: Implement the routine ' save yaml'.
# Inputs:
#   - path: str
#   - obj
# Called by:
#   - src/prestart.py
#   - src/tool_onboard.py
# Calls:
#   - makedirs, RuntimeError, dirname, open, safe_dump
# Returns / emits: None
# Side effects:
#   - reads or writes files
#   - serializes structured data
#   - creates directories
# Key locals:
#   - f
# === End NoemaForge Autodoc Function Header ===
def _save_yaml(path: str, obj: Any) -> None:
    if yaml is None:
        raise RuntimeError("PyYAML missing. Install python3-yaml.")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(obj, f, sort_keys=False, allow_unicode=True)


# === NoemaForge Autodoc Function Header ===
# Function: _save_text(path: str, text: str)
# Purpose: Implement the routine ' save text'.
# Inputs:
#   - path: str
#   - text: str
# Called by:
#   - src/audit_remediation.py
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
# Function: _load_json(path: str)
# Purpose: Implement the routine ' load json'.
# Inputs:
#   - path: str
# Called by:
#   - src/fixture_bundle.py
#   - src/glove_agent.py
#   - src/model_installer_plan.py
#   - src/model_registry.py
#   - src/model_router.py
#   - src/roles/role_entry.py
#   - src/scary_sweep.py
#   - src/team_installer_plan.py
# Calls:
#   - open, load
# Returns / emits: Any
# Side effects:
#   - reads or writes files
# Key locals:
#   - f
# === End NoemaForge Autodoc Function Header ===
def _load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# === NoemaForge Autodoc Function Header ===
# Function: _save_json(path: str, obj)
# Purpose: Implement the routine ' save json'.
# Inputs:
#   - path: str
#   - obj
# Called by:
#   - src/audit_remediation.py
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
# Function: ensure_dirs()
# Purpose: Implement the routine 'ensure dirs'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - makedirs, join
# Returns / emits: None
# Side effects:
#   - creates directories
# Key locals:
#   - p
# === End NoemaForge Autodoc Function Header ===
def ensure_dirs() -> None:
    for p in [PROJECTS_DIR, ROUTINES_DIR, SYS_DIR]:
        os.makedirs(p, exist_ok=True)
    os.makedirs(os.path.join(BASE, "sel", "segments"), exist_ok=True)
    os.makedirs(os.path.join(ROUTINES_DIR, "audit"), exist_ok=True)
    os.makedirs(os.path.join(ROUTINES_DIR, "plans"), exist_ok=True)
    os.makedirs(os.path.join(ROUTINES_DIR, "runs"), exist_ok=True)
    os.makedirs(os.path.join(SYS_DIR, "cap_tokens"), exist_ok=True)
    os.makedirs(os.path.join(SYS_DIR, "locks"), exist_ok=True)
    os.makedirs(os.path.join(BASE, "metrics"), exist_ok=True)
    os.makedirs(os.path.join(BASE, "packets"), exist_ok=True)
    os.makedirs(os.path.join(BASE, "sr"), exist_ok=True)
    os.makedirs(os.path.join(BASE, "taskqueue"), exist_ok=True)
    # v0.9: pre-start request inbox (runtime can only emit requests; pre-start applies)
    os.makedirs(os.path.join(BASE, "requests", "prestart"), exist_ok=True)
    # v0.9: contracts root (epochs live here)
    os.makedirs(os.path.join(BASE, "contracts", "epochs"), exist_ok=True)


# -------------------------
# Paths
# -------------------------

# === NoemaForge Autodoc Function Header ===
# Function: project_path(project_id: str)
# Purpose: Implement the routine 'project path'.
# Inputs:
#   - project_id: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - join
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def project_path(project_id: str) -> str:
    return os.path.join(PROJECTS_DIR, project_id)


# === NoemaForge Autodoc Function Header ===
# Function: project_file(project_id: str)
# Purpose: Implement the routine 'project file'.
# Inputs:
#   - project_id: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - join, project_path
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def project_file(project_id: str) -> str:
    return os.path.join(project_path(project_id), "project.yaml")


# === NoemaForge Autodoc Function Header ===
# Function: backlog_file(project_id: str)
# Purpose: Implement the routine 'backlog file'.
# Inputs:
#   - project_id: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - join, project_path
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def backlog_file(project_id: str) -> str:
    return os.path.join(project_path(project_id), "backlog.yaml")


# === NoemaForge Autodoc Function Header ===
# Function: team_roster_file(project_id: str)
# Purpose: Implement the routine 'team roster file'.
# Inputs:
#   - project_id: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - join, project_path
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def team_roster_file(project_id: str) -> str:
    return os.path.join(project_path(project_id), "team", "roster.yaml")


# === NoemaForge Autodoc Function Header ===
# Function: semaphore_file(project_id: str)
# Purpose: Implement the routine 'semaphore file'.
# Inputs:
#   - project_id: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - join, project_path
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def semaphore_file(project_id: str) -> str:
    return os.path.join(project_path(project_id), "team", "semaphore.json")


# === NoemaForge Autodoc Function Header ===
# Function: batons_dir(project_id: str)
# Purpose: Implement the routine 'batons dir'.
# Inputs:
#   - project_id: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - join, project_path
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def batons_dir(project_id: str) -> str:
    return os.path.join(project_path(project_id), "team", "batons")


# === NoemaForge Autodoc Function Header ===
# Function: wakeq_dir(project_id: str)
# Purpose: Implement the routine 'wakeq dir'.
# Inputs:
#   - project_id: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - join, project_path
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def wakeq_dir(project_id: str) -> str:
    return os.path.join(project_path(project_id), "team", "wakeq")


# === NoemaForge Autodoc Function Header ===
# Function: artifacts_dir(project_id: str)
# Purpose: Implement the routine 'artifacts dir'.
# Inputs:
#   - project_id: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - join, project_path
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def artifacts_dir(project_id: str) -> str:
    return os.path.join(project_path(project_id), "artifacts")


# === NoemaForge Autodoc Function Header ===
# Function: checkpoints_dir(project_id: str)
# Purpose: Implement the routine 'checkpoints dir'.
# Inputs:
#   - project_id: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - join, project_path
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def checkpoints_dir(project_id: str) -> str:
    return os.path.join(project_path(project_id), "checkpoints")


# === NoemaForge Autodoc Function Header ===
# Function: freeze_dir(project_id: str)
# Purpose: Implement the routine 'freeze dir'.
# Inputs:
#   - project_id: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - join, project_path
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def freeze_dir(project_id: str) -> str:
    return os.path.join(project_path(project_id), "team", "freeze")


# === NoemaForge Autodoc Function Header ===
# Function: snapshots_dir(project_id: str)
# Purpose: Implement the routine 'snapshots dir'.
# Inputs:
#   - project_id: str
# Called by:
#   - src/project_snapshot.py
# Calls:
#   - join, project_path
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def snapshots_dir(project_id: str) -> str:
    return os.path.join(project_path(project_id), "snapshots")


# === NoemaForge Autodoc Function Header ===
# Function: list_snapshots(project_id: str)
# Purpose: Implement the routine 'list snapshots'.
# Inputs:
#   - project_id: str
# Called by:
#   - src/project_snapshot.py
# Calls:
#   - sorted, listdir, isdir, snapshots_dir, join
# Returns / emits: List[str]
# === End NoemaForge Autodoc Function Header ===
def list_snapshots(project_id: str) -> List[str]:
    try:
        return sorted([n for n in os.listdir(snapshots_dir(project_id)) if os.path.isdir(os.path.join(snapshots_dir(project_id), n))])
    except Exception:
        return []


# === NoemaForge Autodoc Function Header ===
# Function: freeze_project_state(project_id: str, actor: str, reason: str, include_artifacts: bool = False)
# Purpose: Freeze a project's control-plane state into a snapshot and mark the project as frozen.
# Inputs:
#   - project_id: str
#   - actor: str
#   - reason: str
#   - include_artifacts: bool = False
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - project_path, snapshot_freeze_project, _load_project, get, _save_project, isdir
# Returns / emits: Tuple[bool, Dict[str, Any], str]
# Key locals:
#   - pdir
# === End NoemaForge Autodoc Function Header ===
def freeze_project_state(project_id: str, actor: str, reason: str, include_artifacts: bool = False) -> Tuple[bool, Dict[str, Any], str]:
    """Freeze a project's control-plane state into a snapshot and mark the project as frozen."""
    pdir = project_path(project_id)
    if not os.path.isdir(pdir):
        return False, {"project_id": project_id}, "project_not_found"

    ok, manifest, code = snapshot_freeze_project(
        project_dir=pdir, project_id=project_id, actor=actor, reason=reason, include_artifacts=include_artifacts
    )
    if not ok:
        return False, manifest, code

    # Mark project frozen (idempotent)
    proj, _ = _load_project(project_id)
    proj["status"] = "frozen"
    proj["frozen_at"] = manifest.get("created_at")
    proj["frozen_by"] = actor
    proj["frozen_reason"] = reason
    proj["frozen_snapshot"] = manifest.get("snapshot_id")
    _save_project(project_id, proj)

    return True, manifest, "ok"


# === NoemaForge Autodoc Function Header ===
# Function: thaw_project_state(project_id: str, actor: str, snapshot_id: Optional[str] = None, restore_artifacts: bool = False)
# Purpose: Restore a project from a snapshot and mark it active.
# Inputs:
#   - project_id: str
#   - actor: str
#   - snapshot_id: Optional[str] = None
#   - restore_artifacts: bool = False
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - project_path, snapshot_thaw_project, _load_project, _save_project, isdir, snapshot_latest_snapshot, get, strftime, gmtime
# Returns / emits: Tuple[bool, Dict[str, Any], str]
# Key locals:
#   - pdir, sid
# === End NoemaForge Autodoc Function Header ===
def thaw_project_state(
    project_id: str,
    actor: str,
    snapshot_id: Optional[str] = None,
    restore_artifacts: bool = False,
) -> Tuple[bool, Dict[str, Any], str]:
    """Restore a project from a snapshot and mark it active."""
    pdir = project_path(project_id)
    if not os.path.isdir(pdir):
        return False, {"project_id": project_id}, "project_not_found"

    sid = snapshot_id or snapshot_latest_snapshot(pdir)
    if not sid:
        return False, {"project_id": project_id}, "no_snapshots"

    ok, rep, code = snapshot_thaw_project(
        project_dir=pdir, project_id=project_id, snapshot_id=sid, actor=actor, restore_status="active", restore_artifacts=restore_artifacts
    )
    if not ok:
        return False, rep, code

    proj, _ = _load_project(project_id)
    proj["status"] = "active"
    proj["thawed_at"] = rep.get("thawed_at") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    proj["thawed_by"] = actor
    proj["thawed_snapshot"] = sid
    _save_project(project_id, proj)

    return True, rep, "ok"


# === NoemaForge Autodoc Function Header ===
# Function: _wakeq_subdir(project_id: str, sub: str)
# Purpose: Implement the routine ' wakeq subdir'.
# Inputs:
#   - project_id: str
#   - sub: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - join, wakeq_dir
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _wakeq_subdir(project_id: str, sub: str) -> str:
    return os.path.join(wakeq_dir(project_id), sub)


# === NoemaForge Autodoc Function Header ===
# Function: _work_root()
# Purpose: Implement the routine ' work root'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _work_root() -> str:
    # Keep it simple: core decides the work root. RoleRunner mounts per-run dirs.
    return "/workspace/role-runs"


# === NoemaForge Autodoc Function Header ===
# Function: _tokens_dir()
# Purpose: Implement the routine ' tokens dir'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - join
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _tokens_dir() -> str:
    # Keep in .sys, owned by noemaforge.
    return os.path.join(SYS_DIR, "cap_tokens")


# -------------------------
# SEL events
# -------------------------

# === NoemaForge Autodoc Function Header ===
# Function: _write_event(severity: str, typ: str, actor: Dict[str, Any], decision: str, trace_id: Optional[str] = None, extra: Optional[Dict[str, Any]] = None)
# Purpose: Implement the routine ' write event'.
# Inputs:
#   - severity: str
#   - typ: str
#   - actor: Dict[str, Any]
#   - decision: str
#   - trace_id: Optional[str] = None
#   - extra: Optional[Dict[str, Any]] = None
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - sel_append, str, _nowz, update, uuid4
# Returns / emits: None
# Side effects:
#   - appends to logs or files
# Key locals:
#   - evt
# === End NoemaForge Autodoc Function Header ===
def _write_event(
    severity: str,
    typ: str,
    actor: Dict[str, Any],
    decision: str,
    trace_id: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    evt: Dict[str, Any] = {
        "evt_id": str(uuid.uuid4()),
        "ts": _nowz(),
        "severity": severity,
        "type": typ,
        "actor": actor,
        "decision": decision,
        "trace_id": trace_id or str(uuid.uuid4()),
    }
    if extra:
        evt.update(extra)
    sel_append(evt)


# -------------------------
# Project + Backlog
# -------------------------

# === NoemaForge Autodoc Function Header ===
# Function: _load_project(project_id: str)
# Purpose: Implement the routine ' load project'.
# Inputs:
#   - project_id: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _load_yaml, project_file
# Returns / emits: Dict[str, Any]
# === End NoemaForge Autodoc Function Header ===
def _load_project(project_id: str) -> Dict[str, Any]:
    return _load_yaml(project_file(project_id))


# === NoemaForge Autodoc Function Header ===
# Function: _load_backlog(project_id: str)
# Purpose: Implement the routine ' load backlog'.
# Inputs:
#   - project_id: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - exists, _load_yaml, backlog_file
# Returns / emits: Dict[str, Any]
# === End NoemaForge Autodoc Function Header ===
def _load_backlog(project_id: str) -> Dict[str, Any]:
    if not os.path.exists(backlog_file(project_id)):
        return {"items": []}
    return _load_yaml(backlog_file(project_id)) or {"items": []}


# === NoemaForge Autodoc Function Header ===
# Function: _save_backlog(project_id: str, backlog: Dict[str, Any])
# Purpose: Implement the routine ' save backlog'.
# Inputs:
#   - project_id: str
#   - backlog: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _save_yaml, backlog_file
# Returns / emits: None
# === End NoemaForge Autodoc Function Header ===
def _save_backlog(project_id: str, backlog: Dict[str, Any]) -> None:
    _save_yaml(backlog_file(project_id), backlog)


# === NoemaForge Autodoc Function Header ===
# Function: _load_roster(project_id: str)
# Purpose: Implement the routine ' load roster'.
# Inputs:
#   - project_id: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _load_yaml, team_roster_file
# Returns / emits: Dict[str, Any]
# === End NoemaForge Autodoc Function Header ===
def _load_roster(project_id: str) -> Dict[str, Any]:
    return _load_yaml(team_roster_file(project_id))


# === NoemaForge Autodoc Function Header ===
# Function: _list_projects()
# Purpose: Implement the routine ' list projects'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - src/maintenance.py
# Calls:
#   - ensure_dirs, sorted, glob, basename, exists, join, isdir, project_file, append
# Returns / emits: List[str]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - p, pid, pids
# === End NoemaForge Autodoc Function Header ===
def _list_projects() -> List[str]:
    ensure_dirs()
    pids: List[str] = []
    for p in sorted(glob.glob(os.path.join(PROJECTS_DIR, "*"))):
        if not os.path.isdir(p):
            continue
        pid = os.path.basename(p)
        if os.path.exists(project_file(pid)):
            pids.append(pid)
    return pids


# === NoemaForge Autodoc Function Header ===
# Function: _roles_in_roster(roster: Dict[str, Any])
# Purpose: Implement the routine ' roles in roster'.
# Inputs:
#   - roster: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - get, append
# Returns / emits: List[str]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - r, rid, roles
# === End NoemaForge Autodoc Function Header ===
def _roles_in_roster(roster: Dict[str, Any]) -> List[str]:
    roles: List[str] = []
    for r in roster.get("roles", []) or []:
        rid = r.get("id")
        if rid:
            roles.append(rid)
    return roles


# === NoemaForge Autodoc Function Header ===
# Function: _role_exists(roster: Dict[str, Any], role_id: str)
# Purpose: Implement the routine ' role exists'.
# Inputs:
#   - roster: Dict[str, Any]
#   - role_id: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - set, _roles_in_roster
# Returns / emits: bool
# === End NoemaForge Autodoc Function Header ===
def _role_exists(roster: Dict[str, Any], role_id: str) -> bool:
    return role_id in set(_roles_in_roster(roster))


# === NoemaForge Autodoc Function Header ===
# Function: init_project(project_id: str, title: str, priority: int, team_template: str, default_stream: str = '')
# Purpose: Implement the routine 'init project'.
# Inputs:
#   - project_id: str
#   - title: str
#   - priority: int
#   - team_template: str
#   - default_stream: str = ''
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - ensure_dirs, project_path, makedirs, _save_yaml, endswith, join, _load_yaml, _save_json, _write_event, batons_dir, wakeq_dir, _wakeq_subdir
# Returns / emits: None
# Side effects:
#   - creates directories
# Key locals:
#   - pp, proj, roster, tpl, tpl_id, tpl_path
# === End NoemaForge Autodoc Function Header ===
def init_project(project_id: str, title: str, priority: int, team_template: str, default_stream: str = "") -> None:
    ensure_dirs()
    pp = project_path(project_id)
    os.makedirs(pp, exist_ok=True)
    os.makedirs(os.path.join(pp, "team"), exist_ok=True)
    os.makedirs(batons_dir(project_id), exist_ok=True)
    os.makedirs(wakeq_dir(project_id), exist_ok=True)
    os.makedirs(_wakeq_subdir(project_id, ".inflight"), exist_ok=True)
    os.makedirs(_wakeq_subdir(project_id, ".done"), exist_ok=True)
    os.makedirs(_wakeq_subdir(project_id, ".deadletter"), exist_ok=True)
    os.makedirs(artifacts_dir(project_id), exist_ok=True)
    os.makedirs(checkpoints_dir(project_id), exist_ok=True)
    os.makedirs(freeze_dir(project_id), exist_ok=True)

    proj = {
        "project_id": project_id,
        "title": title,
        "priority": priority,
        "status": "active",
        "team_template": team_template,
        "default_stream": default_stream,
        "team_execution": {"mode": "serial", "max_active_roles": 1, "baton_required": True},
        "created_at": _nowz(),
    }
    _save_yaml(project_file(project_id), proj)

    _save_yaml(backlog_file(project_id), {"items": []})

    tpl_id = team_template
    if tpl_id.endswith(".yaml"):
        tpl_id = tpl_id[:-5]
    tpl_path = os.path.join(TEMPLATES_DIR, f"team-{tpl_id}.yaml")
    if not os.path.exists(tpl_path):
        tpl_path = os.path.join(TEMPLATES_DIR, team_template)
    tpl = _load_yaml(tpl_path)
    roster = {
        "project_id": project_id,
        "team_execution": tpl.get("team_execution", {"mode": "serial", "max_active_roles": 1}),
        "roles": tpl.get("roles", []),
    }
    _save_yaml(team_roster_file(project_id), roster)

    _save_json(semaphore_file(project_id), {"active": None, "lease_until": None})

    _write_event("S1", "PROJECT_CREATED", {"project_id": project_id}, "created")


# === NoemaForge Autodoc Function Header ===
# Function: _next_task_id(backlog: Dict[str, Any])
# Purpose: Implement the routine ' next task id'.
# Inputs:
#   - backlog: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - get, str, match, max, int, group
# Returns / emits: str
# Key locals:
#   - it, m, mx, tid
# === End NoemaForge Autodoc Function Header ===
def _next_task_id(backlog: Dict[str, Any]) -> str:
    mx = 0
    for it in backlog.get("items", []) or []:
        tid = str(it.get("id") or "")
        m = re.match(r"T-(\\d+)$", tid)
        if m:
            mx = max(mx, int(m.group(1)))
    return f"T-{mx + 1:03d}"


# === NoemaForge Autodoc Function Header ===
# Function: add_task(project_id: str, title: str, priority_class: str = 'high', stream_id: str = '')
# Purpose: Implement the routine 'add task'.
# Inputs:
#   - project_id: str
#   - title: str
#   - priority_class: str = 'high'
#   - stream_id: str = ''
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _load_backlog, _next_task_id, append, _save_backlog, _write_event, _nowz, strip, setdefault
# Returns / emits: str
# Side effects:
#   - appends to logs or files
# Key locals:
#   - backlog, item, priority_class, tid
# === End NoemaForge Autodoc Function Header ===
def add_task(project_id: str, title: str, priority_class: str = "high", stream_id: str = "") -> str:
    if priority_class not in PRIO_INDEX:
        priority_class = "high"
    backlog = _load_backlog(project_id)
    tid = _next_task_id(backlog)
    item = {
        "id": tid,
        "title": title,
        "priority_class": priority_class,
        "status": "todo",
        "created_at": _nowz(),
        "updated_at": _nowz(),
        "assigned_role": None,
        "stream_id": (stream_id or "").strip() or None,
    }
    backlog.setdefault("items", []).append(item)
    _save_backlog(project_id, backlog)
    _write_event("S1", "BACKLOG_TASK_ADDED", {"project_id": project_id}, "added", extra={"task_id": tid, "priority_class": priority_class})
    return tid


# === NoemaForge Autodoc Function Header ===
# Function: _find_task(backlog: Dict[str, Any], task_id: str)
# Purpose: Implement the routine ' find task'.
# Inputs:
#   - backlog: Dict[str, Any]
#   - task_id: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - get
# Returns / emits: Optional[Dict[str, Any]]
# Key locals:
#   - it
# === End NoemaForge Autodoc Function Header ===
def _find_task(backlog: Dict[str, Any], task_id: str) -> Optional[Dict[str, Any]]:
    for it in backlog.get("items", []) or []:
        if it.get("id") == task_id:
            return it
    return None


# === NoemaForge Autodoc Function Header ===
# Function: _set_status(backlog: Dict[str, Any], task_id: str, status: str, assigned_role: Optional[str] = None)
# Purpose: Implement the routine ' set status'.
# Inputs:
#   - backlog: Dict[str, Any]
#   - task_id: str
#   - status: str
#   - assigned_role: Optional[str] = None
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _find_task, _nowz
# Returns / emits: None
# Key locals:
#   - it
# === End NoemaForge Autodoc Function Header ===
def _set_status(backlog: Dict[str, Any], task_id: str, status: str, assigned_role: Optional[str] = None) -> None:
    it = _find_task(backlog, task_id)
    if not it:
        return
    it["status"] = status
    it["updated_at"] = _nowz()
    if assigned_role is not None:
        it["assigned_role"] = assigned_role


# -------------------------
# Team semaphore (serial execution)
# -------------------------

# === NoemaForge Autodoc Function Header ===
# Function: acquire_semaphore(project_id: str, role_id: str, lease_sec: int = 600)
# Purpose: Implement the routine 'acquire semaphore'.
# Inputs:
#   - project_id: str
#   - role_id: str
#   - lease_sec: int = 600
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - semaphore_file, makedirs, utcnow, get, _save_json, replace, _write_event, dirname, _load_json, str, _nowz, isoformat
# Returns / emits: bool
# Side effects:
#   - creates directories
# Key locals:
#   - lease_until, now, sf, state, tmp
# === End NoemaForge Autodoc Function Header ===
def acquire_semaphore(project_id: str, role_id: str, lease_sec: int = 600) -> bool:
    sf = semaphore_file(project_id)
    os.makedirs(os.path.dirname(sf), exist_ok=True)

    try:
        state = _load_json(sf)
    except Exception:
        state = {"active": None, "lease_until": None}

    now = dt.datetime.utcnow()
    lease_until = None
    if state.get("lease_until"):
        try:
            lease_until = dt.datetime.fromisoformat(str(state["lease_until"]).replace("Z", ""))
        except Exception:
            lease_until = None

    if state.get("active") and lease_until and lease_until > now:
        return False

    state["active"] = {"role_id": role_id, "run_id": str(uuid.uuid4()), "ts": _nowz()}
    state["lease_until"] = (now + dt.timedelta(seconds=lease_sec)).isoformat() + "Z"

    tmp = sf + ".tmp"
    _save_json(tmp, state)
    os.replace(tmp, sf)

    _write_event("S1", "TEAM_SEMAPHORE_ACQUIRED", {"project_id": project_id, "role": role_id}, "acquired", extra={"lease_sec": lease_sec})
    return True


# === NoemaForge Autodoc Function Header ===
# Function: release_semaphore(project_id: str, role_id: str)
# Purpose: Implement the routine 'release semaphore'.
# Inputs:
#   - project_id: str
#   - role_id: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - semaphore_file, _save_json, replace, _write_event, _load_json
# Returns / emits: None
# Key locals:
#   - sf, state, tmp
# === End NoemaForge Autodoc Function Header ===
def release_semaphore(project_id: str, role_id: str) -> None:
    sf = semaphore_file(project_id)
    try:
        state = _load_json(sf)
    except Exception:
        state = {}
    state["active"] = None
    state["lease_until"] = None
    tmp = sf + ".tmp"
    _save_json(tmp, state)
    os.replace(tmp, sf)
    _write_event("S1", "TEAM_SEMAPHORE_RELEASED", {"project_id": project_id, "role": role_id}, "released")


# -------------------------
# Baton + WakeQueue
# -------------------------

# === NoemaForge Autodoc Function Header ===
# Function: handoff_baton(project_id: str, from_role: str, to_role: str, task_id: str, objective: str, priority_class: str, deliverables: List[Dict[str, Any]], context_refs: List[str], constraints: Dict[str, Any], verification_plan: List[str], stream_id: str = '', notes: str = '')
# Purpose: Implement the routine 'handoff baton'.
# Inputs:
#   - project_id: str
#   - from_role: str
#   - to_role: str
#   - task_id: str
#   - objective: str
#   - priority_class: str
#   - deliverables: List[Dict[str, Any]]
#   - context_refs: List[str]
#   - constraints: Dict[str, Any]
#   - verification_plan: List[str]
#   - stream_id: str = ''
#   - notes: str = ''
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - makedirs, join, _save_json, str, _write_event, strftime, batons_dir, _nowz, uuid4, strip, _project_default_stream, wakeq_dir
# Returns / emits: str
# Side effects:
#   - creates directories
# Key locals:
#   - baton, baton_id, baton_path, wake, wake_id
# === End NoemaForge Autodoc Function Header ===
def handoff_baton(
    project_id: str,
    from_role: str,
    to_role: str,
    task_id: str,
    objective: str,
    priority_class: str,
    deliverables: List[Dict[str, Any]],
    context_refs: List[str],
    constraints: Dict[str, Any],
    verification_plan: List[str],
    stream_id: str = "",
    notes: str = "",
) -> str:
    baton_id = dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ") + f"_{from_role}_to_{to_role}"
    os.makedirs(batons_dir(project_id), exist_ok=True)
    baton_path = os.path.join(batons_dir(project_id), baton_id + ".json")
    baton = {
        "baton_id": baton_id,
        "project_id": project_id,
        "from_role": from_role,
        "stream_id": (stream_id or "").strip() or _project_default_stream(project_id),
        "to_role": to_role,
        "task_id": task_id,
        "priority_class": priority_class,
        "objective": objective,
        "deliverables": deliverables,
        "context_refs": context_refs,
        "constraints": constraints,
        "verification_plan": verification_plan,
        "handoff_notes": notes,
        "ts": _nowz(),
    }
    _save_json(baton_path, baton)

    wake_id = str(uuid.uuid4())
    wake = {
        "wake_id": wake_id,
        "project_id": project_id,
        "to_role": to_role,
        "baton_id": baton_id,
        "stream_id": str(baton.get("stream_id") or ""),
        "requested_by": from_role,
        "ts": _nowz(),
    }
    _save_json(os.path.join(wakeq_dir(project_id), wake_id + ".json"), wake)

    _write_event(
        "S1",
        "ROLE_HANDOFF_WRITTEN",
        {"project_id": project_id, "from": from_role, "to": to_role},
        "handoff",
        extra={"baton_id": baton_id, "wake_id": wake_id},
    )
    return baton_id


# === NoemaForge Autodoc Function Header ===
# Function: _load_baton(project_id: str, baton_id: str)
# Purpose: Implement the routine ' load baton'.
# Inputs:
#   - project_id: str
#   - baton_id: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - join, _load_json, batons_dir, exists
# Returns / emits: Optional[Dict[str, Any]]
# Key locals:
#   - bp
# === End NoemaForge Autodoc Function Header ===
def _load_baton(project_id: str, baton_id: str) -> Optional[Dict[str, Any]]:
    bp = os.path.join(batons_dir(project_id), baton_id + ".json")
    if not os.path.exists(bp):
        return None
    return _load_json(bp)


# === NoemaForge Autodoc Function Header ===
# Function: _pending_wakes(project_id: str)
# Purpose: Implement the routine ' pending wakes'.
# Inputs:
#   - project_id: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - sorted, glob, join, wakeq_dir
# Returns / emits: List[str]
# === End NoemaForge Autodoc Function Header ===
def _pending_wakes(project_id: str) -> List[str]:
    return sorted(glob.glob(os.path.join(wakeq_dir(project_id), "*.json")))


# -------------------------
# DailyPlan + routines
# -------------------------

# === NoemaForge Autodoc Function Header ===
# Function: create_daily_plan()
# Purpose: Implement the routine 'create daily plan'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - ensure_dirs, _load_yaml, get, strftime, join, _save_json, _write_event, append, _today_local, bool, len
# Returns / emits: str
# Side effects:
#   - appends to logs or files
# Key locals:
#   - plan, plan_path, rec, t, tasks, today, tz
# === End NoemaForge Autodoc Function Header ===
def create_daily_plan() -> str:
    ensure_dirs()
    rec = _load_yaml(os.path.join(CONFIG_DIR, "recurring-tasks.yaml"))
    tz = rec.get("timezone", "local")
    today = _today_local().strftime("%Y-%m-%d")

    tasks = []
    for t in rec.get("tasks", []) or []:
        tasks.append(
            {
                "task_id": t["id"],
                "title": t.get("title", ""),
                "priority_class": t.get("priority_class", "daily_sla"),
                "deadline_local": t.get("deadline_local"),
                "must_run": bool(t.get("must_run", False)),
            }
        )

    plan = {"date": today, "timezone": tz, "tasks": tasks}
    plan_path = os.path.join(ROUTINES_DIR, "plans", f"{today}.json")
    _save_json(plan_path, plan)
    _write_event("S1", "DAILY_PLAN_CREATED", {"scope": "routines"}, "created", extra={"date": today, "tasks": len(tasks)})
    return plan_path


# === NoemaForge Autodoc Function Header ===
# Function: _detect_gpu_vram_mib()
# Purpose: Implement the routine ' detect gpu vram mib'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - strip, splitlines, max, check_output, append, int, float
# Returns / emits: Optional[int]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - line, out, vals
# === End NoemaForge Autodoc Function Header ===
def _detect_gpu_vram_mib() -> Optional[int]:
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        if not out:
            return None
        vals = []
        for line in out.splitlines():
            line = line.strip()
            if line:
                vals.append(int(float(line)))
        return max(vals) if vals else None
    except Exception:
        return None


# === NoemaForge Autodoc Function Header ===
# Function: run_recurring(task_id: str)
# Purpose: Execute a recurring task (deterministic pipelines in MVP v0.10.1).
# Inputs:
#   - task_id: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - ensure_dirs, _load_yaml, join, exists, monotonic, _nowz, str, int, strftime, compute_inputs_fingerprint, _write_event, bool
# Returns / emits: int
# Key locals:
#   - a, aid, art_by_id, cand, case_key, checks, chk, day, day_dt, duration_sec, emergency_flag, existing
# === End NoemaForge Autodoc Function Header ===
def run_recurring(task_id: str) -> int:
    """Execute a recurring task (deterministic pipelines in MVP v0.10.1).

    NOTE: This is a *spine* action. No network. No canaries.
    Canaries are pre-start only and governed by Scary+CanaryManager.

    Caching:
      Solution Cache / Casebase sits directly behind this scheduler step.
      We compute an inputs fingerprint and skip if unchanged, unless NOEMAFORGE_FORCE=1.
    """

    ensure_dirs()
    rec = _load_yaml(os.path.join(CONFIG_DIR, "recurring-tasks.yaml"))
    task = None
    for t in rec.get("tasks", []) or []:
        if t.get("id") == task_id:
            task = t
            break
    if not task:
        print("Unknown task:", task_id, file=sys.stderr)
        return 2

    # Resource gates (GPU hard requirement)
    gpu = (task.get("resources") or {}).get("gpu") or {}
    if gpu.get("mode", "never") == "hard":
        free_vram = _detect_gpu_vram_mib()
        min_vram = int(gpu.get("min_vram_mib", 0) or 0)
        if free_vram is None or free_vram < min_vram:
            _write_event(
                "S2",
                "RECURRING_DEFERRED_NO_GPU",
                {"task_id": task_id},
                "deferred",
                extra={"free_vram_mib": free_vram, "min_vram_mib": min_vram},
            )
            return 0

    # Critical memory pressure abort
    emergency_flag = os.path.join(SYS_DIR, "memergency.checkpoint")
    if os.path.exists(emergency_flag):
        _write_event("S3", "RECURRING_ABORTED_MEM_EMERGENCY", {"task_id": task_id}, "aborted")
        return 0

    # v0.11.4: timing + lock (used by maintenance idle detection + SLA stats)
    lock_path = os.path.join(SYS_DIR, "locks", f"recurring_{task_id}.lock")
    t0 = time.monotonic()
    ts_start = _nowz()
    try:
        _save_text(lock_path, ts_start + "\n")
    except Exception:
        pass

    tz = str(rec.get("timezone") or "Europe/Lisbon")
    offset = int(((task.get("work") or {}).get("target_day_offset_days", -1)) or -1)
    day_dt = _today_local(tz) + dt.timedelta(days=offset)
    day = day_dt.strftime("%Y-%m-%d")

    # Resolve artifact paths (strftime on day)
    art_by_id: Dict[str, Dict[str, Any]] = {}
    for a in task.get("artifacts") or []:
        aid = str(a.get("id") or "")
        if not aid:
            continue
        path_t = str(a.get("path") or "")
        resolved = day_dt.strftime(path_t) if path_t else ""
        art_by_id[aid] = {**a, "resolved_path": resolved}

    # Compute inputs fingerprint (cache key)
    from casebase import compute_inputs_fingerprint, get_case_by_key, upsert_case

    # === NoemaForge Autodoc Function Header ===
    # Function: _scan_inputs(root: str, exts: Optional[List[str]] = None)
    # Purpose: Implement the routine ' scan inputs'.
    # Inputs:
    #   - root: str
    #   - exts: Optional[List[str]] = None
    # Called by:
    #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
    # Calls:
    #   - walk, sort, isdir, lower, append, join, splitext
    # Returns / emits: List[str]
    # Side effects:
    #   - appends to logs or files
    # Key locals:
    #   - exts_l, fn, out
    # === End NoemaForge Autodoc Function Header ===
    def _scan_inputs(root: str, exts: Optional[List[str]] = None) -> List[str]:
        out: List[str] = []
        if not os.path.isdir(root):
            return out
        exts_l = {e.lower() for e in (exts or [])}
        for base, _dirs, files in os.walk(root):
            for fn in files:
                if exts_l:
                    if os.path.splitext(fn)[1].lower() not in exts_l:
                        continue
                out.append(os.path.join(base, fn))
        out.sort()
        return out

    stream_id = "system.routines"
    kind = f"recurring:{task_id}"
    inputs: List[str] = []
    if task_id == "daily_photo_pipeline":
        stream_id = "photos.diary"
        kind = "photos.diary"
        inputs = _scan_inputs("/workspace/inbox/photos", exts=[".jpg", ".jpeg", ".png", ".heic", ".webp"])
    elif task_id == "daily_budget_reconcile":
        stream_id = "finance.budget"
        kind = "finance.budget"
        inputs = _scan_inputs("/workspace/inbox/bank", exts=[".csv", ".tsv", ".txt", ".xlsx"])

    inputs_hash = compute_inputs_fingerprint(inputs, mode="fast")
    case_key = f"{task_id}:{day}"

    force = str(os.environ.get("NOEMAFORGE_FORCE", "")).strip() == "1"
    existing = None if force else get_case_by_key(case_key)
    if existing and existing.get("inputs_hash") == inputs_hash:
        run = {
            "run_id": str(uuid.uuid4()),
            "task_id": task_id,
            "ts_start": ts_start,
            "ts_end": _nowz(),
            "status": "CACHE_HIT",
            "day": day,
            "inputs_hash": inputs_hash,
            "case_id": existing.get("case_id"),
        }
        run["duration_sec"] = max(0.0, time.monotonic() - t0)
        run_path = os.path.join(ROUTINES_DIR, "runs", f"{day}_{task_id}.json")
        _save_json(run_path, run)
        _write_event("S1", "RECURRING_CACHE_HIT", {"task_id": task_id}, "success", extra={"run_id": run["run_id"], "case_id": existing.get("case_id")})
        try:
            if record_daily_stat:
                record_daily_stat(task_id, float(run.get("duration_sec") or 0.0), status=str(run.get("status") or "CACHE_HIT"))
        except Exception:
            pass
        try:
            if runtime_state:
                runtime_state.mark_completed(domain="PLANNED", actor=f"recurring:{task_id}", note={"status": "CACHE_HIT"})
        except Exception:
            pass
        try:
            os.remove(lock_path)
        except Exception:
            pass
        return 0

    _write_event("S1", "RECURRING_RUN_START", {"task_id": task_id}, "start", extra={"day": day})

    # Dispatch deterministic pipelines
    res: Dict[str, Any] = {"ok": False}
    try:
        if task_id == "daily_photo_pipeline":
            from pipelines.photos_diary import run as p_run

            out_dir = os.path.dirname(str(art_by_id.get("diary", {}).get("resolved_path") or ""))
            if not out_dir:
                out_dir = os.path.join(ROUTINES_DIR, "diary", day)
            res = p_run(in_dir="/workspace/inbox/photos", out_dir=out_dir, day=day)
            # prefer pipeline fingerprint
            if res.get("inputs_fingerprint"):
                inputs_hash = str(res.get("inputs_fingerprint"))

        elif task_id == "daily_budget_reconcile":
            from pipelines.finance_budget import run as f_run

            res = f_run(inbox="/workspace/inbox/bank", day=day)

        else:
            raise RuntimeError(f"Task not implemented in MVP: {task_id}")

    except Exception as e:
        res = {"ok": False, "error": str(e)}

    # Minimal verification of declared artifacts
    # === NoemaForge Autodoc Function Header ===
    # Function: _check_exists(path: str)
    # Purpose: Implement the routine ' check exists'.
    # Inputs:
    #   - path: str
    # Called by:
    #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
    # Calls:
    #   - bool, exists, getsize
    # Returns / emits: bool
    # === End NoemaForge Autodoc Function Header ===
    def _check_exists(path: str) -> bool:
        return bool(path and os.path.exists(path) and os.path.getsize(path) > 0)

    # === NoemaForge Autodoc Function Header ===
    # Function: _count_lines(path: str)
    # Purpose: Implement the routine ' count lines'.
    # Inputs:
    #   - path: str
    # Called by:
    #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
    # Calls:
    #   - open, sum
    # Returns / emits: int
    # Side effects:
    #   - reads or writes files
    # Key locals:
    #   - f
    # === End NoemaForge Autodoc Function Header ===
    def _count_lines(path: str) -> int:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                return sum(1 for _ in f)
        except Exception:
            return 0

    ok = bool(res.get("ok"))

    checks = ((task.get("verify") or {}).get("checks") or [])
    for chk in checks:
        chk = str(chk)
        if chk.startswith("exists:"):
            aid = chk.split(":", 1)[1].strip()
            p = str(art_by_id.get(aid, {}).get("resolved_path") or "")
            if not _check_exists(p):
                ok = False
        if chk.startswith("min_lines:"):
            try:
                n = int(chk.split(":", 1)[1].strip())
            except Exception:
                n = 1
            # apply to the first required md artifact if present
            cand = None
            for a in (task.get("artifacts") or []):
                if str(a.get("type") or "") in ("report_md", "md") and bool(a.get("required")):
                    cand = str(art_by_id.get(str(a.get("id")), {}).get("resolved_path") or "")
                    break
            if cand and _count_lines(cand) < n:
                ok = False

    status = "SUCCESS" if ok else "FAILED"

    duration_sec = max(0.0, time.monotonic() - t0)

    # Record run + cache entry
    run = {
        "run_id": str(uuid.uuid4()),
        "task_id": task_id,
        "ts_start": ts_start,
        "ts_end": _nowz(),
        "status": status,
        "day": day,
        "inputs_hash": inputs_hash,
        "pipeline": res,
        "duration_sec": duration_sec,
    }
    run_path = os.path.join(ROUTINES_DIR, "runs", f"{day}_{task_id}.json")
    _save_json(run_path, run)

    outputs: List[Dict[str, Any]] = []
    for aid, a in art_by_id.items():
        outputs.append({"id": aid, "type": a.get("type"), "path": a.get("resolved_path"), "required": bool(a.get("required"))})

    summary = str(res.get("summary") or f"Recurring task {task_id} for {day}.")

    if ok:
        upsert_case(
            key=case_key,
            stream_id=stream_id,
            kind=kind,
            inputs_hash=inputs_hash,
            outputs=outputs,
            summary=summary,
            meta={"task_id": task_id, "day": day},
            index=True,
        )
        _write_event("S1", "RECURRING_RUN_SUCCESS", {"task_id": task_id}, "success", extra={"run_id": run["run_id"]})
        try:
            if record_daily_stat:
                record_daily_stat(task_id, float(duration_sec), status=status)
        except Exception:
            pass
        try:
            if runtime_state:
                runtime_state.mark_completed(domain="PLANNED", actor=f"recurring:{task_id}", note={"status": status, "duration_sec": duration_sec})
        except Exception:
            pass
        try:
            os.remove(lock_path)
        except Exception:
            pass
        return 0

    _write_event("S3", "RECURRING_RUN_FAILED", {"task_id": task_id}, "failed", extra={"run_id": run["run_id"], "error": res.get("error")})
    try:
        if record_daily_stat:
            record_daily_stat(task_id, float(duration_sec), status=status)
    except Exception:
        pass
    try:
        if runtime_state:
            runtime_state.mark_completed(domain="PLANNED", actor=f"recurring:{task_id}", note={"status": status, "duration_sec": duration_sec})
    except Exception:
        pass
    try:
        os.remove(lock_path)
    except Exception:
        pass
    return 1


# === NoemaForge Autodoc Function Header ===
# Function: run_audit(check_id: str)
# Purpose: Implement the routine 'run audit'.
# Inputs:
#   - check_id: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - ensure_dirs, _load_yaml, str, strftime, join, _load_json, replace, exists, create_daily_plan, get, append, _save_text
# Returns / emits: int
# Side effects:
#   - appends to logs or files
# Key locals:
#   - arts, aud, in_progress, lines, lock_path, m, missing, plan, plan_path, remediation_rep, report_path, run_marker
# === End NoemaForge Autodoc Function Header ===
def run_audit(check_id: str) -> int:
    ensure_dirs()
    aud = _load_yaml(os.path.join(CONFIG_DIR, "daily-auditor.yaml"))

    tz = str(aud.get("timezone") or "Europe/Lisbon")
    today = _today_local(tz).strftime("%Y-%m-%d")
    plan_path = os.path.join(ROUTINES_DIR, "plans", f"{today}.json")
    if not os.path.exists(plan_path):
        create_daily_plan()

    plan = _load_json(plan_path)

    missing: List[str] = []
    in_progress: List[str] = []
    for t in plan.get("tasks", []) or []:
        tid = t.get("task_id")
        run_path = os.path.join(ROUTINES_DIR, "runs", f"{today}_{tid}.json")
        if not t.get("must_run"):
            continue
        if os.path.exists(run_path):
            continue
        # If a recurring lock exists, the task is still running; don't flag as missing.
        lock_path = os.path.join(SYS_DIR, "locks", f"recurring_{tid}.lock")
        if os.path.exists(lock_path):
            in_progress.append(str(tid))
            continue
        missing.append(str(tid))

    report_path = str(aud.get("artifacts", {}).get("report_path", "")).replace("%Y-%m-%d", today)
    lines = [
        f"# Daily audit report {today}\n",
        f"Check: {check_id}\n",
        f"Missing tasks: {len(missing)}\n",
        f"In-progress tasks: {len(in_progress)}\n",
    ]
    for m in missing:
        lines.append(f"- {m}\n")
    if in_progress:
        lines.append("\n## In progress\n")
        for x in in_progress:
            lines.append(f"- {x}\n")
    # v0.11.10: apply remediation actions (configured per-check). This may enqueue
    # explicit TaskQueue tasks (idempotent via group_key), open incidents, notify user,
    # and create handoff packets for Surgeon/Scary.
    remediation_rep: Dict[str, Any] = {"ok": True, "skipped": True, "reason": "no_missing"}
    if missing and audit_apply_on_missing_actions is not None:
        try:
            remediation_rep = audit_apply_on_missing_actions(
                aud_cfg=aud if isinstance(aud, dict) else {},
                check_id=str(check_id),
                day=str(today),
                tz=str(tz),
                missing=list(missing),
                in_progress=list(in_progress),
                report_path=str(report_path or ""),
            )
        except Exception as e:
            remediation_rep = {"ok": False, "error": repr(e)}

    if remediation_rep and not remediation_rep.get("skipped"):
        try:
            lines.append("\n## Remediation\n")
            lines.append(f"- ok: {bool(remediation_rep.get('ok'))}\n")
            if remediation_rep.get("actions"):
                lines.append(f"- actions: {', '.join([str(x) for x in remediation_rep.get('actions')])}\n")
            arts = (remediation_rep.get("artifacts") or {}) if isinstance(remediation_rep, dict) else {}
            if arts:
                lines.append("\n### Artifacts\n")
                for k, v in arts.items():
                    lines.append(f"- {k}: {v}\n")
        except Exception:
            pass

    if report_path:
        _save_text(report_path, "".join(lines))

    # Marker for schedulers / TaskQueue integration.
    try:
        run_marker = os.path.join(ROUTINES_DIR, "audit", "runs", f"{today}_{check_id}.json")
        _save_json(
            run_marker,
            {
                "check_id": check_id,
                "ts": _nowz(),
                "date": today,
                "timezone": tz,
                "missing": missing,
                "in_progress": in_progress,
                "remediation": remediation_rep,
            },
        )
    except Exception:
        pass

    if missing:
        _write_event(
            "S2",
            "DAILY_AUDIT_MISSING",
            {"scope": "routines"},
            "missing",
            extra={"check_id": check_id, "missing": missing, "in_progress": in_progress},
        )
    elif in_progress:
        _write_event(
            "S1",
            "DAILY_AUDIT_IN_PROGRESS",
            {"scope": "routines"},
            "pending",
            extra={"check_id": check_id, "in_progress": in_progress},
        )
    else:
        _write_event("S1", "DAILY_AUDIT_OK", {"scope": "routines"}, "ok", extra={"check_id": check_id})
    return 0


# -------------------------
# Serial Team worker (RoleRunner-based)
# -------------------------

# === NoemaForge Autodoc Function Header ===
# Function: _artifact_root(project_id: str)
# Purpose: Implement the routine ' artifact root'.
# Inputs:
#   - project_id: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - artifacts_dir
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _artifact_root(project_id: str) -> str:
    return artifacts_dir(project_id)


# === NoemaForge Autodoc Function Header ===
# Function: _task_output_dir(project_id: str, task_id: str)
# Purpose: Implement the routine ' task output dir'.
# Inputs:
#   - project_id: str
#   - task_id: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - join, _artifact_root
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _task_output_dir(project_id: str, task_id: str) -> str:
    return os.path.join(_artifact_root(project_id), "outputs", task_id)


# === NoemaForge Autodoc Function Header ===
# Function: _write_freeze(project_id: str, role_id: str, text: str)
# Purpose: Implement the routine ' write freeze'.
# Inputs:
#   - project_id: str
#   - role_id: str
#   - text: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - join, _save_text, freeze_dir
# Returns / emits: str
# Key locals:
#   - path
# === End NoemaForge Autodoc Function Header ===
def _write_freeze(project_id: str, role_id: str, text: str) -> str:
    path = os.path.join(freeze_dir(project_id), f"{role_id}_last.md")
    _save_text(path, text)
    return path


# === NoemaForge Autodoc Function Header ===
# Function: _write_checkpoint(project_id: str, role_id: str, checkpoint: Dict[str, Any])
# Purpose: Persist a role checkpoint (latest + history).
# Inputs:
#   - project_id: str
#   - role_id: str
#   - checkpoint: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - checkpoints_dir, makedirs, join, strip, strftime, _save_json, str, gmtime, get
# Returns / emits: str
# Side effects:
#   - creates directories
# Key locals:
#   - base, hist_dir, hist_path, latest_path, run_id
# === End NoemaForge Autodoc Function Header ===
def _write_checkpoint(project_id: str, role_id: str, checkpoint: Dict[str, Any]) -> str:
    """Persist a role checkpoint (latest + history)."""
    base = checkpoints_dir(project_id)
    os.makedirs(base, exist_ok=True)
    latest_path = os.path.join(base, f"{role_id}.json")
    hist_dir = os.path.join(base, "history", role_id)
    os.makedirs(hist_dir, exist_ok=True)
    run_id = str(checkpoint.get("run_id") or "").strip()
    if not run_id:
        run_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    hist_path = os.path.join(hist_dir, f"{run_id}.json")
    try:
        _save_json(latest_path, checkpoint)
        _save_json(hist_path, checkpoint)
    except Exception:
        pass
    return latest_path


# === NoemaForge Autodoc Function Header ===
# Function: _collect_outputs_content(project_id: str, task_id: str)
# Purpose: Implement the routine ' collect outputs content'.
# Inputs:
#   - project_id: str
#   - task_id: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _task_output_dir, sorted, glob, join, open, append, read
# Returns / emits: List[Dict[str, Any]]
# Side effects:
#   - reads or writes files
#   - appends to logs or files
# Key locals:
#   - f, out_dir, p, res
# === End NoemaForge Autodoc Function Header ===
def _collect_outputs_content(project_id: str, task_id: str) -> List[Dict[str, Any]]:
    out_dir = _task_output_dir(project_id, task_id)
    res: List[Dict[str, Any]] = []
    for p in sorted(glob.glob(os.path.join(out_dir, "*.md"))):
        try:
            with open(p, "r", encoding="utf-8") as f:
                res.append({"path": p, "content": f.read()})
        except Exception:
            continue
    return res


# === NoemaForge Autodoc Function Header ===
# Function: _issue_role_token(project_id: str, role_id: str, run_id: str, trace_id: str)
# Purpose: Issue caps from ToolPolicy when possible; fall back to the older llm.chat rule.
# Inputs:
#   - project_id: str
#   - role_id: str
#   - run_id: str
#   - trace_id: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - set, issue_token, join, _project_default_stream, strip, safe_load, get, append, add, _tokens_dir, open, str
# Returns / emits: str
# Side effects:
#   - reads or writes files
#   - appends to logs or files
# Key locals:
#   - act, action, allow, c, caps, deduped, pol, seen, stream_id, tool_pol_path
# === End NoemaForge Autodoc Function Header ===
def _issue_role_token(project_id: str, role_id: str, run_id: str, trace_id: str) -> str:
    """Issue caps from ToolPolicy when possible; fall back to the older llm.chat rule."""
    caps: List[Dict[str, Any]] = []
    try:
        tool_pol_path = os.path.join(CONFIG_DIR, "tool-policy.yaml")
        pol = yaml.safe_load(open(tool_pol_path, "r", encoding="utf-8")) or {}
        stream_id = _project_default_stream(project_id)
        allow = (((pol.get("streams") or {}).get(stream_id) or {}).get("roles") or {}).get(role_id, {}).get("allow") or []
        for action in allow:
            act = str(action or "").strip()
            if act:
                caps.append({"action": act})
    except Exception:
        caps = []

    if not caps:
        # Conservative fallback for legacy roles.
        if role_id not in ("pm", "qa"):
            caps.append({"action": "llm.chat"})

    if not caps:
        return ""

    # De-duplicate while preserving order.
    seen = set()
    deduped: List[Dict[str, Any]] = []
    for c in caps:
        act = str(c.get("action") or "").strip()
        if act and act not in seen:
            deduped.append({"action": act})
            seen.add(act)

    return issue_token(
        tokens_dir=_tokens_dir(),
        issued_to={"run_id": run_id, "role": role_id, "project_id": project_id},
        caps=deduped,
        ttl_sec=600,
        trace_id=trace_id,
    )


# === NoemaForge Autodoc Function Header ===
# Function: _run_role_compute(project_id: str, role_id: str, baton: Dict[str, Any], roster: Dict[str, Any], backlog: Optional[Dict[str, Any]])
# Purpose: Run a role via RoleRunner. Returns (role_result, runner_output).
# Inputs:
#   - project_id: str
#   - role_id: str
#   - baton: Dict[str, Any]
#   - roster: Dict[str, Any]
#   - backlog: Optional[Dict[str, Any]]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - str, _roles_in_roster, join, makedirs, _save_json, _issue_role_token, RunSpec, run_role, uuid4, startswith, _collect_outputs_content, _work_root
# Returns / emits: Tuple[Optional[Dict[str, Any]], str]
# Side effects:
#   - creates directories
#   - spawns subprocesses or workers
# Key locals:
#   - cap_token, context_path, ctx, fn, out_path, res, roster_roles, run_id, spec, task_id, trace_id, workdir
# === End NoemaForge Autodoc Function Header ===
def _run_role_compute(project_id: str, role_id: str, baton: Dict[str, Any], roster: Dict[str, Any], backlog: Optional[Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], str]:
    """Run a role via RoleRunner. Returns (role_result, runner_output)."""
    run_id = str(uuid.uuid4())
    trace_id = str(uuid.uuid4())

    roster_roles = _roles_in_roster(roster)

    ctx: Dict[str, Any] = {
        "project_id": project_id,
        "role": role_id,
        "stream_id": str(baton.get("stream_id") or _project_default_stream(project_id)),
        "baton": baton,
        "roster_roles": roster_roles,
    }
    if backlog is not None:
        ctx["backlog"] = backlog

    # QA needs produced outputs content
    task_id = str(baton.get("task_id") or "")
    if role_id == "qa" and task_id.startswith("T-"):
        ctx["produced_outputs"] = _collect_outputs_content(project_id, task_id)

    workdir = os.path.join(_work_root(), project_id, run_id)
    os.makedirs(workdir, exist_ok=True)
    context_path = os.path.join(workdir, "context.json")
    out_path = os.path.join(workdir, "role_result.json")
    _save_json(context_path, ctx)

    cap_token = _issue_role_token(project_id, role_id, run_id, trace_id)

    spec = RunSpec(
        project_id=project_id,
        role=role_id,
        run_id=run_id,
        trace_id=trace_id,
        context_path=context_path,
        out_path=out_path,
        cap_token=cap_token,
        cpu_cores=0,
        ram_mib=0,
        timeout_sec=0,
    )

    ok, runner_out = run_role(spec)

    if not ok:
        _write_event("S2", "ROLE_RUN_FAILED", {"project_id": project_id, "role": role_id}, "failed", trace_id=trace_id, extra={"run_id": run_id})
        # keep workdir for forensics on failure; return without cleanup
        return None, runner_out

    try:
        res = _load_json(out_path)
    except Exception as e:
        res = None

    # Cleanup workdir (ephemeral by default)
    try:
        # keep artifacts minimal; remove everything.
        for fn in os.listdir(workdir):
            try:
                os.remove(os.path.join(workdir, fn))
            except Exception:
                pass
        os.rmdir(workdir)
    except Exception:
        pass

    return res, runner_out


# === NoemaForge Autodoc Function Header ===
# Function: _apply_specialist_result(project_id: str, role_id: str, baton: Dict[str, Any], res: Dict[str, Any])
# Purpose: Implement the routine ' apply specialist result'.
# Inputs:
#   - project_id: str
#   - role_id: str
#   - baton: Dict[str, Any]
#   - res: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - str, _write_freeze, isinstance, _load_backlog, startswith, handoff_baton, get, _save_text, _write_checkpoint, _set_status, _save_backlog, join
# Returns / emits: None
# Key locals:
#   - backlog, content, fr, o, out_path, rel, task_id
# === End NoemaForge Autodoc Function Header ===
def _apply_specialist_result(project_id: str, role_id: str, baton: Dict[str, Any], res: Dict[str, Any]) -> None:
    task_id = str(baton.get("task_id") or "")

    # Write outputs
    for o in res.get("outputs", []) or []:
        rel = str(o.get("path") or "")
        content = str(o.get("content") or "")
        if not rel:
            continue
        # If role returns relative paths (recommended), place under artifacts root.
        if rel.startswith("/"):
            out_path = rel
        else:
            out_path = os.path.join(_artifact_root(project_id), rel)
        _save_text(out_path, content)

    # Freeze
    fr = _write_freeze(project_id, role_id, str(res.get("freeze_summary") or ""))
    if isinstance(res.get("checkpoint"), dict):
        _write_checkpoint(project_id, role_id, res["checkpoint"])

    # Backlog status
    backlog = _load_backlog(project_id)
    if task_id.startswith("T-"):
        _set_status(backlog, task_id, "ready_for_review", assigned_role=role_id)
        _save_backlog(project_id, backlog)

    # Handoff to PM
    handoff_baton(
        project_id=project_id,
        from_role=role_id,
        to_role="pm",
        task_id=task_id,
        objective=f"Review results for {task_id}",
        priority_class=str(baton.get("priority_class") or "high"),
        deliverables=list(baton.get("deliverables") or []),
        context_refs=list(baton.get("context_refs") or []),
        constraints={"network": "deny", "tools": ["llm.chat"], "gpu": "never"},
        verification_plan=list(baton.get("verification_plan") or []),
        stream_id=str(baton.get("stream_id") or ""),
        notes=f"{role_id} -> PM. Freeze: {fr}",
    )


# === NoemaForge Autodoc Function Header ===
# Function: _apply_qa_result(project_id: str, baton: Dict[str, Any], res: Dict[str, Any])
# Purpose: Implement the routine ' apply qa result'.
# Inputs:
#   - project_id: str
#   - baton: Dict[str, Any]
#   - res: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - str, bool, join, _save_text, _write_freeze, isinstance, _load_backlog, startswith, handoff_baton, get, _artifact_root, _write_checkpoint
# Returns / emits: None
# Key locals:
#   - backlog, fr, ok, qa, report, report_path, task_id
# === End NoemaForge Autodoc Function Header ===
def _apply_qa_result(project_id: str, baton: Dict[str, Any], res: Dict[str, Any]) -> None:
    qa = res.get("qa") or {}
    task_id = str(qa.get("task_id") or baton.get("task_id") or "")
    ok = bool(qa.get("ok"))
    report = str(qa.get("report") or "")

    report_path = os.path.join(_artifact_root(project_id), "verification", task_id, "qa_report.md")
    _save_text(report_path, report)

    fr = _write_freeze(project_id, "qa", str(res.get("freeze_summary") or ""))
    if isinstance(res.get("checkpoint"), dict):
        _write_checkpoint(project_id, "qa", res["checkpoint"])

    backlog = _load_backlog(project_id)
    if task_id.startswith("T-"):
        _set_status(backlog, task_id, "verified" if ok else "blocked", assigned_role="qa")
        _save_backlog(project_id, backlog)

    handoff_baton(
        project_id=project_id,
        from_role="qa",
        to_role="pm",
        task_id=task_id,
        objective=f"Close task {task_id} (QA={'OK' if ok else 'FAIL'})",
        priority_class=str(baton.get("priority_class") or "high"),
        deliverables=list(baton.get("deliverables") or []) + [{"type": "qa_report", "path": report_path, "required": True}],
        context_refs=list(baton.get("context_refs") or []),
        constraints={"network": "deny", "tools": [], "gpu": "never"},
        verification_plan=[],
        stream_id=str(baton.get("stream_id") or qa.get("stream_id") or ""),
        notes=f"QA -> PM. Freeze: {fr}",
    )


# === NoemaForge Autodoc Function Header ===
# Function: _apply_pm_result(project_id: str, baton: Dict[str, Any], roster: Dict[str, Any], res: Dict[str, Any])
# Purpose: Implement the routine ' apply pm result'.
# Inputs:
#   - project_id: str
#   - baton: Dict[str, Any]
#   - roster: Dict[str, Any]
#   - res: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - str, _write_freeze, isinstance, _load_backlog, get, _write_checkpoint, _write_event, startswith, _set_status, _save_backlog, _role_exists, _find_task
# Returns / emits: None
# Key locals:
#   - action, backlog, constraints, ctx_refs, deliverables, it, pm, r, task_id, title, to_role, verification_plan
# === End NoemaForge Autodoc Function Header ===
def _apply_pm_result(project_id: str, baton: Dict[str, Any], roster: Dict[str, Any], res: Dict[str, Any]) -> None:
    pm = res.get("pm") or {}
    action = str(pm.get("proposed_action") or "NONE")
    task_id = str(pm.get("task_id") or "")

    _write_freeze(project_id, "pm", str(res.get("freeze_summary") or ""))
    if isinstance(res.get("checkpoint"), dict):
        _write_checkpoint(project_id, role_id, res["checkpoint"])

    backlog = _load_backlog(project_id)

    # If PM is reacting to incoming baton, the backlog may already be updated.
    # PM action applies the next transition.

    if action == "IDLE":
        _write_event("S1", "PROJECT_IDLE", {"project_id": project_id}, "idle")
        return

    if action == "CLOSE_TASK" and task_id.startswith("T-"):
        _set_status(backlog, task_id, "done", assigned_role=None)
        _save_backlog(project_id, backlog)
        _write_event("S1", "TASK_CLOSED", {"project_id": project_id, "task_id": task_id}, "done")
        return

    if action == "REQUEST_QA" and task_id.startswith("T-"):
        if _role_exists(roster, "qa"):
            deliverables = [
                {"type": "qa_report", "path": os.path.join(_artifact_root(project_id), "verification", task_id, "qa_report.md"), "required": True}
            ]
            ctx_refs = list(baton.get("context_refs") or [])
            ctx_refs.append(f"artifacts://outputs/{task_id}")
            handoff_baton(
                project_id=project_id,
                from_role="pm",
                to_role="qa",
                task_id=task_id,
                objective=f"Verify deliverables for {task_id}",
                priority_class=str(baton.get("priority_class") or "high"),
                deliverables=deliverables,
                context_refs=ctx_refs,
                constraints={"network": "deny", "tools": [], "gpu": "never"},
                verification_plan=["mvp:qa"],
                notes="PM -> QA",
            )
            _write_event("S1", "TASK_SENT_TO_QA", {"project_id": project_id, "task_id": task_id}, "sent")
        else:
            _set_status(backlog, task_id, "done", assigned_role=None)
            _save_backlog(project_id, backlog)
            _write_event("S1", "TASK_CLOSED_NO_QA", {"project_id": project_id, "task_id": task_id}, "done")
        return

    if action == "ASSIGN" and task_id.startswith("T-"):
        to_role = str(pm.get("to_role") or "")
        if not _role_exists(roster, to_role):
            # fallback to first non-PM
            for r in _roles_in_roster(roster):
                if r != "pm":
                    to_role = r
                    break
        if not to_role or to_role == "pm":
            # degenerate: PM does it
            _set_status(backlog, task_id, "done", assigned_role=None)
            _save_backlog(project_id, backlog)
            _write_event("S1", "TASK_DONE_BY_PM", {"project_id": project_id, "task_id": task_id}, "done")
            return

        _set_status(backlog, task_id, "in_progress", assigned_role=to_role)
        _save_backlog(project_id, backlog)

        deliverables = [
            {"type": "task_output", "path": os.path.join(_artifact_root(project_id), "outputs", task_id, f"{to_role}.md"), "required": True},
            {"type": "freeze_note", "path": os.path.join(freeze_dir(project_id), f"{to_role}_last.md"), "required": True},
        ]
        ctx_refs = [f"backlog://{project_id}#{task_id}"]
        constraints = {"network": "deny", "tools": ["llm.chat"], "gpu": "never"}
        verification_plan = ["mvp:qa"]

        # objective title comes from backlog
        it = _find_task(backlog, task_id)
        title = str(it.get("title") if it else pm.get("notes") or "")

        handoff_baton(
            project_id=project_id,
            from_role="pm",
            to_role=to_role,
            task_id=task_id,
            objective=title,
            priority_class=str(it.get("priority_class") if it else "high"),
            deliverables=deliverables,
            context_refs=ctx_refs,
            constraints=constraints,
            verification_plan=verification_plan,
            stream_id=str((it.get("stream_id") if it else "") or _project_default_stream(project_id)),
            notes="PM -> specialist",
        )
        _write_event("S1", "TASK_ASSIGNED", {"project_id": project_id, "task_id": task_id}, "assigned", extra={"to_role": to_role})
        return



# === NoemaForge Autodoc Function Header ===
# Function: _process_wake(project_id: str, wake_path: str)
# Purpose: Implement the routine ' process wake'.
# Inputs:
#   - project_id: str
#   - wake_path: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _load_json, str, join, replace, _wakeq_subdir, _load_baton, _load_roster, _write_event, _run_role_compute, get, _load_backlog, _apply_pm_result
# Returns / emits: None
# Side effects:
#   - spawns subprocesses or workers
# Key locals:
#   - backlog_snapshot, baton, baton_id, dead, done, inflight, roster, to_role, wake, wake_id
# === End NoemaForge Autodoc Function Header ===
def _process_wake(project_id: str, wake_path: str) -> None:
    wake = _load_json(wake_path)
    wake_id = str(wake.get("wake_id") or os.path.splitext(os.path.basename(wake_path))[0])
    inflight = os.path.join(_wakeq_subdir(project_id, ".inflight"), wake_id + ".json")
    done = os.path.join(_wakeq_subdir(project_id, ".done"), wake_id + ".json")
    dead = os.path.join(_wakeq_subdir(project_id, ".deadletter"), wake_id + ".json")

    os.replace(wake_path, inflight)

    try:
        baton_id = str(wake.get("baton_id") or "")
        baton = _load_baton(project_id, baton_id)
        if baton is None:
            _write_event("S2", "WAKE_DEADLETTER_NO_BATON", {"project_id": project_id}, "deadletter", extra={"wake_id": wake_id, "baton_id": baton_id})
            os.replace(inflight, dead)
            return

        to_role = str(wake.get("to_role") or baton.get("to_role") or "")
        roster = _load_roster(project_id)

        backlog_snapshot = _load_backlog(project_id) if to_role == "pm" else None

        _write_event("S1", "ROLE_WAKE_GRANTED", {"project_id": project_id, "role": to_role}, "start", extra={"wake_id": wake_id, "baton_id": baton_id})

        res, runner_out = _run_role_compute(project_id, to_role, baton, roster, backlog_snapshot)
        if not res or str(res.get("status") or "") != "OK":
            _write_event("S2", "ROLE_RESULT_INVALID", {"project_id": project_id, "role": to_role}, "deadletter", extra={"wake_id": wake_id, "baton_id": baton_id, "runner_out": runner_out[-500:]})
            os.replace(inflight, dead)
            return

        # Apply result deterministically
        if to_role == "pm":
            _apply_pm_result(project_id, baton, roster, res)
        elif to_role == "qa":
            _apply_qa_result(project_id, baton, res)
        else:
            _apply_specialist_result(project_id, to_role, baton, res)

        _write_event("S1", "ROLE_SLEEPED", {"project_id": project_id, "role": to_role}, "slept", extra={"wake_id": wake_id, "baton_id": baton_id})
        os.replace(inflight, done)

    except Exception as e:
        _write_event("S2", "WAKE_PROCESSING_ERROR", {"project_id": project_id}, "deadletter", extra={"wake_id": wake_id, "error": repr(e)})
        try:
            os.replace(inflight, dead)
        except Exception:
            pass


# === NoemaForge Autodoc Function Header ===
# Function: _maybe_kickoff_pm(project_id: str)
# Purpose: Implement the routine ' maybe kickoff pm'.
# Inputs:
#   - project_id: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _load_project, _pending_wakes, _load_backlog, any, _load_roster, handoff_baton, _write_event, get, _role_exists, _load_json, semaphore_file, join
# Returns / emits: None
# Key locals:
#   - backlog, has_todo, proj, roster, st
# === End NoemaForge Autodoc Function Header ===
def _maybe_kickoff_pm(project_id: str) -> None:
    proj = _load_project(project_id)
    if proj.get("status") != "active":
        return

    if _pending_wakes(project_id):
        return

    backlog = _load_backlog(project_id)
    has_todo = any(it.get("status") == "todo" for it in (backlog.get("items") or []))
    if not has_todo:
        return

    roster = _load_roster(project_id)
    if not _role_exists(roster, "pm"):
        return

    try:
        st = _load_json(semaphore_file(project_id))
        if st.get("active"):
            return
    except Exception:
        pass

    handoff_baton(
        project_id=project_id,
        from_role="system",
        to_role="pm",
        task_id="KICKOFF",
        objective="Kickoff: assign next backlog item",
        priority_class="high",
        deliverables=[{"type": "pm_note", "path": os.path.join(freeze_dir(project_id), "pm_last.md"), "required": True}],
        context_refs=[f"backlog://{project_id}"],
        constraints={"network": "deny", "tools": [], "gpu": "never"},
        verification_plan=[],
        notes="auto-kickoff",
    )
    _write_event("S1", "PM_AUTO_KICKOFF_QUEUED", {"project_id": project_id}, "queued")


# === NoemaForge Autodoc Function Header ===
# Function: teamworker_tick(max_steps: int = 1)
# Purpose: Implement the routine 'teamworker tick'.
# Inputs:
#   - max_steps: int = 1
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - ensure_dirs, join, exists, _list_projects, sort, _write_event, _maybe_kickoff_pm, _load_project, _pending_wakes, _load_json, str, acquire_semaphore
# Returns / emits: int
# Key locals:
#   - baton, candidates, emergency_flag, pid, pr, proj, projects, steps, to_role, ts, w, wp
# === End NoemaForge Autodoc Function Header ===
def teamworker_tick(max_steps: int = 1) -> int:
    ensure_dirs()

    emergency_flag = os.path.join(SYS_DIR, "memergency.checkpoint")
    if os.path.exists(emergency_flag):
        _write_event("S3", "TEAMWORKER_PAUSED_MEM_EMERGENCY", {"subsystem": "teamworker"}, "paused")
        try:
            if runtime_state:
                runtime_state.touch_activity(domain="WORK", actor="teamworker", note={"paused": "memergency"})
        except Exception:
            pass
        return 0

    projects = _list_projects()

    for pid in projects:
        try:
            _maybe_kickoff_pm(pid)
        except Exception as e:
            _write_event("S2", "PM_AUTO_KICKOFF_ERROR", {"project_id": pid}, "error", extra={"error": repr(e)})

    candidates: List[Tuple[int, str, str, str]] = []
    for pid in projects:
        try:
            proj = _load_project(pid)
            if proj.get("status") != "active":
                continue
            for wp in _pending_wakes(pid):
                try:
                    w = _load_json(wp)
                    baton = _load_baton(pid, str(w.get("baton_id") or ""))
                    pr = None
                    ts = str(w.get("ts") or "")
                    if baton:
                        pr = baton.get("priority_class")
                    candidates.append((_prio_idx(str(pr or "normal")), ts, pid, wp))
                except Exception:
                    candidates.append((_prio_idx("normal"), "", pid, wp))
        except Exception:
            continue

    candidates.sort(key=lambda x: (x[0], x[1], x[2]))

    steps = 0
    for prio_i, ts, pid, wp in candidates:
        if steps >= max_steps:
            break
        try:
            w = _load_json(wp)
            to_role = str(w.get("to_role") or "pm")
        except Exception:
            to_role = "pm"

        if not acquire_semaphore(pid, to_role, lease_sec=600):
            continue

        try:
            _process_wake(pid, wp)
            steps += 1
        finally:
            release_semaphore(pid, to_role)

    if steps > 0:
        try:
            if runtime_state:
                runtime_state.mark_completed(domain="WORK", actor="teamworker", note={"steps": steps})
        except Exception:
            pass

    if steps == 0:
        _write_event("S1", "TEAMWORKER_IDLE", {"subsystem": "teamworker"}, "idle")
        try:
            if runtime_state:
                runtime_state.arm_idle(actor="teamworker")
        except Exception:
            pass
    return 0


# -------------------------
# CLI
# -------------------------

# === NoemaForge Autodoc Function Header ===
# Function: main(argv: List[str])
# Purpose: Implement the routine 'main'.
# Inputs:
#   - argv: List[str]
# Called by:
#   - bootstrap/microvm/noemaforge-microvm-run.py
#   - src/bootdoctor.py
#   - src/brainctl.py
#   - src/brainui.py
#   - src/canary_runner.py
#   - src/doctor.py
#   - src/dream_cycle.py
#   - src/firstboot_eval.py
# Calls:
#   - ArgumentParser, add_subparsers, add_parser, add_argument, parse_args, init_project, add_task, print, freeze_project_state, thaw_project_state, list_snapshots, run_recurring
# Returns / emits: int
# Side effects:
#   - spawns subprocesses or workers
# Key locals:
#   - ap, args, p_add, p_aud, p_frz, p_init, p_ls, p_rec, p_thw, p_tw, sid, snaps
# === End NoemaForge Autodoc Function Header ===
def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init-project")
    p_init.add_argument("project_id")
    p_init.add_argument("--title", required=True)
    p_init.add_argument("--priority", type=int, default=100)
    p_init.add_argument("--team-template", default="python-sql-serial")
    p_init.add_argument("--default-stream", default="")

    p_add = sub.add_parser("add-task")
    p_add.add_argument("project_id")
    p_add.add_argument("--title", required=True)
    p_add.add_argument("--priority-class", default="high", choices=PRIORITY_ORDER)
    p_add.add_argument("--stream", default="")

    p_frz = sub.add_parser("freeze-project")
    p_frz.add_argument("project_id")
    p_frz.add_argument("--reason", default="manual")
    p_frz.add_argument("--actor", default="user")
    p_frz.add_argument("--include-artifacts", action="store_true")

    p_thw = sub.add_parser("thaw-project")
    p_thw.add_argument("project_id")
    p_thw.add_argument("--snapshot", default="")
    p_thw.add_argument("--actor", default="user")
    p_thw.add_argument("--restore-artifacts", action="store_true")

    p_ls = sub.add_parser("list-snapshots")
    p_ls.add_argument("project_id")


    sub.add_parser("dailyplan")

    p_rec = sub.add_parser("run-recurring")
    p_rec.add_argument("task_id")

    p_aud = sub.add_parser("run-audit")
    p_aud.add_argument("check_id")

    p_tw = sub.add_parser("teamworker-tick")
    p_tw.add_argument("--max-steps", type=int, default=1)

    args = ap.parse_args(argv)

    if args.cmd == "init-project":
        init_project(args.project_id, args.title, args.priority, args.team_template, args.default_stream)
        return 0

    if args.cmd == "add-task":
        tid = add_task(args.project_id, args.title, args.priority_class, args.stream)
        print(tid)
        return 0


    if args.cmd == "freeze-project":
        ok, rep, code = freeze_project_state(
            args.project_id, actor=args.actor, reason=args.reason, include_artifacts=bool(args.include_artifacts)
        )
        print(json.dumps({"ok": ok, "code": code, "report": rep}, ensure_ascii=False, indent=2))
        return 0 if ok else 2

    if args.cmd == "thaw-project":
        sid = args.snapshot.strip() or None
        ok, rep, code = thaw_project_state(
            args.project_id, actor=args.actor, snapshot_id=sid, restore_artifacts=bool(args.restore_artifacts)
        )
        print(json.dumps({"ok": ok, "code": code, "report": rep}, ensure_ascii=False, indent=2))
        return 0 if ok else 2

    if args.cmd == "list-snapshots":
        snaps = list_snapshots(args.project_id)
        print(json.dumps({"project_id": args.project_id, "snapshots": snaps}, ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "dailyplan":
        print(create_daily_plan())
        return 0

    if args.cmd == "run-recurring":
        return run_recurring(args.task_id)

    if args.cmd == "run-audit":
        return run_audit(args.check_id)

    if args.cmd == "teamworker-tick":
        return teamworker_tick(max_steps=args.max_steps)

    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
