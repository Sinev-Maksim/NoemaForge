#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/glove_runner.py
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
# File: src/glove_runner.py
# Purpose: Provide the module 'glove_runner'.
# Invoked by / imported from:
#   - src/brainctl.py
#   - src/toolproxy.py
# Public API / entry functions:
#   - run_glove
# Inputs:
#   - Common path inputs: /opt/noemaforge/src/glove_agent.py
#   - Imports: __future__, os, shutil, uuid, typing, yaml, sandbox
# Output formats / side effects:
#   - copied filesystem artifacts
#   - JSON files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""glove_runner.py (v0.11.0)

Glove Runner = orchestrates one-shot amnesic glove analysis.

Policy:
- The incident snapshot is treated as evidence: mount RO.
- Output is written to a separate RW folder, then copied/linked as stable artifacts.
- No network.

This module is called by ToolProxy (privileged roles only) and by brainctl webgw review.
"""


import os
import shutil
import uuid
from typing import Any, Dict, Tuple

import yaml

from sandbox import run as sandbox_run, _quota_from_policy


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
# Function: _now_rel()
# Purpose: Implement the routine ' now rel'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - uuid4
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _now_rel() -> str:
    return uuid.uuid4().hex[:8]


# === NoemaForge Autodoc Function Header ===
# Function: _resolve_glove_agent_path()
# Purpose: Find glove_agent.py.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - exists, dirname, join, abspath
# Returns / emits: str
# Key locals:
#   - here, p1, p2
# === End NoemaForge Autodoc Function Header ===
def _resolve_glove_agent_path() -> str:
    """Find glove_agent.py.

    Installed path (normal): /opt/noemaforge/src/glove_agent.py
    Dev path (seed kit / WSL): <this_dir>/glove_agent.py
    """
    p1 = "/opt/noemaforge/src/glove_agent.py"
    if os.path.exists(p1):
        return p1
    here = os.path.dirname(os.path.abspath(__file__))
    p2 = os.path.join(here, "glove_agent.py")
    return p2


# === NoemaForge Autodoc Function Header ===
# Function: run_glove(sandbox_policy: Dict[str, Any], incident_dir: str, profile: str = 'generic', languages: str = 'ru,en,de,zh')
# Purpose: Run glove analysis for an incident.
# Inputs:
#   - sandbox_policy: Dict[str, Any]
#   - incident_dir: str
#   - profile: str = 'generic'
#   - languages: str = 'ru,en,de,zh'
# Called by:
#   - src/brainctl.py
#   - src/toolproxy.py
# Calls:
#   - abspath, join, makedirs, _quota_from_policy, _resolve_glove_agent_path, sandbox_run, isdir, str, setdefault, exists, copy2, bool
# Returns / emits: Tuple[bool, Dict[str, Any]]
# Side effects:
#   - creates directories
#   - copies filesystem artifacts
#   - spawns subprocesses or workers
# Key locals:
#   - argv, env, extra_ro, glove_agent, idir, ok, out_dir, out_path, quota, ro_binds, rw_binds, s1
# === End NoemaForge Autodoc Function Header ===
def run_glove(
    *,
    sandbox_policy: Dict[str, Any],
    incident_dir: str,
    profile: str = "generic",
    languages: str = "ru,en,de,zh",
) -> Tuple[bool, Dict[str, Any]]:
    """Run glove analysis for an incident.

    Returns (ok, result) with paths.
    """

    idir = os.path.abspath(incident_dir)
    if not os.path.isdir(idir):
        return False, {"error": "incident_dir_missing", "incident_dir": idir}

    # Evidence is immutable: do not write into idir from inside sandbox.
    out_dir = os.path.join(idir, "glove_out")
    os.makedirs(out_dir, exist_ok=True)

    out_path = os.path.join(out_dir, f"glove_report_{_now_rel()}.json")

    quota = _quota_from_policy(sandbox_policy, "glove")

    # Minimal env
    env = {
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONNOUSERSITE": "1",
    }

    glove_agent = _resolve_glove_agent_path()

    argv = [
        "python3",
        glove_agent,
        "--incident-dir",
        idir,
        "--out",
        out_path,
        "--profile",
        str(profile or "generic"),
        "--languages",
        languages,
    ]

    # Mount incident dir RO, output dir RW. Also mount glove_agent file RO.
    ro_binds = [idir]
    rw_binds = [out_dir]
    extra_ro = [glove_agent]

    ok, res = sandbox_run(
        policy=sandbox_policy,
        argv=argv,
        cwd=out_dir,
        env=env,
        quota=quota,
        ro_binds=ro_binds,
        rw_binds=rw_binds,
        allow_network=False,
        extra_ro_binds=extra_ro,
        prefer_backends=None,
    )

    # If it succeeded but report is missing, treat as failure.
    if ok and not os.path.exists(out_path):
        ok = False
        res.setdefault("stderr", "")
        res["stderr"] += "\nmissing_glove_report"

    # Create stable names for convenience.
    stable_report = os.path.join(idir, "glove_report.json")
    stable_sanitized = os.path.join(idir, "glove_sanitized.txt")
    stable_inventory = os.path.join(idir, "glove_payload_inventory.json")
    stable_pi = os.path.join(idir, "glove_pi_report.json")
    stable_sani_meta = os.path.join(idir, "glove_sanitized_meta.json")

    if ok:
        try:
            shutil.copy2(out_path, stable_report)
        except Exception:
            pass

        # Side artifacts are optional. If present, copy into incident dir.
        try:
            s1 = os.path.join(out_dir, "sanitized.txt")
            if os.path.exists(s1):
                shutil.copy2(s1, stable_sanitized)
        except Exception:
            pass
        try:
            s1m = os.path.join(out_dir, "sanitized_meta.json")
            if os.path.exists(s1m):
                shutil.copy2(s1m, stable_sani_meta)
        except Exception:
            pass
        try:
            spi = os.path.join(out_dir, "pi_report.json")
            if os.path.exists(spi):
                shutil.copy2(spi, stable_pi)
        except Exception:
            pass
        try:
            s2 = os.path.join(out_dir, "payload_inventory.json")
            if os.path.exists(s2):
                shutil.copy2(s2, stable_inventory)
        except Exception:
            pass

    return ok, {
        "ok": bool(ok),
        "incident_dir": idir,
        "glove_out_dir": out_dir,
        "glove_report": out_path if ok else None,
        "glove_report_stable": stable_report if ok else None,
        "glove_sanitized_stable": stable_sanitized if (ok and os.path.exists(stable_sanitized)) else None,
        "glove_inventory_stable": stable_inventory if (ok and os.path.exists(stable_inventory)) else None,
        "backend": res.get("backend"),
        "stdout": res.get("stdout"),
        "stderr": res.get("stderr"),
        "exit_code": res.get("exit_code"),
    }
