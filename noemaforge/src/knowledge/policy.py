#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/knowledge/policy.py
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
# File: src/knowledge/policy.py
# Purpose: Implement the knowledge subsystem module 'policy'.
# Invoked by / imported from:
#   - src/brainctl.py
#   - src/knowledge/__init__.py
# Public API / entry functions:
#   - load_knowledge_policy
# Inputs:
#   - Common path inputs: /var/lib/noemaforge/contracts, /opt/noemaforge/configs/knowledge-policy.yaml
#   - Imports: __future__, os, typing, yaml, epoch
# Output formats / side effects:
#   - YAML files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""knowledge.policy (v0.16.0)

Loads knowledge-policy.yaml from the current epoch (preferred) or from
/opt/noemaforge/configs fallback.

This follows the same contract-epoch pattern used across NoemaForge.
"""


import os
from typing import Any, Dict

import yaml

from epoch import current_epoch_dir


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
#   - src/llm_backends_manager.py
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
# Function: load_knowledge_policy(contracts_root: str = '/var/lib/noemaforge/contracts')
# Purpose: Implement the routine 'load knowledge policy'.
# Inputs:
#   - contracts_root: str = '/var/lib/noemaforge/contracts'
# Called by:
#   - src/brainctl.py
# Calls:
#   - exists, current_epoch_dir, join, _load_yaml
# Returns / emits: Dict[str, Any]
# Key locals:
#   - e_dir, p, p2
# === End NoemaForge Autodoc Function Header ===
def load_knowledge_policy(contracts_root: str = "/var/lib/noemaforge/contracts") -> Dict[str, Any]:
    # Prefer epoch contract if present
    try:
        e_dir = current_epoch_dir(contracts_root)
        if e_dir:
            p = os.path.join(e_dir, "knowledge-policy.yaml")
            if os.path.exists(p):
                return _load_yaml(p)
    except Exception:
        pass

    # Fallback
    p2 = "/opt/noemaforge/configs/knowledge-policy.yaml"
    if os.path.exists(p2):
        try:
            return _load_yaml(p2)
        except Exception:
            pass

    return {"enabled": False}
