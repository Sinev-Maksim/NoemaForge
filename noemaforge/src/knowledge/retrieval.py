#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/knowledge/retrieval.py
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
# File: src/knowledge/retrieval.py
# Purpose: Implement the knowledge subsystem module 'retrieval'.
# Invoked by / imported from:
#   - src/brainctl.py
#   - src/knowledge/__init__.py
#   - src/knowledge/trails.py
# Public API / entry functions:
#   - gate_decision_for
#   - search_keyword
#   - search_semantic
# Inputs:
#   - Imports: __future__, sqlite3, typing, store, vstore
# Output formats / side effects:
#   - SQLite databases
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""knowledge.retrieval (v0.16.0)

Retrieval helpers for the hypergraph store.

Two modes:
- Keyword search (SQLite LIKE) — good for IDs/names.
- Semantic search (VStore) — good for topic similarity.

Important: semantic similarity != logical agreement.
Contradictions are represented explicitly with Conflict objects.
"""


import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from .store import KnowledgeStore

try:
    from vstore import VStore
except Exception:  # pragma: no cover
    VStore = None  # type: ignore


_DECISION_RANK = {
    "quarantine": 0,
    "review": 1,
    "auto_publish": 2,
}


# === NoemaForge Autodoc Function Header ===
# Function: _rank(decision: str)
# Purpose: Implement the routine ' rank'.
# Inputs:
#   - decision: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - get, lower, strip, str
# Returns / emits: int
# === End NoemaForge Autodoc Function Header ===
def _rank(decision: str) -> int:
    return _DECISION_RANK.get(str(decision or "").strip().lower(), 1)


# === NoemaForge Autodoc Function Header ===
# Function: gate_decision_for(store: KnowledgeStore, object_kind: str, object_id: str)
# Purpose: Return gate decision for an object.
# Inputs:
#   - store: KnowledgeStore
#   - object_kind: str
#   - object_id: str
# Called by:
#   - src/knowledge/trails.py
# Calls:
#   - get_gate_report, lower, str, strip, get
# Returns / emits: str
# Key locals:
#   - dec, rep
# === End NoemaForge Autodoc Function Header ===
def gate_decision_for(store: KnowledgeStore, *, object_kind: str, object_id: str) -> str:
    """Return gate decision for an object.

    Missing gate reports are treated as "review" (safe default).
    """

    rep = store.get_gate_report(object_kind=str(object_kind), object_id=str(object_id))
    dec = str((rep or {}).get("decision") or "").strip().lower()
    return dec if dec else "review"


# === NoemaForge Autodoc Function Header ===
# Function: _gate_allows(decision: str, min_decision: str)
# Purpose: Implement the routine ' gate allows'.
# Inputs:
#   - decision: str
#   - min_decision: str
# Called by:
#   - src/knowledge/trails.py
# Calls:
#   - strip, _rank, str
# Returns / emits: bool
# === End NoemaForge Autodoc Function Header ===
def _gate_allows(*, decision: str, min_decision: str) -> bool:
    if not str(min_decision or "").strip():
        return True
    return _rank(decision) >= _rank(min_decision)


# === NoemaForge Autodoc Function Header ===
# Function: search_keyword(store: KnowledgeStore, q: str, limit: int = 20, min_decision: str = '', include_gate: bool = False)
# Purpose: Implement the routine 'search keyword'.
# Inputs:
#   - store: KnowledgeStore
#   - q: str
#   - limit: int = 20
#   - min_decision: str = ''
#   - include_gate: bool = False
# Called by:
#   - src/brainctl.py
# Calls:
#   - strip, connect, cursor, execute, fetchall, close, lower, gate_decision_for, _gate_allows, str, append, int
# Returns / emits: Dict[str, Any]
# Side effects:
#   - opens a database or socket connection
#   - executes SQL or shell-like commands
#   - appends to logs or files
# Key locals:
#   - con, cur, dec, filtered_out, gated, kind, like, oid, out, q2, r
# === End NoemaForge Autodoc Function Header ===
def search_keyword(
    store: KnowledgeStore,
    *,
    q: str,
    limit: int = 20,
    min_decision: str = "",
    include_gate: bool = False,
) -> Dict[str, Any]:
    q2 = str(q or "").strip()
    if not q2:
        return {"ok": True, "q": q2, "results": []}

    con = sqlite3.connect(store.db_path)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    like = f"%{q2}%"

    out: List[Dict[str, Any]] = []

    try:
        cur.execute("SELECT concept_id, labels_json, realms_json FROM concepts WHERE labels_json LIKE ? LIMIT ?", (like, int(limit)))
        for r in cur.fetchall():
            out.append({"kind": "concept", **dict(r)})

        cur.execute("SELECT claim_id, text_normalized, status, confidence FROM claims WHERE text_normalized LIKE ? LIMIT ?", (like, int(limit)))
        for r in cur.fetchall():
            out.append({"kind": "claim", **dict(r)})

        cur.execute("SELECT passage_id, source_id, substr(text, 1, 300) as preview FROM passages WHERE text LIKE ? LIMIT ?", (like, int(limit)))
        for r in cur.fetchall():
            out.append({"kind": "passage", **dict(r)})

    finally:
        con.close()

    # Gate-aware filtering (default: hide review/quarantine if configured by caller).
    gated: List[Dict[str, Any]] = []
    filtered_out = 0
    for r in out:
        kind = str(r.get("kind") or "").strip().lower()
        oid = str(r.get(f"{kind}_id") or r.get("passage_id") or r.get("claim_id") or r.get("concept_id") or "").strip()
        if not kind or not oid:
            filtered_out += 1
            continue
        dec = gate_decision_for(store, object_kind=kind, object_id=oid)
        if include_gate:
            r["gate"] = {"decision": dec}
        if _gate_allows(decision=dec, min_decision=min_decision):
            gated.append(r)
        else:
            filtered_out += 1

    return {
        "ok": True,
        "q": q2,
        "min_decision": str(min_decision or "").strip(),
        "filtered_out": filtered_out,
        "results": gated[: int(limit)],
    }


# === NoemaForge Autodoc Function Header ===
# Function: search_semantic(vstore, store: Optional[KnowledgeStore] = None, layer: str, vector: List[float], model_id: str, dims: int, topk: int = 10, filters: Optional[Dict[str, Any]] = None, min_decision: str = '')
# Purpose: Implement the routine 'search semantic'.
# Inputs:
#   - vstore
#   - store: Optional[KnowledgeStore] = None
#   - layer: str
#   - vector: List[float]
#   - model_id: str
#   - dims: int
#   - topk: int = 10
#   - filters: Optional[Dict[str, Any]] = None
#   - min_decision: str = ''
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - hasattr, isinstance, query, get, strip, int, str, lower, gate_decision_for, _gate_allows, append
# Returns / emits: Dict[str, Any]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - dec, filtered_out, kept, m, matches, meta, oid, okind, rep
# === End NoemaForge Autodoc Function Header ===
def search_semantic(
    vstore: Any,
    *,
    store: Optional[KnowledgeStore] = None,
    layer: str,
    vector: List[float],
    model_id: str,
    dims: int,
    topk: int = 10,
    filters: Optional[Dict[str, Any]] = None,
    min_decision: str = "",
) -> Dict[str, Any]:
    if VStore is None:
        return {"ok": False, "reason": "vstore_unavailable"}
    if not isinstance(vector, list) or not vector:
        return {"ok": False, "reason": "missing_vector"}

    try:
        # VStore API (preferred): query(vector, dims, model_id, top_k, filters)
        if hasattr(vstore, "query"):
            rep = vstore.query(vector=vector, dims=int(dims), model_id=str(model_id), top_k=int(topk), filters=(filters or {}))
            if not isinstance(rep, dict):
                return {"ok": False, "reason": "bad_vstore_response"}
            if not rep.get("ok", True):
                return {"ok": False, "reason": "vstore_query_failed", "detail": rep}
            matches = rep.get("matches") or []
            if store is not None and str(min_decision or "").strip():
                kept = []
                filtered_out = 0
                for m in matches:
                    try:
                        meta = (m or {}).get("meta") or {}
                        okind = str(meta.get("object_kind") or "").strip().lower()
                        oid = str(meta.get("object_id") or "").strip()
                        if not okind or not oid:
                            kept.append(m)
                            continue
                        dec = gate_decision_for(store, object_kind=okind, object_id=oid)
                        meta["gate"] = {"decision": dec}
                        if _gate_allows(decision=dec, min_decision=min_decision):
                            kept.append(m)
                        else:
                            filtered_out += 1
                    except Exception:
                        kept.append(m)
                return {
                    "ok": True,
                    "layer": layer,
                    "topk": int(topk),
                    "min_decision": str(min_decision or "").strip(),
                    "filtered_out": filtered_out,
                    "matches": kept,
                }
            return {"ok": True, "layer": layer, "topk": int(topk), "matches": matches}
        return {"ok": False, "reason": "vstore_missing_query"}
    except Exception as e:
        return {"ok": False, "reason": "semantic_search_error", "error": str(e)}
