#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/knowledge/gatekeeper.py
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
# File: src/knowledge/gatekeeper.py
# Purpose: Implement the knowledge subsystem module 'gatekeeper'.
# Invoked by / imported from:
#   - src/knowledge_maintainer.py
# Public API / entry functions:
#   - check_passage
#   - check_claim
#   - check_conflict
#   - check_concept
#   - run_gatekeeper
# Inputs:
#   - Imports: __future__, json, sqlite3, typing, store
# Output formats / side effects:
#   - SQLite databases
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""knowledge.gatekeeper (v0.17.0)

Invariant checks + publication gates for the hypergraph store.

We keep this as a separate worker because:
  - ingestion should be fast
  - enforcement is policy-driven
  - we want explainable reports (what failed, why)

Outputs are written to KnowledgeStore.gate_reports.
"""


import json
import sqlite3
from typing import Any, Dict, List, Tuple

from .store import KnowledgeStore


AUTO_PUBLISH_MIN_CONFIDENCE = 0.85
ALLOWED_CONFLICT_STATUSES = {"A_true", "B_true", "Unresolved"}


# === NoemaForge Autodoc Function Header ===
# Function: _as_list(v)
# Purpose: Implement the routine ' as list'.
# Inputs:
#   - v
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - isinstance
# Returns / emits: List[Any]
# === End NoemaForge Autodoc Function Header ===
def _as_list(v: Any) -> List[Any]:
    if isinstance(v, list):
        return v
    return []


# === NoemaForge Autodoc Function Header ===
# Function: _decision(violations: List[Dict[str, Any]])
# Purpose: Implement the routine ' decision'.
# Inputs:
#   - violations: List[Dict[str, Any]]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - lower, str, get
# Returns / emits: Tuple[str, str]
# Key locals:
#   - sev, v
# === End NoemaForge Autodoc Function Header ===
def _decision(violations: List[Dict[str, Any]]) -> Tuple[str, str]:
    if not violations:
        return "auto_publish", "ok"
    sev = "warning"
    for v in violations:
        if str(v.get("severity") or "").lower() in ("critical", "high"):
            sev = "critical"
            break
    if sev == "critical":
        return "quarantine", sev
    return "review", sev


# === NoemaForge Autodoc Function Header ===
# Function: check_passage(row: Dict[str, Any], source_exists: bool)
# Purpose: Implement the routine 'check passage'.
# Inputs:
#   - row: Dict[str, Any]
#   - source_exists: bool
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - str, append, strip, loads, get, isinstance
# Returns / emits: List[Dict[str, Any]]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - aj, txt, v
# === End NoemaForge Autodoc Function Header ===
def check_passage(row: Dict[str, Any], *, source_exists: bool) -> List[Dict[str, Any]]:
    v: List[Dict[str, Any]] = []
    if not source_exists:
        v.append({"code": "passage_missing_source", "severity": "critical"})
    txt = str(row.get("text") or "")
    if not txt.strip():
        v.append({"code": "passage_missing_text", "severity": "warning"})
    try:
        aj = json.loads(str(row.get("anchor_json") or "{}"))
        if not isinstance(aj, dict) or not aj.get("kind"):
            v.append({"code": "passage_bad_anchor", "severity": "warning"})
    except Exception:
        v.append({"code": "passage_anchor_not_json", "severity": "warning"})
    return v


# === NoemaForge Autodoc Function Header ===
# Function: check_claim(row: Dict[str, Any])
# Purpose: Implement the routine 'check claim'.
# Inputs:
#   - row: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - loads, _as_list, append, strip, str, get
# Returns / emits: List[Dict[str, Any]]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - pids, v
# === End NoemaForge Autodoc Function Header ===
def check_claim(row: Dict[str, Any]) -> List[Dict[str, Any]]:
    v: List[Dict[str, Any]] = []
    try:
        pids = json.loads(str(row.get("extracted_from_passages_json") or "[]"))
    except Exception:
        pids = []
    if not _as_list(pids):
        v.append({"code": "claim_no_passage", "severity": "critical"})
    if not str(row.get("text_normalized") or "").strip():
        v.append({"code": "claim_missing_text", "severity": "warning"})
    try:
        confidence = float(row.get("confidence") or 0.0)
    except Exception:
        confidence = 0.0
    if confidence < AUTO_PUBLISH_MIN_CONFIDENCE:
        v.append({"code": "claim_confidence_below_auto_publish", "severity": "warning", "min_confidence": AUTO_PUBLISH_MIN_CONFIDENCE})
    # Realm context is allowed to be empty for now (some sources are realm-less).
    return v


# === NoemaForge Autodoc Function Header ===
# Function: check_conflict(row: Dict[str, Any])
# Purpose: Implement the routine 'check conflict'.
# Inputs:
#   - row: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - strip, append, str, get
# Returns / emits: List[Dict[str, Any]]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - rc, st, v
# === End NoemaForge Autodoc Function Header ===
def check_conflict(row: Dict[str, Any]) -> List[Dict[str, Any]]:
    v: List[Dict[str, Any]] = []
    if not str(row.get("entity_a") or "").strip() or not str(row.get("entity_b") or "").strip():
        v.append({"code": "conflict_missing_entities", "severity": "critical"})
    st = str(row.get("status") or "").strip()
    if st and st not in ALLOWED_CONFLICT_STATUSES:
        v.append({"code": "conflict_bad_status", "severity": "warning", "value": st})
    rc = str(row.get("realm_context_json") or "").strip()
    try:
        realm_context = json.loads(rc or "{}")
    except Exception:
        realm_context = {}
    if not realm_context:
        v.append({"code": "conflict_missing_realm", "severity": "critical"})
    return v


# === NoemaForge Autodoc Function Header ===
# Function: check_concept(row: Dict[str, Any])
# Purpose: Basic sanity checks for Concept objects.
# Inputs:
#   - row: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - loads, strip, append, str, _as_list, get
# Returns / emits: List[Dict[str, Any]]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - labels, labels_list, v
# === End NoemaForge Autodoc Function Header ===
def check_concept(row: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Basic sanity checks for Concept objects.

    Concepts are foundational navigation nodes. If a concept has no labels,
    it is effectively unusable and should be quarantined.
    """

    v: List[Dict[str, Any]] = []
    try:
        labels = json.loads(str(row.get("labels_json") or "[]"))
    except Exception:
        labels = []
    labels_list = [str(x).strip() for x in _as_list(labels) if str(x).strip()]
    if not labels_list:
        v.append({"code": "concept_missing_labels", "severity": "critical"})
    return v


