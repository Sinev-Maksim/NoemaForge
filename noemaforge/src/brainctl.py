#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/brainctl.py
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
# File: src/brainctl.py
# Purpose: Provide the main operator CLI for NoemaForge runtime, policy, gateway, and storage actions.
# Invoked by / imported from:
#   - No inbound Python import detected; treat as library leaf or direct entrypoint.
# Public API / entry functions:
#   - sh
#   - write_unit
#   - epoch_contract_path
#   - provision_toolproxy
#   - provision_recurring
#   - provision_auditor
#   - provision_dailyplan
#   - provision_modelscan
#   - provision_storage_guard
#   - provision_teamworker
#   - provision_maintenance
#   - provision
# Inputs:
#   - --contracts-root
#   - --requests-dir
#   - --policy-lock
#   - --full
#   - --json
#   - request_id
#   - --i-mean-it
#   - --epoch-id
#   - --base-epoch-id
#   - --description
# Output formats / side effects:
#   - JSON files
#   - YAML files
#   - copied filesystem artifacts
#   - SQLite databases
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""brainctl.py (v0.17.1)

NoemaForge provisioning + pre-start epoch manager.

This CLI has two personalities:

1) Provisioning (systemd units) — optional, still MVP.
2) Pre-start (epoch) — the important part:
   - runtime is immutable
   - pre-start builds candidate epochs from PreStartChangeRequest queue
   - canary checks (pre-start only)
   - switch current epoch

Note: this seed kit is offline-first; all commands avoid network.
"""


import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

import yaml
import storage_broker

from roadmap import record_signal, list_items as roadmap_list_items, export_report as roadmap_export_report

from bundles import prepare_bundles_for_epoch

from prestart import (
    DEFAULT_CONTRACTS_ROOT,
    DEFAULT_POLICY_LOCK,
    DEFAULT_REQUESTS_DIR,
    build_candidate_epoch,
    current_epoch_id,
    ensure_epoch_initialized,
    epoch_path,
    list_epochs,
    load_requests,
    mark_requests_applied,
    next_epoch_id,
    policy_lock_state,
    read_mode,
    select_requests_for_build,
    set_policy_lock,
    static_checks,
    switch_current_epoch,
    prepare_plugins_for_epoch,
)
from epoch import current_epoch_dir
from platform_paths import DEFAULT_PATHS as _pp

# SEL/WORM
from seclog import verify as sel_verify, seal as sel_seal, verify_anchors as sel_verify_anchors

# Offline APT builder (driver vault)
from offline_apt import build_offline_apt_plan, build_offline_repo_from_plan

# ModelStore / fleet routing
import model_registry
import model_scorecards
import model_installer_plan
import firstboot_eval
import production_ai_contracts

# Incidents
import incidents
from platform_paths import DEFAULT_PATHS as _pp

CONFIG_DIR = str(_pp.root / "configs")
SYSTEMD_DIR = "/etc/systemd/system"


# === NoemaForge Autodoc Function Header ===
# Function: sh(cmd: list[str])
# Purpose: Implement the routine 'sh'.
# Inputs:
#   - cmd: list[str]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - check_call
# Returns / emits: None
# === End NoemaForge Autodoc Function Header ===
def sh(cmd: list[str]) -> None:
    subprocess.check_call(cmd)


# === NoemaForge Autodoc Function Header ===
# Function: _load_yaml(path: str)
# Purpose: Implement the routine ' load yaml'.
# Inputs:
#   - path: str
# Called by:
#   - src/noemaforge_core.py
#   - src/canary_runner.py
#   - src/daily_scheduler.py
#   - src/fixture_bundle.py
#   - src/flow_metrics.py
#   - src/incidents.py
#   - src/knowledge/policy.py
#   - src/llm_backends_manager.py
# Calls:
#   - open, safe_load
# Returns / emits: Any
# Side effects:
#   - reads or writes files
# Key locals:
#   - f
# === End NoemaForge Autodoc Function Header ===
def _load_yaml(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _active_production_registry_refs(epoch_dir: str = "") -> List[str]:
    candidates = []
    if epoch_dir:
        candidates.append(os.path.join(epoch_dir, "unified-registry.json"))
    candidates.append(os.path.join(CONFIG_DIR, "unified-registry.json"))
    for path in candidates:
        try:
            if os.path.exists(path):
                registry = production_ai_contracts.load_contract_doc(path)
                return production_ai_contracts.active_registry_refs(registry)
        except Exception:
            continue
    return []


# === NoemaForge Autodoc Function Header ===
# Function: write_unit(path: str, content: str)
# Purpose: Implement the routine 'write unit'.
# Inputs:
#   - path: str
#   - content: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - open, write
# Returns / emits: None
# Side effects:
#   - reads or writes files
# Key locals:
#   - f
# === End NoemaForge Autodoc Function Header ===
def write_unit(path: str, content: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


# -------------------------
# Provisioning (unchanged MVP)
# -------------------------


# === NoemaForge Autodoc Function Header ===
# Function: epoch_contract_path(contracts_root: str, filename: str, fallback: str)
# Purpose: Prefer current epoch contract file if present.
# Inputs:
#   - contracts_root: str
#   - filename: str
#   - fallback: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - current_epoch_dir, str, join, exists
# Returns / emits: str
# Key locals:
#   - cand, ep_dir
# === End NoemaForge Autodoc Function Header ===
def epoch_contract_path(contracts_root: str, filename: str, fallback: str) -> str:
    """Prefer current epoch contract file if present."""
    try:
        ep_dir = current_epoch_dir(str(contracts_root or DEFAULT_CONTRACTS_ROOT))
        if ep_dir:
            cand = os.path.join(ep_dir, filename)
            if os.path.exists(cand):
                return cand
    except Exception:
        pass
    return fallback

# === NoemaForge Autodoc Function Header ===
# Function: provision_toolproxy()
# Purpose: Implement the routine 'provision toolproxy'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - write_unit, join
# Returns / emits: str
# Key locals:
#   - svc, svc_body
# === End NoemaForge Autodoc Function Header ===
def provision_toolproxy() -> str:
    svc = "noemaforge-toolproxy.service"

    svc_body = """[Unit]
Description=NoemaForge ToolProxy (capability-gated tools/LLM)
After=local-fs.target noemaforge-llm-gateway.service
Wants=noemaforge-core.slice noemaforge-llm-gateway.service
ConditionPathExists=/var/lib/noemaforge/.sys/setup.done

[Service]
User=noemaforge
Group=noemaforge
Slice=noemaforge-core.slice
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/var/lib/noemaforge /run/noemaforge
ReadWritePaths=/var/lib/modelstore

ExecStart=/usr/bin/python3 /opt/noemaforge/src/toolproxy.py

Restart=on-failure
RestartSec=2

[Install]
WantedBy=multi-user.target
"""

    write_unit(os.path.join(SYSTEMD_DIR, svc), svc_body)
    return svc


# === NoemaForge Autodoc Function Header ===
# Function: provision_recurring()
# Purpose: Implement the routine 'provision recurring'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _load_yaml, join, get, write_unit, append
# Returns / emits: list[str]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - oncal, rec, svc, svc_body, t, tid, timers, tmr, tmr_body
# === End NoemaForge Autodoc Function Header ===
def provision_recurring() -> list[str]:
    rec = _load_yaml(os.path.join(CONFIG_DIR, "recurring-tasks.yaml"))
    timers: list[str] = []
    for t in rec.get("tasks", []) or []:
        tid = t["id"]
        oncal = t.get("schedule_oncalendar")
        if not oncal:
            continue
        svc = f"noemaforge-recurring@{tid}.service"
        tmr = f"noemaforge-recurring@{tid}.timer"

        svc_body = f"""[Unit]
Description=NoemaForge Recurring Task {tid}
After=local-fs.target noemaforge-toolproxy.service
Wants=noemaforge-models.slice noemaforge-toolproxy.service
ConditionPathExists=/var/lib/noemaforge/.sys/setup.done

[Service]
Type=oneshot
User=noemaforge
Group=noemaforge
Slice=noemaforge-models.slice
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/var/lib/noemaforge /workspace /var/lib/modelstore /run/noemaforge

ExecStart=/usr/bin/python3 /opt/noemaforge/src/noemaforge_core.py run-recurring {tid}
"""

        tmr_body = f"""[Unit]
Description=NoemaForge Recurring Task Timer {tid}

[Timer]
OnCalendar={oncal}
Persistent=true
Unit={svc}

[Install]
WantedBy=timers.target
"""

        write_unit(os.path.join(SYSTEMD_DIR, svc), svc_body)
        write_unit(os.path.join(SYSTEMD_DIR, tmr), tmr_body)
        timers.append(tmr)
    return timers


# === NoemaForge Autodoc Function Header ===
# Function: provision_auditor()
# Purpose: Implement the routine 'provision auditor'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _load_yaml, join, get, write_unit, append
# Returns / emits: list[str]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - aud, chk, cid, oncal, svc, svc_body, timers, tmr, tmr_body
# === End NoemaForge Autodoc Function Header ===
def provision_auditor() -> list[str]:
    aud = _load_yaml(os.path.join(CONFIG_DIR, "daily-auditor.yaml"))
    timers: list[str] = []
    for chk in aud.get("checks", []) or []:
        cid = chk["id"]
        oncal = chk.get("schedule_oncalendar")
        if not oncal:
            continue
        svc = f"noemaforge-auditor@{cid}.service"
        tmr = f"noemaforge-auditor@{cid}.timer"
        svc_body = f"""[Unit]
Description=NoemaForge Auditor Check {cid}
After=local-fs.target
ConditionPathExists=/var/lib/noemaforge/.sys/setup.done

[Service]
Type=oneshot
User=noemaforge
Group=noemaforge
Slice=noemaforge-core.slice
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/var/lib/noemaforge

ExecStart=/usr/bin/python3 /opt/noemaforge/src/noemaforge_core.py run-audit {cid}
"""
        tmr_body = f"""[Unit]
Description=NoemaForge Auditor Timer {cid}

[Timer]
OnCalendar={oncal}
Persistent=true
Unit={svc}

[Install]
WantedBy=timers.target
"""
        write_unit(os.path.join(SYSTEMD_DIR, svc), svc_body)
        write_unit(os.path.join(SYSTEMD_DIR, tmr), tmr_body)
        timers.append(tmr)
    return timers


# === NoemaForge Autodoc Function Header ===
# Function: provision_dailyplan()
# Purpose: Implement the routine 'provision dailyplan'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - write_unit, join
# Returns / emits: str
# Key locals:
#   - svc, svc_body, tmr, tmr_body
# === End NoemaForge Autodoc Function Header ===
def provision_dailyplan() -> str:
    svc = "noemaforge-dailyplan.service"
    tmr = "noemaforge-dailyplan.timer"
    svc_body = """[Unit]
Description=NoemaForge DailyPlan generator
After=local-fs.target
ConditionPathExists=/var/lib/noemaforge/.sys/setup.done

[Service]
Type=oneshot
User=noemaforge
Group=noemaforge
Slice=noemaforge-core.slice
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/var/lib/noemaforge

ExecStart=/usr/bin/python3 /opt/noemaforge/src/noemaforge_core.py dailyplan
"""
    tmr_body = """[Unit]
Description=NoemaForge DailyPlan Timer

[Timer]
OnCalendar=*-*-* 00:05:00
Persistent=true
Unit=noemaforge-dailyplan.service

[Install]
WantedBy=timers.target
"""
    write_unit(os.path.join(SYSTEMD_DIR, svc), svc_body)
    write_unit(os.path.join(SYSTEMD_DIR, tmr), tmr_body)
    return tmr


# === NoemaForge Autodoc Function Header ===
# Function: provision_modelscan()
# Purpose: Periodically rebuild ModelStore registry (model_registry.json).
# Inputs:
#   - No explicit parameters.
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - write_unit, join
# Returns / emits: str
# Key locals:
#   - svc, svc_body, tmr, tmr_body
# === End NoemaForge Autodoc Function Header ===
def provision_modelscan() -> str:
    """Periodically rebuild ModelStore registry (model_registry.json)."""
    svc = "noemaforge-modelscan.service"
    tmr = "noemaforge-modelscan.timer"
    svc_body = """[Unit]
Description=NoemaForge ModelStore Registry Scan
After=local-fs.target
ConditionPathExists=/var/lib/noemaforge/.sys/setup.done

[Service]
Type=oneshot
User=noemaforge
Group=noemaforge
Slice=noemaforge-core.slice
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/var/lib/noemaforge /var/lib/modelstore

ExecStart=/usr/bin/python3 /opt/noemaforge/src/model_registry.py --write
"""
    tmr_body = """[Unit]
Description=NoemaForge ModelScan Timer

[Timer]
OnBootSec=60
OnUnitActiveSec=10m
Persistent=true
Unit=noemaforge-modelscan.service

[Install]
WantedBy=timers.target
"""
    write_unit(os.path.join(SYSTEMD_DIR, svc), svc_body)
    write_unit(os.path.join(SYSTEMD_DIR, tmr), tmr_body)
    return tmr


# === NoemaForge Autodoc Function Header ===
# Function: provision_storage_guard()
# Purpose: Periodic storage guard enforcing StoragePolicy on mounted volumes (best-effort).
# Inputs:
#   - No explicit parameters.
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - makedirs, write_unit, run, join, splitlines
# Returns / emits: str
# Side effects:
#   - creates directories
#   - spawns subprocesses or workers
# Key locals:
#   - svc, svc_body, tmr, tmr_body
# === End NoemaForge Autodoc Function Header ===
def provision_storage_guard() -> str:
    """Periodic storage guard enforcing StoragePolicy on mounted volumes (best-effort)."""
    svc = "noemaforge-storage-guard.service"
    tmr = "noemaforge-storage-guard.timer"
    svc_body = """[Unit]
Description=NoemaForge Storage Guard (StoragePolicy enforcement)
After=local-fs.target
ConditionPathExists=/var/lib/noemaforge/.sys/setup.done

[Service]
Type=oneshot
User=root
Group=root
Slice=noemaforge-core.slice
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
CapabilityBoundingSet=CAP_SYS_ADMIN CAP_DAC_OVERRIDE
AmbientCapabilities=CAP_SYS_ADMIN CAP_DAC_OVERRIDE
ReadWritePaths=/var/lib/noemaforge /workspace/outbox
ExecStart=/usr/bin/python3 /opt/noemaforge/src/brainctl.py storage guard --once
"""
    tmr_body = """[Unit]
Description=NoemaForge Storage Guard Timer

[Timer]
OnBootSec=45s
OnUnitActiveSec=60s
Unit=noemaforge-storage-guard.service

[Install]
WantedBy=timers.target
"""
    os.makedirs("/etc/systemd/system", exist_ok=True)
    write_unit(f"/etc/systemd/system/{svc}", "\n".join(svc_body.splitlines()) + "\n")
    write_unit(f"/etc/systemd/system/{tmr}", "\n".join(tmr_body.splitlines()) + "\n")
    subprocess.run(["systemctl", "daemon-reload"], check=False)
    subprocess.run(["systemctl", "enable", "--now", tmr], check=False)
    return tmr

# === NoemaForge Autodoc Function Header ===
# Function: provision_teamworker()
# Purpose: Implement the routine 'provision teamworker'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - write_unit, join
# Returns / emits: str
# Key locals:
#   - svc, svc_body, tmr, tmr_body
# === End NoemaForge Autodoc Function Header ===
def provision_teamworker() -> str:
    svc = "noemaforge-teamworker.service"
    tmr = "noemaforge-teamworker.timer"

    svc_body = """[Unit]
Description=NoemaForge TeamWorker (serial baton execution)
After=local-fs.target noemaforge-toolproxy.service
Wants=noemaforge-core.slice noemaforge-toolproxy.service
ConditionPathExists=/var/lib/noemaforge/.sys/setup.done

[Service]
Type=oneshot
User=noemaforge
Group=noemaforge
Slice=noemaforge-core.slice
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/var/lib/noemaforge /workspace /var/lib/modelstore /run/noemaforge

ExecStart=/usr/bin/python3 /opt/noemaforge/src/noemaforge_core.py teamworker-tick --max-steps 1
"""

    tmr_body = """[Unit]
Description=NoemaForge TeamWorker Timer

[Timer]
OnBootSec=30s
OnUnitActiveSec=30s
AccuracySec=1s
Persistent=true
Unit=noemaforge-teamworker.service

[Install]
WantedBy=timers.target
"""

    write_unit(os.path.join(SYSTEMD_DIR, svc), svc_body)
    write_unit(os.path.join(SYSTEMD_DIR, tmr), tmr_body)
    return tmr


# === NoemaForge Autodoc Function Header ===
# Function: provision_maintenance()
# Purpose: Install the periodic maintenance tick.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - write_unit, join
# Returns / emits: str
# Key locals:
#   - svc, svc_body, tmr, tmr_body
# === End NoemaForge Autodoc Function Header ===
def provision_maintenance() -> str:
    """Install the periodic maintenance tick.

    - Runs SR-lite + recovery after idle>5m
    - Runs daily SLA guard (deadline - mean - sigma)
    """

    svc = "noemaforge-maintenance.service"
    tmr = "noemaforge-maintenance.timer"

    svc_body = """[Unit]
Description=NoemaForge maintenance tick (SR-lite + recovery + dispatch)
After=noemaforge-toolproxy.service noemaforge-memsentinel.service

[Service]
Type=oneshot
User=noemaforge
Group=noemaforge
Slice=noemaforge-core.slice
Environment=PYTHONUNBUFFERED=1
ExecStart=/usr/bin/python3 /opt/noemaforge/src/maintenance.py tick
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/noemaforge /var/lib/modelstore /workspace /run/noemaforge
"""

    tmr_body = """[Unit]
Description=NoemaForge maintenance tick timer

[Timer]
OnBootSec=45s
OnUnitActiveSec=60s
AccuracySec=5s

