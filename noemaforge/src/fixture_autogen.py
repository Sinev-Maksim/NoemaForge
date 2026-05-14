#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/fixture_autogen.py
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
# File: src/fixture_autogen.py
# Purpose: Provide the module 'fixture_autogen'.
# Invoked by / imported from:
#   - src/scary_sweep.py
#   - src/task_runner.py
# Public API / entry functions:
#   - fixture_from_incident
#   - fixtures_patch_for_fixture
#   - canonical_fixture_digest
# Inputs:
#   - Common path inputs: quarantine_slim/v1, noemaforge.security/v1
#   - Imports: __future__, hashlib, json, typing, quarantine_samples, os
# Output formats / side effects:
#   - JSON files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""fixture_autogen.py (v0.12.4)

Auto-generate *security fixtures* (canary scenarios) from repeated Incidents.

Important
---------
- This module produces **test inputs** for PRE-START canary execution.
- It does **not** run canaries at runtime.
- Fixtures are policy-layer checks (allow/deny at ToolProxy decision layer).

The goal is to shorten the loop:
  repeated incident -> fixture draft -> prestart request (draft) -> epoch change -> full canary

Security posture
---------------
- Avoid copying secrets into fixtures.
- Prefer structural reproduction: stream_id/role/action (+ bounded params if present).
"""


import hashlib
import json
from typing import Any, Dict, Optional, Tuple

# Optional: create sterile "slim" samples from quarantine snapshots.
try:  # pragma: no cover
    from quarantine_samples import maybe_store_quarantine_slim_sample
except Exception:  # pragma: no cover
    maybe_store_quarantine_slim_sample = None  # type: ignore


REDACT_KEYS = {
    "token",
    "password",
    "passwd",
    "secret",
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "oauth",
    "bearer",
    "key",
}


# === NoemaForge Autodoc Function Header ===
# Function: _sha256(s: str)
# Purpose: Implement the routine ' sha256'.
# Inputs:
#   - s: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - hexdigest, sha256, encode
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _sha256(s: str) -> str:
    return hashlib.sha256((s or "").encode("utf-8", errors="ignore")).hexdigest()


# === NoemaForge Autodoc Function Header ===
# Function: _truncate_str(s: str, max_len: int = 280)
# Purpose: Implement the routine ' truncate str'.
# Inputs:
#   - s: str
#   - max_len: int = 280
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - str, len
# Returns / emits: str
# Key locals:
#   - s2
# === End NoemaForge Autodoc Function Header ===
def _truncate_str(s: str, max_len: int = 280) -> str:
    if s is None:
        return ""
    s2 = str(s)
    if len(s2) <= max_len:
        return s2
    return s2[:max_len] + "…<truncated>"


# === NoemaForge Autodoc Function Header ===
# Function: _sanitize(value, depth: int = 0, max_depth: int = 3)
# Purpose: Implement the routine ' sanitize'.
# Inputs:
#   - value
#   - depth: int = 0
#   - max_depth: int = 3
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - isinstance, items, _truncate_str, str, _sanitize, lower
# Returns / emits: Any
# Side effects:
#   - spawns subprocesses or workers
# Key locals:
#   - ks, out
# === End NoemaForge Autodoc Function Header ===
def _sanitize(value: Any, *, depth: int = 0, max_depth: int = 3) -> Any:
    if depth > max_depth:
        return "<truncated_depth>"

    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for k, v in value.items():
            ks = str(k)
            if ks.lower() in REDACT_KEYS:
                out[ks] = "<redacted>"
            else:
                out[ks] = _sanitize(v, depth=depth + 1)
        return out

    if isinstance(value, list):
        # Bound lists to keep fixtures small and inspectable.
        return [_sanitize(x, depth=depth + 1) for x in value[:32]]

    if isinstance(value, str):
        return _truncate_str(value)

    return value


# === NoemaForge Autodoc Function Header ===
# Function: _find_quarantine_dir(incident_obj: Dict[str, Any])
# Purpose: Best-effort extraction of a quarantine_dir from an Incident object.
# Inputs:
#   - incident_obj: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - get, isinstance, strip, str, endswith, dirname
# Returns / emits: str
# Key locals:
#   - art, it, qd, rel
# === End NoemaForge Autodoc Function Header ===
def _find_quarantine_dir(incident_obj: Dict[str, Any]) -> str:
    """Best-effort extraction of a quarantine_dir from an Incident object."""

    if not isinstance(incident_obj, dict):
        return ""
    art = incident_obj.get("artifacts")
    if isinstance(art, dict):
        qd = str(art.get("quarantine_dir") or "").strip()
        if qd:
            return qd
    # Also search related artifacts
    rel = None
    if isinstance(art, dict):
        rel = art.get("related")
    if isinstance(rel, list):
        for it in rel:
            if not isinstance(it, dict):
                continue
            qd = str(it.get("quarantine_dir") or it.get("path") or "").strip()
            # Heuristic: if it looks like a directory and contains "quarantine".
            if qd and "/quarantine/" in qd:
                # If it's incident.json file, use its parent.
                if qd.endswith("incident.json"):
                    try:
                        import os

                        qd = os.path.dirname(qd)
                    except Exception:
                        pass
                return qd
    return ""


# === NoemaForge Autodoc Function Header ===
# Function: fixture_from_incident(incident_obj: Dict[str, Any], quarantine_sample_store_dir: str = '', pattern_catalog: Optional[Dict[str, Any]] = None)
# Purpose: Create a single SecurityFixture entry from an Incident object.
# Inputs:
#   - incident_obj: Dict[str, Any]
#   - quarantine_sample_store_dir: str = ''
#   - pattern_catalog: Optional[Dict[str, Any]] = None
# Called by:
#   - src/scary_sweep.py
#   - src/task_runner.py
# Calls:
#   - lower, strip, str, upper, isinstance, get, _sanitize, _truncate_str, setdefault, append, _find_quarantine_dir, _sha256
# Returns / emits: Optional[Dict[str, Any]]
# Side effects:
#   - spawns subprocesses or workers
#   - appends to logs or files
# Key locals:
#   - action, by_action, by_kind, details, fid, fixture, ik, inj, inj_map, pats, pc, qdir
# === End NoemaForge Autodoc Function Header ===
def fixture_from_incident(
    incident_obj: Dict[str, Any],
    *,
    quarantine_sample_store_dir: str = "",
    pattern_catalog: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Create a single SecurityFixture entry from an Incident object.

    Returns None if the incident does not have enough structure.
    """

    if not isinstance(incident_obj, dict):
        return None

    ik = str(incident_obj.get("incident_kind") or "").strip().lower()
    if not ik:
        # Best-effort fallback
        ik = str(incident_obj.get("kind") or "").strip().lower()
    if not ik:
        return None

    src = incident_obj.get("source") or {}
    if not isinstance(src, dict):
        src = {}

    stream_id = str(src.get("stream_id") or "").strip()
    role = str(src.get("role") or "").strip()

    details = incident_obj.get("details_last") or incident_obj.get("details") or {}
    if not isinstance(details, dict):
        details = {}
    action = str(details.get("action") or "").strip()

    if not (stream_id and role and action):
        return None

    # Stable-ish ID: dedupe_key hash if present, else incident_id.
    seed = str(incident_obj.get("dedupe_key") or incident_obj.get("incident_id") or action)
    fid = f"fx-auto-{ik}-{_sha256(seed)[:12]}"

    sev = str(incident_obj.get("severity") or "S2").strip().upper()
    title = str(incident_obj.get("title") or f"Incident: {ik}").strip()
    reason = str(details.get("reason") or "").strip()

    req: Dict[str, Any] = {"stream_id": stream_id, "role": role, "action": action}
    # Optional params (bounded + redacted) if present.
    if isinstance(details.get("params"), dict):
        req["params"] = _sanitize(details.get("params"))

    # Optional: carry a safe injection payload template (non-secret) so the fixture
    # can evolve beyond policy-layer evaluation in future epochs.
    inj = ""
    try:
        pc = pattern_catalog or {}
        pats = pc.get("patterns") if isinstance(pc, dict) else None
        sec = (pats or {}).get("security_fixtures") if isinstance(pats, dict) else None
        tmpl = (sec or {}).get("templates") if isinstance(sec, dict) else None
        inj_map = (tmpl or {}).get("injection_payloads") if isinstance(tmpl, dict) else None
        by_kind = (inj_map or {}).get("by_kind") if isinstance(inj_map, dict) else None
        by_action = (inj_map or {}).get("by_action") if isinstance(inj_map, dict) else None

        # Prefer kind-specific template, then action-specific, then default.
        if isinstance(by_kind, dict):
            inj = str(by_kind.get(ik) or "")
        if not inj and isinstance(by_action, dict):
            inj = str(by_action.get(action) or "")
        if not inj and isinstance(inj_map, dict):
            inj = str(inj_map.get("default") or "")
    except Exception:
        inj = ""

    fixture: Dict[str, Any] = {
        "id": fid,
        "category": f"auto_incident/{ik}",
        "description": _truncate_str(f"[{sev}] {title} ({reason or 'no_reason'})"),
        "injection_payload": _truncate_str(inj, 500) if inj else "",
        "request": req,
        "expected": {"decision": "deny" if "allow" not in ik else "allow"},
        "source_incident": {
            "incident_id": str(incident_obj.get("incident_id") or ""),
            "dedupe_key": _truncate_str(str(incident_obj.get("dedupe_key") or ""), 200),
        },
    }

    # NOTE: In this seed kit, fixtures evaluate allow/deny only.
    # Quarantine is modeled as "must not allow" and evaluated as deny.
    if "quarantine" in ik:
        fixture["expected"]["decision"] = "deny"
        fixture.setdefault("notes", [])
        fixture["notes"].append("autogen_from_quarantine: pre-start fixture models quarantine as deny")

    # If this incident links to a quarantine snapshot, store a *slim* sample signature
    # and attach only its hash reference (no raw content) for future canary evolution.
    try:
        qdir = _find_quarantine_dir(incident_obj)
        if qdir and maybe_store_quarantine_slim_sample is not None:
            store_dir = (quarantine_sample_store_dir or "").strip()
            if store_dir:
                ref = maybe_store_quarantine_slim_sample(quarantine_dir=qdir, store_dir=store_dir)
            else:
                ref = None
            if isinstance(ref, dict) and str(ref.get("sha256") or "").strip():
                fixture["sample_ref"] = {
                    "kind": str(ref.get("kind") or "quarantine_slim/v1"),
                    "sha256": str(ref.get("sha256") or ""),
                }
                fixture.setdefault("notes", [])
                fixture["notes"].append("quarantine_slim_sample: stored structural signature (hash-only reference) for this fixture")
    except Exception:
        pass

    return fixture


