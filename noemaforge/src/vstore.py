#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/vstore.py
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
# File: src/vstore.py
# Purpose: Provide the module 'vstore'.
# Invoked by / imported from:
#   - src/casebase.py
#   - src/knowledge/embedding_worker.py
#   - src/knowledge/retrieval.py
#   - src/memory_system.py
#   - src/toolproxy.py
# Public API / entry functions:
#   - class VStoreConfig
#   - class VStore
# Inputs:
#   - Common path inputs: /var/lib/noemaforge/vstore
#   - Imports: __future__, hashlib, json, os, sqlite3, time, uuid, dataclasses
# Output formats / side effects:
#   - SQLite databases
#   - JSON files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""vstore.py (v0.11.0)

Segmented Vector Store (offline-first)

Design goals:
- Incremental growth WITHOUT full reindex (append-only segments).
- Metadata in SQLite for filtering + tombstones.
- Simple backend choices:
    - flat: exact search (cosine) over segment arrays (MVP)
    - hnsw: optional ANN backend (future; keep API stable)

This is not trying to be 'the perfect vector DB'. It's a pragmatic nerve fiber
inside NoemaForge: fast-enough retrieval + auditable + easy to compact when idle.

IMPORTANT:
- Vector similarity = topical closeness, NOT logical agreement.
  "A" and "not A" can be close, so downstream logic should classify relations
  (entails/contradicts/neutral) and represent contradictions explicitly in the graph.

Paths (default):
  /var/lib/noemaforge/vstore/<layer>/
    meta.sqlite
    segments/
      seg_<id>.npz
      seg_<id>.manifest.json
