#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/knowledge/vector_index.py
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
# File: src/knowledge/vector_index.py
# Purpose: Implement the knowledge subsystem module 'vector_index'.
# Invoked by / imported from:
#   - No inbound Python import detected; treat as library leaf or direct entrypoint.
# Public API / entry functions:
#   - upsert_embedding
# Inputs:
#   - Imports: __future__, typing
# Output formats / side effects:
#   - Returns Python values and/or performs in-memory orchestration.
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""knowledge.vector_index (v0.17.0)

Thin, correct wrapper around VStore for KG objects.

Notes
-----
We intentionally keep the index append-only. "Updates" are implemented as new
entries (or INSERT OR REPLACE for metadata) and cleaned up by compaction.

This module does NOT compute embeddings. Embedding generation belongs to an
embedding worker or an LLM tool.
"""


from typing import Any, Dict, List, Tuple


# === NoemaForge Autodoc Function Header ===
# Function: upsert_embedding(vstore, layer: str, entry_id: str, vector: List[float], model_id: str, dims: int, kind: str, meta: Dict[str, Any], stream_id: str = 'knowledge.vault', project_id: str = '')
# Purpose: Implement the routine 'upsert embedding'.
# Inputs:
#   - vstore
#   - layer: str
#   - entry_id: str
#   - vector: List[float]
#   - model_id: str
#   - dims: int
#   - kind: str
#   - meta: Dict[str, Any]
#   - stream_id: str = 'knowledge.vault'
#   - project_id: str = ''
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - upsert_many, get, isinstance, str, int, float
# Returns / emits: Tuple[bool, Dict[str, Any], str]
# Key locals:
#   - rep
# === End NoemaForge Autodoc Function Header ===
def upsert_embedding(
    vstore: Any,
    *,
    layer: str,
    entry_id: str,
    vector: List[float],
    model_id: str,
    dims: int,
    kind: str,
    meta: Dict[str, Any],
    stream_id: str = "knowledge.vault",
    project_id: str = "",
) -> Tuple[bool, Dict[str, Any], str]:
    if not isinstance(vector, list) or not vector:
        return False, {"ok": False, "reason": "missing_vector"}, "missing_vector"
    if not entry_id:
        return False, {"ok": False, "reason": "missing_entry_id"}, "missing_entry_id"
    try:
        rep = vstore.upsert_many(
            [
                {
                    "entry_id": str(entry_id),
                    "vector": [float(x) for x in vector],
                    "model_id": str(model_id),
                    "dims": int(dims),
                    "stream_id": str(stream_id),
                    "project_id": str(project_id),
                    "kind": str(kind),
                    "meta": meta or {},
                }
            ]
        )
        if rep.get("ok"):
            return True, rep, "ok"
        return False, rep, "vstore_upsert_failed"
    except Exception as e:
        return False, {"ok": False, "error": str(e)}, "vstore_upsert_error"