# === NoemaForge Autodoc Function Header ===
# Function: fixtures_patch_for_fixture(fixture: Dict[str, Any])
# Purpose: Build a deep-merge friendly patch for security-fixtures.yaml.
# Inputs:
#   - fixture: Dict[str, Any]
# Called by:
#   - src/scary_sweep.py
# Returns / emits: Dict[str, Any]
# === End NoemaForge Autodoc Function Header ===
def fixtures_patch_for_fixture(fixture: Dict[str, Any]) -> Dict[str, Any]:
    """Build a deep-merge friendly patch for security-fixtures.yaml."""
    # Keep top-level keys to avoid accidental schema drift.
    return {
        "apiVersion": "noemaforge.security/v1",
        "kind": "SecurityFixtures",
        "fixtures": [fixture],
    }


# === NoemaForge Autodoc Function Header ===
# Function: canonical_fixture_digest(fixture: Dict[str, Any])
# Purpose: Canonical digest used for dedupe across request creation.
# Inputs:
#   - fixture: Dict[str, Any]
# Called by:
#   - src/scary_sweep.py
#   - src/task_runner.py
# Calls:
#   - _sha256, dumps, str
# Returns / emits: str
# Side effects:
#   - serializes structured data
# Key locals:
#   - blob
# === End NoemaForge Autodoc Function Header ===
def canonical_fixture_digest(fixture: Dict[str, Any]) -> str:
    """Canonical digest used for dedupe across request creation."""
    try:
        blob = json.dumps(fixture, ensure_ascii=False, sort_keys=True)
    except Exception:
        blob = str(fixture)
    return _sha256(blob)
