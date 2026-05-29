#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/localgw_secrets.py
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
# File: src/localgw_secrets.py
# Purpose: Provide the module 'localgw_secrets'.
# Invoked by / imported from:
#   - src/localgw_connectors/octoprint.py
# Public API / entry functions:
#   - secret_path
#   - load_secret
#   - has_secret
#   - write_secret
# Inputs:
#   - Common path inputs: /var/lib/noemaforge/.sys/localgw_secrets
#   - Imports: __future__, os
# Output formats / side effects:
#   - Returns Python values and/or performs in-memory orchestration.
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""localgw_secrets.py (v0.15.0)

Local Gateway secret store helper.

Why
----
Connector profiles often need credentials (API keys, tokens).
We must avoid embedding secrets into epoch YAML contracts (which are visible to tooling),
so we store secrets in a spinal-zone directory, referenced by an opaque ID.

By design, executors (LLMs/roles) should never see the secret values.
Only LocalGateway (under ToolProxy, typically privileged) reads them when executing
a connector call.

Storage
-------
/var/lib/noemaforge/.sys/localgw_secrets/<secret_id>.txt

This is intentionally simple.
"""


import os

SECRETS_DIR = "/var/lib/noemaforge/.sys/localgw_secrets"


# === NoemaForge Autodoc Function Header ===
# Function: _safe_id(secret_id: str)
# Purpose: Implement the routine ' safe id'.
# Inputs:
#   - secret_id: str
# Called by:
#   - src/llm_backends_manager.py
#   - src/model_router.py
# Calls:
#   - strip, replace, str
# Returns / emits: str
# Key locals:
#   - s
# === End NoemaForge Autodoc Function Header ===
def _safe_id(secret_id: str) -> str:
    s = str(secret_id or "").strip()
    s = s.replace("/", "_").replace("..", "_")
    return s


# === NoemaForge Autodoc Function Header ===
# Function: secret_path(secret_id: str)
# Purpose: Implement the routine 'secret path'.
# Inputs:
#   - secret_id: str
# Called by:
#   - src/localgw_connectors/octoprint.py
# Calls:
#   - _safe_id, makedirs, join
# Returns / emits: str
# Side effects:
#   - creates directories
# Key locals:
#   - sid
# === End NoemaForge Autodoc Function Header ===
def secret_path(secret_id: str) -> str:
    sid = _safe_id(secret_id)
    os.makedirs(SECRETS_DIR, exist_ok=True)
    return os.path.join(SECRETS_DIR, f"{sid}.txt")


# === NoemaForge Autodoc Function Header ===
# Function: load_secret(secret_id: str, default: str = '')
# Purpose: Implement the routine 'load secret'.
# Inputs:
#   - secret_id: str
#   - default: str = ''
# Called by:
#   - src/localgw_connectors/octoprint.py
# Calls:
#   - secret_path, exists, open, strip, readline
# Returns / emits: str
# Side effects:
#   - reads or writes files
# Key locals:
#   - f, p
# === End NoemaForge Autodoc Function Header ===
def load_secret(secret_id: str, default: str = "") -> str:
    p = secret_path(secret_id)
    if not os.path.exists(p):
        return default
    try:
        with open(p, "r", encoding="utf-8") as f:
            return (f.readline() or "").strip()
    except Exception:
        return default


# === NoemaForge Autodoc Function Header ===
# Function: has_secret(secret_id: str)
# Purpose: Implement the routine 'has secret'.
# Inputs:
#   - secret_id: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - bool, exists, secret_path
# Returns / emits: bool
# === End NoemaForge Autodoc Function Header ===
def has_secret(secret_id: str) -> bool:
    return bool(secret_id) and os.path.exists(secret_path(secret_id))


# === NoemaForge Autodoc Function Header ===
# Function: write_secret(secret_id: str, value: str)
# Purpose: Best-effort helper for manual provisioning (not used automatically).
# Inputs:
#   - secret_id: str
#   - value: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _safe_id, secret_path, makedirs, replace, dirname, open, write, chmod, exists, strip, remove, str
# Returns / emits: bool
# Side effects:
#   - reads or writes files
#   - creates directories
# Key locals:
#   - f, p, sid, tmp
# === End NoemaForge Autodoc Function Header ===
def write_secret(secret_id: str, value: str) -> bool:
    """Best-effort helper for manual provisioning (not used automatically)."""
    sid = _safe_id(secret_id)
    if not sid:
        return False
    p = secret_path(sid)
    tmp = p + ".tmp"
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(str(value or "").strip() + "\n")
        os.replace(tmp, p)
        try:
            os.chmod(p, 0o600)
        except Exception:
            pass
        return True
    except Exception:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass
        return False
