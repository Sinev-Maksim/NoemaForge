#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/resource_policy.py
Zone: release/package
Version: 0.31.13.alpha
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
# File: src/resource_policy.py
# Purpose: Provide the module 'resource_policy'.
# Invoked by / imported from:
#   - src/role_runner.py
# Public API / entry functions:
#   - class Capacity
#   - class Decision
#   - load_policy
#   - system_capacity
#   - enforcement_mode
#   - host_nice
#   - decide_role_request
#   - decide_task_request
#   - dump_decision_json
# Inputs:
#   - Common path inputs: /opt/noemaforge/configs/resource-policy.yaml
#   - Imports: __future__, os, json, dataclasses, typing, yaml
# Output formats / side effects:
#   - JSON files
#   - YAML files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""resource_policy.py (v0.12.8)

Resource governance contracts for NoemaForge.

Goals
-----
- Enforce the "never exceed 95%" rule by default (headroom for spine).
- Provide deterministic per-role caps so the system scales across hardware.
- Keep the spinal zone boring: offline, local-only, no heavy deps.

Notes
-----
This module is currently a *planning + clamping* layer. Real hard enforcement
(cgroups/systemd slice limits, per-process memory capping, etc.) can be wired in
later. For now, we clamp requests used by RoleRunner (podman limits) and expose
helpers for task gating.
"""


import os
import json
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import yaml


DEFAULT_POLICY_PATH = "/opt/noemaforge/configs/resource-policy.yaml"


@dataclass
class Capacity:
    cpu_total: int
    mem_total_mib: int


@dataclass
class Decision:
    ok: bool
    cpu_cores: int
    ram_mib: int
    timeout_sec: int
    clamped: bool
    reason: str
    notes: Dict[str, Any]


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
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# === NoemaForge Autodoc Function Header ===
# Function: load_policy(epoch_dir: str = '', fallback_path: str = DEFAULT_POLICY_PATH)
# Purpose: Load ResourcePolicy from the current epoch dir if provided.
# Inputs:
#   - epoch_dir: str = ''
#   - fallback_path: str = DEFAULT_POLICY_PATH
# Called by:
#   - src/audit_remediation.py
#   - src/bootdoctor.py
#   - src/brainctl.py
#   - src/daily_scheduler.py
#   - src/lsm.py
#   - src/maintenance.py
#   - src/role_runner.py
#   - src/task_tools.py
# Calls:
#   - exists, join, _load_yaml
# Returns / emits: Dict[str, Any]
# Key locals:
#   - p
# === End NoemaForge Autodoc Function Header ===
def load_policy(epoch_dir: str = "", fallback_path: str = DEFAULT_POLICY_PATH) -> Dict[str, Any]:
    """Load ResourcePolicy from the current epoch dir if provided."""
    if epoch_dir:
        p = os.path.join(epoch_dir, "resource-policy.yaml")
        if os.path.exists(p):
            try:
                return _load_yaml(p)
            except Exception:
                return {}
    if os.path.exists(fallback_path):
        try:
            return _load_yaml(fallback_path)
        except Exception:
            return {}
    return {}


# === NoemaForge Autodoc Function Header ===
# Function: _cpu_total()
# Purpose: Implement the routine ' cpu total'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - max, int, cpu_count
# Returns / emits: int
# === End NoemaForge Autodoc Function Header ===
def _cpu_total() -> int:
    try:
        return max(1, int(os.cpu_count() or 1))
    except Exception:
        return 1


# === NoemaForge Autodoc Function Header ===
# Function: _mem_total_mib()
# Purpose: Implement the routine ' mem total mib'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - exists, int, max, sysconf, open, startswith, split, len
# Returns / emits: int
# Side effects:
#   - reads or writes files
# Key locals:
#   - f, kb, line, mib, pages, parts, path, psize
# === End NoemaForge Autodoc Function Header ===
def _mem_total_mib() -> int:
    # Linux: /proc/meminfo
    try:
        path = "/proc/meminfo"
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        parts = line.split()
                        if len(parts) >= 2:
                            kb = int(parts[1])
                            return max(256, int(kb // 1024))
    except Exception:
        pass

    # POSIX sysconf
    try:
        pages = int(os.sysconf("SC_PHYS_PAGES"))
        psize = int(os.sysconf("SC_PAGE_SIZE"))
        mib = int((pages * psize) // (1024 * 1024))
        return max(256, mib)
    except Exception:
        return 2048


# === NoemaForge Autodoc Function Header ===
# Function: system_capacity()
# Purpose: Implement the routine 'system capacity'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - Capacity, _cpu_total, _mem_total_mib
# Returns / emits: Capacity
# === End NoemaForge Autodoc Function Header ===
def system_capacity() -> Capacity:
    return Capacity(cpu_total=_cpu_total(), mem_total_mib=_mem_total_mib())


# === NoemaForge Autodoc Function Header ===
# Function: _get_int(obj, default: int)
# Purpose: Implement the routine ' get int'.
# Inputs:
#   - obj
#   - default: int
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - isinstance, strip, int, lower, float, str
# Returns / emits: int
# Key locals:
#   - s
# === End NoemaForge Autodoc Function Header ===
def _get_int(obj: Any, default: int) -> int:
    try:
        if isinstance(obj, bool):
            return default
        if obj is None:
            return default
        if isinstance(obj, (int, float)):
            return int(obj)
        s = str(obj).strip()
        if s.lower() in ("", "none", "null"):
            return default
        return int(float(s))
    except Exception:
        return default


# === NoemaForge Autodoc Function Header ===
# Function: _role_chain(role: str)
# Purpose: Implement the routine ' role chain'.
# Inputs:
#   - role: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - strip, append, str, rsplit
# Returns / emits: list[str]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - out, r
# === End NoemaForge Autodoc Function Header ===
def _role_chain(role: str) -> list[str]:
    r = str(role or "").strip()
    if not r:
        return []
    out = [r]
    while "." in r:
        r = r.rsplit(".", 1)[0]
        out.append(r)
    return out


# === NoemaForge Autodoc Function Header ===
# Function: _role_caps(policy: Dict[str, Any], role: str)
# Purpose: Return (cpu_cap, ram_cap, timeout_cap) for a role via dot-hierarchy lookup.
# Inputs:
#   - policy: Dict[str, Any]
#   - role: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _get_int, _role_chain, isinstance, get
# Returns / emits: Tuple[Optional[int], Optional[int], Optional[int]]
# Key locals:
#   - cpu, cpu_def, def_role, defaults, k, ram, ram_def, rec, roles, tout, tout_def
# === End NoemaForge Autodoc Function Header ===
def _role_caps(policy: Dict[str, Any], role: str) -> Tuple[Optional[int], Optional[int], Optional[int]]:
    """Return (cpu_cap, ram_cap, timeout_cap) for a role via dot-hierarchy lookup."""
    roles = policy.get("roles") if isinstance(policy.get("roles"), dict) else {}
    defaults = policy.get("defaults") if isinstance(policy.get("defaults"), dict) else {}
    def_role = defaults.get("role") if isinstance(defaults.get("role"), dict) else {}

    cpu_def = _get_int(def_role.get("cpu_cores"), 2)
    ram_def = _get_int(def_role.get("ram_mib"), 2048)
    tout_def = _get_int(def_role.get("timeout_sec"), 600)

    cpu = None
    ram = None
    tout = None

    for k in _role_chain(role):
        rec = roles.get(k)
        if isinstance(rec, dict):
            if cpu is None and rec.get("cpu_cores") is not None:
                cpu = _get_int(rec.get("cpu_cores"), cpu_def)
            if ram is None and rec.get("ram_mib") is not None:
                ram = _get_int(rec.get("ram_mib"), ram_def)
            if tout is None and rec.get("timeout_sec") is not None:
                tout = _get_int(rec.get("timeout_sec"), tout_def)

    if cpu is None:
        cpu = cpu_def
    if ram is None:
        ram = ram_def
    if tout is None:
        tout = tout_def
    return cpu, ram, tout


# === NoemaForge Autodoc Function Header ===
# Function: _global_caps(policy: Dict[str, Any], cap: Capacity)
# Purpose: Implement the routine ' global caps'.
# Inputs:
#   - policy: Dict[str, Any]
#   - cap: Capacity
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _get_int, max, isinstance, get, int
# Returns / emits: Tuple[int, int]
# Key locals:
#   - cpu_cap, limits, max_cpu_pct, max_mem_pct, mem_cap
# === End NoemaForge Autodoc Function Header ===
def _global_caps(policy: Dict[str, Any], cap: Capacity) -> Tuple[int, int]:
    limits = policy.get("limits") if isinstance(policy.get("limits"), dict) else {}
    max_cpu_pct = _get_int(limits.get("max_cpu_pct"), 95)
    max_mem_pct = _get_int(limits.get("max_mem_pct"), 95)

    cpu_cap = max(1, int((cap.cpu_total * max_cpu_pct) // 100))
    mem_cap = max(256, int((cap.mem_total_mib * max_mem_pct) // 100))
    return cpu_cap, mem_cap


# === NoemaForge Autodoc Function Header ===
# Function: enforcement_mode(policy: Dict[str, Any])
# Purpose: Implement the routine 'enforcement mode'.
# Inputs:
#   - policy: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - lower, isinstance, get, strip, str
# Returns / emits: str
# Key locals:
#   - enf, m
# === End NoemaForge Autodoc Function Header ===
def enforcement_mode(policy: Dict[str, Any]) -> str:
    enf = policy.get("enforcement") if isinstance(policy.get("enforcement"), dict) else {}
    m = str(enf.get("mode") or "soft").strip().lower()
    return m if m in ("soft", "hard") else "soft"


# === NoemaForge Autodoc Function Header ===
# Function: host_nice(policy: Dict[str, Any])
# Purpose: Implement the routine 'host nice'.
# Inputs:
#   - policy: Dict[str, Any]
# Called by:
#   - src/role_runner.py
# Calls:
#   - _get_int, isinstance, get
# Returns / emits: int
# Key locals:
#   - enf, host
# === End NoemaForge Autodoc Function Header ===
def host_nice(policy: Dict[str, Any]) -> int:
    enf = policy.get("enforcement") if isinstance(policy.get("enforcement"), dict) else {}
    host = enf.get("host") if isinstance(enf.get("host"), dict) else {}
    return _get_int(host.get("nice"), 10)


# === NoemaForge Autodoc Function Header ===
# Function: decide_role_request(role: str, requested_cpu_cores: int, requested_ram_mib: int, requested_timeout_sec: int, policy: Optional[Dict[str, Any]] = None, epoch_dir: str = '')
# Purpose: Compute effective resources for a role.
# Inputs:
#   - role: str
#   - requested_cpu_cores: int
#   - requested_ram_mib: int
#   - requested_timeout_sec: int
#   - policy: Optional[Dict[str, Any]] = None
#   - epoch_dir: str = ''
# Called by:
#   - src/role_runner.py
# Calls:
#   - system_capacity, _global_caps, _role_caps, max, int, enforcement_mode, Decision, load_policy, min
# Returns / emits: Decision
# Key locals:
#   - cap, clamped, cpu_req, eff_cpu_cap, eff_mem_cap, mode, policy, ram_req, reason, tout_req
# === End NoemaForge Autodoc Function Header ===
def decide_role_request(
    *,
    role: str,
    requested_cpu_cores: int,
    requested_ram_mib: int,
    requested_timeout_sec: int,
    policy: Optional[Dict[str, Any]] = None,
    epoch_dir: str = "",
) -> Decision:
    """Compute effective resources for a role.

    - Applies per-role caps (via dot hierarchy)
    - Applies global 95% caps
    - Soft mode clamps; hard mode denies if request exceeds caps
    """
    policy = policy or load_policy(epoch_dir=epoch_dir)
    cap = system_capacity()
    g_cpu_cap, g_mem_cap = _global_caps(policy, cap)
    r_cpu_cap, r_mem_cap, r_tout_cap = _role_caps(policy, role)

    # Effective caps for the role are the min of global + role cap
    eff_cpu_cap = max(1, min(int(g_cpu_cap), int(r_cpu_cap or g_cpu_cap)))
    eff_mem_cap = max(256, min(int(g_mem_cap), int(r_mem_cap or g_mem_cap)))

    cpu_req = int(requested_cpu_cores or 0)
    ram_req = int(requested_ram_mib or 0)
    tout_req = int(requested_timeout_sec or 0)

    # If not specified, use role cap as default request
    if cpu_req <= 0:
        cpu_req = int(r_cpu_cap or 2)
    if ram_req <= 0:
        ram_req = int(r_mem_cap or 2048)
    if tout_req <= 0:
        tout_req = int(r_tout_cap or 600)

    clamped = False
    reason = "ok"

    mode = enforcement_mode(policy)

    if cpu_req > eff_cpu_cap or ram_req > eff_mem_cap:
        if mode == "hard":
            return Decision(
                ok=False,
                cpu_cores=min(cpu_req, eff_cpu_cap),
                ram_mib=min(ram_req, eff_mem_cap),
                timeout_sec=tout_req,
                clamped=False,
                reason="exceeds_caps",
                notes={
                    "role": role,
                    "requested": {"cpu_cores": cpu_req, "ram_mib": ram_req},
                    "caps": {"cpu_cores": eff_cpu_cap, "ram_mib": eff_mem_cap},
                    "capacity": {"cpu_total": cap.cpu_total, "mem_total_mib": cap.mem_total_mib},
                },
            )
        # soft mode clamps
        clamped = True
        reason = "clamped_to_caps"
        cpu_req = min(cpu_req, eff_cpu_cap)
        ram_req = min(ram_req, eff_mem_cap)

    # Sanity floors
    cpu_req = max(1, int(cpu_req))
    ram_req = max(256, int(ram_req))
    tout_req = max(30, int(tout_req))

    return Decision(
        ok=True,
        cpu_cores=cpu_req,
        ram_mib=ram_req,
        timeout_sec=tout_req,
        clamped=clamped,
        reason=reason,
        notes={
            "role": role,
            "requested": {"cpu_cores": int(requested_cpu_cores or 0), "ram_mib": int(requested_ram_mib or 0), "timeout_sec": int(requested_timeout_sec or 0)},
            "effective": {"cpu_cores": cpu_req, "ram_mib": ram_req, "timeout_sec": tout_req},
            "caps": {"cpu_cores": eff_cpu_cap, "ram_mib": eff_mem_cap},
            "capacity": {"cpu_total": cap.cpu_total, "mem_total_mib": cap.mem_total_mib},
            "mode": mode,
        },
    )


# === NoemaForge Autodoc Function Header ===
# Function: decide_task_request(requested_cpu_cores: int, requested_ram_mib: int, policy: Optional[Dict[str, Any]] = None, epoch_dir: str = '')
# Purpose: Compute effective resources for a TaskQueue task (future).
# Inputs:
#   - requested_cpu_cores: int
#   - requested_ram_mib: int
#   - policy: Optional[Dict[str, Any]] = None
#   - epoch_dir: str = ''
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - system_capacity, _global_caps, _get_int, load_policy, isinstance, get, int, max
# Returns / emits: Tuple[int, int, bool, str]
# Key locals:
#   - cap, clamped, cpu_def, cpu_req, def_task, defaults, policy, ram_def, ram_req
# === End NoemaForge Autodoc Function Header ===
def decide_task_request(
    *,
    requested_cpu_cores: int,
    requested_ram_mib: int,
    policy: Optional[Dict[str, Any]] = None,
    epoch_dir: str = "",
) -> Tuple[int, int, bool, str]:
    """Compute effective resources for a TaskQueue task (future).

    For now, we only apply global caps + defaults.
    Returns (cpu_cores, ram_mib, clamped, reason).
    """
    policy = policy or load_policy(epoch_dir=epoch_dir)
    cap = system_capacity()
    g_cpu_cap, g_mem_cap = _global_caps(policy, cap)

    defaults = policy.get("defaults") if isinstance(policy.get("defaults"), dict) else {}
    def_task = defaults.get("task") if isinstance(defaults.get("task"), dict) else {}
    cpu_def = _get_int(def_task.get("cpu_cores"), 1)
    ram_def = _get_int(def_task.get("ram_mib"), 1024)

    cpu_req = int(requested_cpu_cores or 0) or cpu_def
    ram_req = int(requested_ram_mib or 0) or ram_def

    clamped = False
    if cpu_req > g_cpu_cap:
        cpu_req = g_cpu_cap
        clamped = True
    if ram_req > g_mem_cap:
        ram_req = g_mem_cap
        clamped = True

    return max(1, cpu_req), max(256, ram_req), clamped, "clamped" if clamped else "ok"


# === NoemaForge Autodoc Function Header ===
# Function: dump_decision_json(decision: Decision)
# Purpose: Implement the routine 'dump decision json'.
# Inputs:
#   - decision: Decision
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - dumps
# Returns / emits: str
# Side effects:
#   - serializes structured data
# === End NoemaForge Autodoc Function Header ===
def dump_decision_json(decision: Decision) -> str:
    try:
        return json.dumps(decision.__dict__, ensure_ascii=False)
    except Exception:
        return "{}"
