#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/localgw_connectors/ipp.py
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
# File: src/localgw_connectors/ipp.py
# Purpose: Provide the module 'ipp'.
# Invoked by / imported from:
#   - No inbound Python import detected; treat as library leaf or direct entrypoint.
# Public API / entry functions:
#   - manifest
#   - call
# Inputs:
#   - Imports: __future__, os, shutil, subprocess, typing
# Output formats / side effects:
#   - Returns Python values and/or performs in-memory orchestration.
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""localgw_connectors.ipp (v0.15.0)

IPP / printing connector (typed).

This is a pragmatic connector for local printers:
- Primary path: use CUPS `lp` if present (queue-based).
- Fallback: return a clear 'cups_not_available' reason.

Policy integration
------------------
Device profile example:

devices:
  allowlist:
    - device_uid: lan:...
      name: office_printer
      connectors:
        ipp:
          queue: HP_LaserJet

Methods
-------
- print_file (dangerous / actuation)
"""


import os
import shutil
import subprocess
from typing import Any, Dict, Tuple

from . import base


# === NoemaForge Autodoc Function Header ===
# Function: manifest()
# Purpose: Implement the routine 'manifest'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - src/localgw_connectors/__init__.py
#   - src/localgw_connectors/octoprint.py
# Returns / emits: Dict[str, Any]
# === End NoemaForge Autodoc Function Header ===
def manifest() -> Dict[str, Any]:
    return {
        "id": "ipp",
        "version": "0.15.0",
        "methods": ["print_file"],
        "dangerous_methods": ["print_file"],
    }


# === NoemaForge Autodoc Function Header ===
# Function: _profile(ctx: base.ConnectorContext)
# Purpose: Implement the routine ' profile'.
# Inputs:
#   - ctx: base.ConnectorContext
# Called by:
#   - src/localgw_connectors/octoprint.py
# Calls:
#   - isinstance, get
# Returns / emits: Dict[str, Any]
# Key locals:
#   - oc, prof
# === End NoemaForge Autodoc Function Header ===
def _profile(ctx: base.ConnectorContext) -> Dict[str, Any]:
    prof = (ctx.device_profile or {}) if isinstance(ctx.device_profile, dict) else {}
    oc = (prof.get("connectors") or {}).get("ipp") if isinstance(prof.get("connectors"), dict) else None
    return oc if isinstance(oc, dict) else {}


# === NoemaForge Autodoc Function Header ===
# Function: call(method: str, params: Dict[str, Any], ctx: base.ConnectorContext)
# Purpose: Implement the routine 'call'.
# Inputs:
#   - method: str
#   - params: Dict[str, Any]
#   - ctx: base.ConnectorContext
# Called by:
#   - src/localgateway.py
#   - src/localgw_connectors/__init__.py
# Calls:
#   - strip, _profile, int, which, exists, run, str, get
# Returns / emits: Tuple[bool, Dict[str, Any], str]
# Side effects:
#   - spawns subprocesses or workers
# Key locals:
#   - cmd, copies, lp, m, p, path, profile, queue, title
# === End NoemaForge Autodoc Function Header ===
def call(*, method: str, params: Dict[str, Any], ctx: base.ConnectorContext) -> Tuple[bool, Dict[str, Any], str]:
    m = str(method or "").strip()
    if m != "print_file":
        return False, {"ok": False, "reason": "method_not_allowed"}, "method_not_allowed"

    profile = _profile(ctx)
    queue = str(profile.get("queue") or (params or {}).get("queue") or "").strip()
    path = str((params or {}).get("path") or "").strip()
    copies = int((params or {}).get("copies") or 1)
    title = str((params or {}).get("title") or "").strip()

    if not path:
        return False, {"ok": False, "reason": "missing_path"}, "missing_path"
    if not os.path.exists(path):
        return False, {"ok": False, "reason": "file_not_found"}, "file_not_found"

    lp = shutil.which("lp")
    if not lp:
        return False, {"ok": False, "reason": "cups_not_available"}, "cups_not_available"

    cmd = [lp]
    if queue:
        cmd += ["-d", queue]
    if title:
        cmd += ["-t", title]
    if copies and copies > 1:
        cmd += ["-n", str(copies)]
    cmd += [path]

    try:
        p = subprocess.run(cmd, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60)
        if p.returncode != 0:
            return False, {"ok": False, "reason": "print_failed", "stderr": (p.stderr or "")[:2000]}, "print_failed"
        return True, {"ok": True, "stdout": (p.stdout or "")[:2000]}, "ok"
    except Exception as e:
        return False, {"ok": False, "reason": "print_exception"}, f"print_exception:{e!r}"
