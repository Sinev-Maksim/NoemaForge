#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/knowledge/ingest.py
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
# File: src/knowledge/ingest.py
# Purpose: Implement the knowledge subsystem module 'ingest'.
# Invoked by / imported from:
#   - src/brainctl.py
#   - src/knowledge_maintainer.py
# Public API / entry functions:
#   - ingest_text_file
# Inputs:
#   - Imports: __future__, os, typing, store
# Output formats / side effects:
#   - Returns Python values and/or performs in-memory orchestration.
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""knowledge.ingest (v0.16.0)

Very small ingestion helpers.

This is not an OCR pipeline. It's an offline-first seed that can ingest:
- plain text (.txt, .md)

For real PDFs / web, WebGW+Glove pipelines will feed passages later.
"""


import os
from typing import Any, Dict, List, Tuple

from .store import KnowledgeStore


# === NoemaForge Autodoc Function Header ===
# Function: _chunk_paragraphs(text: str, max_chars: int = 1200)
# Purpose: Implement the routine ' chunk paragraphs'.
# Inputs:
#   - text: str
#   - max_chars: int = 1200
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - strip, append, split, len
# Returns / emits: List[str]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - buf, chunks, p, paras
# === End NoemaForge Autodoc Function Header ===
def _chunk_paragraphs(text: str, *, max_chars: int = 1200) -> List[str]:
    paras = [p.strip() for p in (text or "").split("\n\n") if p.strip()]
    chunks: List[str] = []
    buf = ""
    for p in paras:
        if not buf:
            buf = p
            continue
        if len(buf) + 2 + len(p) <= max_chars:
            buf = buf + "\n\n" + p
        else:
            chunks.append(buf)
            buf = p
    if buf:
        chunks.append(buf)
    return chunks


# === NoemaForge Autodoc Function Header ===
# Function: ingest_text_file(store: KnowledgeStore, path: str, source_type: str = 'file', metadata: Dict[str, Any] | None = None, realm: str = '', created_by: str = 'ingest', max_chars_per_passage: int = 1200)
# Purpose: Implement the routine 'ingest text file'.
# Inputs:
#   - store: KnowledgeStore
#   - path: str
#   - source_type: str = 'file'
#   - metadata: Dict[str, Any] | None = None
#   - realm: str = ''
#   - created_by: str = 'ingest'
#   - max_chars_per_passage: int = 1200
# Called by:
#   - src/brainctl.py
#   - src/knowledge_maintainer.py
# Calls:
#   - abspath, dict, setdefault, add_source, _chunk_paragraphs, enumerate, exists, read, add_passage, append, len, decode
# Returns / emits: Dict[str, Any]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - anchor, chunks, meta, p, pid, pids, raw, sid
# === End NoemaForge Autodoc Function Header ===
def ingest_text_file(
    store: KnowledgeStore,
    *,
    path: str,
    source_type: str = "file",
    metadata: Dict[str, Any] | None = None,
    realm: str = "",
    created_by: str = "ingest",
    max_chars_per_passage: int = 1200,
) -> Dict[str, Any]:
    p = os.path.abspath(path)
    if not os.path.exists(p):
        return {"ok": False, "reason": "file_not_found"}

    meta = dict(metadata or {})
    meta.setdefault("path", p)

    try:
        raw = open(p, "r", encoding="utf-8", errors="replace").read()
    except Exception:
        raw = open(p, "rb").read().decode("utf-8", errors="replace")

    sid = store.add_source(type=source_type, metadata=meta, primary_realm=realm, created_by=created_by)

    chunks = _chunk_paragraphs(raw, max_chars=max_chars_per_passage)
    pids: List[str] = []
    for i, c in enumerate(chunks):
        anchor = {"kind": "file", "path": p, "chunk_index": i, "hint": "paragraph_chunk"}
        pid = store.add_passage(source_id=sid, anchor=anchor, text=c, realm_override="", created_by=created_by)
        pids.append(pid)

    return {"ok": True, "source_id": sid, "passage_ids": pids, "passages": len(pids)}
