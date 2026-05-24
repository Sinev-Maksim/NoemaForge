#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/epoch.py
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
# File: src/epoch.py
# Purpose: Provide the module 'epoch'.
# Invoked by / imported from:
#   - src/bootdoctor.py
#   - src/brainctl.py
#   - src/noemaforge_core.py
#   - src/caps.py
#   - src/incidents.py
#   - src/knowledge/policy.py
#   - src/knowledge_maintainer.py
#   - src/resource_recovery.py
#   - src/role_runner.py
#   - src/scary_sweep.py
# Public API / entry functions:
#   - current_epoch_id
#   - current_epoch_dir
# Inputs:
#   - Environment: NOEMAFORGE_CONTRACTS_ROOT
#   - Common path inputs: /var/lib/noemaforge/contracts
#   - Imports: __future__, os, typing
# Output formats / side effects:
#   - Returns Python values and/or performs in-memory orchestration.
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""epoch.py (v0.11.0)

Contract Epochs

Idea:
- Runtime MUST treat the current contract set as immutable.
- Pre-start is the only time contracts/tools/policies change.
- Every capability token is bound to an epoch_id.
- ToolProxy denies tokens from a different epoch.

This module is intentionally small and dependency-free.
"""


import os
from typing import Optional

DEFAULT_EPOCH_ID = "00000"


# === NoemaForge Autodoc Function Header ===
# Function: _contracts_root()
# Purpose: Implement the routine ' contracts root'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - get
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _contracts_root() -> str:
    return os.environ.get("NOEMAFORGE_CONTRACTS_ROOT", "/var/lib/noemaforge/contracts")


# === NoemaForge Autodoc Function Header ===
# Function: current_epoch_id(contracts_root: Optional[str] = None)
# Purpose: Best-effort: return current epoch id.
# Inputs:
#   - contracts_root: Optional[str] = None
# Called by:
#   - src/bootdoctor.py
#   - src/brainctl.py
#   - src/caps.py
#   - src/firstboot_eval.py
#   - src/llm_backends_manager.py
#   - src/prestart.py
#   - src/scary_sweep.py
#   - src/sr_cycle.py
# Calls:
#   - join, _contracts_root, exists, strip, realpath, basename, rstrip, read, open
# Returns / emits: str
# Side effects:
#   - reads or writes files
# Key locals:
#   - base, epochs_dir, p_cur, p_txt, real, root, v
# === End NoemaForge Autodoc Function Header ===
def current_epoch_id(contracts_root: Optional[str] = None) -> str:
    """Best-effort: return current epoch id.

    Priority:
    1) /var/lib/noemaforge/contracts/epochs/current_epoch.txt
    2) basename(realpath(/var/lib/noemaforge/contracts/epochs/current))
    3) DEFAULT_EPOCH_ID
    """
    root = contracts_root or _contracts_root()
    epochs_dir = os.path.join(root, "epochs")
    p_txt = os.path.join(epochs_dir, "current_epoch.txt")
    try:
        if os.path.exists(p_txt):
            v = open(p_txt, "r", encoding="utf-8").read().strip()
            return v or DEFAULT_EPOCH_ID
    except Exception:
        pass

    p_cur = os.path.join(epochs_dir, "current")
    try:
        if os.path.exists(p_cur):
            real = os.path.realpath(p_cur)
            base = os.path.basename(real.rstrip("/"))
            return base or DEFAULT_EPOCH_ID
    except Exception:
        pass

    return DEFAULT_EPOCH_ID


# === NoemaForge Autodoc Function Header ===
# Function: current_epoch_dir(contracts_root: Optional[str] = None)
# Purpose: Return directory path for current epoch contracts, if it exists.
# Inputs:
#   - contracts_root: Optional[str] = None
# Called by:
#   - src/bootdoctor.py
#   - src/brainctl.py
#   - src/noemaforge_core.py
#   - src/incidents.py
#   - src/knowledge/policy.py
#   - src/knowledge_maintainer.py
#   - src/resource_recovery.py
#   - src/role_runner.py
# Calls:
#   - join, current_epoch_id, isdir, _contracts_root, islink, realpath
# Returns / emits: Optional[str]
# Key locals:
#   - eid, epochs_dir, p, p_cur, root
# === End NoemaForge Autodoc Function Header ===
def current_epoch_dir(contracts_root: Optional[str] = None) -> Optional[str]:
    """Return directory path for current epoch contracts, if it exists."""
    root = contracts_root or _contracts_root()
    epochs_dir = os.path.join(root, "epochs")
    p_cur = os.path.join(epochs_dir, "current")
    if os.path.isdir(p_cur) or os.path.islink(p_cur):
        return os.path.realpath(p_cur)
    # Also allow explicit folder by id
    eid = current_epoch_id(root)
    p = os.path.join(epochs_dir, eid)
    if os.path.isdir(p):
        return p
    return None
