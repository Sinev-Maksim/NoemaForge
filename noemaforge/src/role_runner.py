#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/role_runner.py
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
# File: src/role_runner.py
# Purpose: Provide the module 'role_runner'.
# Invoked by / imported from:
#   - src/noemaforge_core.py
# Public API / entry functions:
#   - class RunSpec
#   - run_role
# Inputs:
#   - Common path inputs: /opt/noemaforge/configs/role-runner.yaml, /run/noemaforge/toolproxy.sock, /opt/noemaforge/src/roles/role_entry.py
#   - Imports: __future__, os, shutil, subprocess, dataclasses, typing, yaml, epoch
# Output formats / side effects:
#   - YAML files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""role_runner.py (v0.12.8)

Runs a role as an *ephemeral* unit of execution.

Backend preference:
- podman (rootless, offline-first with pull_policy=never)
- host (fallback)

The role code itself is in /opt/noemaforge/src/roles/role_entry.py
It receives a context JSON and writes a role_result JSON.

Security posture
----------------
- No network (podman network=none; host path is expected to respect ToolProxy).
- Roles only get a short-lived capability token, enforced by ToolProxy.

Resource posture
----------------
- Applies ResourcePolicy caps (default: never exceed 95% global budget).
- In soft mode, requests are clamped; in hard mode, runs are denied.

