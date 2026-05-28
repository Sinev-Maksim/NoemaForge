#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/casebase.py
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
# File: src/casebase.py
# Purpose: Provide the module 'casebase'.
# Invoked by / imported from:
#   - src/noemaforge_core.py
#   - src/memory_system.py
# Public API / entry functions:
#   - init_db
#   - get_case_by_key
#   - upsert_case
#   - search_cases
#   - compute_inputs_fingerprint
#   - hash_embed
# Inputs:
#   - Common path inputs: /var/lib/noemaforge
#   - Imports: __future__, hashlib, json, os, re, sqlite3, time, uuid
# Output formats / side effects:
#   - SQLite databases
#   - JSON files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""casebase.py (v0.11.0)

Solution Cache / Casebase

Purpose:
- Avoid re-doing the same work from scratch.
- Store structured pointers to artifacts + a short semantic summary.
- Provide a cheap, offline-first "semantic index" via VStore.

Important design constraints (NoemaForge spine):
- Deterministic core must remain auditable.
- We therefore avoid relying on external/LLM embeddings for indexing.
- Instead we use a deterministic "hashing trick" embedding (hash256-v1).
  It captures topical similarity (token overlap), not truth.

Storage:
  /var/lib/noemaforge/casebase/
    casebase.sqlite

VStore:
  layer = 'casebase'
  model_id = 'hash256-v1'
  dims = 256