"""


import hashlib
import json
import os
import sqlite3
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

try:
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover
    np = None  # type: ignore


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
#   - src/casebase.py
#   - src/coordinator_fanout.py
#   - src/dream_cycle.py
#   - src/fixture_bundle.py
# Calls:
#   - strftime, gmtime
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _nowz() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# === NoemaForge Autodoc Function Header ===
# Function: _sha256_file(path: str)
# Purpose: Implement the routine ' sha256 file'.
# Inputs:
#   - path: str
# Called by:
#   - src/bootdoctor.py
#   - src/brainctl.py
#   - src/casebase.py
#   - src/doctor.py
#   - src/glove_agent.py
#   - src/localgw_uplink_agent.py
#   - src/model_registry.py
#   - src/pipelines/finance_budget.py
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


# === NoemaForge Autodoc Function Header ===
# Function: _ensure_dir(p: str)
# Purpose: Implement the routine ' ensure dir'.
# Inputs:
#   - p: str
# Called by:
#   - src/casebase.py
#   - src/memory_system.py
#   - src/pipelines/finance_budget.py
#   - src/pipelines/photos_diary.py
# Calls:
#   - makedirs
# Returns / emits: None
# Side effects:
#   - creates directories
# === End NoemaForge Autodoc Function Header ===
def _ensure_dir(p: str) -> None:
    os.makedirs(p, exist_ok=True)


@dataclass
class VStoreConfig:
    backend: str = "flat"           # flat|hnsw
    metric: str = "cosine"          # cosine (only, for now)
    max_items_per_segment: int = 50000
    base_dir: str = "/var/lib/noemaforge/vstore"


class VStore:
    """Segmented vector store with SQLite metadata."""

    # === NoemaForge Autodoc Function Header ===
    # Function: __init__(self, layer: str, cfg: Optional[VStoreConfig] = None)
    # Purpose: Implement the routine '  init  '.
    # Inputs:
    #   - self
    #   - layer: str
    #   - cfg: Optional[VStoreConfig] = None
    # Called by:
    #   - src/model_scorecards.py
    #   - src/team_scorecards.py
    #   - src/toolproxy.py
    # Calls:
    #   - join, _ensure_dir, _init_db, VStoreConfig
    # Returns / emits: unspecified Python value
    # === End NoemaForge Autodoc Function Header ===
    def __init__(self, layer: str, cfg: Optional[VStoreConfig] = None):
        self.layer = layer
        self.cfg = cfg or VStoreConfig()
        self.layer_dir = os.path.join(self.cfg.base_dir, layer)
        self.seg_dir = os.path.join(self.layer_dir, "segments")
        self.db_path = os.path.join(self.layer_dir, "meta.sqlite")
        _ensure_dir(self.seg_dir)
        self._init_db()

    # === NoemaForge Autodoc Function Header ===
    # Function: _connect(self)
    # Purpose: Implement the routine ' connect'.
    # Inputs:
    #   - self
    # Called by:
    #   - src/casebase.py
    #   - src/dream_cycle.py
    #   - src/knowledge/store.py
    #   - src/memory_system.py
    #   - src/pipelines/finance_budget.py
    #   - src/roadmap.py
    #   - src/task_tools.py
    #   - src/taskqueue.py
    # Calls:
    #   - connect
    # Returns / emits: sqlite3.Connection
    # Side effects:
    #   - opens a database or socket connection
    # Key locals:
    #   - con
    # === End NoemaForge Autodoc Function Header ===
    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        return con

    # === NoemaForge Autodoc Function Header ===
    # Function: _init_db(self)
    # Purpose: Implement the routine ' init db'.
    # Inputs:
    #   - self
    # Called by:
    #   - src/knowledge/store.py
    #   - src/memory_system.py
    #   - tools/prep/scan_tabs.py
    #   - tools/prep/scan_tg.py
    # Calls:
    #   - _connect, cursor, execute, commit, close
    # Returns / emits: None
    # Side effects:
    #   - opens a database or socket connection
    #   - executes SQL or shell-like commands
    # Key locals:
    #   - con, cur
    # === End NoemaForge Autodoc Function Header ===
    def _init_db(self) -> None:
        con = self._connect()
        cur = con.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS segments (
              segment_id TEXT PRIMARY KEY,
              backend TEXT NOT NULL,
              dims INTEGER NOT NULL,
              model_id TEXT NOT NULL,
              created_at TEXT NOT NULL,
              state TEXT NOT NULL,
              count INTEGER NOT NULL,
              path TEXT NOT NULL,
              manifest_path TEXT NOT NULL,
              sha256 TEXT NOT NULL
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS entries (
              entry_id TEXT PRIMARY KEY,
              segment_id TEXT NOT NULL,
              pos INTEGER NOT NULL,
              dims INTEGER NOT NULL,
              model_id TEXT NOT NULL,
              created_at TEXT NOT NULL,
              tombstone INTEGER NOT NULL DEFAULT 0,
              stream_id TEXT,
              project_id TEXT,
              kind TEXT,
              meta_json TEXT
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_entries_model ON entries(model_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_entries_stream ON entries(stream_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_entries_project ON entries(project_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_entries_kind ON entries(kind)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_entries_segment ON entries(segment_id)")
        con.commit()
        con.close()

    # === NoemaForge Autodoc Function Header ===
    # Function: _active_segment(self, dims: int, model_id: str)
    # Purpose: Implement the routine ' active segment'.
    # Inputs:
    #   - self
    #   - dims: int
    #   - model_id: str
    # Called by:
    #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
    # Calls:
    #   - _connect, cursor, execute, fetchone, close
    # Returns / emits: Optional[sqlite3.Row]
    # Side effects:
    #   - opens a database or socket connection
    #   - executes SQL or shell-like commands
    # Key locals:
    #   - con, cur, row
    # === End NoemaForge Autodoc Function Header ===
    def _active_segment(self, dims: int, model_id: str) -> Optional[sqlite3.Row]:
        con = self._connect()
        cur = con.cursor()
        cur.execute(
            "SELECT * FROM segments WHERE state='active' AND dims=? AND model_id=? ORDER BY created_at DESC LIMIT 1",
            (dims, model_id),
        )
        row = cur.fetchone()
        con.close()
        return row

    # === NoemaForge Autodoc Function Header ===
    # Function: _create_segment(self, dims: int, model_id: str)
    # Purpose: Implement the routine ' create segment'.
    # Inputs:
    #   - self
    #   - dims: int
    #   - model_id: str
    # Called by:
    #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
    # Calls:
    #   - join, _sha256_file, _connect, cursor, execute, commit, fetchone, close, savez_compressed, _nowz, open, dump
    # Returns / emits: sqlite3.Row
    # Side effects:
    #   - reads or writes files
    #   - serializes structured data
    #   - opens a database or socket connection
    #   - executes SQL or shell-like commands
    # Key locals:
    #   - con, cur, f, manifest, manifest_path, path, row, seg_id, sha
    # === End NoemaForge Autodoc Function Header ===
    def _create_segment(self, dims: int, model_id: str) -> sqlite3.Row:
        seg_id = f"{int(time.time())}_{uuid.uuid4().hex[:8]}"
        path = os.path.join(self.seg_dir, f"seg_{seg_id}.npz")
        manifest_path = os.path.join(self.seg_dir, f"seg_{seg_id}.manifest.json")

        if np is None:
            # JSONL fallback
            path = path + ".jsonl"
            with open(path, "w", encoding="utf-8") as f:
                f.write("")
        else:
            np.savez_compressed(path, vectors=np.zeros((0, dims), dtype=np.float32), ids=np.array([], dtype=object))

        sha = _sha256_file(path)
        manifest = {
            "segment_id": seg_id,
            "layer": self.layer,
            "backend": self.cfg.backend,
            "dims": dims,
            "model_id": model_id,
            "created_at": _nowz(),
            "count": 0,
            "path": path,
            "state": "active",
            "sha256": sha,
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

        con = self._connect()
        cur = con.cursor()
        cur.execute(
            "INSERT INTO segments(segment_id, backend, dims, model_id, created_at, state, count, path, manifest_path, sha256) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (seg_id, self.cfg.backend, dims, model_id, manifest["created_at"], "active", 0, path, manifest_path, sha),
        )
        con.commit()
        cur.execute("SELECT * FROM segments WHERE segment_id=?", (seg_id,))
        row = cur.fetchone()
        con.close()
        assert row is not None
        return row

    # === NoemaForge Autodoc Function Header ===
    # Function: _seal_segment(self, segment_id: str)
    # Purpose: Implement the routine ' seal segment'.
    # Inputs:
    #   - self
    #   - segment_id: str
    # Called by:
    #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
    # Calls:
    #   - _connect, cursor, execute, commit, fetchone, close, str, loads, read, open, dump
    # Returns / emits: None
    # Side effects:
    #   - reads or writes files
    #   - serializes structured data
    #   - opens a database or socket connection
    #   - executes SQL or shell-like commands
    # Key locals:
    #   - con, cur, f, man, man_path, row
    # === End NoemaForge Autodoc Function Header ===
    def _seal_segment(self, segment_id: str) -> None:
        con = self._connect()
        cur = con.cursor()
        cur.execute("UPDATE segments SET state='sealed' WHERE segment_id=?", (segment_id,))
        con.commit()
        cur.execute("SELECT * FROM segments WHERE segment_id=?", (segment_id,))
        row = cur.fetchone()
        con.close()
        if not row:
            return
        man_path = str(row["manifest_path"])
        try:
            man = json.loads(open(man_path, "r", encoding="utf-8").read())
            man["state"] = "sealed"
            with open(man_path, "w", encoding="utf-8") as f:
                json.dump(man, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # === NoemaForge Autodoc Function Header ===
    # Function: upsert_many(self, items: List[Dict[str, Any]])
    # Purpose: Append entries. Each item must contain:
    # Inputs:
    #   - self
    #   - items: List[Dict[str, Any]]
    # Called by:
    #   - src/casebase.py
    #   - src/knowledge/embedding_worker.py
    #   - src/knowledge/vector_index.py
    #   - src/memory_system.py
    #   - src/toolproxy.py
    # Calls:
    #   - items, get, int, strip, str, append, _load_segment_arrays, len, _save_segment_arrays, _sha256_file, loads, _connect
    # Returns / emits: Dict[str, Any]
    # Side effects:
    #   - opens a database or socket connection
    #   - appends to logs or files
    # Key locals:
    #   - added, base_pos, con, cur, dims, f, groups, it, man, man_path, meta_json, model_id
    # === End NoemaForge Autodoc Function Header ===
    def upsert_many(self, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Append entries. Each item must contain:
          - vector: list[float]
          - model_id: str
        Optional:
          - entry_id, created_at, meta, stream_id, project_id, kind
        """
        if not items:
            return {"ok": True, "added": 0}

        # Validate & group by (dims, model_id)
        groups: Dict[Tuple[int, str], List[Dict[str, Any]]] = {}
        for it in items:
            vec = it.get("vector")
            if not isinstance(vec, list) or not vec:
                raise ValueError("vector_missing")
            dims = int(it.get("dims") or len(vec))
            model_id = str(it.get("model_id") or "").strip()
            if not model_id:
                raise ValueError("model_id_missing")

            it["dims"] = dims
            it["entry_id"] = str(it.get("entry_id") or uuid.uuid4())
            it["created_at"] = str(it.get("created_at") or _nowz())
            it["meta"] = it.get("meta") or {}
            groups.setdefault((dims, model_id), []).append(it)

        added = 0
        for (dims, model_id), batch in groups.items():
            seg = self._active_segment(dims, model_id) or self._create_segment(dims, model_id)
            seg_id = str(seg["segment_id"])

            vectors, ids = self._load_segment_arrays(str(seg["path"]), dims)

            for it in batch:
                ids.append(it["entry_id"])
                vectors.append([float(x) for x in it["vector"]])

            new_count = len(ids)
            self._save_segment_arrays(str(seg["path"]), dims, vectors, ids)

            sha = _sha256_file(str(seg["path"]))
            man_path = str(seg["manifest_path"])
            man = json.loads(open(man_path, "r", encoding="utf-8").read())
            man["count"] = new_count
            man["sha256"] = sha
            with open(man_path, "w", encoding="utf-8") as f:
                json.dump(man, f, ensure_ascii=False, indent=2)

            con = self._connect()
            cur = con.cursor()
            cur.execute("UPDATE segments SET count=?, sha256=? WHERE segment_id=?", (new_count, sha, seg_id))

            base_pos = new_count - len(batch)
            for i, it in enumerate(batch):
                pos = base_pos + i
                meta_json = json.dumps(it.get("meta") or {}, ensure_ascii=False)
                cur.execute(
                    "INSERT OR REPLACE INTO entries(entry_id, segment_id, pos, dims, model_id, created_at, tombstone, stream_id, project_id, kind, meta_json) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        it["entry_id"],
                        seg_id,
                        pos,
                        dims,
                        model_id,
                        it["created_at"],
                        0,
                        it.get("stream_id"),
                        it.get("project_id"),
                        it.get("kind"),
                        meta_json,
                    ),
                )

            con.commit()
            con.close()

            added += len(batch)

            if new_count >= int(self.cfg.max_items_per_segment):
                self._seal_segment(seg_id)

        return {"ok": True, "added": added}

    # === NoemaForge Autodoc Function Header ===
    # Function: tombstone(self, entry_ids: List[str])
    # Purpose: Implement the routine 'tombstone'.
    # Inputs:
    #   - self
    #   - entry_ids: List[str]
    # Called by:
    #   - src/toolproxy.py
    # Calls:
    #   - _connect, cursor, commit, close, execute
    # Returns / emits: Dict[str, Any]
    # Side effects:
    #   - opens a database or socket connection
    #   - executes SQL or shell-like commands
    # Key locals:
    #   - con, cur, eid, n
    # === End NoemaForge Autodoc Function Header ===
    def tombstone(self, entry_ids: List[str]) -> Dict[str, Any]:
        if not entry_ids:
            return {"ok": True, "tombstoned": 0}
        con = self._connect()
        cur = con.cursor()
        n = 0
        for eid in entry_ids:
            cur.execute("UPDATE entries SET tombstone=1 WHERE entry_id=?", (eid,))
            n += cur.rowcount
        con.commit()
        con.close()
        return {"ok": True, "tombstoned": n}

    # === NoemaForge Autodoc Function Header ===
    # Function: entry_exists(self, entry_id: str)
    # Purpose: Return True if a non-tombstoned entry exists.
    # Inputs:
    #   - self
    #   - entry_id: str
    # Called by:
    #   - src/knowledge/embedding_worker.py
    # Calls:
    #   - strip, _connect, cursor, execute, fetchone, close, bool, str
    # Returns / emits: bool
    # Side effects:
    #   - opens a database or socket connection
    #   - executes SQL or shell-like commands
    # Key locals:
    #   - con, cur, eid, row
    # === End NoemaForge Autodoc Function Header ===
    def entry_exists(self, entry_id: str) -> bool:
        """Return True if a non-tombstoned entry exists."""

        eid = str(entry_id or "").strip()
        if not eid:
            return False
        con = self._connect()
        cur = con.cursor()
        cur.execute("SELECT 1 FROM entries WHERE entry_id=? AND tombstone=0 LIMIT 1", (eid,))
        row = cur.fetchone()
        con.close()
        return bool(row)

    # === NoemaForge Autodoc Function Header ===
    # Function: query(self, vector: List[float], dims: int, model_id: str, top_k: int = 10, filters: Optional[Dict[str, Any]] = None)
    # Purpose: Implement the routine 'query'.
    # Inputs:
    #   - self
    #   - vector: List[float]
    #   - dims: int
    #   - model_id: str
    #   - top_k: int = 10
    #   - filters: Optional[Dict[str, Any]] = None
    # Called by:
    #   - src/casebase.py
    #   - src/knowledge/retrieval.py
    #   - src/memory_system.py
    #   - src/toolproxy.py
    # Calls:
    #   - max, _connect, cursor, execute, fetchall, close, sort, min, _prefilter_entry_ids, float, str, _load_segment_arrays
    # Returns / emits: Dict[str, Any]
    # Side effects:
    #   - opens a database or socket connection
    #   - executes SQL or shell-like commands
    # Key locals:
    #   - allowed_ids, candidates, con, cur, eid, filters, meta, out, path, qv, row, scored
    # === End NoemaForge Autodoc Function Header ===
    def query(self, vector: List[float], dims: int, model_id: str, top_k: int = 10, filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        filters = filters or {}
        top_k = max(1, min(int(top_k), 200))

        con = self._connect()
        cur = con.cursor()
        cur.execute(
            "SELECT * FROM segments WHERE dims=? AND model_id=? AND state IN ('active','sealed')",
            (int(dims), str(model_id)),
        )
        seg_rows = cur.fetchall()
        con.close()

        if not seg_rows:
            return {"ok": True, "matches": []}

        allowed_ids: Optional[set] = None
        if filters:
            allowed_ids = self._prefilter_entry_ids(int(dims), str(model_id), filters)

        # Search each segment and keep a rolling top list
        scored: List[Tuple[float, str]] = []
        qv = [float(x) for x in vector]

        for seg in seg_rows:
            path = str(seg["path"])
            vectors, ids = self._load_segment_arrays(path, int(dims))
            scores = self._cosine_scores(qv, vectors)
            for score, idx in scores:
                eid = ids[idx]
                if allowed_ids is not None and eid not in allowed_ids:
                    continue
                scored.append((score, eid))

        scored.sort(key=lambda x: x[0], reverse=True)
        # Pull more than top_k to survive tombstone filtering
        candidates = scored[: top_k * 10]

        out: List[Dict[str, Any]] = []
        con = self._connect()
        cur = con.cursor()
        for score, eid in candidates:
            cur.execute("SELECT * FROM entries WHERE entry_id=?", (eid,))
            row = cur.fetchone()
            if not row:
                continue
            if int(row["tombstone"]) == 1:
                continue
            meta = {}
            try:
                meta = json.loads(row["meta_json"] or "{}")
            except Exception:
                meta = {}
            out.append({
                "entry_id": eid,
                "score": float(score),
                "created_at": row["created_at"],
                "stream_id": row["stream_id"],
                "project_id": row["project_id"],
                "kind": row["kind"],
                "meta": meta,
            })
            if len(out) >= top_k:
                break
        con.close()
        return {"ok": True, "matches": out}

    # === NoemaForge Autodoc Function Header ===
    # Function: _prefilter_entry_ids(self, dims: int, model_id: str, filters: Dict[str, Any])
    # Purpose: Implement the routine ' prefilter entry ids'.
    # Inputs:
    #   - self
    #   - dims: int
    #   - model_id: str
    #   - filters: Dict[str, Any]
    # Called by:
    #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
    # Calls:
    #   - _connect, cursor, execute, close, append, join, tuple, str, fetchall
    # Returns / emits: set
    # Side effects:
    #   - opens a database or socket connection
    #   - executes SQL or shell-like commands
    #   - appends to logs or files
    # Key locals:
    #   - args, con, cur, ids, q, where
    # === End NoemaForge Autodoc Function Header ===
    def _prefilter_entry_ids(self, dims: int, model_id: str, filters: Dict[str, Any]) -> set:
        where = ["dims=?", "model_id=?", "tombstone=0"]
        args: List[Any] = [dims, model_id]

        if "stream_id" in filters:
            where.append("stream_id=?")
            args.append(filters["stream_id"])
        if "project_id" in filters:
            where.append("project_id=?")
            args.append(filters["project_id"])
        if "kind" in filters:
            where.append("kind=?")
            args.append(filters["kind"])
        if "created_from" in filters:
            where.append("created_at>=?")
            args.append(filters["created_from"])
        if "created_to" in filters:
            where.append("created_at<=?")
            args.append(filters["created_to"])

        q = "SELECT entry_id FROM entries WHERE " + " AND ".join(where)
        con = self._connect()
        cur = con.cursor()
        cur.execute(q, tuple(args))
        ids = {str(r[0]) for r in cur.fetchall()}
        con.close()
        return ids

    # === NoemaForge Autodoc Function Header ===
    # Function: _load_segment_arrays(self, path: str, dims: int)
    # Purpose: Implement the routine ' load segment arrays'.
    # Inputs:
    #   - self
    #   - path: str
    #   - dims: int
    # Called by:
    #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
    # Calls:
    #   - load, astype, tolist, endswith, str, exists, getsize, open, loads, append
    # Returns / emits: Tuple[List[List[float]], List[str]]
    # Side effects:
    #   - reads or writes files
    #   - appends to logs or files
    # Key locals:
    #   - data, f, ids, ids_arr, line, obj, vecs, vectors
    # === End NoemaForge Autodoc Function Header ===
    def _load_segment_arrays(self, path: str, dims: int) -> Tuple[List[List[float]], List[str]]:
        if np is None or path.endswith(".jsonl"):
            vectors: List[List[float]] = []
            ids: List[str] = []
            if os.path.exists(path) and os.path.getsize(path) > 0:
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        obj = json.loads(line)
                        ids.append(str(obj["id"]))
                        vectors.append(obj["v"])
            return vectors, ids

        data = np.load(path, allow_pickle=True)
        vecs = data["vectors"].astype(np.float32)
        ids_arr = data["ids"]
        vectors = vecs.tolist()
        ids = [str(x) for x in ids_arr.tolist()]
        return vectors, ids

    # === NoemaForge Autodoc Function Header ===
    # Function: _save_segment_arrays(self, path: str, dims: int, vectors: List[List[float]], ids: List[str])
    # Purpose: Implement the routine ' save segment arrays'.
    # Inputs:
    #   - self
    #   - path: str
    #   - dims: int
    #   - vectors: List[List[float]]
    #   - ids: List[str]
    # Called by:
    #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
    # Calls:
    #   - array, savez_compressed, endswith, open, zip, write, dumps
    # Returns / emits: None
    # Side effects:
    #   - reads or writes files
    #   - serializes structured data
    # Key locals:
    #   - f, ids_arr, vecs
    # === End NoemaForge Autodoc Function Header ===
    def _save_segment_arrays(self, path: str, dims: int, vectors: List[List[float]], ids: List[str]) -> None:
        if np is None or path.endswith(".jsonl"):
            with open(path, "w", encoding="utf-8") as f:
                for eid, v in zip(ids, vectors):
                    f.write(json.dumps({"id": eid, "v": v}, ensure_ascii=False) + "\n")
            return
        vecs = np.array(vectors, dtype=np.float32)
        ids_arr = np.array(ids, dtype=object)
        np.savez_compressed(path, vectors=vecs, ids=ids_arr)

    # === NoemaForge Autodoc Function Header ===
    # Function: _cosine_scores(self, q: List[float], vectors: List[List[float]])
    # Purpose: Implement the routine ' cosine scores'.
    # Inputs:
    #   - self
    #   - q: List[float]
    #   - vectors: List[List[float]]
    # Called by:
    #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
    # Calls:
    #   - norm, enumerate, sum, max, append, zip, dot
    # Returns / emits: List[Tuple[float, int]]
    # Side effects:
    #   - appends to logs or files
    # Key locals:
    #   - out, qn
    # === End NoemaForge Autodoc Function Header ===
    def _cosine_scores(self, q: List[float], vectors: List[List[float]]) -> List[Tuple[float, int]]:
        # === NoemaForge Autodoc Function Header ===
        # Function: dot(a: List[float], b: List[float])
        # Purpose: Implement the routine 'dot'.
        # Inputs:
        #   - a: List[float]
        #   - b: List[float]
        # Called by:
        #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
        # Calls:
        #   - sum, zip
        # Returns / emits: float
        # === End NoemaForge Autodoc Function Header ===
        def dot(a: List[float], b: List[float]) -> float:
            return sum(x * y for x, y in zip(a, b))

        # === NoemaForge Autodoc Function Header ===
        # Function: norm(a: List[float])
        # Purpose: Implement the routine 'norm'.
        # Inputs:
        #   - a: List[float]
        # Called by:
        #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
        # Calls:
        #   - max, sum
        # Returns / emits: float
        # === End NoemaForge Autodoc Function Header ===
        def norm(a: List[float]) -> float:
            return max(1e-12, sum(x * x for x in a) ** 0.5)

        qn = norm(q)
        out: List[Tuple[float, int]] = []
        for i, v in enumerate(vectors):
            out.append((dot(q, v) / (qn * norm(v)), i))
        return out
