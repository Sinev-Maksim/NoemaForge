#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/lsm.py
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
# File: src/lsm.py
# Purpose: Provide the module 'lsm'.
# Invoked by / imported from:
#   - src/brainctl.py
#   - src/prestart.py
# Public API / entry functions:
#   - detect_apparmor
#   - detect_selinux
#   - detect
#   - load_policy
#   - check_policy
#   - static_check
# Inputs:
#   - Common path inputs: noemaforge.lsm/v1
#   - Imports: __future__, os, subprocess, typing, yaml, shutil
# Output formats / side effects:
#   - YAML files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""lsm.py (v0.14.0)

Lightweight LSM (Linux Security Modules) detection + policy checks.

NoemaForge uses LSM as an *optional* hardening layer:
- AppArmor on Ubuntu/Debian-like hosts
- SELinux on Fedora/RHEL-like hosts

We do NOT assume LSM is available (portable seed), but we do want:
- a deterministic pre-start policy switch (off/prefer/require)
- a single place to check host status
- a way to surface problems into Canary/PreStart/Incidents
"""


import os
import subprocess
from typing import Any, Dict, Tuple

import yaml


# === NoemaForge Autodoc Function Header ===
# Function: _read_text(path: str)
# Purpose: Implement the routine ' read text'.
# Inputs:
#   - path: str
# Called by:
#   - src/hwscan.py
#   - tools/autodoc_inject.py
#   - tools/checker/noemaforge_check.py
# Calls:
#   - open, read
# Returns / emits: str
# Side effects:
#   - reads or writes files
# Key locals:
#   - f
# === End NoemaForge Autodoc Function Header ===
def _read_text(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


# === NoemaForge Autodoc Function Header ===
# Function: _which(cmd: str)
# Purpose: Implement the routine ' which'.
# Inputs:
#   - cmd: str
# Called by:
#   - src/role_runner.py
#   - src/sandbox.py
# Calls:
#   - which
# Returns / emits: str
# Key locals:
#   - p
# === End NoemaForge Autodoc Function Header ===
def _which(cmd: str) -> str:
    import shutil
    p = shutil.which(cmd)
    return p or ""


# === NoemaForge Autodoc Function Header ===
# Function: detect_apparmor()
# Purpose: Implement the routine 'detect apparmor'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - strip, _which, startswith, isdir, bool, _read_text, run
# Returns / emits: Dict[str, Any]
# Side effects:
#   - spawns subprocesses or workers
# Key locals:
#   - aa_status, enabled, enabled_flag, loaded_profiles, out, p
# === End NoemaForge Autodoc Function Header ===
def detect_apparmor() -> Dict[str, Any]:
    enabled_flag = _read_text("/sys/module/apparmor/parameters/enabled").strip()
    enabled = enabled_flag.startswith("Y") or os.path.isdir("/sys/kernel/security/apparmor")
    aa_status = _which("apparmor_status")
    loaded_profiles = None
    if aa_status:
        try:
            p = subprocess.run([aa_status], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=2)
            out = p.stdout or ""
            # Heuristic: count lines with "profiles are loaded"
            loaded_profiles = out.strip()
        except Exception:
            loaded_profiles = None
    return {
        "enabled": bool(enabled),
        "enabled_flag": enabled_flag or None,
        "apparmor_status": bool(aa_status),
        "raw": loaded_profiles,
    }


# === NoemaForge Autodoc Function Header ===
# Function: detect_selinux()
# Purpose: Implement the routine 'detect selinux'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - isdir, exists, _which, strip, bool, run, _read_text
# Returns / emits: Dict[str, Any]
# Side effects:
#   - spawns subprocesses or workers
# Key locals:
#   - enabled, enforce_path, enforcing, getenforce, mode, p, v
# === End NoemaForge Autodoc Function Header ===
def detect_selinux() -> Dict[str, Any]:
    enforce_path = "/sys/fs/selinux/enforce"
    enabled = os.path.isdir("/sys/fs/selinux")
    enforcing = None
    if os.path.exists(enforce_path):
        v = _read_text(enforce_path).strip()
        enforcing = (v == "1")
    getenforce = _which("getenforce")
    mode = None
    if getenforce:
        try:
            p = subprocess.run([getenforce], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=2)
            mode = (p.stdout or "").strip() or None
        except Exception:
            mode = None
    return {
        "enabled": bool(enabled),
        "enforcing": enforcing,
        "getenforce": bool(getenforce),
        "mode": mode,
    }


# === NoemaForge Autodoc Function Header ===
# Function: detect()
# Purpose: Implement the routine 'detect'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - src/brainctl.py
# Calls:
#   - detect_apparmor, detect_selinux
# Returns / emits: Dict[str, Any]
# === End NoemaForge Autodoc Function Header ===
def detect() -> Dict[str, Any]:
    return {
        "apparmor": detect_apparmor(),
        "selinux": detect_selinux(),
    }


# === NoemaForge Autodoc Function Header ===
# Function: load_policy(epoch_dir: str)
# Purpose: Implement the routine 'load policy'.
# Inputs:
#   - epoch_dir: str
# Called by:
#   - src/audit_remediation.py
#   - src/bootdoctor.py
#   - src/brainctl.py
#   - src/daily_scheduler.py
#   - src/maintenance.py
#   - src/resource_policy.py
#   - src/role_runner.py
#   - src/task_tools.py
# Calls:
#   - join, exists, isinstance, open, safe_load
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads or writes files
# Key locals:
#   - f, obj, path
# === End NoemaForge Autodoc Function Header ===
def load_policy(epoch_dir: str) -> Dict[str, Any]:
    path = os.path.join(epoch_dir, "lsm-policy.yaml")
    if not os.path.exists(path):
        return {
            "apiVersion": "noemaforge.lsm/v1",
            "kind": "LSMPPolicy",
            "require": {"mode": "prefer", "fail_closed": False},
            "apparmor": {"enabled": True, "enforce": False, "profiles": {}},
            "selinux": {"enabled": True, "enforce": False, "contexts": {}},
        }
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = yaml.safe_load(f) or {}
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    return {
        "apiVersion": "noemaforge.lsm/v1",
        "kind": "LSMPPolicy",
        "require": {"mode": "prefer", "fail_closed": False},
        "apparmor": {"enabled": True, "enforce": False, "profiles": {}},
        "selinux": {"enabled": True, "enforce": False, "contexts": {}},
    }


# === NoemaForge Autodoc Function Header ===
# Function: check_policy(policy: Dict[str, Any], host: Dict[str, Any])
# Purpose: Implement the routine 'check policy'.
# Inputs:
#   - policy: Dict[str, Any]
#   - host: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - lower, bool, get, strip, append, str
# Returns / emits: Tuple[bool, Dict[str, Any]]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - aa, enabled_any, fail_closed, mode, ok, problems, req, se
# === End NoemaForge Autodoc Function Header ===
def check_policy(policy: Dict[str, Any], host: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    req = policy.get("require") or {}
    mode = str(req.get("mode") or "prefer").strip().lower()
    fail_closed = bool(req.get("fail_closed", False))

    problems = []

    aa = host.get("apparmor") or {}
    se = host.get("selinux") or {}

    enabled_any = bool(aa.get("enabled")) or bool(se.get("enabled"))

    if mode == "off":
        return True, {"mode": mode, "enabled_any": enabled_any, "problems": []}

    if mode in ("prefer", "require") and not enabled_any:
        # prefer => warn, require => problem
        if mode == "require" and fail_closed:
            problems.append("lsm:required_but_no_lsm_enabled")
        else:
            problems.append("lsm:recommended_but_no_lsm_enabled")

    ok = not (mode == "require" and fail_closed and problems)
    return ok, {"mode": mode, "enabled_any": enabled_any, "problems": problems}


# === NoemaForge Autodoc Function Header ===
# Function: static_check(epoch_dir: str)
# Purpose: Implement the routine 'static check'.
# Inputs:
#   - epoch_dir: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - load_policy, detect, check_policy
# Returns / emits: Tuple[bool, Dict[str, Any]]
# Key locals:
#   - host, pol
# === End NoemaForge Autodoc Function Header ===
def static_check(epoch_dir: str) -> Tuple[bool, Dict[str, Any]]:
    pol = load_policy(epoch_dir)
    host = detect()
    ok, rep = check_policy(pol, host)
    rep["host"] = host
    return ok, rep
