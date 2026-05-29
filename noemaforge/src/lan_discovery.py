#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/lan_discovery.py
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
# File: src/lan_discovery.py
# Purpose: Provide the module 'lan_discovery'.
# Invoked by / imported from:
#   - src/localgateway.py
#   - src/nids_lite.py
# Public API / entry functions:
#   - parse_ip_neigh
#   - ip_addr_show
#   - ip_route_show
#   - ss_listeners
# Inputs:
#   - Imports: __future__, subprocess, typing
# Output formats / side effects:
#   - Returns Python values and/or performs in-memory orchestration.
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""lan_discovery.py (v0.15.0)

Best-effort LAN discovery primitives.

We deliberately avoid active scanning by default:
- no mass port scans
- no raw sockets
- rely on OS neighbor tables and interface state

Used by:
- localgateway.py (preflight/discover)
- nids_lite.py (monitoring snapshots)

All commands are best-effort: failures should not crash the system.
"""


import subprocess
from typing import Any, Dict, List


# === NoemaForge Autodoc Function Header ===
# Function: parse_ip_neigh()
# Purpose: Parse `ip neigh` output.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - src/localgateway.py
#   - src/nids_lite.py
# Calls:
#   - run, splitlines, strip, split, append, index
# Returns / emits: List[Dict[str, Any]]
# Side effects:
#   - spawns subprocesses or workers
#   - appends to logs or files
# Key locals:
#   - iface, ip, ln, mac, out, p, parts, state, txt
# === End NoemaForge Autodoc Function Header ===
def parse_ip_neigh() -> List[Dict[str, Any]]:
    """Parse `ip neigh` output.

    Returns dicts:
      - ip
      - iface
      - mac
      - state
      - source
    """
    out: List[Dict[str, Any]] = []
    try:
        p = subprocess.run(["ip", "neigh"], check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        txt = p.stdout or ""
        for ln in txt.splitlines():
            ln = ln.strip()
            if not ln:
                continue
            parts = ln.split()
            ip = parts[0] if parts else ""
            iface = ""
            mac = ""
            state = parts[-1] if parts else ""
            if "dev" in parts:
                try:
                    iface = parts[parts.index("dev") + 1]
                except Exception:
                    pass
            if "lladdr" in parts:
                try:
                    mac = parts[parts.index("lladdr") + 1]
                except Exception:
                    pass
            out.append({"ip": ip, "iface": iface, "mac": mac, "state": state, "source": "ip_neigh"})
    except Exception:
        return out
    return out


# === NoemaForge Autodoc Function Header ===
# Function: ip_addr_show()
# Purpose: Implement the routine 'ip addr show'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - src/nids_lite.py
# Calls:
#   - run
# Returns / emits: str
# Side effects:
#   - spawns subprocesses or workers
# Key locals:
#   - p
# === End NoemaForge Autodoc Function Header ===
def ip_addr_show() -> str:
    try:
        p = subprocess.run(["ip", "addr", "show"], check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return p.stdout or ""
    except Exception:
        return ""


# === NoemaForge Autodoc Function Header ===
# Function: ip_route_show()
# Purpose: Implement the routine 'ip route show'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - src/nids_lite.py
# Calls:
#   - run
# Returns / emits: str
# Side effects:
#   - spawns subprocesses or workers
# Key locals:
#   - p
# === End NoemaForge Autodoc Function Header ===
def ip_route_show() -> str:
    try:
        p = subprocess.run(["ip", "route", "show"], check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return p.stdout or ""
    except Exception:
        return ""


# === NoemaForge Autodoc Function Header ===
# Function: ss_listeners()
# Purpose: Best-effort listening sockets snapshot.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - src/nids_lite.py
# Calls:
#   - run
# Returns / emits: str
# Side effects:
#   - spawns subprocesses or workers
# Key locals:
#   - p
# === End NoemaForge Autodoc Function Header ===
def ss_listeners() -> str:
    """Best-effort listening sockets snapshot."""
    try:
        p = subprocess.run(["ss", "-H", "-tunlp"], check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return p.stdout or ""
    except Exception:
        return ""