# === NoemaForge Autodoc Function Header ===
# Function: run_gatekeeper(store: KnowledgeStore, limit_each: int = 500)
# Purpose: Scan recent objects and write gate reports.
# Inputs:
#   - store: KnowledgeStore
#   - limit_each: int = 500
# Called by:
#   - src/knowledge_maintainer.py
# Calls:
#   - connect, cursor, execute, fetchall, close, str, dict, check_passage, _decision, upsert_gate_report, check_claim, check_conflict
# Returns / emits: Dict[str, Any]
# Side effects:
#   - opens a database or socket connection
#   - executes SQL or shell-like commands
# Key locals:
#   - cid, con, counts, cur, fid, pid, r, row, sources, viol
# === End NoemaForge Autodoc Function Header ===
def run_gatekeeper(
    store: KnowledgeStore,
    *,
    limit_each: int = 500,
) -> Dict[str, Any]:
    """Scan recent objects and write gate reports."""

    con = sqlite3.connect(store.db_path)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    # Sources lookup for passage checks.
    cur.execute("SELECT source_id FROM sources")
    sources = {str(r[0]) for r in cur.fetchall()}

    counts = {"passages": 0, "claims": 0, "conflicts": 0, "concepts": 0, "auto_publish": 0, "review": 0, "quarantine": 0}

    # Passages
    cur.execute(
        "SELECT passage_id, source_id, anchor_json, text, realm_override, created_at FROM passages ORDER BY created_at DESC LIMIT ?",
        (int(limit_each),),
    )
    for r in cur.fetchall():
        row = dict(r)
        pid = str(row.get("passage_id") or "")
        if not pid:
            continue
        viol = check_passage(row, source_exists=str(row.get("source_id") or "") in sources)
        dec, sev = _decision(viol)
        store.upsert_gate_report(object_kind="passage", object_id=pid, decision=dec, severity=sev, violations=viol)
        counts["passages"] += 1
        counts[dec] += 1

    # Claims
    cur.execute(
        "SELECT claim_id, text_normalized, extracted_from_passages_json, realm_context_json, status, confidence, created_at FROM claims ORDER BY created_at DESC LIMIT ?",
        (int(limit_each),),
    )
    for r in cur.fetchall():
        row = dict(r)
        cid = str(row.get("claim_id") or "")
        if not cid:
            continue
        viol = check_claim(row)
        dec, sev = _decision(viol)
        store.upsert_gate_report(object_kind="claim", object_id=cid, decision=dec, severity=sev, violations=viol)
        counts["claims"] += 1
        counts[dec] += 1

    # Conflicts
    cur.execute(
        "SELECT conflict_id, entity_a, entity_b, incompatibility_type, realm_context_json, status, confidence, created_at FROM conflicts ORDER BY created_at DESC LIMIT ?",
        (int(limit_each),),
    )
    for r in cur.fetchall():
        row = dict(r)
        fid = str(row.get("conflict_id") or "")
        if not fid:
            continue
        viol = check_conflict(row)
        dec, sev = _decision(viol)
        store.upsert_gate_report(object_kind="conflict", object_id=fid, decision=dec, severity=sev, violations=viol)
        counts["conflicts"] += 1
        counts[dec] += 1

    # Concepts
    cur.execute(
        "SELECT concept_id, labels_json, realms_json, realm_scope, introduced_in, created_at FROM concepts ORDER BY created_at DESC LIMIT ?",
        (int(limit_each),),
    )
    for r in cur.fetchall():
        row = dict(r)
        cid = str(row.get("concept_id") or "")
        if not cid:
            continue
        viol = check_concept(row)
        dec, sev = _decision(viol)
        store.upsert_gate_report(object_kind="concept", object_id=cid, decision=dec, severity=sev, violations=viol)
        counts["concepts"] += 1
        counts[dec] += 1

    con.close()
    return {"ok": True, "counts": counts}