"""


import hashlib
import json
import os
import re
import sqlite3
import time
import uuid
from typing import Any, Dict, List, Optional


BASE = "/var/lib/noemaforge"
CASEBASE_DIR = os.path.join(BASE, "casebase")
DB_PATH = os.path.join(CASEBASE_DIR, "casebase.sqlite")

HASH_EMBED_DIMS = 256
HASH_EMBED_MODEL_ID = "hash256-v1"


# === NoemaForge Autodoc Function Header ===
# Function: _nowz()
# Purpose: Implement the routine ' nowz'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - src/audit_remediation.py
#   - src/noemaforge_core.py
#   - src/bundles.py
#   - src/caps.py
#   - src/coordinator_fanout.py
#   - src/dream_cycle.py
#   - src/fixture_bundle.py
#   - src/glove_agent.py
# Calls:
#   - strftime, gmtime
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _nowz() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# === NoemaForge Autodoc Function Header ===
# Function: _ensure_dir(p: str)
# Purpose: Implement the routine ' ensure dir'.
# Inputs:
#   - p: str
# Called by:
#   - src/memory_system.py
#   - src/pipelines/finance_budget.py
#   - src/pipelines/photos_diary.py
#   - src/vstore.py
# Calls:
#   - makedirs
# Returns / emits: None
# Side effects:
#   - creates directories
# === End NoemaForge Autodoc Function Header ===
def _ensure_dir(p: str) -> None:
    os.makedirs(p, exist_ok=True)


# === NoemaForge Autodoc Function Header ===
# Function: _connect()
# Purpose: Implement the routine ' connect'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - src/dream_cycle.py
#   - src/knowledge/store.py
#   - src/memory_system.py
#   - src/pipelines/finance_budget.py
#   - src/roadmap.py
#   - src/task_tools.py
#   - src/taskqueue.py
#   - src/vstore.py
# Calls:
#   - _ensure_dir, connect
# Returns / emits: sqlite3.Connection
# Side effects:
#   - opens a database or socket connection
# Key locals:
#   - con
# === End NoemaForge Autodoc Function Header ===
def _connect() -> sqlite3.Connection:
    _ensure_dir(CASEBASE_DIR)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


# === NoemaForge Autodoc Function Header ===
# Function: init_db()
# Purpose: Implement the routine 'init db'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - src/pipelines/finance_budget.py
# Calls:
#   - _connect, cursor, execute, commit, close
# Returns / emits: None
# Side effects:
#   - opens a database or socket connection
#   - executes SQL or shell-like commands
# Key locals:
#   - con, cur
# === End NoemaForge Autodoc Function Header ===
def init_db() -> None:
    con = _connect()
    cur = con.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS cases (
          case_id TEXT PRIMARY KEY,
          key TEXT UNIQUE,
          stream_id TEXT,
          kind TEXT,
          created_at TEXT,
          inputs_hash TEXT,
          outputs_json TEXT,
          summary TEXT,
          vstore_entry_id TEXT,
          meta_json TEXT
        )
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_cases_stream ON cases(stream_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_cases_kind ON cases(kind)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_cases_created ON cases(created_at)")
    con.commit()
    con.close()


# === NoemaForge Autodoc Function Header ===
# Function: get_case_by_key(key: str)
# Purpose: Implement the routine 'get case by key'.
# Inputs:
#   - key: str
# Called by:
#   - src/noemaforge_core.py
# Calls:
#   - init_db, _connect, cursor, execute, fetchone, close, _row_to_case, str
# Returns / emits: Optional[Dict[str, Any]]
# Side effects:
#   - opens a database or socket connection
#   - executes SQL or shell-like commands
# Key locals:
#   - con, cur, row
# === End NoemaForge Autodoc Function Header ===
def get_case_by_key(key: str) -> Optional[Dict[str, Any]]:
    init_db()
    con = _connect()
    cur = con.cursor()
    cur.execute("SELECT * FROM cases WHERE key=?", (str(key),))
    row = cur.fetchone()
    con.close()
    if not row:
        return None
    return _row_to_case(row)


# === NoemaForge Autodoc Function Header ===
# Function: upsert_case(key: str, stream_id: str, kind: str, inputs_hash: str, outputs: List[Dict[str, Any]], summary: str, meta: Optional[Dict[str, Any]] = None, created_at: Optional[str] = None, index: bool = True)
# Purpose: Insert or update a case by key.
# Inputs:
#   - key: str
#   - stream_id: str
#   - kind: str
#   - inputs_hash: str
#   - outputs: List[Dict[str, Any]]
#   - summary: str
#   - meta: Optional[Dict[str, Any]] = None
#   - created_at: Optional[str] = None
#   - index: bool = True
# Called by:
#   - src/noemaforge_core.py
# Calls:
#   - init_db, get_case_by_key, _connect, cursor, execute, commit, close, _nowz, str, get, hash_embed, VStore
# Returns / emits: Dict[str, Any]
# Side effects:
#   - opens a database or socket connection
#   - executes SQL or shell-like commands
# Key locals:
#   - case_id, con, created_at, cur, entry_id, existing, meta, vec, vs, vstore_entry_id
# === End NoemaForge Autodoc Function Header ===
def upsert_case(
    *,
    key: str,
    stream_id: str,
    kind: str,
    inputs_hash: str,
    outputs: List[Dict[str, Any]],
    summary: str,
    meta: Optional[Dict[str, Any]] = None,
    created_at: Optional[str] = None,
    index: bool = True,
) -> Dict[str, Any]:
    """Insert or update a case by key.

    If index=True, also upsert into VStore(casebase) using hash embedding.
    """

    init_db()
    created_at = created_at or _nowz()
    meta = meta or {}

    existing = get_case_by_key(key)
    case_id = existing["case_id"] if existing else str(uuid.uuid4())

    vstore_entry_id = existing.get("vstore_entry_id") if existing else None

    if index:
        vec = hash_embed(summary, dims=HASH_EMBED_DIMS)
        from vstore import VStore, VStoreConfig  # local import

        vs = VStore(
            "casebase",
            VStoreConfig(backend="flat", metric="cosine", base_dir=os.path.join(BASE, "vstore")),
        )
        entry_id = vstore_entry_id or str(uuid.uuid4())
        vs.upsert_many(
            [
                {
                    "entry_id": entry_id,
                    "vector": vec,
                    "dims": HASH_EMBED_DIMS,
                    "model_id": HASH_EMBED_MODEL_ID,
                    "stream_id": stream_id,
                    "project_id": meta.get("project_id") or "",
                    "kind": kind,
                    "meta": {
                        "case_id": case_id,
                        "key": key,
                        "inputs_hash": inputs_hash,
                        "summary": summary[:4000],
                        "outputs": outputs,
                        **(meta or {}),
                    },
                }
            ]
        )
        vstore_entry_id = entry_id

    con = _connect()
    cur = con.cursor()
    cur.execute(
        """
        INSERT INTO cases(case_id, key, stream_id, kind, created_at, inputs_hash, outputs_json, summary, vstore_entry_id, meta_json)
        VALUES(?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(key) DO UPDATE SET
          stream_id=excluded.stream_id,
          kind=excluded.kind,
          created_at=excluded.created_at,
          inputs_hash=excluded.inputs_hash,
          outputs_json=excluded.outputs_json,
          summary=excluded.summary,
          vstore_entry_id=excluded.vstore_entry_id,
          meta_json=excluded.meta_json
        """,
        (
            case_id,
            key,
            stream_id,
            kind,
            created_at,
            inputs_hash,
            json.dumps(outputs, ensure_ascii=False),
            summary,
            vstore_entry_id or "",
            json.dumps(meta, ensure_ascii=False),
        ),
    )
    con.commit()
    con.close()

    return {
        "ok": True,
        "case_id": case_id,
        "key": key,
        "inputs_hash": inputs_hash,
        "indexed": bool(index),
        "vstore_entry_id": vstore_entry_id,
    }


# === NoemaForge Autodoc Function Header ===
# Function: search_cases(query_text: str, stream_id: str = '', kind: str = '', top_k: int = 10)
# Purpose: Semantic-ish search over casebase using deterministic hash embedding.
# Inputs:
#   - query_text: str
#   - stream_id: str = ''
#   - kind: str = ''
#   - top_k: int = 10
# Called by:
#   - src/memory_system.py
# Calls:
#   - init_db, VStore, hash_embed, _connect, cursor, close, VStoreConfig, get, str, execute, fetchone, _row_to_case
# Returns / emits: Dict[str, Any]
# Side effects:
#   - opens a database or socket connection
#   - executes SQL or shell-like commands
# Key locals:
#   - c, cid, con, cur, filters, m, matches, meta, out, qv, row, vs
# === End NoemaForge Autodoc Function Header ===
def search_cases(
    query_text: str,
    *,
    stream_id: str = "",
    kind: str = "",
    top_k: int = 10,
) -> Dict[str, Any]:
    """Semantic-ish search over casebase using deterministic hash embedding."""

    init_db()
    from vstore import VStore, VStoreConfig

    vs = VStore(
        "casebase",
        VStoreConfig(backend="flat", metric="cosine", base_dir=os.path.join(BASE, "vstore")),
    )
    qv = hash_embed(query_text, dims=HASH_EMBED_DIMS)

    filters: Dict[str, Any] = {}
    if stream_id:
        filters["stream_id"] = stream_id
    if kind:
        filters["kind"] = kind

    matches = (
        vs.query(qv, dims=HASH_EMBED_DIMS, model_id=HASH_EMBED_MODEL_ID, top_k=top_k, filters=filters).get("matches")
        or []
    )

    out: List[Dict[str, Any]] = []
    con = _connect()
    cur = con.cursor()
    for m in matches:
        meta = m.get("meta") or {}
        cid = str(meta.get("case_id") or "")
        if not cid:
            continue
        cur.execute("SELECT * FROM cases WHERE case_id=?", (cid,))
        row = cur.fetchone()
        if not row:
            continue
        c = _row_to_case(row)
        c["score"] = float(m.get("score") or 0.0)
        out.append(c)
    con.close()

    return {"ok": True, "matches": out}


# === NoemaForge Autodoc Function Header ===
# Function: compute_inputs_fingerprint(paths: List[str], mode: str = 'fast')
# Purpose: Compute a stable fingerprint for a set of input files.
# Inputs:
#   - paths: List[str]
#   - mode: str = 'fast'
# Called by:
#   - src/noemaforge_core.py
# Calls:
#   - sorted, sha256, update, hexdigest, set, encode, stat, append, str, join, _sha256_file, int
# Returns / emits: str
# Side effects:
#   - appends to logs or files
# Key locals:
#   - h, items, p, st
# === End NoemaForge Autodoc Function Header ===
def compute_inputs_fingerprint(paths: List[str], *, mode: str = "fast") -> str:
    """Compute a stable fingerprint for a set of input files.

    mode:
      - fast: hash path + size + mtime (cheap, good-enough for daily routines)
      - full: additionally sha256 file contents (expensive)
    """

    items: List[str] = []
    for p in sorted(set([str(x) for x in paths if x])):
        try:
            st = os.stat(p)
            items.append(f"{p}|{st.st_size}|{int(st.st_mtime)}")
            if mode == "full":
                items.append(_sha256_file(p))
        except Exception:
            continue

    h = hashlib.sha256()
    h.update("\n".join(items).encode("utf-8"))
    return h.hexdigest()


# === NoemaForge Autodoc Function Header ===
# Function: _sha256_file(path: str)
# Purpose: Implement the routine ' sha256 file'.
# Inputs:
#   - path: str
# Called by:
#   - src/bootdoctor.py
#   - src/brainctl.py
#   - src/doctor.py
#   - src/glove_agent.py
#   - src/localgw_uplink_agent.py
#   - src/model_registry.py
#   - src/pipelines/finance_budget.py
#   - src/prestart.py
# Calls:
#   - sha256, hexdigest, open, iter, update, read
# Returns / emits: str
# Side effects:
#   - reads or writes files
# Key locals:
#   - chunk, f, h
# === End NoemaForge Autodoc Function Header ===
def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


_token_re = re.compile(r"[\w\-]+", re.UNICODE)


# === NoemaForge Autodoc Function Header ===
# Function: hash_embed(text: str, dims: int = HASH_EMBED_DIMS)
# Purpose: Deterministic feature-hashing embedding.
# Inputs:
#   - text: str
#   - dims: int = HASH_EMBED_DIMS
# Called by:
#   - src/knowledge/embedding_worker.py
#   - src/memory_system.py
# Calls:
#   - int, lower, sum, findall, hexdigest, sha256, encode
# Returns / emits: List[float]
# Key locals:
#   - hi, hs, idx, norm, sign, t, tokens, vec
# === End NoemaForge Autodoc Function Header ===
def hash_embed(text: str, *, dims: int = HASH_EMBED_DIMS) -> List[float]:
    """Deterministic feature-hashing embedding.

    This is NOT a replacement for real embeddings.
    It's a cheap offline indexing signal that supports incremental indexing.

    Returns a L2-normalized vector of length `dims`.
    """

    vec = [0.0] * int(dims)
    if not text:
        return vec

    tokens = [t.lower() for t in _token_re.findall(text.lower()) if t]
    if not tokens:
        return vec

    for t in tokens:
        hi = int(hashlib.sha256(("i:" + t).encode("utf-8")).hexdigest(), 16)
        idx = hi % dims
        hs = int(hashlib.sha256(("s:" + t).encode("utf-8")).hexdigest(), 16)
        sign = 1.0 if (hs % 2 == 0) else -1.0
        vec[idx] += sign

    norm = sum(x * x for x in vec) ** 0.5
    if norm > 0:
        vec = [x / norm for x in vec]
    return vec


# === NoemaForge Autodoc Function Header ===
# Function: _row_to_case(row: sqlite3.Row)
# Purpose: Implement the routine ' row to case'.
# Inputs:
#   - row: sqlite3.Row
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - loads, str
# Returns / emits: Dict[str, Any]
# Key locals:
#   - meta, outputs
# === End NoemaForge Autodoc Function Header ===
def _row_to_case(row: sqlite3.Row) -> Dict[str, Any]:
    outputs = []
    meta = {}
    try:
        outputs = json.loads(row["outputs_json"] or "[]")
    except Exception:
        outputs = []
    try:
        meta = json.loads(row["meta_json"] or "{}")
    except Exception:
        meta = {}

    return {
        "case_id": str(row["case_id"]),
        "key": str(row["key"]),
        "stream_id": str(row["stream_id"] or ""),
        "kind": str(row["kind"] or ""),
        "created_at": str(row["created_at"] or ""),
        "inputs_hash": str(row["inputs_hash"] or ""),
        "summary": str(row["summary"] or ""),
        "vstore_entry_id": str(row["vstore_entry_id"] or ""),
        "outputs": outputs,
        "meta": meta,
    }