[Install]
WantedBy=timers.target
"""

    write_unit(os.path.join(SYSTEMD_DIR, svc), svc_body)
    write_unit(os.path.join(SYSTEMD_DIR, tmr), tmr_body)
    return tmr


# === NoemaForge Autodoc Function Header ===
# Function: provision()
# Purpose: Implement the routine 'provision'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - provision_toolproxy, extend, append, sh, provision_recurring, provision_auditor, provision_dailyplan, provision_modelscan, provision_storage_guard, provision_teamworker, provision_maintenance
# Returns / emits: int
# Side effects:
#   - appends to logs or files
# Key locals:
#   - t, timers, tool_svc
# === End NoemaForge Autodoc Function Header ===
def provision() -> int:
    tool_svc = provision_toolproxy()

    timers: list[str] = []
    timers.extend(provision_recurring())
    timers.extend(provision_auditor())
    timers.append(provision_dailyplan())
    timers.append(provision_modelscan())
    timers.append(provision_storage_guard())
    timers.append(provision_teamworker())
    timers.append(provision_maintenance())

    sh(["systemctl", "daemon-reload"])

    sh(["systemctl", "enable", "--now", tool_svc])

    for t in timers:
        sh(["systemctl", "enable", "--now", t])

    return 0


# -------------------------
# Epoch / Pre-start
# -------------------------

# === NoemaForge Autodoc Function Header ===
# Function: cmd_epoch_status(args: argparse.Namespace)
# Purpose: Implement the routine 'cmd epoch status'.
# Inputs:
#   - args: argparse.Namespace
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - ensure_epoch_initialized, current_epoch_id, epoch_path, print, list_epochs, policy_lock_state, join
# Returns / emits: int
# Key locals:
#   - all_epochs, cur, ep_dir
# === End NoemaForge Autodoc Function Header ===
def cmd_epoch_status(args: argparse.Namespace) -> int:
    ensure_epoch_initialized(config_dir=CONFIG_DIR, contracts_root=args.contracts_root)
    cur = current_epoch_id(args.contracts_root)
    ep_dir = epoch_path(cur, args.contracts_root)
    print(f"current_epoch_id: {cur}")
    print(f"current_epoch_dir: {ep_dir}")
    print(f"policy_lock: {policy_lock_state(args.policy_lock)}")
    all_epochs = list_epochs(args.contracts_root)
    print(f"epochs: {', '.join(all_epochs) if all_epochs else '(none)'}")
    return 0


# === NoemaForge Autodoc Function Header ===
# Function: cmd_prestart_queue(args: argparse.Namespace)
# Purpose: Implement the routine 'cmd prestart queue'.
# Inputs:
#   - args: argparse.Namespace
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - load_requests, print, str, get, splitext, basename
# Returns / emits: int
# Key locals:
#   - obj, r, reqs, rid, st, who
# === End NoemaForge Autodoc Function Header ===
def cmd_prestart_queue(args: argparse.Namespace) -> int:
    reqs = load_requests(args.requests_dir)
    if not reqs:
        print("(no prestart requests)")
        return 0
    for r in reqs:
        obj = r.obj
        rid = str(obj.get("request_id") or os.path.splitext(os.path.basename(r.path))[0])
        st = str(obj.get("status") or "")
        who = (obj.get("created_by") or {}).get("actor_type")
        print(f"- {rid}  status={st}  by={who}  file={os.path.basename(r.path)}")
    return 0


# === NoemaForge Autodoc Function Header ===
# Function: _rewrite_request_status(req_path: str, status: str)
# Purpose: Implement the routine ' rewrite request status'.
# Inputs:
#   - req_path: str
#   - status: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - endswith, safe_dump, load, dump, safe_load, open
# Returns / emits: None
# Side effects:
#   - reads or writes files
#   - serializes structured data
# Key locals:
#   - obj
# === End NoemaForge Autodoc Function Header ===
def _rewrite_request_status(req_path: str, status: str) -> None:
    # Keep format: yaml stays yaml, json stays json.
    if req_path.endswith(".json"):
        import json as _json
        obj = _json.load(open(req_path, "r", encoding="utf-8"))
        obj["status"] = status
        _json.dump(obj, open(req_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        return

    obj = yaml.safe_load(open(req_path, "r", encoding="utf-8")) or {}
    obj["status"] = status
    yaml.safe_dump(obj, open(req_path, "w", encoding="utf-8"), sort_keys=False, allow_unicode=True)


# === NoemaForge Autodoc Function Header ===
# Function: cmd_prestart_approve(args: argparse.Namespace)
# Purpose: Implement the routine 'cmd prestart approve'.
# Inputs:
#   - args: argparse.Namespace
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - load_requests, _rewrite_request_status, print, str, get, splitext, basename
# Returns / emits: int
# Key locals:
#   - r, reqs, rid, tgt
# === End NoemaForge Autodoc Function Header ===
def cmd_prestart_approve(args: argparse.Namespace) -> int:
    reqs = load_requests(args.requests_dir)
    tgt = None
    for r in reqs:
        rid = str(r.obj.get("request_id") or os.path.splitext(os.path.basename(r.path))[0])
        if rid == args.request_id:
            tgt = r
            break
    if not tgt:
        print("request not found", file=sys.stderr)
        return 2
    _rewrite_request_status(tgt.path, "approved")
    print(f"approved: {args.request_id}")
    return 0


# === NoemaForge Autodoc Function Header ===
# Function: cmd_prestart_reject(args: argparse.Namespace)
# Purpose: Implement the routine 'cmd prestart reject'.
# Inputs:
#   - args: argparse.Namespace
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - load_requests, _rewrite_request_status, print, str, get, splitext, basename
# Returns / emits: int
# Key locals:
#   - r, reqs, rid, tgt
# === End NoemaForge Autodoc Function Header ===
def cmd_prestart_reject(args: argparse.Namespace) -> int:
    reqs = load_requests(args.requests_dir)
    tgt = None
    for r in reqs:
        rid = str(r.obj.get("request_id") or os.path.splitext(os.path.basename(r.path))[0])
        if rid == args.request_id:
            tgt = r
            break
    if not tgt:
        print("request not found", file=sys.stderr)
        return 2
    _rewrite_request_status(tgt.path, "rejected")
    print(f"rejected: {args.request_id}")
    return 0


# === NoemaForge Autodoc Function Header ===
# Function: cmd_prestart_lock(args: argparse.Namespace)
# Purpose: Implement the routine 'cmd prestart lock'.
# Inputs:
#   - args: argparse.Namespace
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - set_policy_lock, print
# Returns / emits: int
# === End NoemaForge Autodoc Function Header ===
def cmd_prestart_lock(args: argparse.Namespace) -> int:
    set_policy_lock("LOCKED", args.policy_lock)
    print("policy_lock: LOCKED")
    return 0


# === NoemaForge Autodoc Function Header ===
# Function: cmd_prestart_unlock(args: argparse.Namespace)
# Purpose: Implement the routine 'cmd prestart unlock'.
# Inputs:
#   - args: argparse.Namespace
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - set_policy_lock, print
# Returns / emits: int
# === End NoemaForge Autodoc Function Header ===
def cmd_prestart_unlock(args: argparse.Namespace) -> int:
    # Minimal safety friction.
    if not args.i_mean_it:
        print("Refusing: add --i-mean-it to unlock policy lock", file=sys.stderr)
        return 2
    set_policy_lock("UNLOCKED", args.policy_lock)
    print("policy_lock: UNLOCKED")
    return 0


# === NoemaForge Autodoc Function Header ===
# Function: cmd_prestart_build(args: argparse.Namespace)
# Purpose: Implement the routine 'cmd prestart build'.
# Inputs:
#   - args: argparse.Namespace
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - ensure_epoch_initialized, read_mode, select_requests_for_build, static_checks, print, policy_lock_state, next_epoch_id, load_requests, build_candidate_epoch, epoch_path, len
# Returns / emits: int
# Key locals:
#   - desired, eid, mode, p, reqs
# === End NoemaForge Autodoc Function Header ===
def cmd_prestart_build(args: argparse.Namespace) -> int:
    ensure_epoch_initialized(config_dir=CONFIG_DIR, contracts_root=args.contracts_root)

    # v0.9.4: build-epoch runs canaries; enforce pre-start mode + policy lock.
    mode = read_mode()
    if mode == "runtime":
        print(
            "Refusing: runtime mode detected (build-epoch runs canaries). "
            "Reboot into pre-start/maintenance mode.",
            file=sys.stderr,
        )
        return 2
    if policy_lock_state(args.policy_lock) != "UNLOCKED":
        print("Refusing: policy lock is not UNLOCKED. Run: brainctl prestart unlock --i-mean-it", file=sys.stderr)
        return 2

    desired = args.epoch_id or next_epoch_id(args.contracts_root)

    reqs = select_requests_for_build(load_requests(args.requests_dir))

    try:
        eid = build_candidate_epoch(
            desired_epoch_id=desired,
            contracts_root=args.contracts_root,
            base_epoch_id=args.base_epoch_id,
            requests=reqs,
            created_by={"actor_type": "human", "channel": "brainctl"},
            description=args.description or "",
            user_comment=args.user_comment or "",
        )
    except RuntimeError as e:
        print(f"Refusing: {e}", file=sys.stderr)
        return 2

    ok, problems = static_checks(epoch_path(eid, args.contracts_root))
    if not ok:
        print("candidate built, but static checks FAILED:")
        for p in problems:
            print("  -", p)
        return 1

    print(f"candidate_epoch_built: {eid}")
    print(f"candidate_dir: {epoch_path(eid, args.contracts_root)}")
    if reqs:
        print(f"included_requests: {len(reqs)}")
    if args.user_comment:
        print("user_comment_applied: yes")
    return 0


# === NoemaForge Autodoc Function Header ===
# Function: cmd_prestart_apply(args: argparse.Namespace)
# Purpose: Implement the routine 'cmd prestart apply'.
# Inputs:
#   - args: argparse.Namespace
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - ensure_epoch_initialized, read_mode, epoch_path, current_epoch_id, join, print, switch_current_epoch, load_requests, mark_requests_applied, policy_lock_state, load, str
# Returns / emits: int
# Key locals:
#   - all_reqs, applied_ids, base_current, base_expected, build_report, build_report_path, ch, ep_dir, law_dir, man, mode, pr
# === End NoemaForge Autodoc Function Header ===
def cmd_prestart_apply(args: argparse.Namespace) -> int:
    ensure_epoch_initialized(config_dir=CONFIG_DIR, contracts_root=args.contracts_root)

    # Canary is pre-start only. Runtime must not auto-run canaries.
    # Break-glass is possible, but requires explicit flags.
    mode = read_mode()
    if mode == "runtime" and not args.override_runtime:
        print(
            "Refusing: runtime mode detected (canary is pre-start only). "
            "Reboot into pre-start/maintenance mode, or pass --override-runtime --i-mean-it (break-glass).",
            file=sys.stderr,
        )
        return 2
    if mode == "runtime" and args.override_runtime and not args.i_mean_it:
        print("Refusing: add --i-mean-it for break-glass runtime override", file=sys.stderr)
        return 2

    if policy_lock_state(args.policy_lock) != "UNLOCKED":
        print("Refusing: policy lock is not UNLOCKED. Run: brainctl prestart unlock --i-mean-it", file=sys.stderr)
        return 2

    ep_dir = epoch_path(args.epoch_id, args.contracts_root)

    # Safety: refuse to apply stale candidate built from a different base.
    try:
        import json as _json
        man = _json.load(open(os.path.join(ep_dir, "epoch_manifest.json"), "r", encoding="utf-8"))
        base_expected = str(man.get("base_epoch_id") or "")
    except Exception:
        base_expected = ""
    base_current = current_epoch_id(args.contracts_root)
    if base_expected and base_expected != base_current:
        print(
            f"Refusing: candidate base_epoch_id={base_expected} != current_epoch_id={base_current}. Rebuild candidate epoch.",
            file=sys.stderr,
        )
        return 2

    # v0.9.4: build-epoch runs per-change canaries + final integration canary.
    # apply-epoch only verifies the build artifacts and switches epochs.

    import json as _json
    build_report_path = os.path.join(ep_dir, "prestart_build_report.json")
    if not os.path.exists(build_report_path):
        print("Refusing: missing prestart_build_report.json (run: brainctl prestart build-epoch)", file=sys.stderr)
        return 2
    try:
        build_report = _json.load(open(build_report_path, "r", encoding="utf-8"))
    except Exception:
        print("Refusing: failed to read prestart_build_report.json", file=sys.stderr)
        return 2

    if str(build_report.get("overall_decision") or "").lower().strip() != "pass":
        print("Refusing: build report is not PASS (candidate is not safe to apply)", file=sys.stderr)
        return 2

    trig = build_report.get("trigger") or {}
    if not (bool(trig.get("system_changes")) or bool(trig.get("policy_changes")) or bool(trig.get("user_request"))):
        print("Refusing: epoch switch has no valid trigger (system/policy/user)", file=sys.stderr)
        return 2

    # Verify scary_report.json exists and passes.
    scary_path = os.path.join(ep_dir, "scary_report.json")
    if not os.path.exists(scary_path):
        # Some builds may store the path in build_report.final_canary
        scary_path = str(((build_report.get("final_canary") or {}).get("report_path") or scary_path))
    if not os.path.exists(scary_path):
        print("Refusing: missing scary_report.json (final canary)", file=sys.stderr)
        return 2
    try:
        scary = _json.load(open(scary_path, "r", encoding="utf-8"))
    except Exception:
        print("Refusing: failed to read scary_report.json", file=sys.stderr)
        return 2
    if str(scary.get("decision") or "").lower().strip() != "pass" or not bool(scary.get("overall_ok")):
        print("Refusing: scary_report is not PASS", file=sys.stderr)
        return 2

    applied_ids: List[str] = []
    for ch in (build_report.get("changes") or []) or []:
        try:
            if str(ch.get("status") or "") == "applied":
                applied_ids.append(str(ch.get("request_id") or ""))
        except Exception:
            continue
    applied_ids = [x for x in applied_ids if x]

    print(f"prestart_build_report: {build_report_path}")
    print(f"scary_report: {scary_path}")
    print(f"applied_changes: {len(applied_ids)}")

        # Pre-start: prepare/install requested bundles (ToolVault bundles, offline apt repo bundles).
    # This is a *pre-start* operation and is audited to SEL/WORM.
    try:
        law_dir = epoch_path(base_current, args.contracts_root)
        all_reqs = load_requests(args.requests_dir)
        ok_b, b_problems = prepare_bundles_for_epoch(
            epoch_dir=ep_dir,
            law_epoch_dir=law_dir,
            request_objs=all_reqs,
            only_request_ids=applied_ids,
        )
        if not ok_b:
            print("Refusing: bundle preparation failed:", file=sys.stderr)
            for pr in b_problems[:50]:
                print(f" - {pr}", file=sys.stderr)
            return 2
        if b_problems:
            print("bundle_prepare_warnings:")
            for pr in b_problems[:20]:
                print(f" - {pr}")
    except Exception as e:
        print(f"Refusing: bundle preparation exception: {e!r}", file=sys.stderr)
        return 2

    # Pre-start: prepare ToolVault plugin bundles for the candidate epoch.
    try:
        law_dir = epoch_path(base_current, args.contracts_root)
        ok_p, p_problems = prepare_plugins_for_epoch(epoch_dir=ep_dir, law_epoch_dir=law_dir)
        if not ok_p:
            print("Refusing: plugin preparation failed:", file=sys.stderr)
            for pr in p_problems[:50]:
                print(f" - {pr}", file=sys.stderr)
            return 2
        if p_problems:
            print("plugin_prepare_warnings:")
            for pr in p_problems[:20]:
                print(f" - {pr}")
    except Exception as e:
        print(f"Refusing: plugin preparation exception: {e!r}", file=sys.stderr)
        return 2

    # Switch
    trace_id = str(getattr(args, "trace_id", "") or scary.get("trace_id") or build_report.get("trace_id") or production_ai_contracts.new_trace_id("epoch-apply"))
    try:
        release_evidence = production_ai_contracts.build_epoch_release_evidence(
            args.epoch_id,
            build_report,
            scary,
            build_report_path=build_report_path,
            scary_report_path=scary_path,
            registry_refs=_active_production_registry_refs(ep_dir),
            trace_id=trace_id,
            actor="brainctl",
        )
        if not (release_evidence.get("gate") or {}).get("ok") or not (release_evidence.get("rollout") or {}).get("ok"):
            print("Refusing: release evidence gate/rollout is not passing", file=sys.stderr)
            return 2
        release_evidence_path = os.path.join(ep_dir, "release_evidence.json")
        with open(release_evidence_path, "w", encoding="utf-8") as f:
            json.dump(release_evidence, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Refusing: failed to write release evidence: {e!r}", file=sys.stderr)
        return 2

    switch_current_epoch(args.epoch_id, args.contracts_root)

    # Mark requests applied (only those recorded as applied in the build report)
    all_reqs = load_requests(args.requests_dir)
    mark_requests_applied(all_reqs, applied_epoch_id=args.epoch_id, only_request_ids=applied_ids)

    print(f"current_epoch_switched: {args.epoch_id}")
    print(f"trace_id: {trace_id}")
    print(f"release_evidence: {release_evidence_path}")
    return 0



# === NoemaForge Autodoc Function Header ===
# Function: _epoch_dir_from_args(args: argparse.Namespace)
# Purpose: Implement the routine ' epoch dir from args'.
# Inputs:
#   - args: argparse.Namespace
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - current_epoch_id, epoch_path
# Returns / emits: str
# Key locals:
#   - eid
# === End NoemaForge Autodoc Function Header ===
def _epoch_dir_from_args(args: argparse.Namespace) -> str:
    eid = current_epoch_id(args.contracts_root)
    return epoch_path(eid, args.contracts_root)


# === NoemaForge Autodoc Function Header ===
# Function: cmd_roadmap_list(args: argparse.Namespace)
# Purpose: Implement the routine 'cmd roadmap list'.
# Inputs:
#   - args: argparse.Namespace
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _epoch_dir_from_args, roadmap_list_items, print, safe_dump, int, strip
# Returns / emits: int
# Side effects:
#   - serializes structured data
# Key locals:
#   - epoch_dir, out
# === End NoemaForge Autodoc Function Header ===
def cmd_roadmap_list(args: argparse.Namespace) -> int:
    epoch_dir = _epoch_dir_from_args(args)
    out = roadmap_list_items(epoch_dir=epoch_dir, target_role=(args.target_role or "").strip() or None, limit=int(args.limit))
    print(yaml.safe_dump(out, sort_keys=False, allow_unicode=True))
    return 0


# === NoemaForge Autodoc Function Header ===
# Function: cmd_roadmap_export(args: argparse.Namespace)
# Purpose: Implement the routine 'cmd roadmap export'.
# Inputs:
#   - args: argparse.Namespace
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _epoch_dir_from_args, roadmap_export_report, print, safe_dump, int, strip, bool
# Returns / emits: int
# Side effects:
#   - serializes structured data
# Key locals:
#   - epoch_dir, res
# === End NoemaForge Autodoc Function Header ===
def cmd_roadmap_export(args: argparse.Namespace) -> int:
    epoch_dir = _epoch_dir_from_args(args)
    res = roadmap_export_report(
        epoch_dir=epoch_dir,
        target_role=(args.target_role or "").strip() or None,
        include_role_roadmaps=not bool(args.no_role_roadmaps),
        limit=int(args.limit),
    )
    print(yaml.safe_dump(res, sort_keys=False, allow_unicode=True))
    return 0


# === NoemaForge Autodoc Function Header ===
# Function: cmd_roadmap_record(args: argparse.Namespace)
# Purpose: Implement the routine 'cmd roadmap record'.
# Inputs:
#   - args: argparse.Namespace
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _epoch_dir_from_args, record_signal, print, str, safe_dump
# Returns / emits: int
# Side effects:
#   - serializes structured data
# Key locals:
#   - epoch_dir, requested_by, sig
# === End NoemaForge Autodoc Function Header ===
def cmd_roadmap_record(args: argparse.Namespace) -> int:
    epoch_dir = _epoch_dir_from_args(args)
    requested_by = {
        "stream_id": str(args.source_stream),
        "role": str(args.source_role),
        "project_id": str(args.project_id),
        "run_id": str(args.run_id),
        "process_id": str(args.process_id),
    }
    sig = record_signal(
        target_role=str(args.target_role),
        key=str(args.key),
        title=str(args.title),
        description=str(args.description),
        requested_by=requested_by,
    )
    print(yaml.safe_dump(sig, sort_keys=False, allow_unicode=True))
    return 0



# === NoemaForge Autodoc Function Header ===
# Function: cmd_incidents_list(args: argparse.Namespace)
# Purpose: Implement the routine 'cmd incidents list'.
# Inputs:
#   - args: argparse.Namespace
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - list_incidents, print, str, int, dumps, get
# Returns / emits: int
# Side effects:
#   - serializes structured data
# Key locals:
#   - it, items
# === End NoemaForge Autodoc Function Header ===
def cmd_incidents_list(args: argparse.Namespace) -> int:
    items = incidents.list_incidents(status=str(args.status or ""), kind=str(args.kind or ""), limit=int(args.limit or 50))
    if args.json:
        print(json.dumps({"ok": True, "items": items}, ensure_ascii=False, indent=2))
        return 0
    for it in items:
        print(f"{it.get('incident_id')} [{it.get('severity')} {it.get('status')}] {it.get('kind')}: {it.get('title')}")
    return 0


# === NoemaForge Autodoc Function Header ===
# Function: cmd_incidents_show(args: argparse.Namespace)
# Purpose: Implement the routine 'cmd incidents show'.
# Inputs:
#   - args: argparse.Namespace
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - get_incident, print, str, dumps
# Returns / emits: int
# Side effects:
#   - serializes structured data
# Key locals:
#   - obj
# === End NoemaForge Autodoc Function Header ===
def cmd_incidents_show(args: argparse.Namespace) -> int:
    obj = incidents.get_incident(str(args.incident_id))
    print(json.dumps({"ok": True, "incident": obj}, ensure_ascii=False, indent=2))
    return 0


# === NoemaForge Autodoc Function Header ===
# Function: cmd_incidents_update(args: argparse.Namespace, action: str)
# Purpose: Implement the routine 'cmd incidents update'.
# Inputs:
#   - args: argparse.Namespace
#   - action: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - update_incident, print, dumps, str
# Returns / emits: int
# Side effects:
#   - serializes structured data
# Key locals:
#   - upd
# === End NoemaForge Autodoc Function Header ===
def cmd_incidents_update(args: argparse.Namespace, action: str) -> int:
    upd = incidents.update_incident(incident_id=str(args.incident_id), action=action, actor={"subsystem": "brainctl"}, comment=str(args.comment or ""))
    print(json.dumps({"ok": True, "update": upd}, ensure_ascii=False, indent=2))
    return 0

# === NoemaForge Autodoc Function Header ===
# Function: cmd_hwscan(args: argparse.Namespace)
# Purpose: Implement the routine 'cmd hwscan'.
# Inputs:
#   - args: argparse.Namespace
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - collect_inventory, fingerprint_inventory, strip, bool, print, device_uid_from_fingerprint, get, getattr, str, makedirs, strftime, join
# Returns / emits: int
# Side effects:
#   - creates directories
# Key locals:
#   - f, fp, inv, lvl, out, outbox, p, ts
# === End NoemaForge Autodoc Function Header ===
def cmd_hwscan(args: argparse.Namespace) -> int:
    from hwscan import collect_inventory, fingerprint_inventory, device_uid_from_fingerprint
    import json
    import datetime as dt

    inv = collect_inventory()
    fp = fingerprint_inventory(inv)
    out: Dict[str, Any] = {
        "fingerprint": fp,
        "device_uid": device_uid_from_fingerprint(fp),
        "pci_source": inv.get("pci_source"),
    }
    lvl = str(getattr(args, "level", "summary") or "summary").lower().strip()
    if lvl == "full":
        out["inventory"] = inv
    else:
        out["summary"] = {
            "cpu": (inv.get("cpu") or {}).get("model"),
            "cores": (inv.get("cpu") or {}).get("cores"),
            "mem_total_kb": inv.get("mem_total_kb"),
            "pci_count": len(inv.get("pci") or []),
            "net_ifaces": [x.get("name") for x in (inv.get("net") or []) if isinstance(x, dict)],
        }

    if bool(getattr(args, "write", False)):
        outbox = str(getattr(args, "outbox_dir", "") or "/workspace/outbox/hwscan")
        os.makedirs(outbox, exist_ok=True)
        ts = dt.datetime.now(dt.UTC).replace(tzinfo=None).strftime("%Y%m%dT%H%M%SZ")
        p = os.path.join(outbox, f"hwscan-{ts}-{fp[:12]}.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print(p)
        return 0

    print(yaml.safe_dump(out, sort_keys=False, allow_unicode=True))
    return 0


# === NoemaForge Autodoc Function Header ===
# Function: cmd_installer_plan(args: argparse.Namespace)
# Purpose: Implement the routine 'cmd installer plan'.
# Inputs:
#   - args: argparse.Namespace
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - collect_inventory, load_installer_policy, build_plan, write_plan, bool, current_epoch_id, epoch_path, getattr, print, dumps, safe_dump
# Returns / emits: int
# Side effects:
#   - serializes structured data
# Key locals:
#   - eid, epoch_dir, inv, out, paths, plan, pol
# === End NoemaForge Autodoc Function Header ===
def cmd_installer_plan(args: argparse.Namespace) -> int:
    from hwscan import collect_inventory
    from installer_plan import load_policy as load_installer_policy, build_plan, write_plan
    import json

    inv = collect_inventory()

    # Prefer current epoch policy if available
    epoch_dir = ""
    try:
        eid = current_epoch_id(args.contracts_root)
        epoch_dir = epoch_path(eid, args.contracts_root)
    except Exception:
        epoch_dir = ""

    pol = load_installer_policy(epoch_dir or None)
    plan = build_plan(inv, pol)
    paths = write_plan(plan, pol)
    out = {"plan": plan, "paths": paths}

    if bool(getattr(args, "json", False)):
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(yaml.safe_dump(out, sort_keys=False, allow_unicode=True))
    return 0

# === NoemaForge Autodoc Function Header ===
# Function: main(argv: list[str])
# Purpose: Implement the routine 'main'.
# Inputs:
#   - argv: list[str]
# Called by:
#   - bootstrap/microvm/noemaforge-microvm-run.py
#   - src/bootdoctor.py
#   - src/noemaforge_core.py
#   - src/brainui.py
#   - src/canary_runner.py
#   - src/doctor.py
#   - src/dream_cycle.py
#   - src/firstboot_eval.py
# Calls:
#   - ArgumentParser, add_argument, add_subparsers, add_parser, parse_args, provision, detect, print, run_doctor, bool, cmd_epoch_status, load_policy
# Returns / emits: int
# Side effects:
#   - spawns subprocesses or workers
# Key locals:
#   - _cmd, ap, args, bd_sub, day, db_path, ed, eid, epoch_sub, f, fmt, inc_sub
# === End NoemaForge Autodoc Function Header ===
def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()

    ap.add_argument("--contracts-root", default=DEFAULT_CONTRACTS_ROOT)
    ap.add_argument("--requests-dir", default=DEFAULT_REQUESTS_DIR)
    ap.add_argument("--policy-lock", default=DEFAULT_POLICY_LOCK)

    sub = ap.add_subparsers(dest="cmd", required=True)

    # Provisioning
    sub.add_parser("provision")

    # LSM
    sub.add_parser("lsm-status")

    # Doctor (offline self-checks)
    p_doc = sub.add_parser("doctor")
    p_doc.add_argument("--full", action="store_true", help="verify file hashes (slow)")
    p_doc.add_argument("--json", action="store_true", help="print JSON (default)")



    # Epoch
    p_epoch = sub.add_parser("epoch")
    epoch_sub = p_epoch.add_subparsers(dest="epoch_cmd", required=True)
    epoch_sub.add_parser("status")

    # Pre-start
    p_ps = sub.add_parser("prestart")
    ps_sub = p_ps.add_subparsers(dest="ps_cmd", required=True)
    ps_sub.add_parser("queue")

    p_app = ps_sub.add_parser("approve")
    p_app.add_argument("request_id")

    p_rej = ps_sub.add_parser("reject")
    p_rej.add_argument("request_id")

    ps_sub.add_parser("lock")

    p_un = ps_sub.add_parser("unlock")
    p_un.add_argument("--i-mean-it", action="store_true")

    p_b = ps_sub.add_parser("build-epoch")
    p_b.add_argument("--epoch-id", default="")
    p_b.add_argument("--base-epoch-id", default="")
    p_b.add_argument("--description", default="")
    p_b.add_argument("--user-comment", default="", help="manual comment to trigger an epoch switch without contract changes")

    p_a = ps_sub.add_parser("apply-epoch")
    p_a.add_argument("epoch_id")
    p_a.add_argument("--suite", default="auto", choices=["auto", "smoke", "full"], help="canary suite (auto=Scary minimum)")
    p_a.add_argument("--override-runtime", action="store_true", help="break-glass: allow canary while runtime mode is detected")
    p_a.add_argument("--i-mean-it", action="store_true", help="required together with --override-runtime")
    p_a.add_argument("--trace-id", default="", help="optional trace id to carry into release_evidence.json")



    # ToolVault (offline / local)
    p_tv = sub.add_parser("toolvault")
    tv_sub = p_tv.add_subparsers(dest="tv_cmd", required=True)

    p_tvh = tv_sub.add_parser("hash")
    p_tvh.add_argument("path")

    p_tvi = tv_sub.add_parser("import")
    p_tvi.add_argument("path")
    p_tvi.add_argument("--force", action="store_true")

    tv_sub.add_parser("list")

    # WebGateway (strict intake)
    p_wg = sub.add_parser("webgw")
    wg_sub = p_wg.add_subparsers(dest="wg_cmd", required=True)

    p_wgf = wg_sub.add_parser("fetch")
    p_wgf.add_argument("url")
    p_wgf.add_argument("--channel", default="packages", choices=["packages", "rss", "git", "generic"], help="intake channel")
    p_wgf.add_argument("--override-runtime", action="store_true", help="break-glass: allow during runtime mode")
    p_wgf.add_argument("--i-mean-it", dest="i_mean_it", action="store_true")

    p_wgr = wg_sub.add_parser("review")
    p_wgr.add_argument("incident_id")
    p_wgr.add_argument("--profile", default="auto", help="glove profile (auto => policy channel default)")
    p_wgr.add_argument("--languages", default="ru,en,de,zh")

    p_wga = wg_sub.add_parser("approve")
    p_wga.add_argument("incident_id")
    p_wga.add_argument("--comment", required=True)

    p_wgp = wg_sub.add_parser("promote")
    p_wgp.add_argument("incident_id")
    p_wgp.add_argument("--target", default="", help="promotion target (default from policy)")
    p_wgp.add_argument("--comment", default="")

    # WebGateway policy patcher (pre-start only via PreStartChangeRequest)
    p_wgpol = wg_sub.add_parser("policy")
    pol_sub = p_wgpol.add_subparsers(dest="wg_policy_cmd", required=True)

    p_wgpd = pol_sub.add_parser("draft")
    p_wgpd.add_argument("--enable", action="store_true", help="set webgw.enabled=true")
    p_wgpd.add_argument("--disable", action="store_true", help="set webgw.enabled=false")
    p_wgpd.add_argument("--enable-channel", action="append", default=[], help="enable channel (repeatable)")
    p_wgpd.add_argument("--disable-channel", action="append", default=[], help="disable channel (repeatable)")
    p_wgpd.add_argument("--allow", action="append", default=[], help="allowlist entry as channel:domain (repeatable). Use channel=global to patch global allow_domains.")
    p_wgpd.add_argument("--comment", default="", help="operator comment (stored in request)")
    p_wgpd.add_argument("--outbox-dir", default="/workspace/outbox/webgw-policy")
    p_wgpd.add_argument("--emit-to-requests", action="store_true", help="write draft directly to --requests-dir (instead of outbox)")

    # WebGateway policy helpers
    p_wgdiff = pol_sub.add_parser("diff")
    p_wgdiff.add_argument("--request", default="", help="path to a *.prestart-request.yaml (default: latest draft in outbox)")
    p_wgdiff.add_argument("--outbox-dir", default="/workspace/outbox/webgw-policy")
    p_wgdiff.add_argument("--policy-path", default="", help="override path to web-gateway-policy.yaml (dev/testing)")
    p_wgdiff.add_argument("--show-final", action="store_true", help="print final YAML after diff")
    p_wgdiff.add_argument("--color", action="store_true", help="ANSI colorize diff output")

    p_wglint = pol_sub.add_parser("lint")
    p_wglint.add_argument("--request", default="", help="path to a *.prestart-request.yaml (default: latest draft in outbox)")
    p_wglint.add_argument("--outbox-dir", default="/workspace/outbox/webgw-policy")
    p_wglint.add_argument("--policy-path", default="", help="override path to web-gateway-policy.yaml (dev/testing)")
    p_wglint.add_argument("--strict", action="store_true", help="exit nonzero on warnings")
    p_wglint.add_argument("--show-final", action="store_true", help="print final YAML if lint passes")




    # LocalGateway (LAN airlock)
    p_lg = sub.add_parser("localgw")
    lg_sub = p_lg.add_subparsers(dest="lg_cmd", required=True)

    p_lgp = lg_sub.add_parser("preflight")
    p_lgp.add_argument("--suite", default="auto", choices=["auto", "smoke", "full"], help="preflight depth")

    lg_sub.add_parser("discover")

    p_lge = lg_sub.add_parser("enroll")
    p_lge.add_argument("--all-unknown", action="store_true", help="enroll all currently unknown devices")
    p_lge.add_argument("--uid", action="append", default=[], help="explicit device_uid to enroll (repeatable)")
    p_lge.add_argument("--outbox-dir", default="/workspace/outbox/localgw")

    # LocalGateway policy patcher (pre-start only via PreStartChangeRequest)
    p_lgpol = lg_sub.add_parser("policy")
    lgpol_sub = p_lgpol.add_subparsers(dest="lg_policy_cmd", required=True)

    p_lgpd = lgpol_sub.add_parser("draft")
    p_lgpd.add_argument("--enable", action="store_true", help="set localgw.enabled=true")
    p_lgpd.add_argument("--disable", action="store_true", help="set localgw.enabled=false")
    p_lgpd.add_argument("--allowlist-mode", default="", choices=["", "required", "permissive"], help="devices.allowlist_mode")
    p_lgpd.add_argument("--allow-device", action="append", default=[], help="device_uid to add to allowlist (repeatable)")
    p_lgpd.add_argument("--all-unknown", action="store_true", help="auto-add all currently unknown devices (best-effort discover)")
    p_lgpd.add_argument("--comment", default="", help="operator comment (stored in request)")
    p_lgpd.add_argument("--outbox-dir", default="/workspace/outbox/localgw-policy")
    p_lgpd.add_argument("--emit-to-requests", action="store_true", help="write draft directly to --requests-dir (instead of outbox)")
    p_lgpd.add_argument("--policy-path", default="", help="override path to local-gateway-policy.yaml (dev/testing)")

    p_lgdiff = lgpol_sub.add_parser("diff")
    p_lgdiff.add_argument("--request", default="", help="path to a *.prestart-request.yaml (default: latest draft in outbox)")
    p_lgdiff.add_argument("--outbox-dir", default="/workspace/outbox/localgw-policy")
    p_lgdiff.add_argument("--policy-path", default="", help="override path to local-gateway-policy.yaml (dev/testing)")
    p_lgdiff.add_argument("--show-final", action="store_true", help="print final YAML after diff")
    p_lgdiff.add_argument("--color", action="store_true", help="ANSI colorize diff output")

    p_lglint = lgpol_sub.add_parser("lint")
    p_lglint.add_argument("--request", default="", help="path to a *.prestart-request.yaml (default: latest draft in outbox)")
    p_lglint.add_argument("--outbox-dir", default="/workspace/outbox/localgw-policy")
    p_lglint.add_argument("--policy-path", default="", help="override path to local-gateway-policy.yaml (dev/testing)")
    p_lglint.add_argument("--strict", action="store_true", help="exit nonzero on warnings")
    p_lglint.add_argument("--show-final", action="store_true", help="print final YAML if lint passes")

    
    # LocalGateway connectors patcher (pre-start only via PreStartChangeRequest)
    p_lgcon = lg_sub.add_parser("connectors")
    lgcon_sub = p_lgcon.add_subparsers(dest="lg_conn_cmd", required=True)

    p_lgcd = lgcon_sub.add_parser("draft")
    p_lgcd.add_argument("--enable", action="store_true", help="set connectors.enabled=true")
    p_lgcd.add_argument("--disable", action="store_true", help="set connectors.enabled=false")
    p_lgcd.add_argument("--allow", action="append", default=[], help="connector name to allow (repeatable)")
    p_lgcd.add_argument("--deny", action="append", default=[], help="connector name to deny (repeatable; deny wins)")
    p_lgcd.add_argument("--comment", default="", help="operator comment (stored in request)")
    p_lgcd.add_argument("--outbox-dir", default="/workspace/outbox/localgw-connectors")
    p_lgcd.add_argument("--emit-to-requests", action="store_true", help="write draft directly to --requests-dir (instead of outbox)")
    p_lgcd.add_argument("--policy-path", default="", help="override path to local-gateway-policy.yaml (dev/testing)")

    p_lgcdiff = lgcon_sub.add_parser("diff")
    p_lgcdiff.add_argument("--request", default="", help="path to a *.prestart-request.yaml (default: latest draft in outbox)")
    p_lgcdiff.add_argument("--outbox-dir", default="/workspace/outbox/localgw-connectors")
    p_lgcdiff.add_argument("--policy-path", default="", help="override path to local-gateway-policy.yaml (dev/testing)")
    p_lgcdiff.add_argument("--show-final", action="store_true", help="print final YAML after diff")
    p_lgcdiff.add_argument("--color", action="store_true", help="ANSI colorize diff output")

    p_lgclint = lgcon_sub.add_parser("lint")
    p_lgclint.add_argument("--request", default="", help="path to a *.prestart-request.yaml (default: latest draft in outbox)")
    p_lgclint.add_argument("--outbox-dir", default="/workspace/outbox/localgw-connectors")
    p_lgclint.add_argument("--policy-path", default="", help="override path to local-gateway-policy.yaml (dev/testing)")
    p_lgclint.add_argument("--strict", action="store_true", help="exit nonzero on warnings")
    p_lgclint.add_argument("--show-final", action="store_true", help="print final YAML if lint passes")

# Hardware scan / installer planning (offline-first)
    # Incidents
    p_inc = sub.add_parser("incidents")
    inc_sub = p_inc.add_subparsers(dest="inc_cmd", required=True)
    p_il = inc_sub.add_parser("list")
    p_il.add_argument("--status", default="", help="open|acknowledged|escalated|closed")
    p_il.add_argument("--kind", default="", help="incident kind (e.g. daily_audit)")
    p_il.add_argument("--limit", type=int, default=50)
    p_il.add_argument("--json", action="store_true")

    p_is = inc_sub.add_parser("show")
    p_is.add_argument("incident_id")

    for _cmd in ("ack", "close", "escalate"):
        p_u = inc_sub.add_parser(_cmd)
        p_u.add_argument("incident_id")
        p_u.add_argument("--comment", default="")

    p_hw = sub.add_parser("hwscan")
    p_hw.add_argument("--level", default="summary", choices=["summary", "full"])
    p_hw.add_argument("--write", action="store_true", help="write JSON artifact to outbox and print its path")
    p_hw.add_argument("--outbox-dir", default="/workspace/outbox/hwscan")

    p_inst = sub.add_parser("installer")
    inst_sub = p_inst.add_subparsers(dest="inst_cmd", required=True)
    p_ip = inst_sub.add_parser("plan")
    p_ip.add_argument("--json", action="store_true")

    # Offline APT (builder planning / driver vault)
    p_oa = sub.add_parser("offline-apt")
    oa_sub = p_oa.add_subparsers(dest="oa_cmd", required=True)
    p_oap = oa_sub.add_parser("plan")
    p_oap.add_argument("--outbox-dir", default="/workspace/outbox/offline-apt")

    p_oab = oa_sub.add_parser("build")
    p_oab.add_argument("--plan", required=True, help="path to offline-apt-plan-*.json")
    p_oab.add_argument("--repo-dir", required=True, help="output directory for aptrepo (Packages, debs)")
    p_oab.add_argument("--artifact-out", required=True, help="output .tar.gz path")
    p_oab.add_argument("--manifest", default="", help="optional manifest yaml to update with artifact sha")
    p_oab.add_argument("--no-apt-update", action="store_true", help="skip apt-get update")


    # Storage (origin-only by default)
    p_st = sub.add_parser("storage")
    st_sub = p_st.add_subparsers(dest="st_cmd", required=True)
    st_sub.add_parser("status")
    p_sts = st_sub.add_parser("scan")
    p_stg = st_sub.add_parser("guard")
    p_stg.add_argument("--dry-run", action="store_true")
    p_stg.add_argument("--outbox-dir", default="/workspace/outbox/storage")

    # Models (ModelStore registry + scorecards)
    p_models = sub.add_parser("models")
    m_sub = p_models.add_subparsers(dest="m_cmd", required=True)

    p_mscan = m_sub.add_parser("scan")
    p_mscan.add_argument("--root", default="/var/lib/modelstore")
    p_mscan.add_argument("--registry", default="/var/lib/modelstore/model_registry.json")
    p_mscan.add_argument("--write", action="store_true", help="write registry if changed")
    p_mscan.add_argument("--no-sel", action="store_true")

    p_mlist = m_sub.add_parser("list")
    p_mlist.add_argument("--registry", default="/var/lib/modelstore/model_registry.json")
    p_mlist.add_argument("--json", action="store_true")

    p_msc = m_sub.add_parser("scorecard")
    sc_sub = p_msc.add_subparsers(dest="sc_cmd", required=True)
    p_scrun = sc_sub.add_parser("run")
    p_scrun.add_argument("--epoch-id", default="", help="epoch id (default: current)")
    p_scrun.add_argument("--model", required=True)
    p_scrun.add_argument("--stream", required=True)
    p_scrun.add_argument("--role", required=True)
    p_scrun.add_argument("--cap", default="llm", choices=["llm", "embed"])
    p_scrun.add_argument("--suite", default="smoke", choices=["smoke", "full"])
    p_scrun.add_argument("--gateway-sock", default=str(_pp.llm_gateway_socket))
    p_scrun.add_argument("--scorecards-dir", default=str(_pp.data_root / "model_scorecards"))
    p_scrun.add_argument("--no-sel", action="store_true")

    # First-boot helper: compute scorecards + emit a draft pre-start plan
    p_mboot = m_sub.add_parser("bootstrap-eval")
    p_mboot.add_argument("--force", action="store_true", help="ignore marker and run anyway")
    p_mboot.add_argument("--no-all", action="store_true", help="only evaluate main model")
    p_mboot.add_argument("--top-k", type=int, default=2)

    # Generate a draft pre-start plan (no evaluation)
    p_mplan = m_sub.add_parser("plan")
    p_mplan.add_argument("--epoch-id", default="", help="epoch id (default: current)")
    p_mplan.add_argument("--registry", default="/var/lib/modelstore/model_registry.json")
    p_mplan.add_argument("--scorecards-dir", default=str(_pp.data_root / "model_scorecards"))
    p_mplan.add_argument("--outbox-dir", default="/workspace/outbox/installer-plan")
    p_mplan.add_argument("--requests-dir", default=str(_pp.data_root / "requests" / "prestart"))
    p_mplan.add_argument("--top-k", type=int, default=2)

    # Roadmap (SR/SSR -> Surgeon)
    p_rm = sub.add_parser("roadmap")
    rm_sub = p_rm.add_subparsers(dest="rm_cmd", required=True)
    p_rml = rm_sub.add_parser("list")
    p_rml.add_argument("--target-role", default="", help="filter by target role (e.g., solution_architect)")
    p_rml.add_argument("--limit", type=int, default=50)

    p_rme = rm_sub.add_parser("export")
    p_rme.add_argument("--target-role", default="", help="filter by target role")
    p_rme.add_argument("--limit", type=int, default=100)
    p_rme.add_argument("--no-role-roadmaps", action="store_true", help="do not embed role-roadmaps.yaml in report")

    p_rmr = rm_sub.add_parser("record")
    p_rmr.add_argument("--target-role", default="solution_architect")
    p_rmr.add_argument("--key", required=True)
    p_rmr.add_argument("--title", default="")
    p_rmr.add_argument("--description", default="")
    p_rmr.add_argument("--source-stream", default="manual")
    p_rmr.add_argument("--source-role", default="human")
    p_rmr.add_argument("--project-id", default="")
    p_rmr.add_argument("--run-id", default="")
    p_rmr.add_argument("--process-id", default="")


    # SR/SSR (explicit self-reflection artifacts)
    p_sr = sub.add_parser("sr")
    sr_sub = p_sr.add_subparsers(dest="sr_cmd", required=True)
    sr_sub.add_parser("run")

    p_ssr = sub.add_parser("ssr")
    ssr_sub = p_ssr.add_subparsers(dest="ssr_cmd", required=True)
    ssr_sub.add_parser("run")


    # Invites (user break-glass tokens)
    p_inv = sub.add_parser("invite")
    inv_sub = p_inv.add_subparsers(dest="inv_cmd", required=True)

    p_i1 = inv_sub.add_parser("issue")
    p_i1.add_argument("scope", help="invite scope (e.g. surgeon_live)")
    p_i1.add_argument("--ttl", type=int, default=900)
    p_i1.add_argument("--issued-by", default="user")
    p_i1.add_argument("--comment", default="")

    p_i2 = inv_sub.add_parser("activate")
    p_i2.add_argument("scope")
    p_i2.add_argument("token")

    p_i3 = inv_sub.add_parser("revoke")
    p_i3.add_argument("scope")

    p_i4 = inv_sub.add_parser("status")
    p_i4.add_argument("--scope", default="")


    # BootDoctor (boot/startup diagnostics + support bundles)
    p_bd = sub.add_parser("bootdoctor")
    bd_sub = p_bd.add_subparsers(dest="bd_cmd", required=True)
    bd_sub.add_parser("quick")
    bd_sub.add_parser("bundle")

    # Knowledge hypergraph (Stage D)
    p_kg = sub.add_parser("kg")
    kg_sub = p_kg.add_subparsers(dest="kg_cmd", required=True)
    p_kgi = kg_sub.add_parser("init")
    p_kgi.add_argument("--db", default="", help="Override db path (otherwise from knowledge-policy)")
    p_kgt = kg_sub.add_parser("ingest-text")
    p_kgt.add_argument("path")
    p_kgt.add_argument("--realm", default="", help="Realm id/name (optional)")
    p_kgt.add_argument("--max-chars", type=int, default=1200)
    p_kgs = kg_sub.add_parser("search")
    p_kgs.add_argument("q")
    p_kgs.add_argument("--limit", type=int, default=20)
    p_kgs.add_argument("--min-decision", default="", help="Override gate decision floor (auto_publish/review/quarantine). Default: from knowledge-policy")
    p_kgs.add_argument("--include-gate", action="store_true", help="Include gate decision in result objects")
    p_kge = kg_sub.add_parser("trail-exec")
    p_kge.add_argument("trail_id")
    p_kge.add_argument("--min-decision", default="", help="Override gate decision floor (auto_publish/review/quarantine). Default: from knowledge-policy")
    p_kge.add_argument("--include-gate", action="store_true", help="Include gate decision in resolved objects")

    p_kgpi = kg_sub.add_parser("prep-init")
    p_kgpi.add_argument("--db", default="", help="Override prep-store db path (otherwise from knowledge-policy)")
    p_kgpe = kg_sub.add_parser("prep-enqueue")
    p_kgpe.add_argument("path")
    p_kgpe.add_argument("--db", default="", help="Override prep-store db path (otherwise from knowledge-policy)")
    p_kgpe.add_argument("--queue-name", default="default")
    p_kgpe.add_argument("--priority", type=int, default=100)
    p_kgpe.add_argument("--canonicalization-profile", default="default")
    p_kgpe.add_argument("--book-title", default="")
    p_kgpq = kg_sub.add_parser("prep-queue")
    p_kgpq.add_argument("--db", default="", help="Override prep-store db path (otherwise from knowledge-policy)")
    p_kgpq.add_argument("--queue-name", default="default")
    p_kgpq.add_argument("--queue-status", default="")
    p_kgpx = kg_sub.add_parser("prep-export")
    p_kgpx.add_argument("out_dir")
    p_kgpx.add_argument("--db", default="", help="Override prep-store db path (otherwise from knowledge-policy)")
    p_kgpm = kg_sub.add_parser("prep-import")
    p_kgpm.add_argument("in_dir")
    p_kgpm.add_argument("--db", default="", help="Override prep-store db path (otherwise from knowledge-policy)")
    p_kgpm.add_argument("--merge", default="replace", choices=["replace", "insert"])
    p_kgpa = kg_sub.add_parser("prep-analyze")
    p_kgpa.add_argument("path")
    p_kgpa.add_argument("--db", default="", help="Override prep-store db path (otherwise from knowledge-policy)")
    p_kgpa.add_argument("--artifact-root", default="")
    p_kgpa.add_argument("--queue-name", default="default")
    p_kgpa.add_argument("--priority", type=int, default=100)
    p_kgpa.add_argument("--canonicalization-profile", default="default")
    p_kgpa.add_argument("--book-title", default="")
    p_kgpa.add_argument("--normalization-version", default="")
    p_kgpa.add_argument("--max-tokens", type=int, default=0)
    p_kgpa.add_argument("--min-sentences", type=int, default=0)
    p_kgpr = kg_sub.add_parser("prep-run-next")
    p_kgpr.add_argument("--db", default="", help="Override prep-store db path (otherwise from knowledge-policy)")
    p_kgpr.add_argument("--artifact-root", default="")
    p_kgpr.add_argument("--queue-name", default="default")
    p_kgpr.add_argument("--worker-id", default="brainctl-prep")
    p_kgpr.add_argument("--lease-ttl", type=int, default=900)
    p_kgpr.add_argument("--normalization-version", default="")
    p_kgpr.add_argument("--max-tokens", type=int, default=0)
    p_kgpr.add_argument("--min-sentences", type=int, default=0)
    p_kgpl = kg_sub.add_parser("prep-leaves")
    p_kgpl.add_argument("book_id")
    p_kgpl.add_argument("--db", default="", help="Override prep-store db path (otherwise from knowledge-policy)")
    p_kgpl.add_argument("--artifact-root", default="")
    p_kgpl.add_argument("--include-text", action="store_true")
    p_kgex = kg_sub.add_parser("extract-book")
    p_kgex.add_argument("book_id")
    p_kgex.add_argument("--prep-db", default="", help="Override prep-store db path")
    p_kgex.add_argument("--kg-db", default="", help="Override knowledge store db path")
    p_kgex.add_argument("--artifact-root", default="")
    p_kgex.add_argument("--realm", default="")
    p_kgxn = kg_sub.add_parser("extract-next")
    p_kgxn.add_argument("--prep-db", default="", help="Override prep-store db path")
    p_kgxn.add_argument("--kg-db", default="", help="Override knowledge store db path")
    p_kgxn.add_argument("--artifact-root", default="")
    p_kgxn.add_argument("--realm", default="")
    p_kgco = kg_sub.add_parser("claim-origin")
    p_kgco.add_argument("claim_id")
    p_kgco.add_argument("--prep-db", default="", help="Override prep-store db path")
    p_kgsy = kg_sub.add_parser("synth-book")
    p_kgsy.add_argument("out_dir")
    p_kgaa = kg_sub.add_parser("admin-answer")
    p_kgaa.add_argument("query")
    p_kgaa.add_argument("--kg-db", default="", help="Override knowledge store db path")
    p_kgaa.add_argument("--prep-db", default="", help="Override prep-store db path")
    p_kgaa.add_argument("--book-id", default="")
    p_kgaa.add_argument("--limit", type=int, default=5)
    p_kgev = kg_sub.add_parser("eval-book")
    p_kgev.add_argument("book_id")
    p_kgev.add_argument("gold_claims_path")
    p_kgev.add_argument("--gold-queries-path", default="")
    p_kgev.add_argument("--prep-db", default="", help="Override prep-store db path")
    p_kgev.add_argument("--kg-db", default="", help="Override knowledge store db path")
    p_kgev.add_argument("--error-db", default="", help="Override error-learning db path")
    p_kgev.add_argument("--record-errors", action="store_true")
    p_kgeri = kg_sub.add_parser("error-init")
    p_kgeri.add_argument("--db", default="", help="Override error-learning db path")
    p_kgerl = kg_sub.add_parser("error-list")
    p_kgerl.add_argument("--db", default="", help="Override error-learning db path")
    p_kgerl.add_argument("--component", default="")
    p_kgerl.add_argument("--review-status", default="")
    p_kgerl.add_argument("--limit", type=int, default=50)
    p_kgerx = kg_sub.add_parser("error-export")
    p_kgerx.add_argument("out_dir")
    p_kgerx.add_argument("--db", default="", help="Override error-learning db path")
    p_kgerx.add_argument("--component", default="")
    p_kgdc = kg_sub.add_parser("detect-conflicts")
    p_kgdc.add_argument("--book-id", default="")
    p_kgdc.add_argument("--prep-db", default="", help="Override prep-store db path")
    p_kgdc.add_argument("--kg-db", default="", help="Override knowledge store db path")

    # SEL/WORM
    p_sel = sub.add_parser("sel")
    sel_sub = p_sel.add_subparsers(dest="sel_cmd", required=True)
    p_sv = sel_sub.add_parser("verify")
    p_sv.add_argument("--day", default="", help="YYYY-MM-DD (default: today)")
    p_sa = sel_sub.add_parser("verify-anchors")
    p_ss = sel_sub.add_parser("seal")
    p_ss.add_argument("--day", default="", help="YYYY-MM-DD (default: today)")

    args = ap.parse_args(argv)

    if args.cmd == "provision":
        return provision()

    if args.cmd == "lsm-status":
        from lsm import detect
        st = detect()
        print(json.dumps(st, ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "doctor":
        from doctor import run_doctor
        rep = run_doctor(base_dir=str(Path(__file__).resolve().parent.parent), full=bool(getattr(args, "full", False)))
        if bool(getattr(args, "json", False)):
            print(json.dumps(rep, ensure_ascii=False, indent=2))
        else:
            print(yaml.safe_dump(rep, sort_keys=False, allow_unicode=True))
        return 0 if rep.get("ok") else 1



    if args.cmd == "epoch" and args.epoch_cmd == "status":
        return cmd_epoch_status(args)

    if args.cmd == "incidents":
        if args.inc_cmd == "list":
            return cmd_incidents_list(args)
        if args.inc_cmd == "show":
            return cmd_incidents_show(args)
        if args.inc_cmd in ("ack", "close", "escalate"):
            return cmd_incidents_update(args, action=args.inc_cmd)


    if args.cmd == "roadmap":
        if args.rm_cmd == "list":
            return cmd_roadmap_list(args)
        if args.rm_cmd == "export":
            return cmd_roadmap_export(args)
        if args.rm_cmd == "record":
            return cmd_roadmap_record(args)


    if args.cmd == "sr":
        if args.sr_cmd == "run":
            from sr_cycle import run as sr_run
            rep = sr_run()
            print(rep.get("sr_report"))
            return 0 if rep.get("ok") else 1

    if args.cmd == "ssr":
        if args.ssr_cmd == "run":
            from ssr_cycle import run as ssr_run
            rep = ssr_run()
            print(rep.get("ssr_report"))
            return 0 if rep.get("ok") else 1


    if args.cmd == "invite":
        import invites as _inv
        if args.inv_cmd == "issue":
            tok = _inv.issue_invite(scope=args.scope, ttl_sec=int(args.ttl), issued_by=str(args.issued_by), comment=str(args.comment))
            # Security: token is printed to stdout (for operator capture/scripting).
            # A plaintext advisory is written to stderr; the token itself must not
            # be written to application log files or shared channels (CWE-312).
            import sys as _sys
            print("SECURITY: Store this invite token securely — it grants break-glass operator access.", file=_sys.stderr)
            print(tok)
            return 0
        if args.inv_cmd == "activate":
            ok, msg = _inv.activate_invite(scope=args.scope, token=args.token)
            print(yaml.safe_dump({"ok": bool(ok), "msg": msg}, sort_keys=False, allow_unicode=True))
            return 0 if ok else 1
        if args.inv_cmd == "revoke":
            ok = _inv.deactivate_invite(scope=args.scope)
            print(yaml.safe_dump({"ok": bool(ok)}, sort_keys=False, allow_unicode=True))
            return 0 if ok else 1
        if args.inv_cmd == "status":
            if str(args.scope or "").strip():
                rec = _inv.active_record(str(args.scope))
                print(yaml.safe_dump({"scope": str(args.scope), "active": bool(rec), "record": rec or {}}, sort_keys=False, allow_unicode=True))
                return 0
            print(yaml.safe_dump(_inv.list_active_scopes(), sort_keys=False, allow_unicode=True))
            return 0


    if args.cmd == "bootdoctor":
        from bootdoctor import load_policy, quick as doctor_quick, bundle as doctor_bundle
        pol = load_policy(None)
        if args.bd_cmd == "quick":
            return doctor_quick(pol)
        if args.bd_cmd == "bundle":
            return doctor_bundle(pol)

    if args.cmd == "kg":
        from knowledge.policy import load_knowledge_policy
        from knowledge.store import KnowledgeStore
        from knowledge.ingest import ingest_text_file
        from knowledge.retrieval import search_keyword
        from knowledge.trails import execute_trail
        from knowledge.prep_store import PrepStore
        from knowledge.prep_pipeline import analyze_book_path, analyze_next_queue_entry, load_prep_processing_config
        from knowledge.extraction_pipeline import extract_book, extract_next_book, load_extraction_config
        from knowledge.synthetic_book import write_synthetic_book
        from knowledge.grounded_administrator import answer_query as grounded_answer_query
        from knowledge.eval_runtime import evaluate_extraction_against_gold, evaluate_grounded_queries
        from knowledge.error_learning import ErrorLearningStore
        from knowledge.conflict_runtime import detect_conflicts

        kpol = load_knowledge_policy(str(args.contracts_root))
        retr = (kpol.get("retrieval") or {}) if isinstance(kpol.get("retrieval"), dict) else {}
        min_decision = str(retr.get("default_min_decision") or "").strip()
        include_gate = bool(retr.get("include_gate_in_results", False))
        # CLI overrides
        if str(getattr(args, "min_decision", "") or "").strip():
            min_decision = str(getattr(args, "min_decision")).strip()
        if bool(getattr(args, "include_gate", False)):
            include_gate = True
        db_path = str((kpol.get("store") or {}).get("db_path") or str(_pp.data_root / "kg" / "kg.sqlite"))
        prep_defaults = load_prep_processing_config(str(args.contracts_root))
        prep_db_path = str(prep_defaults.get("db_path") or str(_pp.data_root / "kg" / "prep_index.sqlite"))
        prep_artifact_root = str(prep_defaults.get("artifact_root") or str(_pp.data_root / "kg" / "prep_artifacts"))
        err_cfg = (kpol.get("error_learning") or {}) if isinstance(kpol.get("error_learning"), dict) else {}
        error_db_path = str(err_cfg.get("db_path") or str(_pp.data_root / "kg" / "error_learning.sqlite"))
        if str(getattr(args, "db", "") or "").strip():
            if str(args.kg_cmd).startswith("prep-"):
                prep_db_path = str(getattr(args, "db"))
            else:
                db_path = str(getattr(args, "db"))
        if str(getattr(args, "artifact_root", "") or "").strip():
            prep_artifact_root = str(getattr(args, "artifact_root"))
        if str(getattr(args, "prep_db", "") or "").strip():
            prep_db_path = str(getattr(args, "prep_db"))
        if str(getattr(args, "kg_db", "") or "").strip():
            db_path = str(getattr(args, "kg_db"))
        if str(getattr(args, "error_db", "") or "").strip():
            error_db_path = str(getattr(args, "error_db"))
        if str(getattr(args, "db", "") or "").strip() and str(getattr(args, "kg_cmd", "")).startswith('error-'):
            error_db_path = str(getattr(args, 'db'))
        st = KnowledgeStore(db_path)

        if args.kg_cmd == "init":
            print(yaml.safe_dump({"ok": True, "db_path": db_path}, sort_keys=False, allow_unicode=True))
            return 0

        if args.kg_cmd == "ingest-text":
            rep = ingest_text_file(st, path=str(args.path), realm=str(args.realm or ""), max_chars_per_passage=int(args.max_chars), created_by="brainctl")
            print(yaml.safe_dump(rep, sort_keys=False, allow_unicode=True))
            return 0 if rep.get("ok") else 1

        if args.kg_cmd == "search":
            rep = search_keyword(st, q=str(args.q), limit=int(args.limit), min_decision=min_decision, include_gate=include_gate)
            print(json.dumps(rep, ensure_ascii=False, indent=2))
            return 0 if rep.get("ok") else 1

        if args.kg_cmd == "trail-exec":
            rep = execute_trail(st, trail_id=str(args.trail_id), min_decision=min_decision, include_gate=include_gate)
            print(json.dumps(rep, ensure_ascii=False, indent=2))
            return 0 if rep.get("ok") else 1

        if args.kg_cmd == "prep-init":
            ps = PrepStore(prep_db_path)
            print(yaml.safe_dump({"ok": True, "db_path": prep_db_path, "tables": ps.list_tables()}, sort_keys=False, allow_unicode=True))
            return 0

        if args.kg_cmd == "prep-enqueue":
            ps = PrepStore(prep_db_path)
            rep = ps.enqueue_book_path(path=str(args.path), queue_name=str(args.queue_name), priority=int(args.priority), canonicalization_profile=str(args.canonicalization_profile), book_title=str(args.book_title or ""))
            print(yaml.safe_dump(rep, sort_keys=False, allow_unicode=True))
            return 0 if rep.get("ok") else 1

        if args.kg_cmd == "prep-queue":
            ps = PrepStore(prep_db_path)
            rep = {"ok": True, "queue": ps.list_queue(queue_name=str(args.queue_name), queue_status=str(args.queue_status or ""))}
            print(json.dumps(rep, ensure_ascii=False, indent=2))
            return 0

        if args.kg_cmd == "prep-export":
            ps = PrepStore(prep_db_path)
            rep = ps.export_jsonl(out_dir=str(args.out_dir))
            print(yaml.safe_dump(rep, sort_keys=False, allow_unicode=True))
            return 0 if rep.get("ok") else 1

        if args.kg_cmd == "prep-import":
            ps = PrepStore(prep_db_path)
            rep = ps.import_jsonl(in_dir=str(args.in_dir), merge=str(args.merge))
            print(yaml.safe_dump(rep, sort_keys=False, allow_unicode=True))
            return 0 if rep.get("ok") else 1

        if args.kg_cmd == "prep-analyze":
            ps = PrepStore(prep_db_path)
            rep = analyze_book_path(
                prep_store=ps,
                source_path=str(args.path),
                artifact_root=str(prep_artifact_root),
                canonicalization_profile=str(args.canonicalization_profile or "default"),
                normalization_version=str(args.normalization_version or prep_defaults.get("normalization_version") or "norm-v1"),
                queue_name=str(args.queue_name or "default"),
                priority=int(args.priority),
                book_title=str(args.book_title or ""),
                max_tokens_per_leaf=int(args.max_tokens or prep_defaults.get("max_tokens_per_leaf") or 350),
                min_sentences_per_leaf=int(args.min_sentences or prep_defaults.get("min_sentences_per_leaf") or 1),
                sentence_token_chars_per_token=int(prep_defaults.get("sentence_token_chars_per_token") or 4),
                paragraph_split_preference=bool(prep_defaults.get("paragraph_split_preference", True)),
                clause_split_enabled=bool(prep_defaults.get("clause_split_enabled", True)),
                clause_delimiters=list(prep_defaults.get("clause_delimiters") or [",", ";", ":", "—", "–"]),
                worker_id="brainctl-prep-analyze",
            )
            print(json.dumps(rep, ensure_ascii=False, indent=2))
            return 0 if rep.get("ok") else 1

        if args.kg_cmd == "prep-run-next":
            ps = PrepStore(prep_db_path)
            rep = analyze_next_queue_entry(
                prep_store=ps,
                artifact_root=str(prep_artifact_root),
                queue_name=str(args.queue_name or "default"),
                worker_id=str(args.worker_id or "brainctl-prep"),
                lease_ttl_sec=int(args.lease_ttl),
                normalization_version=str(args.normalization_version or prep_defaults.get("normalization_version") or "norm-v1"),
                max_tokens_per_leaf=int(args.max_tokens or prep_defaults.get("max_tokens_per_leaf") or 350),
                min_sentences_per_leaf=int(args.min_sentences or prep_defaults.get("min_sentences_per_leaf") or 1),
                sentence_token_chars_per_token=int(prep_defaults.get("sentence_token_chars_per_token") or 4),
                paragraph_split_preference=bool(prep_defaults.get("paragraph_split_preference", True)),
                clause_split_enabled=bool(prep_defaults.get("clause_split_enabled", True)),
                clause_delimiters=list(prep_defaults.get("clause_delimiters") or [",", ";", ":", "—", "–"]),
            )
            print(json.dumps(rep, ensure_ascii=False, indent=2))
            return 0 if rep.get("ok") else 1

        if args.kg_cmd == "prep-leaves":
            ps = PrepStore(prep_db_path)
            rows = []
            for item in ps.iter_leaf_chunk_bodies(book_id=str(args.book_id), artifact_root=str(prep_artifact_root)):
                if not bool(args.include_text):
                    item = {k: v for k, v in item.items() if k != "text"}
                rows.append(item)
            rep = {"ok": True, "book_id": str(args.book_id), "leaf_chunks": rows}
            print(json.dumps(rep, ensure_ascii=False, indent=2))
            return 0

        if args.kg_cmd == "extract-book":
            ps = PrepStore(prep_db_path)
            ext = load_extraction_config(str(args.contracts_root))
            rep = extract_book(
                prep_store=ps,
                store=st,
                book_id=str(args.book_id),
                artifact_root=str(prep_artifact_root),
                default_realm=str(args.realm or ext.get("default_realm") or ""),
                passage_profile_id=str(ext.get("passage_profile_id") or "passage_builder_v1"),
                claim_profile_id=str(ext.get("claim_profile_id") or "claim_sentence_v1"),
                min_claim_chars=int(ext.get("min_claim_chars") or 24),
                min_claim_words=int(ext.get("min_claim_words") or 4),
                create_evidence_objects=bool(ext.get("create_evidence_objects", True)),
                create_lineage_links=bool(ext.get("create_lineage_links", True)),
                auto_concepts_enabled=bool(ext.get("auto_concepts_enabled", True)),
                max_auto_concepts_per_claim=int(ext.get("max_auto_concepts_per_claim") or 3),
                concept_min_token_len=int(ext.get("concept_min_token_len") or 4),
                quote_fingerprint_alg=str(ext.get("quote_fingerprint_alg") or "sha256"),
                created_by="brainctl-kg-extract",
            )
            print(json.dumps(rep, ensure_ascii=False, indent=2))
            return 0 if rep.get("ok") else 1

        if args.kg_cmd == "extract-next":
            ps = PrepStore(prep_db_path)
            ext = load_extraction_config(str(args.contracts_root))
            rep = extract_next_book(
                prep_store=ps,
                store=st,
                artifact_root=str(prep_artifact_root),
                default_realm=str(args.realm or ext.get("default_realm") or ""),
                passage_profile_id=str(ext.get("passage_profile_id") or "passage_builder_v1"),
                claim_profile_id=str(ext.get("claim_profile_id") or "claim_sentence_v1"),
                min_claim_chars=int(ext.get("min_claim_chars") or 24),
                min_claim_words=int(ext.get("min_claim_words") or 4),
                create_evidence_objects=bool(ext.get("create_evidence_objects", True)),
                create_lineage_links=bool(ext.get("create_lineage_links", True)),
                auto_concepts_enabled=bool(ext.get("auto_concepts_enabled", True)),
                max_auto_concepts_per_claim=int(ext.get("max_auto_concepts_per_claim") or 3),
                concept_min_token_len=int(ext.get("concept_min_token_len") or 4),
                quote_fingerprint_alg=str(ext.get("quote_fingerprint_alg") or "sha256"),
                created_by="brainctl-kg-extract",
            )
            print(json.dumps(rep, ensure_ascii=False, indent=2))
            return 0 if rep.get("ok") else 1

        if args.kg_cmd == "claim-origin":
            ps = PrepStore(prep_db_path)
            rep = ps.get_claim_origin(claim_id=str(args.claim_id)) or {}
            print(json.dumps({"ok": bool(rep), "claim_id": str(args.claim_id), "origin": rep}, ensure_ascii=False, indent=2))
            return 0 if rep else 1
        if args.kg_cmd == "synth-book":
            rep = write_synthetic_book(str(args.out_dir))
            print(json.dumps(rep, ensure_ascii=False, indent=2))
            return 0 if rep.get("ok") else 1

        if args.kg_cmd == "admin-answer":
            ps = PrepStore(prep_db_path)
            gpol = (kpol.get("grounded_administrator") or {}) if isinstance(kpol.get("grounded_administrator"), dict) else {}
            rep = grounded_answer_query(
                store=st,
                prep_store=ps,
                query=str(args.query),
                book_id=str(args.book_id or ""),
                limit=int(args.limit or gpol.get("top_claim_limit") or 5),
                max_citations=int(gpol.get("max_citations") or 4),
            )
            print(json.dumps(rep, ensure_ascii=False, indent=2))
            return 0 if rep.get("ok") else 1

        if args.kg_cmd == "eval-book":
            ps = PrepStore(prep_db_path)
            err = ErrorLearningStore(error_db_path) if bool(getattr(args, 'record_errors', False)) else None
            run_id = ''
            if err is not None:
                run_id = err.start_run(component='claim_extractor_eval', book_id=str(args.book_id), profile_id='synthetic_book_eval')
            rep = evaluate_extraction_against_gold(
                store=st,
                prep_store=ps,
                book_id=str(args.book_id),
                gold_claims_path=str(args.gold_claims_path),
                error_store=err,
                record_errors=bool(getattr(args, 'record_errors', False)),
                run_id=run_id,
            )
            if str(getattr(args, 'gold_queries_path', '') or '').strip():
                rep['grounded_queries'] = evaluate_grounded_queries(
                    store=st,
                    prep_store=ps,
                    gold_queries_path=str(args.gold_queries_path),
                    book_id=str(args.book_id),
                    limit=5,
                )
            if err is not None and run_id:
                err.finish_run(run_id=run_id, status='completed')
                rep['error_run_id'] = run_id
                rep['error_db_path'] = error_db_path
            print(json.dumps(rep, ensure_ascii=False, indent=2))
            return 0 if rep.get("ok") else 1

        if args.kg_cmd == "detect-conflicts":
            ps = PrepStore(prep_db_path)
            rep = detect_conflicts(store=st, prep_store=ps, book_id=str(args.book_id or ''), created_by='brainctl-kg-conflicts')
            print(json.dumps(rep, ensure_ascii=False, indent=2))
            return 0 if rep.get('ok') else 1

        if args.kg_cmd == "error-init":
            es = ErrorLearningStore(error_db_path)
            print(json.dumps({"ok": True, "db_path": error_db_path, "tables": es.list_tables()}, ensure_ascii=False, indent=2))
            return 0

        if args.kg_cmd == "error-list":
            es = ErrorLearningStore(error_db_path)
            rep = {"ok": True, "errors": es.list_errors(component=str(args.component or ''), review_status=str(args.review_status or ''), limit=int(args.limit))}
            print(json.dumps(rep, ensure_ascii=False, indent=2))
            return 0

        if args.kg_cmd == "error-export":
            es = ErrorLearningStore(error_db_path)
            rep = es.export_regression_cases(str(args.out_dir), component=str(args.component or ''))
            print(json.dumps(rep, ensure_ascii=False, indent=2))
            return 0 if rep.get("ok") else 1

    if args.cmd == "hwscan":
        return cmd_hwscan(args)

    if args.cmd == "installer":
        if args.inst_cmd == "plan":
            return cmd_installer_plan(args)

    if args.cmd == "offline-apt":
        if args.oa_cmd == "plan":
            return cmd_offline_apt_plan(args)
        if args.oa_cmd == "build":
            return cmd_offline_apt_build(args)


    if args.cmd == "storage":
        if args.st_cmd == "status":
            return cmd_storage_status(args)
        if args.st_cmd == "scan":
            return cmd_storage_scan(args)
        if args.st_cmd == "guard":
            return cmd_storage_guard(args)

    if args.cmd == "models":
        if args.m_cmd == "scan":
            if args.write:
                changed, summary = model_registry.update_registry(
                    modelstore_root=str(args.root),
                    registry_path=str(args.registry),
                    emit_sel=not bool(args.no_sel),
                )
                print(json.dumps({"ok": True, "changed": changed, "summary": summary}, ensure_ascii=False, indent=2))
                return 0
            reg, summary = model_registry.scan_modelstore(
                modelstore_root=str(args.root),
                registry_path=str(args.registry),
                emit_sel=False,
            )
            print(json.dumps({"ok": True, "registry": reg, "summary": summary}, ensure_ascii=False, indent=2))
            return 0

        if args.m_cmd == "list":
            reg = model_registry.load_registry(str(args.registry))
            if args.json:
                print(json.dumps(reg, ensure_ascii=False, indent=2))
                return 0
            models = (reg.get("models") or [])
            for m in models:
                mm = m or {}
                mid = str(mm.get("model_id") or "")
                fmt = str(mm.get("format") or "")
                trust = str(mm.get("trust") or "")
                sz = int(mm.get("size_bytes") or 0)
                print(f"{mid}\t{fmt}\t{trust}\t{sz}")
            return 0

        if args.m_cmd == "scorecard" and args.sc_cmd == "run":
            ensure_epoch_initialized(config_dir=CONFIG_DIR, contracts_root=args.contracts_root)
            eid = str(getattr(args, "epoch_id", "") or "").strip() or current_epoch_id(args.contracts_root)
            ed = epoch_path(eid, args.contracts_root)
            res = model_scorecards.run_scorecard(
                epoch_dir=ed,
                model_id=str(args.model),
                stream_id=str(args.stream),
                role=str(args.role),
                cap=str(args.cap),
                suite=str(args.suite),
                gateway_socket=str(args.gateway_sock),
                scorecards_dir=str(args.scorecards_dir),
                emit_sel=not bool(args.no_sel),
            )
            print(json.dumps(res, ensure_ascii=False, indent=2))
            return 0

        if args.m_cmd == "bootstrap-eval":
            # First-boot helper (runtime exception). Safe: it only writes scorecards + draft request.
            res = firstboot_eval.run(
                eval_all_models=not bool(getattr(args, "no_all", False)),
                top_k=int(getattr(args, "top_k", 2)),
            )
            print(yaml.safe_dump(res, sort_keys=False, allow_unicode=True))
            return 0 if res.get("ok") else 1

        if args.m_cmd == "plan":
            ensure_epoch_initialized(config_dir=CONFIG_DIR, contracts_root=args.contracts_root)
            eid = str(getattr(args, "epoch_id", "") or "").strip() or current_epoch_id(args.contracts_root)
            ed = epoch_path(eid, args.contracts_root)

            roles = firstboot_eval.default_eval_surface()
            patches = model_installer_plan.propose_policy_patches(
                role_model_policy_path=os.path.join(ed, "role-model-policy.yaml"),
                llm_backends_policy_path=os.path.join(ed, "llm-backends-policy.yaml"),
                registry_path=str(args.registry),
                scorecards_dir=str(args.scorecards_dir),
                roles_to_consider=roles,
                top_k=int(getattr(args, "top_k", 2)),
            )
            rid = f"plan-{dt.datetime.now(dt.UTC).replace(tzinfo=None).strftime('%Y%m%dT%H%M%SZ')}"
            req = model_installer_plan.make_prestart_request(
                request_id=rid,
                created_by={"actor_type": "system", "actor_id": "brainctl_models_plan"},
                track="policy",
                patches=patches,
                user_comment="Model fleet plan (draft). Review in PRE-START.",
            )
            os.makedirs(str(args.outbox_dir), exist_ok=True)
            os.makedirs(str(args.requests_dir), exist_ok=True)
            outbox_path = os.path.join(str(args.outbox_dir), f"{rid}.prestart_request.yaml")
            q_path = os.path.join(str(args.requests_dir), f"{rid}.yaml")
            with open(outbox_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(req, f, sort_keys=False, allow_unicode=True)
            with open(q_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(req, f, sort_keys=False, allow_unicode=True)
            print(yaml.safe_dump({"ok": True, "outbox": outbox_path, "queue": q_path, "picked_models": patches.get("picked_models")}, sort_keys=False, allow_unicode=True))
            return 0

    if args.cmd == "sel":
        if args.sel_cmd == "verify":
            day = str(getattr(args, "day", "") or "").strip() or None
            ok = bool(sel_verify(day))
            print("OK" if ok else "FAIL")
            return 0 if ok else 1
        if args.sel_cmd == "verify-anchors":
            ok = bool(sel_verify_anchors())
            print("OK" if ok else "FAIL")
            return 0 if ok else 1
        if args.sel_cmd == "seal":
            day = str(getattr(args, "day", "") or "").strip() or None
            out = sel_seal(day)
            print(yaml.safe_dump(out, sort_keys=False, allow_unicode=True))
            return 0 if out.get("ok") else 1


    if args.cmd == "toolvault":
        if args.tv_cmd == "hash":
            return cmd_toolvault_hash(args)
        if args.tv_cmd == "import":
            return cmd_toolvault_import(args)
        if args.tv_cmd == "list":
            return cmd_toolvault_list(args)

    if args.cmd == "webgw":
        if args.wg_cmd == "fetch":
            return cmd_webgw_fetch(args)
        if args.wg_cmd == "review":
            return cmd_webgw_review(args)
        if args.wg_cmd == "approve":
            return cmd_webgw_approve(args)
        if args.wg_cmd == "promote":
            return cmd_webgw_promote(args)
        if args.wg_cmd == "policy":
            if args.wg_policy_cmd == "draft":
                return cmd_webgw_policy_draft(args)
            if args.wg_policy_cmd == "diff":
                return cmd_webgw_policy_diff(args)
            if args.wg_policy_cmd == "lint":
                return cmd_webgw_policy_lint(args)

    if args.cmd == "localgw":
        if args.lg_cmd == "preflight":
            return cmd_localgw_preflight(args)
        if args.lg_cmd == "discover":
            return cmd_localgw_discover(args)
        if args.lg_cmd == "enroll":
            return cmd_localgw_enroll(args)
        if args.lg_cmd == "policy":
            if args.lg_policy_cmd == "draft":
                return cmd_localgw_policy_draft(args)
            if args.lg_policy_cmd == "diff":
                return cmd_localgw_policy_diff(args)
            if args.lg_policy_cmd == "lint":
                return cmd_localgw_policy_lint(args)

        if args.lg_cmd == "connectors":
            if args.lg_conn_cmd == "draft":
                return cmd_localgw_connectors_draft(args)
            if args.lg_conn_cmd == "diff":
                return cmd_localgw_connectors_diff(args)
            if args.lg_conn_cmd == "lint":
                return cmd_localgw_connectors_lint(args)


    if args.cmd == "prestart":
        if args.ps_cmd == "queue":
            return cmd_prestart_queue(args)
        if args.ps_cmd == "approve":
            return cmd_prestart_approve(args)
        if args.ps_cmd == "reject":
            return cmd_prestart_reject(args)
        if args.ps_cmd == "lock":
            return cmd_prestart_lock(args)
        if args.ps_cmd == "unlock":
            return cmd_prestart_unlock(args)
        if args.ps_cmd == "build-epoch":
            return cmd_prestart_build(args)
        if args.ps_cmd == "apply-epoch":
            return cmd_prestart_apply(args)

    return 2



# -------------------------
# ToolVault helpers (offline, local file import)
# -------------------------

# === NoemaForge Autodoc Function Header ===
# Function: _toolvault_paths_from_epoch(epoch_dir: str)
# Purpose: Implement the routine ' toolvault paths from epoch'.
# Inputs:
#   - epoch_dir: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - join, exists, str, _load_yaml, get
# Returns / emits: Dict[str, str]
# Key locals:
#   - fn, p, pol, root, tv
# === End NoemaForge Autodoc Function Header ===
def _toolvault_paths_from_epoch(epoch_dir: str) -> Dict[str, str]:
    # Prefer supplychain-policy, fallback to bundle-policy.
    for fn in ("supplychain-policy.yaml", "bundle-policy.yaml"):
        p = os.path.join(epoch_dir, fn)
        if os.path.exists(p):
            try:
                pol = _load_yaml(p) or {}
                tv = pol.get("tool_vault") or {}
                root = str(tv.get("root") or str(_pp.vault_dir))
                return {
                    "root": root,
                    "manifests": str(tv.get("manifests_dir") or os.path.join(root, "manifests")),
                    "artifacts": str(tv.get("artifacts_dir") or os.path.join(root, "artifacts")),
                    "installed": str(tv.get("installed_dir") or os.path.join(root, "installed")),
                }
            except Exception:
                continue
    root = str(_pp.vault_dir)
    return {"root": root, "manifests": os.path.join(root, "manifests"), "artifacts": os.path.join(root, "artifacts"), "installed": os.path.join(root, "installed")}


# === NoemaForge Autodoc Function Header ===
# Function: _sha256_file(path: str)
# Purpose: Implement the routine ' sha256 file'.
# Inputs:
#   - path: str
# Called by:
#   - src/bootdoctor.py
#   - src/casebase.py
#   - src/doctor.py
#   - src/glove_agent.py
#   - src/localgw_uplink_agent.py
#   - src/model_registry.py
#   - src/pipelines/finance_budget.py
#   - src/prestart.py
# Calls:
#   - sha256, hexdigest, open, read, update
# Returns / emits: str
# Side effects:
#   - reads or writes files
# Key locals:
#   - b, f, h
# === End NoemaForge Autodoc Function Header ===
def _sha256_file(path: str) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(65536)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


# === NoemaForge Autodoc Function Header ===
# Function: cmd_toolvault_hash(args: argparse.Namespace)
# Purpose: Implement the routine 'cmd toolvault hash'.
# Inputs:
#   - args: argparse.Namespace
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - str, print, exists, _sha256_file
# Returns / emits: int
# Key locals:
#   - p
# === End NoemaForge Autodoc Function Header ===
def cmd_toolvault_hash(args: argparse.Namespace) -> int:
    p = str(args.path)
    if not os.path.exists(p):
        print("missing_file", file=sys.stderr)
        return 2
    print(_sha256_file(p))
    return 0


# === NoemaForge Autodoc Function Header ===
# Function: cmd_toolvault_import(args: argparse.Namespace)
# Purpose: Implement the routine 'cmd toolvault import'.
# Inputs:
#   - args: argparse.Namespace
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - ensure_epoch_initialized, epoch_path, _toolvault_paths_from_epoch, str, _sha256_file, makedirs, join, copy2, print, current_epoch_id, splitext, exists
# Returns / emits: int
# Side effects:
#   - creates directories
#   - copies filesystem artifacts
# Key locals:
#   - dst, epoch_dir, ext, name, sha, src, tv
# === End NoemaForge Autodoc Function Header ===
def cmd_toolvault_import(args: argparse.Namespace) -> int:
    ensure_epoch_initialized(config_dir=CONFIG_DIR, contracts_root=args.contracts_root)
    epoch_dir = epoch_path(current_epoch_id(args.contracts_root), args.contracts_root)
    tv = _toolvault_paths_from_epoch(epoch_dir)

    src = str(args.path)
    if not os.path.exists(src) or not os.path.isfile(src):
        print("missing_file", file=sys.stderr)
        return 2

    sha = _sha256_file(src)
    ext = os.path.splitext(src)[1]
    if ext and len(ext) <= 10:
        name = sha + ext
    else:
        name = sha + ".bin"

    os.makedirs(tv["artifacts"], exist_ok=True)
    dst = os.path.join(tv["artifacts"], name)

    if os.path.exists(dst) and not args.force:
        print(yaml.safe_dump({"ok": True, "already_present": True, "artifact_sha256": sha, "artifact_path": dst}, sort_keys=False, allow_unicode=True))
        return 0

    import shutil
    shutil.copy2(src, dst)
    try:
        os.chmod(dst, 0o600)
    except Exception:
        pass

    print(yaml.safe_dump({"ok": True, "artifact_sha256": sha, "artifact_path": dst}, sort_keys=False, allow_unicode=True))
    return 0


# === NoemaForge Autodoc Function Header ===
# Function: cmd_toolvault_list(args: argparse.Namespace)
# Purpose: Implement the routine 'cmd toolvault list'.
# Inputs:
#   - args: argparse.Namespace
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - ensure_epoch_initialized, epoch_path, _toolvault_paths_from_epoch, print, current_epoch_id, isdir, safe_dump, sorted, listdir, append, endswith
# Returns / emits: int
# Side effects:
#   - serializes structured data
#   - appends to logs or files
# Key locals:
#   - epoch_dir, fn, out, tv
# === End NoemaForge Autodoc Function Header ===
def cmd_toolvault_list(args: argparse.Namespace) -> int:
    ensure_epoch_initialized(config_dir=CONFIG_DIR, contracts_root=args.contracts_root)
    epoch_dir = epoch_path(current_epoch_id(args.contracts_root), args.contracts_root)
    tv = _toolvault_paths_from_epoch(epoch_dir)

    out: Dict[str, Any] = {"toolvault": tv, "manifests": [], "artifacts": []}

    try:
        if os.path.isdir(tv["manifests"]):
            for fn in sorted(os.listdir(tv["manifests"])):
                if fn.endswith(".yaml") or fn.endswith(".yml"):
                    out["manifests"].append(fn)
    except Exception:
        pass

    try:
        if os.path.isdir(tv["artifacts"]):
            for fn in sorted(os.listdir(tv["artifacts"]))[:200]:
                out["artifacts"].append(fn)
    except Exception:
        pass

    print(yaml.safe_dump(out, sort_keys=False, allow_unicode=True))
    return 0


# -------------------------
# WebGateway (strict) — pre-start intake
# -------------------------

# === NoemaForge Autodoc Function Header ===
# Function: cmd_webgw_fetch(args: argparse.Namespace)
# Purpose: Implement the routine 'cmd webgw fetch'.
# Inputs:
#   - args: argparse.Namespace
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - ensure_epoch_initialized, read_mode, epoch_path, fetch_to_quarantine, print, policy_lock_state, current_epoch_id, safe_dump, str, getattr
# Returns / emits: int
# Side effects:
#   - serializes structured data
# Key locals:
#   - actor, epoch_dir, mode
# === End NoemaForge Autodoc Function Header ===
def cmd_webgw_fetch(args: argparse.Namespace) -> int:
    ensure_epoch_initialized(config_dir=CONFIG_DIR, contracts_root=args.contracts_root)

    # Guardrails: policy lock must be UNLOCKED, and we should be in pre-start mode.
    mode = read_mode()
    if mode == "runtime" and not args.override_runtime:
        print("Refusing: runtime mode detected. Reboot into pre-start/maintenance mode, or pass --override-runtime --i-mean-it (break-glass).", file=sys.stderr)
        return 2
    if mode == "runtime" and args.override_runtime and not args.i_mean_it:
        print("Refusing: add --i-mean-it for break-glass runtime override", file=sys.stderr)
        return 2

    if policy_lock_state(args.policy_lock) != "UNLOCKED":
        print("Refusing: policy lock is not UNLOCKED. Run: brainctl prestart unlock --i-mean-it", file=sys.stderr)
        return 2

    from webgateway import fetch_to_quarantine

    epoch_dir = epoch_path(current_epoch_id(args.contracts_root), args.contracts_root)
    actor = {"actor_type": "human", "role": "scary", "project_id": "system", "run_id": "webgw"}
    ok, result, reason = fetch_to_quarantine(epoch_dir=epoch_dir, actor=actor, trace_id="webgw-cli", url=str(args.url), channel=str(getattr(args,'channel','packages')))
    if ok:
        print(yaml.safe_dump({"ok": True, **result}, sort_keys=False, allow_unicode=True))
        return 0
    print(yaml.safe_dump({"ok": False, "reason": reason, **(result or {})}, sort_keys=False, allow_unicode=True), file=sys.stderr)
    return 2


# -------------------------
# WebGateway review/approve/promote (strict)
# -------------------------


# === NoemaForge Autodoc Function Header ===
# Function: cmd_webgw_review(args: argparse.Namespace)
# Purpose: Run glove analysis for a WebGateway quarantine incident.
# Inputs:
#   - args: argparse.Namespace
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - ensure_epoch_initialized, epoch_path, load_web_gateway_policy, incident_dir_for_id, strip, _load_yaml, run_glove, print, current_epoch_id, str, isdir, channel_profile_for_incident
# Returns / emits: int
# Side effects:
#   - spawns subprocesses or workers
# Key locals:
#   - epoch_dir, idir, pol, prof, sp
# === End NoemaForge Autodoc Function Header ===
def cmd_webgw_review(args: argparse.Namespace) -> int:
    """Run glove analysis for a WebGateway quarantine incident.

    This is intended to be executed by the operator (scary) in pre-start.
    """
    ensure_epoch_initialized(config_dir=CONFIG_DIR, contracts_root=args.contracts_root)

    from webgateway import load_web_gateway_policy, incident_dir_for_id, channel_profile_for_incident
    from glove_runner import run_glove

    epoch_dir = epoch_path(current_epoch_id(args.contracts_root), args.contracts_root)
    pol = load_web_gateway_policy(epoch_dir)

    idir = incident_dir_for_id(pol, str(args.incident_id))
    if not os.path.isdir(idir):
        print("incident_not_found", file=sys.stderr)
        return 2

    # profile auto => derive from channel policy + incident meta.
    prof = str(args.profile or "auto").strip()
    if prof == "auto":
        prof = channel_profile_for_incident(pol, idir)

    # Load sandbox policy from epoch.
    sp = _load_yaml(os.path.join(epoch_dir, "sandbox-policy.yaml"))

    ok, result = run_glove(
        sandbox_policy=sp,
        incident_dir=idir,
        profile=prof,
        languages=str(args.languages or "ru,en,de,zh"),
    )

    if ok:
        print(yaml.safe_dump({"ok": True, **result}, sort_keys=False, allow_unicode=True))
        return 0

    print(yaml.safe_dump({"ok": False, **result}, sort_keys=False, allow_unicode=True), file=sys.stderr)
    return 2


# === NoemaForge Autodoc Function Header ===
# Function: cmd_webgw_approve(args: argparse.Namespace)
# Purpose: Write an approval record into the incident directory.
# Inputs:
#   - args: argparse.Namespace
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - ensure_epoch_initialized, epoch_path, load_web_gateway_policy, incident_dir_for_id, approve_incident, print, current_epoch_id, str, isdir, safe_dump, strip
# Returns / emits: int
# Side effects:
#   - serializes structured data
# Key locals:
#   - actor, epoch_dir, idir, pol
# === End NoemaForge Autodoc Function Header ===
def cmd_webgw_approve(args: argparse.Namespace) -> int:
    """Write an approval record into the incident directory."""
    ensure_epoch_initialized(config_dir=CONFIG_DIR, contracts_root=args.contracts_root)

    from webgateway import load_web_gateway_policy, incident_dir_for_id, approve_incident

    epoch_dir = epoch_path(current_epoch_id(args.contracts_root), args.contracts_root)
    pol = load_web_gateway_policy(epoch_dir)
    idir = incident_dir_for_id(pol, str(args.incident_id))
    if not os.path.isdir(idir):
        print("incident_not_found", file=sys.stderr)
        return 2

    actor = {"actor_type": "human", "role": "scary", "project_id": "system", "run_id": "webgw"}
    ok, result, reason = approve_incident(
        epoch_dir=epoch_dir,
        incident_dir=idir,
        actor=actor,
        trace_id="webgw-cli",
        comment=str(args.comment or "").strip(),
    )
    if ok:
        print(yaml.safe_dump({"ok": True, **result}, sort_keys=False, allow_unicode=True))
        return 0
    print(yaml.safe_dump({"ok": False, "reason": reason, **(result or {})}, sort_keys=False, allow_unicode=True), file=sys.stderr)
    return 2


# === NoemaForge Autodoc Function Header ===
# Function: cmd_webgw_promote(args: argparse.Namespace)
# Purpose: Promote a reviewed incident into a local vault (ToolVault/DocsVault/CodeVault).
# Inputs:
#   - args: argparse.Namespace
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - ensure_epoch_initialized, epoch_path, load_web_gateway_policy, incident_dir_for_id, promote_incident, print, policy_lock_state, current_epoch_id, str, isdir, safe_dump, strip
# Returns / emits: int
# Side effects:
#   - serializes structured data
# Key locals:
#   - actor, epoch_dir, idir, pol
# === End NoemaForge Autodoc Function Header ===
def cmd_webgw_promote(args: argparse.Namespace) -> int:
    """Promote a reviewed incident into a local vault (ToolVault/DocsVault/CodeVault).

    Promotion is *not* an executor tool: it's an operator action.
    """
    ensure_epoch_initialized(config_dir=CONFIG_DIR, contracts_root=args.contracts_root)

    # Guardrails: policy lock must be UNLOCKED.
    if policy_lock_state(args.policy_lock) != "UNLOCKED":
        print("Refusing: policy lock is not UNLOCKED. Run: brainctl prestart unlock --i-mean-it", file=sys.stderr)
        return 2

    from webgateway import load_web_gateway_policy, incident_dir_for_id, promote_incident

    epoch_dir = epoch_path(current_epoch_id(args.contracts_root), args.contracts_root)
    pol = load_web_gateway_policy(epoch_dir)
    idir = incident_dir_for_id(pol, str(args.incident_id))
    if not os.path.isdir(idir):
        print("incident_not_found", file=sys.stderr)
        return 2

    actor = {"actor_type": "human", "role": "scary", "project_id": "system", "run_id": "webgw"}

    ok, result, reason = promote_incident(
        epoch_dir=epoch_dir,
        incident_dir=idir,
        actor=actor,
        trace_id="webgw-cli",
        target=str(getattr(args, "target", "") or "").strip(),
        comment=str(getattr(args, "comment", "") or "").strip(),
    )

    if ok:
        print(yaml.safe_dump({"ok": True, **result}, sort_keys=False, allow_unicode=True))
        return 0

    print(yaml.safe_dump({"ok": False, "reason": reason, **(result or {})}, sort_keys=False, allow_unicode=True), file=sys.stderr)
    return 2


# -------------------------
# LocalGateway (LAN airlock)
# -------------------------

# === NoemaForge Autodoc Function Header ===
# Function: cmd_webgw_policy_draft(args: argparse.Namespace)
# Purpose: Emit a PreStartChangeRequest draft to patch web-gateway-policy.yaml.
# Inputs:
#   - args: argparse.Namespace
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - ensure_epoch_initialized, epoch_path, bool, items, str, makedirs, strftime, join, strip, print, current_epoch_id, load_web_gateway_policy
# Returns / emits: int
# Side effects:
#   - creates directories
# Key locals:
#   - add_by_channel, allow_entries, b, bad, c, ch, comment, cur, dis_ch, dom_n, en_ch, ent
# === End NoemaForge Autodoc Function Header ===
def cmd_webgw_policy_draft(args: argparse.Namespace) -> int:
    """Emit a PreStartChangeRequest draft to patch web-gateway-policy.yaml.

    This is the safe way to edit allowlists / enablement: no manual YAML surgery.
    Apply via: prestart approve -> build-epoch -> apply-epoch (FULL on first run).
    """
    ensure_epoch_initialized(config_dir=CONFIG_DIR, contracts_root=args.contracts_root)
    from webgateway import load_web_gateway_policy

    epoch_dir = epoch_path(current_epoch_id(args.contracts_root), args.contracts_root)
    pol = load_web_gateway_policy(epoch_dir) or {}

    # === NoemaForge Autodoc Function Header ===
    # Function: norm_domain(s: str)
    # Purpose: Implement the routine 'norm domain'.
    # Inputs:
    #   - s: str
    # Called by:
    #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
    # Calls:
    #   - strip, lower, any, startswith, rsplit, isdigit, urlparse, split, isspace
    # Returns / emits: str
    # Key locals:
    #   - s, u
    # === End NoemaForge Autodoc Function Header ===
    def norm_domain(s: str) -> str:
        s = (s or "").strip()
        if not s:
            return ""
        # If user provided a URL, parse host.
        if "://" in s:
            try:
                import urllib.parse
                u = urllib.parse.urlparse(s)
                s = u.netloc or ""
            except Exception:
                pass
        # remove path
        if "/" in s:
            s = s.split("/", 1)[0]
        # remove port
        if ":" in s and not s.startswith("["):
            # keep IPv6 literals bracketed; otherwise treat as host:port
            host, port = s.rsplit(":", 1)
            if port.isdigit():
                s = host
        s = s.strip().lower()
        # basic sanity
        if any(c.isspace() for c in s):
            return ""
        if s.startswith("http"):
            return ""
        return s

    patch: Dict[str, Any] = {}

    if bool(getattr(args, "enable", False)) and bool(getattr(args, "disable", False)):
        print("Refusing: --enable and --disable are mutually exclusive", file=sys.stderr)
        return 2
    if bool(getattr(args, "enable", False)):
        patch["enabled"] = True
    if bool(getattr(args, "disable", False)):
        patch["enabled"] = False

    # channel enabled/disabled flags
    en_ch = [str(x).strip().lower() for x in (getattr(args, "enable_channel", []) or []) if str(x).strip()]
    dis_ch = [str(x).strip().lower() for x in (getattr(args, "disable_channel", []) or []) if str(x).strip()]
    if set(en_ch) & set(dis_ch):
        print("Refusing: same channel appears in both --enable-channel and --disable-channel", file=sys.stderr)
        return 2

    # === NoemaForge Autodoc Function Header ===
    # Function: set_channel_flag(ch: str, enabled: bool)
    # Purpose: Implement the routine 'set channel flag'.
    # Inputs:
    #   - ch: str
    #   - enabled: bool
    # Called by:
    #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
    # Calls:
    #   - setdefault, bool
    # Returns / emits: None
    # === End NoemaForge Autodoc Function Header ===
    def set_channel_flag(ch: str, enabled: bool) -> None:
        nonlocal patch
        if not ch:
            return
        patch.setdefault("channels", {})
        patch["channels"].setdefault(ch, {})
        patch["channels"][ch]["enabled"] = bool(enabled)

    for c in en_ch:
        set_channel_flag(c, True)
    for c in dis_ch:
        set_channel_flag(c, False)

    # allowlist entries channel:domain
    allow_entries = [str(x) for x in (getattr(args, "allow", []) or []) if str(x).strip()]
    add_by_channel: Dict[str, List[str]] = {}
    bad: List[str] = []
    for ent in allow_entries:
        ent = ent.strip()
        if ":" in ent:
            ch, dom = ent.split(":", 1)
        elif "=" in ent:
            ch, dom = ent.split("=", 1)
        else:
            bad.append(ent)
            continue
        ch = (ch or "").strip().lower()
        dom_n = norm_domain(dom)
        if not ch or not dom_n:
            bad.append(ent)
            continue
        add_by_channel.setdefault(ch, []).append(dom_n)

    if bad:
        print("WARN: skipped malformed --allow entries:", file=sys.stderr)
        for b in bad:
            print("  -", b, file=sys.stderr)

    # === NoemaForge Autodoc Function Header ===
    # Function: merge_allowlist(cur: List[str], adds: List[str])
    # Purpose: Implement the routine 'merge allowlist'.
    # Inputs:
    #   - cur: List[str]
    #   - adds: List[str]
    # Called by:
    #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
    # Calls:
    #   - set, sorted, lower, add, append, strip, str
    # Returns / emits: List[str]
    # Side effects:
    #   - appends to logs or files
    # Key locals:
    #   - s, seen, x
    # === End NoemaForge Autodoc Function Header ===
    def merge_allowlist(cur: List[str], adds: List[str]) -> List[str]:
        s = []
        seen = set()
        for x in cur + adds:
            x = str(x).strip().lower()
            if not x:
                continue
            if x not in seen:
                seen.add(x)
                s.append(x)
        return sorted(s)

    for ch, adds in add_by_channel.items():
        if ch in ("global", "*", "all"):
            cur = [str(x) for x in (((pol.get("network") or {}).get("allow_domains")) or [])]
            nxt = merge_allowlist(cur, adds)
            patch.setdefault("network", {})
            patch["network"]["allow_domains"] = nxt
            continue

        cur = [str(x) for x in ((((pol.get("channels") or {}).get(ch) or {}).get("network") or {}).get("allow_domains") or [])]
        nxt = merge_allowlist(cur, adds)
        patch.setdefault("channels", {})
        patch["channels"].setdefault(ch, {})
        patch["channels"][ch].setdefault("network", {})
        patch["channels"][ch]["network"]["allow_domains"] = nxt

    if not patch:
        print("Refusing: no changes requested. Use --enable/--disable, --enable-channel/--disable-channel, or --allow channel:domain.", file=sys.stderr)
        return 2

    out_dir = str(getattr(args, "outbox_dir", "/workspace/outbox/webgw-policy"))
    if bool(getattr(args, "emit_to_requests", False)):
        out_dir = str(getattr(args, "requests_dir", DEFAULT_REQUESTS_DIR))
    os.makedirs(out_dir, exist_ok=True)

    stamp = dt.datetime.now(dt.UTC).replace(tzinfo=None).strftime("%Y%m%dT%H%M%SZ")
    rid = f"webgw-policy-{stamp}"
    out_req = os.path.join(out_dir, f"{rid}.prestart-request.yaml")

    comment = str(getattr(args, "comment", "") or "").strip()
    if not comment:
        comment = "AUTO-GENERATED. Review and apply via pre-start + FULL canary (first time)."

    req = {
        "apiVersion": "noemaforge.prestart/v1",
        "kind": "PreStartChangeRequest",
        "request_id": rid,
        "created_at": dt.datetime.now(dt.UTC).replace(tzinfo=None).isoformat() + "Z",
        "created_by": {"actor_type": "human", "channel": "webgw-policy"},
        "status": "draft",
        "track": "policy",
        "requested_changes": {
            "web_gateway_policy_patch": patch
        },
        "user_comment": comment,
    }

    with open(out_req, "w", encoding="utf-8") as f:
        yaml.safe_dump(req, f, sort_keys=False, allow_unicode=True)

    print(out_req)
    if not bool(getattr(args, "emit_to_requests", False)):
        print(f"NEXT: copy into {args.requests_dir} then run: brainctl prestart approve {rid}")
    else:
        print(f"NEXT: run: brainctl prestart approve {rid}")
    return 0




# === NoemaForge Autodoc Function Header ===
# Function: _webgw_find_latest_request(outbox_dir: str, prefix: str = 'webgw-policy-')
# Purpose: Implement the routine ' webgw find latest request'.
# Inputs:
#   - outbox_dir: str
#   - prefix: str = 'webgw-policy-'
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - sorted, join, extend, glob
# Returns / emits: str
# Key locals:
#   - files, p, pats
# === End NoemaForge Autodoc Function Header ===
def _webgw_find_latest_request(outbox_dir: str, prefix: str = "webgw-policy-") -> str:
    try:
        import glob
        pats = [os.path.join(outbox_dir, f"{prefix}*.prestart-request.yaml"), os.path.join(outbox_dir, f"{prefix}*.prestart-request.yml")]
        files: list[str] = []
        for p in pats:
            files.extend(glob.glob(p))
        files = sorted(files)
        return files[-1] if files else ""
    except Exception:
        return ""


# === NoemaForge Autodoc Function Header ===
# Function: _webgw_load_policy_for_tools(args: argparse.Namespace)
# Purpose: Load the current WebGW policy (dict) and return (policy, source_label).
# Inputs:
#   - args: argparse.Namespace
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - strip, ensure_epoch_initialized, epoch_path, current_epoch_id, load_web_gateway_policy, join, str, safe_load, SystemExit, getattr, open
# Returns / emits: tuple[dict, str]
# Side effects:
#   - reads or writes files
# Key locals:
#   - epoch_dir, pol, pol_path
# === End NoemaForge Autodoc Function Header ===
def _webgw_load_policy_for_tools(args: argparse.Namespace) -> tuple[dict, str]:
    """Load the current WebGW policy (dict) and return (policy, source_label)."""
    pol_path = str(getattr(args, "policy_path", "") or "").strip()
    if pol_path:
        try:
            pol = yaml.safe_load(open(pol_path, "r", encoding="utf-8")) or {}
            return pol, pol_path
        except Exception as e:
            raise SystemExit(f"Failed to read policy from {pol_path}: {e}")

    # Default: read from current epoch
    ensure_epoch_initialized(config_dir=CONFIG_DIR, contracts_root=args.contracts_root)
    from webgateway import load_web_gateway_policy
    epoch_dir = epoch_path(current_epoch_id(args.contracts_root), args.contracts_root)
    pol = load_web_gateway_policy(epoch_dir) or {}
    return pol, os.path.join(epoch_dir, "web-gateway-policy.yaml")


# === NoemaForge Autodoc Function Header ===
# Function: _webgw_load_patch_from_request(req_path: str)
# Purpose: Implement the routine ' webgw load patch from request'.
# Inputs:
#   - req_path: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - safe_load, str, SystemExit, get, open, isinstance
# Returns / emits: dict
# Side effects:
#   - reads or writes files
# Key locals:
#   - ch, obj, patch
# === End NoemaForge Autodoc Function Header ===
def _webgw_load_patch_from_request(req_path: str) -> dict:
    obj = yaml.safe_load(open(req_path, "r", encoding="utf-8")) or {}
    if str(obj.get("kind") or "") != "PreStartChangeRequest":
        raise SystemExit("Not a PreStartChangeRequest")
    ch = (obj.get("requested_changes") or {})
    patch = (ch.get("web_gateway_policy_patch") or {})
    if not isinstance(patch, dict) or not patch:
        raise SystemExit("Request does not contain requested_changes.web_gateway_policy_patch")
    return patch


# === NoemaForge Autodoc Function Header ===
# Function: _webgw_deep_merge(a: dict, b: dict)
# Purpose: Implement the routine ' webgw deep merge'.
# Inputs:
#   - a: dict
#   - b: dict
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - dict, items, isinstance, _webgw_deep_merge, get
# Returns / emits: dict
# Key locals:
#   - out
# === End NoemaForge Autodoc Function Header ===
def _webgw_deep_merge(a: dict, b: dict) -> dict:
    out = dict(a or {})
    for k, v in (b or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _webgw_deep_merge(out.get(k) or {}, v)  # type: ignore
        else:
            out[k] = v
    return out


# === NoemaForge Autodoc Function Header ===
# Function: _webgw_norm_domain(s: str)
# Purpose: Implement the routine ' webgw norm domain'.
# Inputs:
#   - s: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - strip, lower, any, startswith, rsplit, isdigit, urlparse, split, isspace
# Returns / emits: str
# Key locals:
#   - s, u
# === End NoemaForge Autodoc Function Header ===
def _webgw_norm_domain(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    if "://" in s:
        try:
            import urllib.parse
            u = urllib.parse.urlparse(s)
            s = u.netloc or ""
        except Exception:
            pass
    if "/" in s:
        s = s.split("/", 1)[0]
    if ":" in s and not s.startswith("["):
        host, port = s.rsplit(":", 1)
        if port.isdigit():
            s = host
    s = s.strip().lower()
    if not s:
        return ""
    if any(c.isspace() for c in s):
        return ""
    if s.startswith("http"):
        return ""
    return s


# === NoemaForge Autodoc Function Header ===
# Function: _webgw_lint_patch(patch: dict, base_policy: dict)
# Purpose: Return (warnings, errors, patched_policy).
# Inputs:
#   - patch: dict
#   - base_policy: dict
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - keys, _webgw_deep_merge, isinstance, append, get, bool, items, strip, str, _webgw_norm_domain, join, sorted
# Returns / emits: tuple[list[str], list[str], dict]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - ads, al, allowed_top, base_channels, ch, chans, ck, cn, cnet, d, dn, empty_ch
# === End NoemaForge Autodoc Function Header ===
def _webgw_lint_patch(patch: dict, base_policy: dict) -> tuple[list[str], list[str], dict]:
    """Return (warnings, errors, patched_policy)."""
    warnings: list[str] = []
    errors: list[str] = []

    if not isinstance(patch, dict):
        return warnings, ["patch is not a dict"], base_policy

    allowed_top = {"enabled", "channels", "network"}
    for k in patch.keys():
        if k not in allowed_top:
            errors.append(f"patch contains unsupported top-level key: {k}")

    # enabled
    if "enabled" in patch and not isinstance(patch.get("enabled"), bool):
        errors.append("patch.enabled must be boolean")

    # network.allow_domains
    if "network" in patch:
        net = patch.get("network")
        if not isinstance(net, dict):
            errors.append("patch.network must be dict")
        else:
            for nk in net.keys():
                if nk != "allow_domains":
                    errors.append(f"patch.network contains unsupported key: {nk}")
            if "allow_domains" in net:
                ads = net.get("allow_domains")
                if not isinstance(ads, list):
                    errors.append("patch.network.allow_domains must be list")
                else:
                    for d in ads:
                        dn = _webgw_norm_domain(str(d))
                        if not dn:
                            errors.append(f"invalid domain in network.allow_domains: {d}")

    # channels
    base_channels = (base_policy.get("channels") or {}) if isinstance(base_policy, dict) else {}
    if "channels" in patch:
        ch = patch.get("channels")
        if not isinstance(ch, dict):
            errors.append("patch.channels must be dict")
        else:
            for cname, cpatch in ch.items():
                cn = str(cname).strip()
                if not cn:
                    errors.append("empty channel name in patch.channels")
                    continue
                if isinstance(base_channels, dict) and base_channels and cn not in base_channels:
                    errors.append(f"unknown channel in patch.channels: {cn}")
                if not isinstance(cpatch, dict):
                    errors.append(f"patch.channels.{cn} must be dict")
                    continue
                for ck in cpatch.keys():
                    if ck not in {"enabled", "network"}:
                        errors.append(f"patch.channels.{cn} contains unsupported key: {ck}")
                if "enabled" in cpatch and not isinstance(cpatch.get("enabled"), bool):
                    errors.append(f"patch.channels.{cn}.enabled must be boolean")
                if "network" in cpatch:
                    cnet = cpatch.get("network")
                    if not isinstance(cnet, dict):
                        errors.append(f"patch.channels.{cn}.network must be dict")
                    else:
                        for nk in cnet.keys():
                            if nk != "allow_domains":
                                errors.append(f"patch.channels.{cn}.network contains unsupported key: {nk}")
                        if "allow_domains" in cnet:
                            ads = cnet.get("allow_domains")
                            if not isinstance(ads, list):
                                errors.append(f"patch.channels.{cn}.network.allow_domains must be list")
                            else:
                                normed: list[str] = []
                                for d in ads:
                                    dn = _webgw_norm_domain(str(d))
                                    if not dn:
                                        errors.append(f"invalid domain in channels.{cn}.network.allow_domains: {d}")
                                    else:
                                        normed.append(dn)
                                # warn if not sorted/unique
                                if normed and (sorted(set(normed)) != normed):
                                    warnings.append(f"channels.{cn}.network.allow_domains is not sorted/unique (will be normalized by patcher)")

    patched = _webgw_deep_merge(base_policy, patch)

    # semantic warnings: enabled but no allowlists
    try:
        if bool(patched.get("enabled", False)):
            global_allow = ((patched.get("network") or {}).get("allow_domains") or [])
            global_allow = [str(x) for x in global_allow if str(x).strip()]
            chans = patched.get("channels") or {}
            empty_ch = []
            if isinstance(chans, dict):
                for cn, cpol in chans.items():
                    if not isinstance(cpol, dict):
                        continue
                    if bool(cpol.get("enabled", True)) is False:
                        continue
                    al = (((cpol.get("network") or {}).get("allow_domains")) or [])
                    al = [str(x) for x in al if str(x).strip()]
                    if not al and not global_allow:
                        empty_ch.append(cn)
            if empty_ch:
                warnings.append("webgw is enabled but some channels have empty allow_domains (will deny all): " + ", ".join(sorted(empty_ch)))
            if not global_allow and not empty_ch:
                # enabled but potentially all empty (if channels dict missing)
                warnings.append("webgw is enabled but global allow_domains is empty (deny-by-default)")
    except Exception:
        pass

    return warnings, errors, patched


# === NoemaForge Autodoc Function Header ===
# Function: _colorize_unified_diff(diff_text: str)
# Purpose: Implement the routine ' colorize unified diff'.
# Inputs:
#   - diff_text: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - splitlines, join, startswith, append, rstrip
# Returns / emits: str
# Side effects:
#   - appends to logs or files
# Key locals:
#   - ln, out_lines
# === End NoemaForge Autodoc Function Header ===
def _colorize_unified_diff(diff_text: str) -> str:
    # minimal ANSI coloring: + green, - red, @@ cyan
    out_lines: list[str] = []
    for ln in diff_text.splitlines(True):
        if ln.startswith("+++") or ln.startswith("---"):
            out_lines.append(ln)
            continue
        if ln.startswith("@@"):
            out_lines.append("\x1b[36m" + ln.rstrip("\n") + "\x1b[0m\n")
            continue
        if ln.startswith("+"):
            out_lines.append("\x1b[32m" + ln.rstrip("\n") + "\x1b[0m\n")
            continue
        if ln.startswith("-"):
            out_lines.append("\x1b[31m" + ln.rstrip("\n") + "\x1b[0m\n")
            continue
        out_lines.append(ln)
    return "".join(out_lines)


# === NoemaForge Autodoc Function Header ===
# Function: cmd_webgw_policy_diff(args: argparse.Namespace)
# Purpose: Show a unified diff of the WebGW policy after applying a draft request.
# Inputs:
#   - args: argparse.Namespace
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _webgw_load_policy_for_tools, strip, _webgw_load_patch_from_request, safe_dump, _webgw_lint_patch, join, bool, print, _webgw_find_latest_request, unified_diff, getattr, _colorize_unified_diff
# Returns / emits: int
# Side effects:
#   - serializes structured data
# Key locals:
#   - base_txt, diff, new_txt, patch, req_path
# === End NoemaForge Autodoc Function Header ===
def cmd_webgw_policy_diff(args: argparse.Namespace) -> int:
    """Show a unified diff of the WebGW policy after applying a draft request."""
    pol, pol_src = _webgw_load_policy_for_tools(args)

    req_path = str(getattr(args, "request", "") or "").strip()
    if not req_path:
        req_path = _webgw_find_latest_request(str(getattr(args, "outbox_dir", "/workspace/outbox/webgw-policy")))
    if not req_path:
        print("No request provided and no draft found in outbox.", file=sys.stderr)
        return 2

    patch = _webgw_load_patch_from_request(req_path)

    base_txt = yaml.safe_dump(pol, sort_keys=False, allow_unicode=True)
    _w, errs, patched = _webgw_lint_patch(patch, pol)
    if errs:
        print(yaml.safe_dump({"ok": False, "errors": errs, "request": req_path}, sort_keys=False, allow_unicode=True), file=sys.stderr)
        return 2

    new_txt = yaml.safe_dump(patched, sort_keys=False, allow_unicode=True)

    import difflib
    diff = "".join(difflib.unified_diff(
        base_txt.splitlines(True),
        new_txt.splitlines(True),
        fromfile=f"{pol_src} (current)",
        tofile=f"{pol_src} (patched)",
    ))

    if not diff:
        diff = "(no changes)\n"

    if bool(getattr(args, "color", False)):
        diff = _colorize_unified_diff(diff)

    print(diff, end="" if diff.endswith("\n") else "\n")

    if bool(getattr(args, "show_final", False)):
        print("\n# --- patched policy (YAML) ---")
        print(new_txt)

    return 0


# === NoemaForge Autodoc Function Header ===
# Function: cmd_webgw_policy_lint(args: argparse.Namespace)
# Purpose: Validate a WebGW policy patch request (static checks + safety warnings).
# Inputs:
#   - args: argparse.Namespace
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _webgw_load_policy_for_tools, strip, _webgw_load_patch_from_request, _webgw_lint_patch, print, bool, _webgw_find_latest_request, safe_dump, getattr, str, len
# Returns / emits: int
# Side effects:
#   - serializes structured data
# Key locals:
#   - out, patch, req_path
# === End NoemaForge Autodoc Function Header ===
def cmd_webgw_policy_lint(args: argparse.Namespace) -> int:
    """Validate a WebGW policy patch request (static checks + safety warnings)."""
    pol, _pol_src = _webgw_load_policy_for_tools(args)

    req_path = str(getattr(args, "request", "") or "").strip()
    if not req_path:
        req_path = _webgw_find_latest_request(str(getattr(args, "outbox_dir", "/workspace/outbox/webgw-policy")))
    if not req_path:
        print("No request provided and no draft found in outbox.", file=sys.stderr)
        return 2

    patch = _webgw_load_patch_from_request(req_path)
    warnings, errors, patched = _webgw_lint_patch(patch, pol)

    out = {
        "ok": (len(errors) == 0),
        "request": req_path,
        "warnings": warnings,
        "errors": errors,
    }

    print(yaml.safe_dump(out, sort_keys=False, allow_unicode=True))

    if errors:
        return 2
    if bool(getattr(args, "strict", False)) and warnings:
        return 2

    if bool(getattr(args, "show_final", False)):
        print("\n# --- patched policy (YAML) ---")
        print(yaml.safe_dump(patched, sort_keys=False, allow_unicode=True))

    return 0




# --- LocalGW policy patcher helpers (lint/diff) ---


# === NoemaForge Autodoc Function Header ===
# Function: cmd_localgw_policy_draft(args: argparse.Namespace)
# Purpose: Emit a PreStartChangeRequest draft to patch local-gateway-policy.yaml.
# Inputs:
#   - args: argparse.Namespace
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _localgw_load_policy_for_tools, bool, lower, set, str, makedirs, strftime, join, strip, print, getattr, setdefault
# Returns / emits: int
# Side effects:
#   - creates directories
# Key locals:
#   - adds, allow_set, b, bad, comment, cur_allow, cur_mode, dev_cfg, f, ident, merged, mode_req
# === End NoemaForge Autodoc Function Header ===
def cmd_localgw_policy_draft(args: argparse.Namespace) -> int:
    """Emit a PreStartChangeRequest draft to patch local-gateway-policy.yaml.

    Safe operator workflow: generate a request -> lint/diff -> apply via pre-start + canaries.
    """
    # Load policy (epoch by default; allow --policy-path for dev/testing).
    pol, _src = _localgw_load_policy_for_tools(args)

    patch: Dict[str, Any] = {}

    if bool(getattr(args, "enable", False)) and bool(getattr(args, "disable", False)):
        print("Refusing: --enable and --disable are mutually exclusive", file=sys.stderr)
        return 2
    if bool(getattr(args, "enable", False)):
        patch["enabled"] = True
    if bool(getattr(args, "disable", False)):
        patch["enabled"] = False

    mode_req = str(getattr(args, "allowlist_mode", "") or "").strip().lower()
    if mode_req:
        if mode_req not in ("required", "permissive"):
            print("Refusing: --allowlist-mode must be required|permissive", file=sys.stderr)
            return 2
        patch.setdefault("devices", {})
        patch["devices"]["allowlist_mode"] = mode_req

    # Merge allowlist additions
    dev_cfg = (pol.get("devices") or {}) if isinstance(pol, dict) else {}
    cur_mode = str(dev_cfg.get("allowlist_mode") or "required").strip().lower()
    if mode_req:
        cur_mode = mode_req

    cur_allow = [str(x) for x in (dev_cfg.get("allowlist_uids") or []) if str(x).strip()]
    allow_set = set(cur_allow)

    adds: List[str] = []
    for u in (getattr(args, "allow_device", []) or []):
        u = str(u).strip()
        if not u:
            continue
        adds.append(u)

    # optional: add unknown devices based on current discovery
    if bool(getattr(args, "all_unknown", False)):
        try:
            from localgateway import discover_devices
            observed = discover_devices(pol)
            observed_uids = [str(d.get("device_uid") or "") for d in observed if str(d.get("device_uid") or "").strip()]
            for uid in observed_uids:
                if cur_mode == "required":
                    if uid not in allow_set:
                        adds.append(uid)
                else:
                    if allow_set and uid not in allow_set:
                        adds.append(uid)
        except Exception as e:
            print(f"WARN: failed to discover unknown devices for --all-unknown: {e}", file=sys.stderr)

    # Normalize + dedup + validate
    ident = (pol.get("identity") or {}) if isinstance(pol, dict) else {}
    prefix = str(ident.get("uid_prefix") or "lan:")
    normed: List[str] = []
    bad: List[str] = []
    for u in adds:
        nu = _localgw_norm_uid(str(u), prefix=prefix)
        if not nu:
            bad.append(str(u))
            continue
        if nu not in allow_set and nu not in normed:
            normed.append(nu)

    if bad:
        print("WARN: skipped invalid --allow-device entries:", file=sys.stderr)
        for b in bad[:20]:
            print("  -", b, file=sys.stderr)
        if len(bad) > 20:
            print(f"  ... ({len(bad)-20} more)", file=sys.stderr)

    if normed:
        merged = sorted(list(set(cur_allow + normed)))
        patch.setdefault("devices", {})
        patch["devices"]["allowlist_uids"] = merged

    if not patch:
        print("Refusing: no changes requested. Use --enable/--disable, --allowlist-mode, or --allow-device/--all-unknown.", file=sys.stderr)
        return 2

    out_dir = str(getattr(args, "outbox_dir", "/workspace/outbox/localgw-policy"))
    if bool(getattr(args, "emit_to_requests", False)):
        out_dir = str(getattr(args, "requests_dir", DEFAULT_REQUESTS_DIR))
    os.makedirs(out_dir, exist_ok=True)

    stamp = dt.datetime.now(dt.UTC).replace(tzinfo=None).strftime("%Y%m%dT%H%M%SZ")
    rid = f"localgw-policy-{stamp}"
    out_req = os.path.join(out_dir, f"{rid}.prestart-request.yaml")

    comment = str(getattr(args, "comment", "") or "").strip()
    if not comment:
        comment = "AUTO-GENERATED. Review + lint/diff, then apply via pre-start + FULL canary (first time)."

    req = {
        "apiVersion": "noemaforge.prestart/v1",
        "kind": "PreStartChangeRequest",
        "request_id": rid,
        "created_at": dt.datetime.now(dt.UTC).replace(tzinfo=None).isoformat() + "Z",
        "created_by": {"actor_type": "human", "channel": "localgw-policy"},
        "status": "draft",
        "track": "policy",
        "requested_changes": {"local_gateway_policy_patch": patch},
        "user_comment": comment,
    }

    with open(out_req, "w", encoding="utf-8") as f:
        yaml.safe_dump(req, f, sort_keys=False, allow_unicode=True)

    print(out_req)
    if not bool(getattr(args, "emit_to_requests", False)):
        print(f"NEXT: brainctl localgw policy lint --request {out_req} --policy-path {_src if _src else ''}")
    else:
        print(f"NEXT: run: brainctl prestart approve {rid}")
    return 0



# === NoemaForge Autodoc Function Header ===
# Function: cmd_localgw_connectors_draft(args: argparse.Namespace)
# Purpose: Emit a PreStartChangeRequest draft to patch LocalGW connectors settings.
# Inputs:
#   - args: argparse.Namespace
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _localgw_load_policy_for_tools, set, bool, str, makedirs, strftime, join, strip, print, isinstance, lower, _norm_name
# Returns / emits: int
# Side effects:
#   - creates directories
# Key locals:
#   - a, adds_allow, adds_deny, allow_set, changed, comment, con, cur_allow, cur_deny, d, deny_set, f
# === End NoemaForge Autodoc Function Header ===
def cmd_localgw_connectors_draft(args: argparse.Namespace) -> int:
    """Emit a PreStartChangeRequest draft to patch LocalGW connectors settings.

    This is a strict, safe operator workflow:
      draft -> lint/diff -> apply via pre-start + canaries.

    Supports:
      - connectors.enabled (bool)
      - connectors.allow_connectors (list[str])
      - connectors.deny_connectors (list[str])  # deny wins

    Notes:
      - We treat allowlist as *deny-all by default* when empty.
      - Naming is normalized to lowercase [a-z0-9_-].
    """
    pol, _src = _localgw_load_policy_for_tools(args)
    con = (pol.get("connectors") or {}) if isinstance(pol, dict) else {}

    if bool(getattr(args, "enable", False)) and bool(getattr(args, "disable", False)):
        print("Refusing: --enable and --disable are mutually exclusive", file=sys.stderr)
        return 2

    # === NoemaForge Autodoc Function Header ===
    # Function: _norm_name(x: str)
    # Purpose: Implement the routine ' norm name'.
    # Inputs:
    #   - x: str
    # Called by:
    #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
    # Calls:
    #   - lower, match, strip
    # Returns / emits: str
    # Key locals:
    #   - n
    # === End NoemaForge Autodoc Function Header ===
    def _norm_name(x: str) -> str:
        n = (x or "").strip().lower()
        if not n:
            return ""
        if not re.match(r"^[a-z0-9][a-z0-9_-]{0,63}$", n):
            return ""
        return n

    cur_allow = [_norm_name(str(x)) for x in (con.get("allow_connectors") or [])]
    cur_allow = [x for x in cur_allow if x]
    cur_deny = [_norm_name(str(x)) for x in (con.get("deny_connectors") or [])]
    cur_deny = [x for x in cur_deny if x]

    allow_set = set(cur_allow)
    deny_set = set(cur_deny)

    adds_allow: list[str] = []
    adds_deny: list[str] = []

    for a in (getattr(args, "allow", []) or []):
        na = _norm_name(str(a))
        if not na:
            print(f"WARN: invalid connector name for --allow: {a}", file=sys.stderr)
            continue
        adds_allow.append(na)

    for d in (getattr(args, "deny", []) or []):
        nd = _norm_name(str(d))
        if not nd:
            print(f"WARN: invalid connector name for --deny: {d}", file=sys.stderr)
            continue
        adds_deny.append(nd)

    changed = False

    # Apply allow: add to allow_set, remove from deny_set
    for a in adds_allow:
        if a not in allow_set:
            allow_set.add(a)
            changed = True
        if a in deny_set:
            deny_set.remove(a)
            changed = True

    # Apply deny: add to deny_set, remove from allow_set (explicit deny)
    for d in adds_deny:
        if d not in deny_set:
            deny_set.add(d)
            changed = True
        if d in allow_set:
            allow_set.remove(d)
            changed = True

    patch: Dict[str, Any] = {}
    patch_con: Dict[str, Any] = {}

    if bool(getattr(args, "enable", False)):
        patch_con["enabled"] = True
        changed = True
    if bool(getattr(args, "disable", False)):
        patch_con["enabled"] = False
        changed = True

    if adds_allow or adds_deny:
        patch_con["allow_connectors"] = sorted(list(allow_set))
        patch_con["deny_connectors"] = sorted(list(deny_set))

    if patch_con:
        patch["connectors"] = patch_con

    if not patch or not changed:
        print("Refusing: no connector changes requested. Use --enable/--disable and/or --allow/--deny.", file=sys.stderr)
        return 2

    out_dir = str(getattr(args, "outbox_dir", "/workspace/outbox/localgw-connectors"))
    if bool(getattr(args, "emit_to_requests", False)):
        out_dir = str(getattr(args, "requests_dir", DEFAULT_REQUESTS_DIR))
    os.makedirs(out_dir, exist_ok=True)

    stamp = dt.datetime.now(dt.UTC).replace(tzinfo=None).strftime("%Y%m%dT%H%M%SZ")
    rid = f"localgw-connectors-{stamp}"
    out_req = os.path.join(out_dir, f"{rid}.prestart-request.yaml")

    comment = str(getattr(args, "comment", "") or "").strip()
    if not comment:
        comment = "AUTO-GENERATED. Review + lint/diff, then apply via pre-start + FULL canary (first time)."

    req = {
        "apiVersion": "noemaforge.prestart/v1",
        "kind": "PreStartChangeRequest",
        "request_id": rid,
        "created_at": dt.datetime.now(dt.UTC).replace(tzinfo=None).isoformat() + "Z",
        "created_by": {"actor_type": "human", "channel": "localgw-connectors"},
        "status": "draft",
        "track": "policy",
        "requested_changes": {"local_gateway_policy_patch": patch},
        "user_comment": comment,
    }

    with open(out_req, "w", encoding="utf-8") as f:
        yaml.safe_dump(req, f, sort_keys=False, allow_unicode=True)

    print(out_req)
    if not bool(getattr(args, "emit_to_requests", False)):
        print(f"NEXT: brainctl localgw connectors lint --request {out_req} --policy-path {_src if _src else ''}")
    else:
        print(f"NEXT: run: brainctl prestart approve {rid}")
    return 0


# === NoemaForge Autodoc Function Header ===
# Function: cmd_localgw_connectors_diff(args: argparse.Namespace)
# Purpose: Implement the routine 'cmd localgw connectors diff'.
# Inputs:
#   - args: argparse.Namespace
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _localgw_load_policy_for_tools, strip, _localgw_load_patch_from_request, safe_dump, _localgw_lint_patch, join, bool, print, _localgw_find_latest_request, unified_diff, getattr, _colorize_unified_diff
# Returns / emits: int
# Side effects:
#   - serializes structured data
# Key locals:
#   - base_txt, diff, new_txt, patch, req_path
# === End NoemaForge Autodoc Function Header ===
def cmd_localgw_connectors_diff(args: argparse.Namespace) -> int:
    pol, pol_src = _localgw_load_policy_for_tools(args)

    req_path = str(getattr(args, "request", "") or "").strip()
    if not req_path:
        req_path = _localgw_find_latest_request(str(getattr(args, "outbox_dir", "/workspace/outbox/localgw-connectors")), prefix="localgw-connectors-")
    if not req_path:
        print("No request provided and no draft found in outbox.", file=sys.stderr)
        return 2

    patch = _localgw_load_patch_from_request(req_path)

    base_txt = yaml.safe_dump(pol, sort_keys=False, allow_unicode=True)
    _w, errs, patched = _localgw_lint_patch(patch, pol)
    if errs:
        print(yaml.safe_dump({"ok": False, "errors": errs, "request": req_path}, sort_keys=False, allow_unicode=True), file=sys.stderr)
        return 2

    new_txt = yaml.safe_dump(patched, sort_keys=False, allow_unicode=True)

    import difflib
    diff = "".join(difflib.unified_diff(
        base_txt.splitlines(True),
        new_txt.splitlines(True),
        fromfile=f"{pol_src} (current)",
        tofile=f"{pol_src} (patched)",
    ))
    if not diff:
        diff = "(no changes)\n"
    if bool(getattr(args, "color", False)):
        diff = _colorize_unified_diff(diff)
    print(diff, end="" if diff.endswith("\n") else "\n")
    if bool(getattr(args, "show_final", False)):
        print("\n# --- patched policy (YAML) ---")
        print(new_txt)
    return 0


# === NoemaForge Autodoc Function Header ===
# Function: cmd_localgw_connectors_lint(args: argparse.Namespace)
# Purpose: Implement the routine 'cmd localgw connectors lint'.
# Inputs:
#   - args: argparse.Namespace
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _localgw_load_policy_for_tools, strip, _localgw_load_patch_from_request, _localgw_lint_patch, print, bool, _localgw_find_latest_request, safe_dump, getattr, str, len
# Returns / emits: int
# Side effects:
#   - serializes structured data
# Key locals:
#   - out, patch, req_path
# === End NoemaForge Autodoc Function Header ===
def cmd_localgw_connectors_lint(args: argparse.Namespace) -> int:
    pol, _pol_src = _localgw_load_policy_for_tools(args)

    req_path = str(getattr(args, "request", "") or "").strip()
    if not req_path:
        req_path = _localgw_find_latest_request(str(getattr(args, "outbox_dir", "/workspace/outbox/localgw-connectors")), prefix="localgw-connectors-")
    if not req_path:
        print("No request provided and no draft found in outbox.", file=sys.stderr)
        return 2

    patch = _localgw_load_patch_from_request(req_path)
    warnings, errors, patched = _localgw_lint_patch(patch, pol)

    out = {
        "ok": (len(errors) == 0),
        "request": req_path,
        "warnings": warnings,
        "errors": errors,
    }
    print(yaml.safe_dump(out, sort_keys=False, allow_unicode=True))

    if errors:
        return 2
    if bool(getattr(args, "strict", False)) and warnings:
        return 2

    if bool(getattr(args, "show_final", False)):
        print("\n# --- patched policy (YAML) ---")
        print(yaml.safe_dump(patched, sort_keys=False, allow_unicode=True))

    return 0



# === NoemaForge Autodoc Function Header ===
# Function: _localgw_find_latest_request(outbox_dir: str, prefix: str = 'localgw-policy-')
# Purpose: Implement the routine ' localgw find latest request'.
# Inputs:
#   - outbox_dir: str
#   - prefix: str = 'localgw-policy-'
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - sorted, join, extend, glob
# Returns / emits: str
# Key locals:
#   - files, p, pats
# === End NoemaForge Autodoc Function Header ===
def _localgw_find_latest_request(outbox_dir: str, prefix: str = "localgw-policy-") -> str:
    try:
        import glob
        pats = [os.path.join(outbox_dir, f"{prefix}*.prestart-request.yaml"), os.path.join(outbox_dir, f"{prefix}*.prestart-request.yml")]
        files: list[str] = []
        for p in pats:
            files.extend(glob.glob(p))
        files = sorted(files)
        return files[-1] if files else ""
    except Exception:
        return ""


# === NoemaForge Autodoc Function Header ===
# Function: _localgw_load_policy_for_tools(args: argparse.Namespace)
# Purpose: Load the current LocalGW policy (dict) and return (policy, source_label).
# Inputs:
#   - args: argparse.Namespace
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - strip, ensure_epoch_initialized, epoch_path, current_epoch_id, load_local_gateway_policy, join, str, safe_load, SystemExit, getattr, open
# Returns / emits: tuple[dict, str]
# Side effects:
#   - reads or writes files
# Key locals:
#   - epoch_dir, pol, pol_path
# === End NoemaForge Autodoc Function Header ===
def _localgw_load_policy_for_tools(args: argparse.Namespace) -> tuple[dict, str]:
    """Load the current LocalGW policy (dict) and return (policy, source_label)."""
    pol_path = str(getattr(args, "policy_path", "") or "").strip()
    if pol_path:
        try:
            pol = yaml.safe_load(open(pol_path, "r", encoding="utf-8")) or {}
            return pol, pol_path
        except Exception as e:
            raise SystemExit(f"Failed to read policy from {pol_path}: {e}")

    ensure_epoch_initialized(config_dir=CONFIG_DIR, contracts_root=args.contracts_root)
    from localgateway import load_local_gateway_policy
    epoch_dir = epoch_path(current_epoch_id(args.contracts_root), args.contracts_root)
    pol = load_local_gateway_policy(epoch_dir) or {}
    return pol, os.path.join(epoch_dir, "local-gateway-policy.yaml")


# === NoemaForge Autodoc Function Header ===
# Function: _localgw_load_patch_from_request(req_path: str)
# Purpose: Implement the routine ' localgw load patch from request'.
# Inputs:
#   - req_path: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - safe_load, str, SystemExit, get, open, isinstance
# Returns / emits: dict
# Side effects:
#   - reads or writes files
# Key locals:
#   - ch, obj, patch
# === End NoemaForge Autodoc Function Header ===
def _localgw_load_patch_from_request(req_path: str) -> dict:
    obj = yaml.safe_load(open(req_path, "r", encoding="utf-8")) or {}
    if str(obj.get("kind") or "") != "PreStartChangeRequest":
        raise SystemExit("Not a PreStartChangeRequest")
    ch = (obj.get("requested_changes") or {})
    patch = (ch.get("local_gateway_policy_patch") or {})
    if not isinstance(patch, dict) or not patch:
        raise SystemExit("Request does not contain requested_changes.local_gateway_policy_patch")
    return patch


# === NoemaForge Autodoc Function Header ===
# Function: _localgw_deep_merge(a: dict, b: dict)
# Purpose: Implement the routine ' localgw deep merge'.
# Inputs:
#   - a: dict
#   - b: dict
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - dict, items, isinstance, _localgw_deep_merge, get
# Returns / emits: dict
# Key locals:
#   - out
# === End NoemaForge Autodoc Function Header ===
def _localgw_deep_merge(a: dict, b: dict) -> dict:
    out = dict(a or {})
    for k, v in (b or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _localgw_deep_merge(out.get(k) or {}, v)  # type: ignore
        else:
            out[k] = v
    return out


# === NoemaForge Autodoc Function Header ===
# Function: _localgw_norm_uid(uid: str, prefix: str = 'lan:')
# Purpose: Implement the routine ' localgw norm uid'.
# Inputs:
#   - uid: str
#   - prefix: str = 'lan:'
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - strip, lower, set, any, startswith, len
# Returns / emits: str
# Key locals:
#   - hexd, rest, u
# === End NoemaForge Autodoc Function Header ===
def _localgw_norm_uid(uid: str, prefix: str = "lan:") -> str:
    u = (uid or "").strip()
    if not u:
        return ""
    u = u.strip()
    if not u.startswith(prefix):
        return ""
    rest = u[len(prefix):]
    rest = rest.strip().lower()
    if not rest:
        return ""
    # sha256 hexdigest length is 64
    if len(rest) != 64:
        return ""
    import string
    hexd = set(string.hexdigits.lower())
    if any(c not in hexd for c in rest):
        return ""
    return prefix + rest


# === NoemaForge Autodoc Function Header ===
# Function: _localgw_lint_patch(patch: dict, base_policy: dict)
# Purpose: Implement the routine ' localgw lint patch'.
# Inputs:
#   - patch: dict
#   - base_policy: dict
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - keys, str, _localgw_deep_merge, isinstance, append, get, bool, lower, set, sorted, match, list
# Returns / emits: tuple[list[str], list[str], dict]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - a, al, al0, allow, allowc, allowed_top, bad, base_ident, both, both2, ck, con
# === End NoemaForge Autodoc Function Header ===
def _localgw_lint_patch(patch: dict, base_policy: dict) -> tuple[list[str], list[str], dict]:
    warnings: list[str] = []
    errors: list[str] = []

    if not isinstance(patch, dict):
        return warnings, ["patch is not a dict"], base_policy

    allowed_top = {"enabled", "devices", "connectors"}
    for k in patch.keys():
        if k not in allowed_top:
            errors.append(f"patch contains unsupported top-level key: {k}")

    if "enabled" in patch and not isinstance(patch.get("enabled"), bool):
        errors.append("patch.enabled must be boolean")

    base_ident = (base_policy.get("identity") or {}) if isinstance(base_policy, dict) else {}
    prefix = str(base_ident.get("uid_prefix") or "lan:")

    if "devices" in patch:
        dev = patch.get("devices")
        if not isinstance(dev, dict):
            errors.append("patch.devices must be dict")
        else:
            for dk in dev.keys():
                if dk not in {"allowlist_uids", "allowlist_mode"}:
                    errors.append(f"patch.devices contains unsupported key: {dk}")
            if "allowlist_mode" in dev:
                m = str(dev.get("allowlist_mode") or "").strip().lower()
                if m not in ("required", "permissive"):
                    errors.append("patch.devices.allowlist_mode must be required|permissive")
            if "allowlist_uids" in dev:
                uids = dev.get("allowlist_uids")
                if not isinstance(uids, list):
                    errors.append("patch.devices.allowlist_uids must be list")
                else:
                    normed: list[str] = []
                    for u in uids:
                        nu = _localgw_norm_uid(str(u), prefix=prefix)
                        if not nu:
                            errors.append(f"invalid device_uid in allowlist_uids: {u}")
                        else:
                            normed.append(nu)
                    if normed and (sorted(set(normed)) != normed):
                        warnings.append("devices.allowlist_uids is not sorted/unique (will be normalized by patcher)")


    if "connectors" in patch:
        con = patch.get("connectors")
        if not isinstance(con, dict):
            errors.append("patch.connectors must be dict")
        else:
            for ck in con.keys():
                if ck not in {"enabled", "allow_connectors", "deny_connectors"}:
                    errors.append(f"patch.connectors contains unsupported key: {ck}")
            if "enabled" in con and not isinstance(con.get("enabled"), bool):
                errors.append("patch.connectors.enabled must be boolean")

            # === NoemaForge Autodoc Function Header ===
            # Function: _norm_con_name(x: str)
            # Purpose: Implement the routine ' norm con name'.
            # Inputs:
            #   - x: str
            # Called by:
            #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
            # Calls:
            #   - lower, match, strip
            # Returns / emits: str
            # Key locals:
            #   - n
            # === End NoemaForge Autodoc Function Header ===
            def _norm_con_name(x: str) -> str:
                n = (x or "").strip().lower()
                if not n:
                    return ""
                if not re.match(r"^[a-z0-9][a-z0-9_-]{0,63}$", n):
                    return ""
                return n

            if "allow_connectors" in con:
                al = con.get("allow_connectors")
                if not isinstance(al, list):
                    errors.append("patch.connectors.allow_connectors must be list")
                else:
                    normed: list[str] = []
                    bad: list[str] = []
                    for a in al:
                        na = _norm_con_name(str(a))
                        if not na:
                            bad.append(str(a))
                        else:
                            normed.append(na)
                    if bad:
                        warnings.append("invalid connector names in allow_connectors will be ignored by patcher")
                    if normed and (sorted(set(normed)) != normed):
                        warnings.append("connectors.allow_connectors is not sorted/unique (will be normalized by patcher)")

            if "deny_connectors" in con:
                dl = con.get("deny_connectors")
                if not isinstance(dl, list):
                    errors.append("patch.connectors.deny_connectors must be list")
                else:
                    normed: list[str] = []
                    bad: list[str] = []
                    for d in dl:
                        nd = _norm_con_name(str(d))
                        if not nd:
                            bad.append(str(d))
                        else:
                            normed.append(nd)
                    if bad:
                        warnings.append("invalid connector names in deny_connectors will be ignored by patcher")
                    if normed and (sorted(set(normed)) != normed):
                        warnings.append("connectors.deny_connectors is not sorted/unique (will be normalized by patcher)")

            try:
                al0 = set([str(x).strip().lower() for x in (con.get("allow_connectors") or []) if str(x).strip()])
                dl0 = set([str(x).strip().lower() for x in (con.get("deny_connectors") or []) if str(x).strip()])
                both = sorted(list(al0.intersection(dl0)))
                if both:
                    warnings.append(f"connectors has names in both allow and deny: {', '.join(both[:10])}")
            except Exception:
                pass

    patched = _localgw_deep_merge(base_policy, patch)

    # semantic warnings
    try:
        if bool(patched.get("enabled", False)):
            devp = patched.get("devices") or {}
            mode = str(devp.get("allowlist_mode") or "required").strip().lower()
            allow = [str(x) for x in (devp.get("allowlist_uids") or []) if str(x).strip()]
            if mode == "required" and not allow:
                warnings.append("localgw enabled with allowlist_mode=required but allowlist_uids is empty: all devices will be unknown until enrolled")
            if mode == "permissive" and not allow:
                warnings.append("localgw enabled with allowlist_mode=permissive and empty allowlist: permissive mode reduces security; consider required+enroll")

            conp = patched.get("connectors") or {}
            if bool(conp.get("enabled", False)):
                allowc = [str(x).strip().lower() for x in (conp.get("allow_connectors") or []) if str(x).strip()]
                denyc = [str(x).strip().lower() for x in (conp.get("deny_connectors") or []) if str(x).strip()]
                if not allowc:
                    warnings.append("localgw connectors enabled but allow_connectors is empty: secure default is deny-all; add allowed connectors")
                both2 = sorted(list(set(allowc).intersection(set(denyc))))
                if both2:
                    warnings.append("localgw connectors has names in both allow and deny; deny wins: " + ", ".join(both2[:10]))
                if conp.get("deny_raw_sockets") is False:
                    warnings.append("localgw connectors deny_raw_sockets=false increases risk; keep true unless you fully understand the implications")
    except Exception:
        pass

    return warnings, errors, patched


# === NoemaForge Autodoc Function Header ===
# Function: cmd_localgw_policy_diff(args: argparse.Namespace)
# Purpose: Implement the routine 'cmd localgw policy diff'.
# Inputs:
#   - args: argparse.Namespace
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _localgw_load_policy_for_tools, strip, _localgw_load_patch_from_request, safe_dump, _localgw_lint_patch, join, bool, print, _localgw_find_latest_request, unified_diff, getattr, _colorize_unified_diff
# Returns / emits: int
# Side effects:
#   - serializes structured data
# Key locals:
#   - base_txt, diff, new_txt, patch, req_path
# === End NoemaForge Autodoc Function Header ===
def cmd_localgw_policy_diff(args: argparse.Namespace) -> int:
    pol, pol_src = _localgw_load_policy_for_tools(args)

    req_path = str(getattr(args, "request", "") or "").strip()
    if not req_path:
        req_path = _localgw_find_latest_request(str(getattr(args, "outbox_dir", "/workspace/outbox/localgw-policy")))
    if not req_path:
        print("No request provided and no draft found in outbox.", file=sys.stderr)
        return 2

    patch = _localgw_load_patch_from_request(req_path)

    base_txt = yaml.safe_dump(pol, sort_keys=False, allow_unicode=True)
    _w, errs, patched = _localgw_lint_patch(patch, pol)
    if errs:
        print(yaml.safe_dump({"ok": False, "errors": errs, "request": req_path}, sort_keys=False, allow_unicode=True), file=sys.stderr)
        return 2

    new_txt = yaml.safe_dump(patched, sort_keys=False, allow_unicode=True)

    import difflib
    diff = "".join(difflib.unified_diff(
        base_txt.splitlines(True),
        new_txt.splitlines(True),
        fromfile=f"{pol_src} (current)",
        tofile=f"{pol_src} (patched)",
    ))

    if not diff:
        diff = "(no changes)\n"

    if bool(getattr(args, "color", False)):
        diff = _colorize_unified_diff(diff)

    print(diff, end="" if diff.endswith("\n") else "\n")

    if bool(getattr(args, "show_final", False)):
        print("\n# --- patched policy (YAML) ---")
        print(new_txt)

    return 0


# === NoemaForge Autodoc Function Header ===
# Function: cmd_localgw_policy_lint(args: argparse.Namespace)
# Purpose: Implement the routine 'cmd localgw policy lint'.
# Inputs:
#   - args: argparse.Namespace
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _localgw_load_policy_for_tools, strip, _localgw_load_patch_from_request, _localgw_lint_patch, print, bool, _localgw_find_latest_request, safe_dump, getattr, str, len
# Returns / emits: int
# Side effects:
#   - serializes structured data
# Key locals:
#   - out, patch, req_path
# === End NoemaForge Autodoc Function Header ===
def cmd_localgw_policy_lint(args: argparse.Namespace) -> int:
    pol, _pol_src = _localgw_load_policy_for_tools(args)

    req_path = str(getattr(args, "request", "") or "").strip()
    if not req_path:
        req_path = _localgw_find_latest_request(str(getattr(args, "outbox_dir", "/workspace/outbox/localgw-policy")))
    if not req_path:
        print("No request provided and no draft found in outbox.", file=sys.stderr)
        return 2

    patch = _localgw_load_patch_from_request(req_path)
    warnings, errors, patched = _localgw_lint_patch(patch, pol)

    out = {
        "ok": (len(errors) == 0),
        "request": req_path,
        "warnings": warnings,
        "errors": errors,
    }

    print(yaml.safe_dump(out, sort_keys=False, allow_unicode=True))

    if errors:
        return 2
    if bool(getattr(args, "strict", False)) and warnings:
        return 2

    if bool(getattr(args, "show_final", False)):
        print("\n# --- patched policy (YAML) ---")
        print(yaml.safe_dump(patched, sort_keys=False, allow_unicode=True))

    return 0


# === NoemaForge Autodoc Function Header ===
# Function: cmd_localgw_preflight(args: argparse.Namespace)
# Purpose: Implement the routine 'cmd localgw preflight'.
# Inputs:
#   - args: argparse.Namespace
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - ensure_epoch_initialized, epoch_path, preflight, print, current_epoch_id, safe_dump, str
# Returns / emits: int
# Side effects:
#   - serializes structured data
# Key locals:
#   - actor, epoch_dir
# === End NoemaForge Autodoc Function Header ===
def cmd_localgw_preflight(args: argparse.Namespace) -> int:
    ensure_epoch_initialized(config_dir=CONFIG_DIR, contracts_root=args.contracts_root)

    # LocalGW arming may be used both in pre-start and (optionally) runtime,
    # but it is still controlled by role scary and logged via SEL.
    from localgateway import preflight

    epoch_dir = epoch_path(current_epoch_id(args.contracts_root), args.contracts_root)
    actor = {"actor_type": "human", "role": "scary", "project_id": "system", "run_id": "localgw"}
    ok, result, reason = preflight(epoch_dir=epoch_dir, actor=actor, trace_id="localgw-cli", requested_suite=str(args.suite))
    if ok:
        print(yaml.safe_dump({"ok": True, **result}, sort_keys=False, allow_unicode=True))
        return 0
    print(yaml.safe_dump({"ok": False, "reason": reason, **(result or {})}, sort_keys=False, allow_unicode=True), file=sys.stderr)
    return 2


# === NoemaForge Autodoc Function Header ===
# Function: cmd_localgw_discover(args: argparse.Namespace)
# Purpose: Implement the routine 'cmd localgw discover'.
# Inputs:
#   - args: argparse.Namespace
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - ensure_epoch_initialized, epoch_path, load_local_gateway_policy, discover_devices, print, current_epoch_id, len, safe_dump
# Returns / emits: int
# Side effects:
#   - serializes structured data
# Key locals:
#   - devs, epoch_dir, out, pol
# === End NoemaForge Autodoc Function Header ===
def cmd_localgw_discover(args: argparse.Namespace) -> int:
    ensure_epoch_initialized(config_dir=CONFIG_DIR, contracts_root=args.contracts_root)
    from localgateway import load_local_gateway_policy, discover_devices

    epoch_dir = epoch_path(current_epoch_id(args.contracts_root), args.contracts_root)
    pol = load_local_gateway_policy(epoch_dir)
    devs = discover_devices(pol)
    out = {"ok": True, "count": len(devs), "devices": devs[:100]}
    print(yaml.safe_dump(out, sort_keys=False, allow_unicode=True))
    return 0


# === NoemaForge Autodoc Function Header ===
# Function: cmd_localgw_enroll(args: argparse.Namespace)
# Purpose: Emit a PreStartChangeRequest skeleton to add devices to allowlist.
# Inputs:
#   - args: argparse.Namespace
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - ensure_epoch_initialized, epoch_path, load_local_gateway_policy, strip, set, discover_devices, bool, str, makedirs, strftime, join, print
# Returns / emits: int
# Side effects:
#   - creates directories
# Key locals:
#   - allow, allow_set, dev_cfg, epoch_dir, explicit, f, mode, observed, observed_uids, out_req, outbox, pol
# === End NoemaForge Autodoc Function Header ===
def cmd_localgw_enroll(args: argparse.Namespace) -> int:
    """Emit a PreStartChangeRequest skeleton to add devices to allowlist.

    This keeps the invariant: policy changes only via pre-start.
    """
    ensure_epoch_initialized(config_dir=CONFIG_DIR, contracts_root=args.contracts_root)
    from localgateway import load_local_gateway_policy, discover_devices

    epoch_dir = epoch_path(current_epoch_id(args.contracts_root), args.contracts_root)
    pol = load_local_gateway_policy(epoch_dir)

    dev_cfg = pol.get("devices") or {}
    mode = str((dev_cfg.get("allowlist_mode") or "permissive")).lower().strip()
    allow = [str(x) for x in (dev_cfg.get("allowlist_uids") or []) if str(x).strip()]
    allow_set = set(allow)

    observed = discover_devices(pol)
    observed_uids = [str(d.get("device_uid") or "") for d in observed if str(d.get("device_uid") or "").strip()]

    unknown: List[str] = []
    for uid in observed_uids:
        if mode == "required":
            if uid not in allow_set:
                unknown.append(uid)
        else:
            if allow_set and uid not in allow_set:
                unknown.append(uid)

    to_add: List[str] = []
    explicit = [str(x).strip() for x in (getattr(args, "uid", []) or []) if str(x).strip()]
    if explicit:
        to_add.extend(explicit)
    if bool(getattr(args, "all_unknown", False)):
        to_add.extend(unknown)

    # de-dup + remove already present
    to_add2: List[str] = []
    for u in to_add:
        if u and u not in allow_set and u not in to_add2:
            to_add2.append(u)

    outbox = str(getattr(args, "outbox_dir", "/workspace/outbox/localgw"))
    os.makedirs(outbox, exist_ok=True)
    stamp = dt.datetime.now(dt.UTC).replace(tzinfo=None).strftime("%Y%m%dT%H%M%SZ")
    out_req = os.path.join(outbox, f"localgw-enroll-{stamp}.prestart-request.yaml")

    req = {
        "apiVersion": "noemaforge.prestart/v1",
        "kind": "PreStartChangeRequest",
        "request_id": f"localgw-enroll-{stamp}",
        "created_at": dt.datetime.now(dt.UTC).replace(tzinfo=None).isoformat() + "Z",
        "created_by": {"actor_type": "human", "channel": "localgw"},
        "status": "draft",
        "requested_changes": {
            "local_gateway_policy_patch": {
                "devices": {
                    "allowlist_uids": sorted(list(set(allow + to_add2))),
                    "allowlist_mode": mode or "permissive",
                }
            }
        },
        "user_comment": "AUTO-GENERATED. Review allowlist, then apply via pre-start + FULL canary.",
    }

    with open(out_req, "w", encoding="utf-8") as f:
        yaml.safe_dump(req, f, sort_keys=False, allow_unicode=True)

    print(out_req)
    if to_add2:
        print(f"NOTE: proposed add count: {len(to_add2)}")
    else:
        print("NOTE: nothing to add.")
    return 0



# -------------------------
# StoragePolicy / mounts
# -------------------------

# === NoemaForge Autodoc Function Header ===
# Function: _load_storage_policy_for_brainctl(contracts_root: str)
# Purpose: Implement the routine ' load storage policy for brainctl'.
# Inputs:
#   - contracts_root: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - epoch_contract_path, load_storage_policy
# Returns / emits: Tuple[str, Dict[str, Any]]
# Key locals:
#   - pol, spath
# === End NoemaForge Autodoc Function Header ===
def _load_storage_policy_for_brainctl(contracts_root: str) -> Tuple[str, Dict[str, Any]]:
    spath = epoch_contract_path(contracts_root, "storage-policy.yaml", str(_pp.root / "configs/storage-policy.yaml"))
    try:
        pol = storage_broker.load_storage_policy(spath)
    except Exception:
        pol = {}
    return spath, (pol or {})


# === NoemaForge Autodoc Function Header ===
# Function: cmd_storage_status(args: argparse.Namespace)
# Purpose: Implement the routine 'cmd storage status'.
# Inputs:
#   - args: argparse.Namespace
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _load_storage_policy_for_brainctl, print, str, isinstance, dumps, getattr, get
# Returns / emits: int
# Side effects:
#   - serializes structured data
# Key locals:
#   - origin, out
# === End NoemaForge Autodoc Function Header ===
def cmd_storage_status(args: argparse.Namespace) -> int:
    spath, pol = _load_storage_policy_for_brainctl(str(getattr(args, "contracts_root", DEFAULT_CONTRACTS_ROOT)))
    origin = (pol.get("origin") or {}) if isinstance(pol, dict) else {}
    out = {
        "policy_path": spath,
        "origin": origin,
        "foreign_volumes": pol.get("foreign_volumes") if isinstance(pol, dict) else {},
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


# === NoemaForge Autodoc Function Header ===
# Function: cmd_storage_scan(args: argparse.Namespace)
# Purpose: Implement the routine 'cmd storage scan'.
# Inputs:
#   - args: argparse.Namespace
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _load_storage_policy_for_brainctl, mount_table, print, str, append, len, dumps, getattr, path_allowed, bool
# Returns / emits: int
# Side effects:
#   - serializes structured data
#   - appends to logs or files
# Key locals:
#   - m, mp, mts, out, rows
# === End NoemaForge Autodoc Function Header ===
def cmd_storage_scan(args: argparse.Namespace) -> int:
    spath, pol = _load_storage_policy_for_brainctl(str(getattr(args, "contracts_root", DEFAULT_CONTRACTS_ROOT)))
    mts = storage_broker.mount_table()
    rows: List[Dict[str, Any]] = []
    for m in mts:
        mp = str(m.mount_point or "")
        if not mp:
            continue
        # Evaluate on mount point itself
        ok, reason, ctx = storage_broker.path_allowed(pol, mp, "stat") if pol else (True, "no_policy", {"mount_point": mp, "source": m.source, "fstype": m.fstype})
        rows.append({
            "mount_point": mp,
            "source": str(m.source or ""),
            "fstype": str(m.fstype or ""),
            "allowed": bool(ok),
            "reason": str(reason),
            "ctx": ctx,
        })
    out = {"policy_path": spath, "mounts": rows, "count": len(rows)}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


# === NoemaForge Autodoc Function Header ===
# Function: cmd_storage_guard(args: argparse.Namespace)
# Purpose: Implement the routine 'cmd storage guard'.
# Inputs:
#   - args: argparse.Namespace
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - str, _load_storage_policy_for_brainctl, bool, makedirs, strftime, join, print, getattr, enforce_mounts, utcnow, open, dump
# Returns / emits: int
# Side effects:
#   - reads or writes files
#   - serializes structured data
#   - creates directories
# Key locals:
#   - contracts_root, dedupe, dry, f, out_path, outbox, rep, stamp
# === End NoemaForge Autodoc Function Header ===
def cmd_storage_guard(args: argparse.Namespace) -> int:
    contracts_root = str(getattr(args, "contracts_root", DEFAULT_CONTRACTS_ROOT))
    spath, pol = _load_storage_policy_for_brainctl(contracts_root)
    dry = bool(getattr(args, "dry_run", False))
    rep = storage_broker.enforce_mounts(pol, dry_run=dry) if pol else {"dry_run": dry, "actions": [], "count": 0}

    outbox = str(getattr(args, "outbox_dir", "/workspace/outbox/storage"))
    os.makedirs(outbox, exist_ok=True)
    stamp = dt.datetime.now(dt.UTC).replace(tzinfo=None).strftime("%Y%m%dT%H%M%SZ")
    out_path = os.path.join(outbox, f"storage-guard-{stamp}.json")
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump({"policy_path": spath, "report": rep}, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    # If actions occurred, open/record an incident (deduped).
    try:
        if int(rep.get("count") or 0) > 0 and not dry:
            dedupe = "storage_guard:actions"
            incidents.open_incident(kind="storage_guard", severity="S1", title="Storage guard took actions", details=rep, dedupe_key=dedupe)
    except Exception:
        pass

    print(out_path)
    return 0

# === NoemaForge Autodoc Function Header ===
# Function: cmd_offline_apt_plan(args: argparse.Namespace)
# Purpose: Implement the routine 'cmd offline apt plan'.
# Inputs:
#   - args: argparse.Namespace
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - build_offline_apt_plan, print, dumps, str, getattr
# Returns / emits: int
# Side effects:
#   - serializes structured data
# Key locals:
#   - res
# === End NoemaForge Autodoc Function Header ===
def cmd_offline_apt_plan(args: argparse.Namespace) -> int:
    res = build_offline_apt_plan(outbox_dir=str(getattr(args, "outbox_dir", "/workspace/outbox/offline-apt")))
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0


# === NoemaForge Autodoc Function Header ===
# Function: cmd_offline_apt_build(args: argparse.Namespace)
# Purpose: Implement the routine 'cmd offline apt build'.
# Inputs:
#   - args: argparse.Namespace
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - build_offline_repo_from_plan, print, dumps, str, getattr, strip, bool
# Returns / emits: int
# Side effects:
#   - serializes structured data
# Key locals:
#   - res
# === End NoemaForge Autodoc Function Header ===
def cmd_offline_apt_build(args: argparse.Namespace) -> int:
    res = build_offline_repo_from_plan(
        plan_json_path=str(getattr(args, "plan")),
        repo_dir=str(getattr(args, "repo_dir")),
        artifact_out=str(getattr(args, "artifact_out")),
        bundle_manifest_path=(str(getattr(args, "manifest", "")).strip() or None),
        run_apt_update=not bool(getattr(args, "no_apt_update", False)),
    )
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
