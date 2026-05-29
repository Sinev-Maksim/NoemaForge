"""
=== NoemaForge File Header ===
File: noemaforge/src/localgw_connectors/__init__.py
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
# File: src/localgw_connectors/__init__.py
# Purpose: Provide the module '__init__'.
# Invoked by / imported from:
#   - src/localgateway.py
#   - src/localgw_connectors/ipp.py
#   - src/localgw_connectors/octoprint.py
# Public API / entry functions:
#   - list_connectors
#   - has_connector
#   - call
# Inputs:
#   - Imports: __future__, typing
# Output formats / side effects:
#   - Returns Python values and/or performs in-memory orchestration.
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""localgw_connectors package (v0.15.0)

Typed connector registry for LocalGateway.

A connector is a small adapter that implements a stable method surface.
LocalGateway enforces:
- session token (arming)
- connector allowlist
- invite gating for actuation methods (optional policy)
- network target allowlist (subnets/interfaces) best-effort
- SEL/WORM audit events

Connectors should:
- avoid returning secrets
- be deterministic, fail closed
"""


from typing import Any, Dict, Tuple

from . import base
from . import octoprint
from . import ipp


_REGISTRY = {
    "octoprint": octoprint,
    "ipp": ipp,
}


# === NoemaForge Autodoc Function Header ===
# Function: list_connectors()
# Purpose: Implement the routine 'list connectors'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - src/localgateway.py
# Calls:
#   - items, manifest
# Returns / emits: Dict[str, Dict[str, Any]]
# Key locals:
#   - out
# === End NoemaForge Autodoc Function Header ===
def list_connectors() -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for cid, mod in _REGISTRY.items():
        try:
            out[cid] = mod.manifest()
        except Exception:
            out[cid] = {"id": cid, "methods": [], "version": "unknown"}
    return out


# === NoemaForge Autodoc Function Header ===
# Function: has_connector(connector_id: str)
# Purpose: Implement the routine 'has connector'.
# Inputs:
#   - connector_id: str
# Called by:
#   - src/localgateway.py
# Calls:
#   - str
# Returns / emits: bool
# === End NoemaForge Autodoc Function Header ===
def has_connector(connector_id: str) -> bool:
    return str(connector_id or "") in _REGISTRY


# === NoemaForge Autodoc Function Header ===
# Function: call(connector_id: str, method: str, params: Dict[str, Any], ctx: base.ConnectorContext)
# Purpose: Implement the routine 'call'.
# Inputs:
#   - connector_id: str
#   - method: str
#   - params: Dict[str, Any]
#   - ctx: base.ConnectorContext
# Called by:
#   - src/localgateway.py
# Calls:
#   - strip, call, str
# Returns / emits: Tuple[bool, Dict[str, Any], str]
# Key locals:
#   - cid, mod
# === End NoemaForge Autodoc Function Header ===
def call(*, connector_id: str, method: str, params: Dict[str, Any], ctx: base.ConnectorContext) -> Tuple[bool, Dict[str, Any], str]:
    cid = str(connector_id or "").strip()
    if cid not in _REGISTRY:
        return False, {"ok": False, "reason": "connector_not_found"}, "connector_not_found"
    mod = _REGISTRY[cid]
    try:
        return mod.call(method=method, params=params, ctx=ctx)
    except Exception as e:
        return False, {"ok": False, "reason": "connector_exception"}, f"connector_exception:{e!r}"
