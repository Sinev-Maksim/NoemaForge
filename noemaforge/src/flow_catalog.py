#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/flow_catalog.py
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
# File: src/flow_catalog.py
# Purpose: Provide the module 'flow_catalog'.
# Invoked by / imported from:
#   - src/team_search.py
# Public API / entry functions:
#   - load_flow_catalog
#   - get_flow
#   - list_flow_ids
#   - flow_nodes
#   - role_chain
# Inputs:
#   - Common path inputs: noemaforge.flows/v1
#   - Imports: __future__, os, typing, yaml
# Output formats / side effects:
#   - YAML files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""flow_catalog.py (v0.11.6)

Flow catalog: stream-independent description of "how the team works".

In NoemaForge:
  - StreamCatalog (streams.yaml) = environment policy: resources + access.
  - FlowCatalog (flow-catalog.yaml) = logical pipeline: nodes/roles order.

Roles are future-proofed for specialization:
  dev -> dev.python -> dev.python.sql

We represent specialization using dots '.' (not '/') to avoid ambiguity
with keys formatted as <stream>/<role>.
"""


import os
from typing import Any, Dict, List, Optional

import yaml


# === NoemaForge Autodoc Function Header ===
# Function: load_flow_catalog(epoch_dir: str)
# Purpose: Implement the routine 'load flow catalog'.
# Inputs:
#   - epoch_dir: str
# Called by:
#   - src/team_search.py
# Calls:
#   - join, exists, isinstance, open, safe_load
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads or writes files
# Key locals:
#   - f, obj, path
# === End NoemaForge Autodoc Function Header ===
def load_flow_catalog(epoch_dir: str) -> Dict[str, Any]:
    path = os.path.join(epoch_dir, "flow-catalog.yaml")
    if not os.path.exists(path):
        return {"apiVersion": "noemaforge.flows/v1", "kind": "FlowCatalog", "flows": {}}
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = yaml.safe_load(f) or {}
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    return {"apiVersion": "noemaforge.flows/v1", "kind": "FlowCatalog", "flows": {}}


# === NoemaForge Autodoc Function Header ===
# Function: get_flow(doc: Dict[str, Any], flow_id: str)
# Purpose: Implement the routine 'get flow'.
# Inputs:
#   - doc: Dict[str, Any]
#   - flow_id: str
# Called by:
#   - src/team_search.py
# Calls:
#   - isinstance, get
# Returns / emits: Dict[str, Any]
# Key locals:
#   - f, flows
# === End NoemaForge Autodoc Function Header ===
def get_flow(doc: Dict[str, Any], flow_id: str) -> Dict[str, Any]:
    flows = doc.get("flows") or {}
    if isinstance(flows, dict):
        f = flows.get(flow_id) or {}
        if isinstance(f, dict):
            return f
    return {}


# === NoemaForge Autodoc Function Header ===
# Function: list_flow_ids(doc: Dict[str, Any])
# Purpose: Implement the routine 'list flow ids'.
# Inputs:
#   - doc: Dict[str, Any]
# Called by:
#   - src/team_search.py
# Calls:
#   - sorted, get, isinstance, str, keys
# Returns / emits: List[str]
# Key locals:
#   - flows
# === End NoemaForge Autodoc Function Header ===
def list_flow_ids(doc: Dict[str, Any]) -> List[str]:
    flows = doc.get("flows") or {}
    if not isinstance(flows, dict):
        return []
    return sorted([str(k) for k in flows.keys()])


# === NoemaForge Autodoc Function Header ===
# Function: flow_nodes(flow: Dict[str, Any])
# Purpose: Implement the routine 'flow nodes'.
# Inputs:
#   - flow: Dict[str, Any]
# Called by:
#   - src/team_search.py
# Calls:
#   - isinstance, get, append, dict
# Returns / emits: List[Dict[str, Any]]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - n, nodes, out
# === End NoemaForge Autodoc Function Header ===
def flow_nodes(flow: Dict[str, Any]) -> List[Dict[str, Any]]:
    nodes = flow.get("nodes") or []
    out: List[Dict[str, Any]] = []
    if isinstance(nodes, list):
        for n in nodes:
            if isinstance(n, dict) and n.get("id") and n.get("role"):
                out.append(dict(n))
    return out


# === NoemaForge Autodoc Function Header ===
# Function: role_chain(role_id: str)
# Purpose: Return role_id ancestry chain for specialization.
# Inputs:
#   - role_id: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - strip, split, range, set, len, append, str, join, add
# Returns / emits: List[str]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - final, i, out, parts, r, seen, x
# === End NoemaForge Autodoc Function Header ===
def role_chain(role_id: str) -> List[str]:
    """Return role_id ancestry chain for specialization.

    Example:
      dev.python.sql -> ["dev.python.sql", "dev.python", "dev"]
    """
    r = str(role_id or "").strip()
    if not r:
        return []
    parts = r.split(".")
    out: List[str] = []
    for i in range(len(parts), 0, -1):
        out.append(".".join(parts[:i]))
    # Keep unique in order
    seen = set()
    final: List[str] = []
    for x in out:
        if x not in seen:
            seen.add(x)
            final.append(x)
    return final