Note: this is still MVP isolation. Stronger enforcement (systemd/cgroups) can be
wired later; podman limits already provide decent guardrails.
"""


import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import yaml


CFG_PATH = "/opt/noemaforge/configs/role-runner.yaml"

try:
    import epoch
except Exception:  # pragma: no cover
    epoch = None  # type: ignore

try:
    import resource_policy
except Exception:  # pragma: no cover
    resource_policy = None  # type: ignore


@dataclass
class RunSpec:
    project_id: str
    role: str
    run_id: str
    trace_id: str
    context_path: str
    out_path: str
    cap_token: str
    cpu_cores: int = 2
    ram_mib: int = 2048
    timeout_sec: int = 600
    host_nice: int = 0


# === NoemaForge Autodoc Function Header ===
# Function: _load_cfg(path: str)
# Purpose: Implement the routine ' load cfg'.
# Inputs:
#   - path: str
# Called by:
#   - src/memsentinel.py
# Calls:
#   - open, safe_load
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads or writes files
# Key locals:
#   - f
# === End NoemaForge Autodoc Function Header ===
def _load_cfg(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# === NoemaForge Autodoc Function Header ===
# Function: _which(cmd: str)
# Purpose: Implement the routine ' which'.
# Inputs:
#   - cmd: str
# Called by:
#   - src/lsm.py
#   - src/sandbox.py
# Calls:
#   - which
# Returns / emits: Optional[str]
# === End NoemaForge Autodoc Function Header ===
def _which(cmd: str) -> Optional[str]:
    return shutil.which(cmd)


# === NoemaForge Autodoc Function Header ===
# Function: _run_host(cfg: Dict[str, Any], spec: RunSpec)
# Purpose: Implement the routine ' run host'.
# Inputs:
#   - cfg: Dict[str, Any]
#   - spec: RunSpec
# Called by:
#   - src/sandbox.py
# Calls:
#   - copy, get, str, run, int, _which
# Returns / emits: Tuple[int, str]
# Side effects:
#   - spawns subprocesses or workers
# Key locals:
#   - base_cmd, cmd, env, p
# === End NoemaForge Autodoc Function Header ===
def _run_host(cfg: Dict[str, Any], spec: RunSpec) -> Tuple[int, str]:
    env = os.environ.copy()
    env["NOEMAFORGE_TOOLPROXY_SOCKET"] = (cfg.get("paths") or {}).get("toolproxy_socket", "/run/noemaforge/toolproxy.sock")
    env["NOEMAFORGE_CAP_TOKEN"] = spec.cap_token
    env["NOEMAFORGE_RUN_ID"] = spec.run_id
    env["NOEMAFORGE_TRACE_ID"] = spec.trace_id
    env["NOEMAFORGE_PROJECT_ID"] = spec.project_id
    env["NOEMAFORGE_ROLE"] = spec.role
    env["NOEMAFORGE_CPU_CORES"] = str(int(spec.cpu_cores))
    env["NOEMAFORGE_RAM_MIB"] = str(int(spec.ram_mib))

    base_cmd = [
        "/usr/bin/python3",
        "/opt/noemaforge/src/roles/role_entry.py",
        "--role",
        spec.role,
        "--context",
        spec.context_path,
        "--out",
        spec.out_path,
        "--run-id",
        spec.run_id,
        "--trace-id",
        spec.trace_id,
    ]

    cmd = base_cmd
    # Host is weaker isolation; use nice to be polite.
    if int(spec.host_nice or 0) != 0 and _which("nice"):
        cmd = ["nice", "-n", str(int(spec.host_nice))] + base_cmd

    p = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=spec.timeout_sec)
    return p.returncode, (p.stdout + "\n" + p.stderr)


# === NoemaForge Autodoc Function Header ===
# Function: _run_podman(cfg: Dict[str, Any], spec: RunSpec)
# Purpose: Implement the routine ' run podman'.
# Inputs:
#   - cfg: Dict[str, Any]
#   - spec: RunSpec
# Called by:
#   - src/sandbox.py
# Calls:
#   - _which, str, int, dirname, get, exists, run, basename
# Returns / emits: Tuple[int, str]
# Side effects:
#   - spawns subprocesses or workers
# Key locals:
#   - cmd, image, net, p, pcfg, pids, pod, pull, tool_sock, workdir
# === End NoemaForge Autodoc Function Header ===
def _run_podman(cfg: Dict[str, Any], spec: RunSpec) -> Tuple[int, str]:
    pod = _which("podman")
    if not pod:
        return 127, "podman_not_found"

    pcfg = cfg.get("podman") or {}
    image = str(pcfg.get("image") or "python:3.11-slim")
    net = str(pcfg.get("network") or "none")
    pull = str(pcfg.get("pull_policy") or "never")
    pids = int(pcfg.get("pids_limit") or 256)

    # Prepare a workdir containing context + output.
    # For podman we mount the dir to /work.
    workdir = os.path.dirname(spec.context_path)

    cmd = [
        pod,
        "run",
        "--rm",
        "--pull",
        pull,
        "--network",
        net,
        "--pids-limit",
        str(pids),
        "--memory",
        f"{int(spec.ram_mib)}m",
        "--cpus",
        str(int(spec.cpu_cores)),
        "-v",
        f"{workdir}:/work:Z",
        "-v",
        "/opt/noemaforge/src/roles:/roles:ro,Z",
    ]

    tool_sock = (cfg.get("paths") or {}).get("toolproxy_socket", "/run/noemaforge/toolproxy.sock")
    if os.path.exists(str(tool_sock)):
        cmd += ["-v", f"{tool_sock}:{tool_sock}:ro,Z"]

    cmd += [
        "--env",
        f"NOEMAFORGE_TOOLPROXY_SOCKET={tool_sock}",
        "--env",
        f"NOEMAFORGE_CAP_TOKEN={spec.cap_token}",
        "--env",
        f"NOEMAFORGE_RUN_ID={spec.run_id}",
        "--env",
        f"NOEMAFORGE_TRACE_ID={spec.trace_id}",
        "--env",
        f"NOEMAFORGE_PROJECT_ID={spec.project_id}",
        "--env",
        f"NOEMAFORGE_ROLE={spec.role}",
        "--env",
        f"NOEMAFORGE_CPU_CORES={int(spec.cpu_cores)}",
        "--env",
        f"NOEMAFORGE_RAM_MIB={int(spec.ram_mib)}",
        image,
        "python3",
        "/roles/role_entry.py",
        "--role",
        spec.role,
        "--context",
        "/work/" + os.path.basename(spec.context_path),
        "--out",
        "/work/" + os.path.basename(spec.out_path),
        "--run-id",
        spec.run_id,
        "--trace-id",
        spec.trace_id,
    ]

    p = subprocess.run(cmd, capture_output=True, text=True, timeout=spec.timeout_sec)
    return p.returncode, (p.stdout + "\n" + p.stderr)


# === NoemaForge Autodoc Function Header ===
# Function: _current_epoch_dir()
# Purpose: Implement the routine ' current epoch dir'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - src/firstboot_eval.py
#   - src/llm_backends_manager.py
# Calls:
#   - str, current_epoch_dir
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _current_epoch_dir() -> str:
    try:
        if epoch is None:
            return ""
        return str(epoch.current_epoch_dir() or "")
    except Exception:
        return ""


# === NoemaForge Autodoc Function Header ===
# Function: _apply_resource_policy(spec: RunSpec)
# Purpose: Implement the routine ' apply resource policy'.
# Inputs:
#   - spec: RunSpec
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _current_epoch_dir, load_policy, decide_role_request, int, bool, host_nice
# Returns / emits: Tuple[bool, str]
# Key locals:
#   - dec, e_dir, note, pol
# === End NoemaForge Autodoc Function Header ===
def _apply_resource_policy(spec: RunSpec) -> Tuple[bool, str]:
    if resource_policy is None:
        return True, "no_resource_policy"

    e_dir = _current_epoch_dir()
    pol = resource_policy.load_policy(epoch_dir=e_dir)

    dec = resource_policy.decide_role_request(
        role=spec.role,
        requested_cpu_cores=int(spec.cpu_cores or 0),
        requested_ram_mib=int(spec.ram_mib or 0),
        requested_timeout_sec=int(spec.timeout_sec or 0),
        policy=pol,
        epoch_dir=e_dir,
    )

    if not bool(dec.ok):
        return False, f"resource_policy_denied:{dec.reason}"

    spec.cpu_cores = int(dec.cpu_cores)
    spec.ram_mib = int(dec.ram_mib)
    spec.timeout_sec = int(dec.timeout_sec)
    try:
        spec.host_nice = int(resource_policy.host_nice(pol))
    except Exception:
        spec.host_nice = 0

    # In soft mode, clamping is ok; we just carry it in logs via stderr.
    note = dec.reason
    if bool(dec.clamped):
        note += ":clamped"
    return True, note


# === NoemaForge Autodoc Function Header ===
# Function: run_role(spec: RunSpec, cfg_path: str = CFG_PATH)
# Purpose: Implement the routine 'run role'.
# Inputs:
#   - spec: RunSpec
#   - cfg_path: str = CFG_PATH
# Called by:
#   - src/noemaforge_core.py
# Calls:
#   - _load_cfg, _apply_resource_policy, get, int, _run_podman, _run_host
# Returns / emits: Tuple[bool, str]
# Side effects:
#   - spawns subprocesses or workers
# Key locals:
#   - b, cfg, defaults, last_out, prefs
# === End NoemaForge Autodoc Function Header ===
def run_role(spec: RunSpec, cfg_path: str = CFG_PATH) -> Tuple[bool, str]:
    cfg = _load_cfg(cfg_path)

    defaults = cfg.get("defaults") or {}
    if spec.cpu_cores <= 0:
        spec.cpu_cores = int(defaults.get("cpu_cores") or 2)
    if spec.ram_mib <= 0:
        spec.ram_mib = int(defaults.get("ram_mib") or 2048)
    if spec.timeout_sec <= 0:
        spec.timeout_sec = int(defaults.get("timeout_sec") or 600)

    ok_pol, pol_note = _apply_resource_policy(spec)
    if not ok_pol:
        return False, pol_note

    prefs = cfg.get("backend_preference") or ["podman", "host"]

    last_out = ""
    for b in prefs:
        if b == "podman":
            rc, out = _run_podman(cfg, spec)
            last_out = out
            if rc == 0:
                return True, out
        if b == "host":
            rc, out = _run_host(cfg, spec)
            last_out = out
            if rc == 0:
                return True, out

    return False, last_out or pol_note
