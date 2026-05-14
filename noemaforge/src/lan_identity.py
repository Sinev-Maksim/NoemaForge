#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/lan_identity.py
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
# File: src/lan_identity.py
# Purpose: Provide the module 'lan_identity'.
# Invoked by / imported from:
#   - src/localgateway.py
#   - src/nids_lite.py
# Public API / entry functions:
#   - norm_mac
#   - compute_device_uid
# Inputs:
#   - Imports: __future__, hashlib, json, re, typing
# Output formats / side effects:
#   - JSON files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""lan_identity.py (v0.15.0)

Stable device identity for Local Gateway / NIDS-lite.

Goal
----
- Produce SSID-independent stable identifiers for LAN devices.
- Prefer strong, stable fields when available (TLS pubkey hash, device cert, serial).
- Fallback to MAC when nothing else exists.

Design notes
------------
- This module is intentionally tiny and dependency-free.
- It is used by both LocalGateway and NIDS-lite to avoid drift.

Security
--------
- Only uses *fingerprints* (stable identifiers), never secrets.
"""


import hashlib
import json
import re
from typing import Any, Dict, List


# === NoemaForge Autodoc Function Header ===
# Function: norm_mac(mac: str, normalization: str = 'lower')
# Purpose: Implement the routine 'norm mac'.
# Inputs:
#   - mac: str
#   - normalization: str = 'lower'
# Called by:
#   - src/localgateway.py
#   - src/nids_lite.py
# Calls:
#   - strip, sub, lower
# Returns / emits: str
# Key locals:
#   - m
# === End NoemaForge Autodoc Function Header ===
def norm_mac(mac: str, normalization: str = "lower") -> str:
    m = (mac or "").strip()
    if normalization == "lower":
        m = m.lower()
    # Keep hex+colon only
    m = re.sub(r"[^0-9a-fA-F:]", "", m)
    return m


# === NoemaForge Autodoc Function Header ===
# Function: compute_device_uid(identity_policy: Dict[str, Any], fingerprint: Dict[str, Any])
# Purpose: Compute a stable device UID from fingerprint fields.
# Inputs:
#   - identity_policy: Dict[str, Any]
#   - fingerprint: Dict[str, Any]
# Called by:
#   - src/localgateway.py
#   - src/nids_lite.py
# Calls:
#   - str, strip, dumps, hexdigest, sorted, get, lower, list, sha256, norm_mac, keys, encode
# Returns / emits: str
# Side effects:
#   - serializes structured data
# Key locals:
#   - algo, canonical, fp, h, k, mac_norm, prefer, prefix, v
# === End NoemaForge Autodoc Function Header ===
def compute_device_uid(identity_policy: Dict[str, Any], fingerprint: Dict[str, Any]) -> str:
    """Compute a stable device UID from fingerprint fields.

    identity_policy keys (subset):
      - uid_prefix
      - uid_algorithm (sha256 only for now)
      - prefer_fields (ordered list)
      - mac_normalization
    """
    prefix = str(identity_policy.get("uid_prefix") or "lan:")
    algo = str(identity_policy.get("uid_algorithm") or "sha256").lower().strip()
    prefer: List[str] = [str(x) for x in (identity_policy.get("prefer_fields") or [])]
    mac_norm = str(identity_policy.get("mac_normalization") or "lower")

    fp: Dict[str, Any] = {}
    for k in prefer:
        if k in fingerprint and fingerprint.get(k):
            v = fingerprint.get(k)
            if k == "mac":
                v = norm_mac(str(v), mac_norm)
            fp[k] = v

    if not fp:
        # fallback: include any stable-ish key
        for k in sorted(list(fingerprint.keys())):
            v = fingerprint.get(k)
            if v:
                fp[k] = v
                break

    canonical = json.dumps(fp, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    if algo != "sha256":
        algo = "sha256"
    h = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return prefix + h
