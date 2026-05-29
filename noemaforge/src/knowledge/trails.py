#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/knowledge/trails.py
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
# File: src/knowledge/trails.py
# Purpose: Implement the knowledge subsystem module 'trails'.
# Invoked by / imported from:
#   - src/brainctl.py
# Public API / entry functions:
#   - execute_trail
# Inputs:
#   - Imports: __future__, typing, store, retrieval
# Output formats / side effects:
#   - Returns Python values and/or performs in-memory orchestration.
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""knowledge.trails (v0.16.0)

Trail execution (context pack builder).

A Trail is an "executable route" through the hypergraph.
For an MVP we treat execution as:
- load trail record
- load ordered steps
- resolve referenced node objects (Concept/Claim/Passage/Conflict/Source)

Later versions may enforce gates (confidence/conflicts) and realm bridges.
"""


from typing import Any, Dict, List, Tuple

from .store import KnowledgeStore
from .retrieval import gate_decision_for, _gate_allows


# === NoemaForge Autodoc Function Header ===
# Function: execute_trail(store: KnowledgeStore, trail_id: str, max_nodes: int = 200, min_decision: str = '', include_gate: bool = False)
# Purpose: Implement the routine 'execute trail'.
# Inputs:
#   - store: KnowledgeStore
#   - trail_id: str
#   - max_nodes: int = 200
#   - min_decision: str = ''
#   - include_gate: bool = False
# Called by:
#   - src/brainctl.py
# Calls:
#   - fetch_by_ids, list_trail_steps, list, items, lower, strip, keys, get, isinstance, append, gate_decision_for, _gate_allows
# Returns / emits: Dict[str, Any]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - by_kind, dec, dropped, gated_out, k, kept, kind, mapping, oid, r, ref, resolved
# === End NoemaForge Autodoc Function Header ===
def execute_trail(
    store: KnowledgeStore,
    *,
    trail_id: str,
    max_nodes: int = 200,
    min_decision: str = "",
    include_gate: bool = False,
) -> Dict[str, Any]:
    trail_rows = store.fetch_by_ids("trails", [trail_id])
    if not trail_rows:
        return {"ok": False, "reason": "trail_not_found"}

    steps = store.list_trail_steps(trail_id)

    # Collect node refs by kind
    by_kind: Dict[str, List[str]] = {}
    for s in steps:
        ref = s.get("node_ref") or {}
        if not isinstance(ref, dict):
            continue
        kind = str(ref.get("kind") or "").strip().lower()
        rid = str(ref.get("id") or "").strip()
        if kind and rid:
            by_kind.setdefault(kind, []).append(rid)

    # Deduplicate + cap
    for k in list(by_kind.keys()):
        seen = []
        for rid in by_kind[k]:
            if rid not in seen:
                seen.append(rid)
        by_kind[k] = seen[:max_nodes]

    resolved: Dict[str, Any] = {}

    # Map kinds to tables
    mapping = {
        "source": "sources",
        "passage": "passages",
        "concept": "concepts",
        "claim": "claims",
        "conflict": "conflicts",
        "realm": "realms",
        "bridge": "realm_bridges",
    }

    gated_out: Dict[str, List[str]] = {}
    for kind, ids in by_kind.items():
        table = mapping.get(kind)
        if not table:
            continue
        rows = store.fetch_by_ids(table, ids)
        if not str(min_decision or "").strip() or kind not in ("passage", "claim", "concept", "conflict"):
            resolved[kind] = rows
            continue

        kept = []
        dropped = []
        for r in rows:
            oid = str(r.get(f"{kind}_id") or r.get("passage_id") or r.get("claim_id") or r.get("concept_id") or r.get("conflict_id") or "").strip()
            if not oid:
                kept.append(r)
                continue
            dec = gate_decision_for(store, object_kind=kind, object_id=oid)
            if include_gate:
                r["gate"] = {"decision": dec}
            if _gate_allows(decision=dec, min_decision=min_decision):
                kept.append(r)
            else:
                dropped.append(oid)
        resolved[kind] = kept
        if dropped:
            gated_out[kind] = dropped

    return {
        "ok": True,
        "trail": trail_rows[0],
        "steps": steps,
        "resolved": resolved,
        "min_decision": str(min_decision or "").strip(),
        "gated_out": gated_out,
    }
