#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/memory_system.py
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
# File: src/memory_system.py
# Purpose: Provide the module 'memory_system'.
# Invoked by / imported from:
#   - src/noemaforge_core.py
# Public API / entry functions:
#   - load_memory_policy
#   - class MemoryLayer
#   - class MemorySystem
#   - init_memory_system
# Inputs:
#   - Common path inputs: noemaforge.memory/v1, /var/lib/noemaforge/vstore, /var/lib/noemaforge/memory/longterm.sqlite, /var/lib/noemaforge/.tmp/session_memory.sqlite, /var/lib/noemaforge/.tmp/vstore
#   - Imports: __future__, datetime, json, os, sqlite3, time, uuid, dataclasses
# Output formats / side effects:
#   - SQLite databases
#   - JSON files
#   - YAML files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""memory_system.py (v0.19.0)

Layered memory for NoemaForge.

This module formalizes the "backlog-context-artifact" memory story we discussed:
- Session memory: short-lived, RAM-backed working set ("эта сессия")
- Long-term memory: persisted semantic index (vstore-backed)
- Casebase: solution cache behind scheduler/pipelines

Notes
-----
- For the spine, embeddings default to deterministic hash embeddings.
- Similarity != logical agreement. Contradictions must be represented explicitly
  at the knowledge layer.
- RAM limiting is best-effort: we estimate bytes using stored payload size.

The big idea: you can incrementally extend memory without full reindex
(VStore segments append; compaction can be done during idle cycles).
"""


import datetime as dt
import json
import os
import sqlite3
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from embeddings import hash_embed
from vstore import VStore, VStoreConfig


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
#   - isoformat, utcnow
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _nowz() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


# === NoemaForge Autodoc Function Header ===
# Function: _load_yaml(path: str)
# Purpose: Implement the routine ' load yaml'.
# Inputs:
#   - path: str
# Called by:
#   - src/brainctl.py
#   - src/noemaforge_core.py
#   - src/canary_runner.py
#   - src/daily_scheduler.py
#   - src/fixture_bundle.py
#   - src/flow_metrics.py
#   - src/incidents.py
#   - src/knowledge/policy.py
# Calls:
#   - open, safe_load
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads or writes files
# Key locals:
#   - f
# === End NoemaForge Autodoc Function Header ===
def _load_yaml(path: str) -> Dict[str, Any]:
    try:
        import yaml  # type: ignore

        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


# === NoemaForge Autodoc Function Header ===
# Function: load_memory_policy(epoch_dir: str)
# Purpose: Implement the routine 'load memory policy'.
# Inputs:
#   - epoch_dir: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - join, exists, _load_yaml, isinstance
# Returns / emits: Dict[str, Any]
# Key locals:
#   - obj, p
# === End NoemaForge Autodoc Function Header ===
def load_memory_policy(epoch_dir: str) -> Dict[str, Any]:
    p = os.path.join(epoch_dir, "memory-policy.yaml")
    if os.path.exists(p):
        obj = _load_yaml(p)
        if isinstance(obj, dict) and obj:
            return obj
    # Safe defaults (do not write to disk unless necessary)
    return {
        "apiVersion": "noemaforge.memory/v1",
        "kind": "MemoryPolicy",
        "enabled": True,
        "session": {
            "enabled": True,
            "max_ram_ratio": 0.25,
            "vstore_base_dir": "/dev/shm/noemaforge/vstore",
            "sqlite_path": "/dev/shm/noemaforge/session_memory.sqlite",
            "layer": "memory_session",
            "embed": {"model_id": "hash256-v1", "dims": 256},
            "osmyslenie": {
                "enabled": True,
                "n_per_category": 3,
                "similarity_threshold": 0.62,
                "max_categories": 200,
                "max_subcategories": 50,
                "min_cluster_size": 3,
            },
        },
        "longterm": {
            "enabled": True,
            "vstore_base_dir": "/var/lib/noemaforge/vstore",
            "sqlite_path": "/var/lib/noemaforge/memory/longterm.sqlite",
            "layer": "memory_long",
            "embed": {"model_id": "hash256-v1", "dims": 256},
        },
        "casebase": {"enabled": True, "behind_scheduler": True},
        "retrieval": {"top_k": 8, "include_casebase": True, "include_longterm": True, "include_session": True},
    }


# === NoemaForge Autodoc Function Header ===
# Function: _mem_total_bytes()
# Purpose: Best-effort physical RAM total.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - open, startswith, split, int
# Returns / emits: int
# Side effects:
#   - reads or writes files
# Key locals:
#   - f, kb, line, parts
# === End NoemaForge Autodoc Function Header ===
def _mem_total_bytes() -> int:
    """Best-effort physical RAM total."""
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    parts = line.split()
                    # kB
                    kb = int(parts[1])
                    return kb * 1024
    except Exception:
        pass
    return 0


# === NoemaForge Autodoc Function Header ===
# Function: _estimate_bytes(text: str, meta: Dict[str, Any])
# Purpose: Implement the routine ' estimate bytes'.
# Inputs:
#   - text: str
#   - meta: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - int, len, dumps, encode
# Returns / emits: int
# Side effects:
#   - serializes structured data
# Key locals:
#   - b, mj
# === End NoemaForge Autodoc Function Header ===
def _estimate_bytes(text: str, meta: Dict[str, Any]) -> int:
    # crude: utf-8 bytes + meta JSON bytes + overhead
    try:
        b = len((text or "").encode("utf-8"))
    except Exception:
        b = len(text or "")
    try:
        mj = json.dumps(meta or {}, ensure_ascii=False)
        b += len(mj.encode("utf-8"))
    except Exception:
        b += 0
    return int(b + 64)


# === NoemaForge Autodoc Function Header ===
# Function: _safe_sqlite_path(p: str)
# Purpose: Implement the routine ' safe sqlite path'.
# Inputs:
#   - p: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - strip, str
# Returns / emits: str
# Key locals:
#   - p
# === End NoemaForge Autodoc Function Header ===
def _safe_sqlite_path(p: str) -> str:
    p = str(p or "").strip()
    if not p:
        return "/dev/shm/noemaforge/session_memory.sqlite"
    return p


# === NoemaForge Autodoc Function Header ===
# Function: _ensure_dir(path: str)
# Purpose: Implement the routine ' ensure dir'.
# Inputs:
#   - path: str
# Called by:
#   - src/casebase.py
#   - src/pipelines/finance_budget.py
#   - src/pipelines/photos_diary.py
#   - src/vstore.py
# Calls:
#   - makedirs, dirname
# Returns / emits: None
# Side effects:
#   - creates directories
# === End NoemaForge Autodoc Function Header ===
def _ensure_dir(path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)


# === NoemaForge Autodoc Function Header ===
# Function: _connect(db_path: str)
# Purpose: Implement the routine ' connect'.
# Inputs:
#   - db_path: str
# Called by:
#   - src/casebase.py
#   - src/dream_cycle.py
#   - src/knowledge/store.py
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
def _connect(db_path: str) -> sqlite3.Connection:
    _ensure_dir(db_path)
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    return con


# === NoemaForge Autodoc Function Header ===
# Function: _init_db(db_path: str)
# Purpose: Implement the routine ' init db'.
# Inputs:
#   - db_path: str
# Called by:
#   - src/knowledge/store.py
#   - src/vstore.py
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
def _init_db(db_path: str) -> None:
    con = _connect(db_path)
    cur = con.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
          event_id TEXT PRIMARY KEY,
          ts TEXT,
          stream_id TEXT,
          project_id TEXT,
          kind TEXT,
          text TEXT,
          meta_json TEXT,
          bytes_est INTEGER,
          category_id TEXT,
          subcategory_id TEXT
        )
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_events_stream ON events(stream_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_events_project ON events(project_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_events_cat ON events(category_id)")
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS categories (
          category_id TEXT PRIMARY KEY,
          parent_id TEXT,
          label TEXT,
          centroid_json TEXT,
          created_at TEXT,
          kind TEXT
        )
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_categories_parent ON categories(parent_id)")
    con.commit()
    con.close()


# === NoemaForge Autodoc Function Header ===
# Function: _classify_first_layer(text: str, kind: str = '', stream_id: str = '')
# Purpose: Implement the routine ' classify first layer'.
# Inputs:
#   - text: str
#   - kind: str = ''
#   - stream_id: str = ''
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - lower, any
# Returns / emits: str
# Key locals:
#   - k, s, t
# === End NoemaForge Autodoc Function Header ===
def _classify_first_layer(text: str, kind: str = "", stream_id: str = "") -> str:
    t = (text or "").lower()
    k = (kind or "").lower()
    s = (stream_id or "").lower()

    # task-ish
    if any(x in t for x in ("нарис", "сгенерируй", "рендер", "blender")) or "blender" in t:
        return "task:render"
    if any(x in t for x in ("посч", "расч", "sql", "python", "код", "запрос")) or "dev" in k:
        return "task:dev"
    if any(x in t for x in ("найди", "поиск", "rss", "новост")):
        return "task:research"

    # domain-ish
    if "photos" in s or "photo" in k or "diary" in k or "фото" in t:
        return "domain:photos"
    if "bank" in s or "finance" in k or "бюдж" in t or "банк" in t:
        return "domain:finance"
    if "3d" in t or "печать" in t or "slicer" in t:
        return "domain:3dprint"

    # default
    return "misc"


# === NoemaForge Autodoc Function Header ===
# Function: _label_from_text(text: str)
# Purpose: Implement the routine ' label from text'.
# Inputs:
#   - text: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - join, lower, findall, len
# Returns / emits: str
# Key locals:
#   - toks
# === End NoemaForge Autodoc Function Header ===
def _label_from_text(text: str) -> str:
    # Use first few non-trivial tokens
    import re

    toks = [t.lower() for t in re.findall(r"[\w\-]+", text or "", flags=re.UNICODE)]
    toks = [t for t in toks if len(t) >= 3][:6]
    if not toks:
        return "untitled"
    return "_".join(toks[:3])


# === NoemaForge Autodoc Function Header ===
# Function: _cosine(a: List[float], b: List[float])
# Purpose: Implement the routine ' cosine'.
# Inputs:
#   - a: List[float]
#   - b: List[float]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - min, range, float, len
# Returns / emits: float
# Key locals:
#   - i, n, s
# === End NoemaForge Autodoc Function Header ===
def _cosine(a: List[float], b: List[float]) -> float:
    # a,b are normalized (hash_embed), so dot product is cosine
    s = 0.0
    n = min(len(a), len(b))
    for i in range(n):
        s += float(a[i]) * float(b[i])
    return float(s)


# === NoemaForge Autodoc Function Header ===
# Function: _normalize(v: List[float])
# Purpose: Implement the routine ' normalize'.
# Inputs:
#   - v: List[float]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - sum, float
# Returns / emits: List[float]
# Key locals:
#   - n, ss
# === End NoemaForge Autodoc Function Header ===
def _normalize(v: List[float]) -> List[float]:
    ss = sum(float(x) * float(x) for x in v)
    if ss <= 0:
        return [0.0 for _ in v]
    n = ss ** 0.5
    return [float(x) / n for x in v]


# === NoemaForge Autodoc Function Header ===
# Function: _mean_vec(vecs: List[List[float]])
# Purpose: Implement the routine ' mean vec'.
# Inputs:
#   - vecs: List[List[float]]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - len, _normalize, range, float, max
# Returns / emits: List[float]
# Key locals:
#   - dims, i, out, v
# === End NoemaForge Autodoc Function Header ===
def _mean_vec(vecs: List[List[float]]) -> List[float]:
    if not vecs:
        return []
    dims = len(vecs[0])
    out = [0.0] * dims
    for v in vecs:
        for i in range(dims):
            out[i] += float(v[i])
    out = [x / max(1, len(vecs)) for x in out]
    return _normalize(out)


@dataclass
class MemoryLayer:
    enabled: bool
    sqlite_path: str
    vstore_layer: str
    vstore_base_dir: str
    embed_model_id: str
    embed_dims: int


class MemorySystem:
    """Layered memory: session + longterm + (optional) casebase search helper."""

    # === NoemaForge Autodoc Function Header ===
    # Function: __init__(self, epoch_dir: str, policy: Optional[Dict[str, Any]] = None)
    # Purpose: Implement the routine '  init  '.
    # Inputs:
    #   - self
    #   - epoch_dir: str
    #   - policy: Optional[Dict[str, Any]] = None
    # Called by:
    #   - src/model_scorecards.py
    #   - src/team_scorecards.py
    #   - src/toolproxy.py
    # Calls:
    #   - bool, _load_layer, _compute_session_limit, load_memory_policy, get, isinstance, _init_db, VStore, VStoreConfig
    # Returns / emits: unspecified Python value
    # === End NoemaForge Autodoc Function Header ===
    def __init__(self, *, epoch_dir: str, policy: Optional[Dict[str, Any]] = None):
        self.epoch_dir = epoch_dir
        self.policy = policy or load_memory_policy(epoch_dir)

        self.enabled = bool(self.policy.get("enabled", True))
        self.session = self._load_layer("session")
        self.longterm = self._load_layer("longterm")

        self.session_limit_bytes = self._compute_session_limit()
        self.osm_cfg = ((self.policy.get("session") or {}).get("osmyslenie") or {}) if isinstance((self.policy.get("session") or {}), dict) else {}

        if self.session.enabled:
            _init_db(self.session.sqlite_path)
            self._vs_session = VStore(
                self.session.vstore_layer,
                VStoreConfig(backend="flat", metric="cosine", base_dir=self.session.vstore_base_dir),
            )
        else:
            self._vs_session = None

        if self.longterm.enabled:
            _init_db(self.longterm.sqlite_path)
            self._vs_long = VStore(
                self.longterm.vstore_layer,
                VStoreConfig(backend="flat", metric="cosine", base_dir=self.longterm.vstore_base_dir),
            )
        else:
            self._vs_long = None

    # === NoemaForge Autodoc Function Header ===
    # Function: _load_layer(self, name: str)
    # Purpose: Implement the routine ' load layer'.
    # Inputs:
    #   - self
    #   - name: str
    # Called by:
    #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
    # Calls:
    #   - bool, _safe_sqlite_path, str, int, MemoryLayer, get, isinstance, isdir
    # Returns / emits: MemoryLayer
    # Key locals:
    #   - cfg, dims, emb, enabled, model_id, sqlite_path, vstore_base_dir, vstore_layer
    # === End NoemaForge Autodoc Function Header ===
    def _load_layer(self, name: str) -> MemoryLayer:
        cfg = self.policy.get(name) or {}
        if not isinstance(cfg, dict):
            cfg = {}
        enabled = bool(cfg.get("enabled", True))

        sqlite_path = _safe_sqlite_path(str(cfg.get("sqlite_path") or ""))
        vstore_layer = str(cfg.get("layer") or f"memory_{name}")
        vstore_base_dir = str(cfg.get("vstore_base_dir") or ("/dev/shm/noemaforge/vstore" if name == "session" else "/var/lib/noemaforge/vstore"))

        emb = cfg.get("embed") or {}
        if not isinstance(emb, dict):
            emb = {}
        model_id = str(emb.get("model_id") or "hash256-v1")
        dims = int(emb.get("dims") or 256)

        # If /dev/shm is missing, fall back to a temp dir. Still cleaned by recovery.
        if name == "session":
            try:
                if not os.path.isdir("/dev/shm"):
                    sqlite_path = "/var/lib/noemaforge/.tmp/session_memory.sqlite"
                    vstore_base_dir = "/var/lib/noemaforge/.tmp/vstore"
            except Exception:
                sqlite_path = "/var/lib/noemaforge/.tmp/session_memory.sqlite"
                vstore_base_dir = "/var/lib/noemaforge/.tmp/vstore"

        return MemoryLayer(
            enabled=enabled,
            sqlite_path=sqlite_path,
            vstore_layer=vstore_layer,
            vstore_base_dir=vstore_base_dir,
            embed_model_id=model_id,
            embed_dims=dims,
        )

    # === NoemaForge Autodoc Function Header ===
    # Function: _compute_session_limit(self)
    # Purpose: Implement the routine ' compute session limit'.
    # Inputs:
    #   - self
    # Called by:
    #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
    # Calls:
    #   - float, max, _mem_total_bytes, int, get, isinstance, min
    # Returns / emits: int
    # Key locals:
    #   - ratio, sess, tot
    # === End NoemaForge Autodoc Function Header ===
    def _compute_session_limit(self) -> int:
        sess = self.policy.get("session") or {}
        if not isinstance(sess, dict):
            sess = {}
        ratio = float(sess.get("max_ram_ratio") or 0.25)
        ratio = max(0.01, min(ratio, 0.9))
        tot = _mem_total_bytes()
        if tot <= 0:
            # fallback 512MB
            return int(512 * 1024 * 1024 * ratio)
        return int(tot * ratio)

    # === NoemaForge Autodoc Function Header ===
    # Function: _session_bytes_used(self)
    # Purpose: Implement the routine ' session bytes used'.
    # Inputs:
    #   - self
    # Called by:
    #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
    # Calls:
    #   - _connect, cursor, execute, int, close, fetchone
    # Returns / emits: int
    # Side effects:
    #   - opens a database or socket connection
    #   - executes SQL or shell-like commands
    # Key locals:
    #   - con, cur, used
    # === End NoemaForge Autodoc Function Header ===
    def _session_bytes_used(self) -> int:
        if not self.session.enabled:
            return 0
        con = _connect(self.session.sqlite_path)
        cur = con.cursor()
        cur.execute("SELECT COALESCE(SUM(bytes_est),0) FROM events")
        used = int(cur.fetchone()[0] or 0)
        con.close()
        return used

    # === NoemaForge Autodoc Function Header ===
    # Function: record_event(self, kind: str, text: str, stream_id: str = '', project_id: str = '', meta: Optional[Dict[str, Any]] = None, promote_longterm: bool = False)
    # Purpose: Record an event into session memory (and optionally longterm).
    # Inputs:
    #   - self
    #   - kind: str
    #   - text: str
    #   - stream_id: str = ''
    #   - project_id: str = ''
    #   - meta: Optional[Dict[str, Any]] = None
    #   - promote_longterm: bool = False
    # Called by:
    #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
    # Calls:
    #   - str, _nowz, _estimate_bytes, dumps, hash_embed, uuid4, _connect, cursor, execute, commit, close, _session_bytes_used
    # Returns / emits: Dict[str, Any]
    # Side effects:
    #   - serializes structured data
    #   - opens a database or socket connection
    #   - executes SQL or shell-like commands
    # Key locals:
    #   - be, con, cur, eid, meta, meta_json, ts, used, vec
    # === End NoemaForge Autodoc Function Header ===
    def record_event(
        self,
        *,
        kind: str,
        text: str,
        stream_id: str = "",
        project_id: str = "",
        meta: Optional[Dict[str, Any]] = None,
        promote_longterm: bool = False,
    ) -> Dict[str, Any]:
        """Record an event into session memory (and optionally longterm)."""

        if not self.enabled:
            return {"ok": True, "skipped": True}

        meta = meta or {}
        eid = str(uuid.uuid4())
        ts = _nowz()
        be = _estimate_bytes(text, meta)
        meta_json = json.dumps(meta, ensure_ascii=False)

        vec = hash_embed(text + "\n" + json.dumps(meta, ensure_ascii=False), dims=self.session.embed_dims)

        if self.session.enabled:
            con = _connect(self.session.sqlite_path)
            cur = con.cursor()
            cur.execute(
                "INSERT INTO events(event_id, ts, stream_id, project_id, kind, text, meta_json, bytes_est, category_id, subcategory_id) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (eid, ts, stream_id, project_id, kind, text, meta_json, be, "", ""),
            )
            con.commit()
            con.close()

            if self._vs_session is not None:
                self._vs_session.upsert_many(
                    [
                        {
                            "entry_id": eid,
                            "vector": vec,
                            "dims": self.session.embed_dims,
                            "model_id": self.session.embed_model_id,
                            "stream_id": stream_id,
                            "project_id": project_id,
                            "kind": kind,
                            "meta": {"event_id": eid, "ts": ts, "bytes_est": be, "text": text[:4000], **meta},
                        }
                    ]
                )

            # Enforce limiter
            used = self._session_bytes_used()
            if used > self.session_limit_bytes:
                self._osmyslenie(reason="limit_exceeded")

        if promote_longterm:
            self.promote_to_longterm(event_id=eid)

        return {"ok": True, "event_id": eid, "ts": ts, "bytes_est": be}

    # === NoemaForge Autodoc Function Header ===
    # Function: promote_to_longterm(self, event_id: str)
    # Purpose: Copy an event into longterm layer (keeps session copy).
    # Inputs:
    #   - self
    #   - event_id: str
    # Called by:
    #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
    # Calls:
    #   - _connect, cursor, execute, fetchone, close, str, hash_embed, commit, loads, upsert_many, dumps, int
    # Returns / emits: Dict[str, Any]
    # Side effects:
    #   - serializes structured data
    #   - opens a database or socket connection
    #   - executes SQL or shell-like commands
    # Key locals:
    #   - con, con2, cur, cur2, meta, row, text, vec
    # === End NoemaForge Autodoc Function Header ===
    def promote_to_longterm(self, *, event_id: str) -> Dict[str, Any]:
        """Copy an event into longterm layer (keeps session copy)."""

        if not (self.enabled and self.longterm.enabled):
            return {"ok": True, "skipped": True}

        # read session record
        con = _connect(self.session.sqlite_path)
        cur = con.cursor()
        cur.execute("SELECT * FROM events WHERE event_id=?", (str(event_id),))
        row = cur.fetchone()
        con.close()
        if not row:
            return {"ok": False, "error": "event_not_found"}

        text = str(row["text"] or "")
        meta = {}
        try:
            meta = json.loads(row["meta_json"] or "{}")
        except Exception:
            meta = {}

        vec = hash_embed(text + "\n" + json.dumps(meta, ensure_ascii=False), dims=self.longterm.embed_dims)

        # insert to longterm sqlite
        con2 = _connect(self.longterm.sqlite_path)
        cur2 = con2.cursor()
        cur2.execute(
            "INSERT OR REPLACE INTO events(event_id, ts, stream_id, project_id, kind, text, meta_json, bytes_est, category_id, subcategory_id) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                str(event_id),
                str(row["ts"] or _nowz()),
                str(row["stream_id"] or ""),
                str(row["project_id"] or ""),
                str(row["kind"] or ""),
                text,
                str(row["meta_json"] or "{}"),
                int(row["bytes_est"] or 0),
                str(row["category_id"] or ""),
                str(row["subcategory_id"] or ""),
            ),
        )
        con2.commit()
        con2.close()

        if self._vs_long is not None:
            self._vs_long.upsert_many(
                [
                    {
                        "entry_id": str(event_id),
                        "vector": vec,
                        "dims": self.longterm.embed_dims,
                        "model_id": self.longterm.embed_model_id,
                        "stream_id": str(row["stream_id"] or ""),
                        "project_id": str(row["project_id"] or ""),
                        "kind": str(row["kind"] or ""),
                        "meta": {"event_id": str(event_id), "ts": str(row["ts"] or ""), "text": text[:4000], **meta},
                    }
                ]
            )

        return {"ok": True, "event_id": str(event_id), "promoted": True}

    # === NoemaForge Autodoc Function Header ===
    # Function: search(self, query_text: str, top_k: Optional[int] = None, stream_id: str = '', project_id: str = '', kind: str = '')
    # Purpose: Search memory layers (and casebase if enabled) for similar items.
    # Inputs:
    #   - self
    #   - query_text: str
    #   - top_k: Optional[int] = None
    #   - stream_id: str = ''
    #   - project_id: str = ''
    #   - kind: str = ''
    # Called by:
    #   - src/doctor.py
    #   - src/hwscan.py
    #   - src/model_scorecards.py
    #   - src/offline_apt.py
    #   - src/pi_firewall.py
    #   - src/pipelines/finance_budget.py
    #   - src/team_memory_sync.py
    #   - tools/autodoc_inject_misc.py
    # Calls:
    #   - int, max, hash_embed, sort, get, isinstance, min, bool, append, search_cases, float, query
    # Returns / emits: Dict[str, Any]
    # Side effects:
    #   - appends to logs or files
    # Key locals:
    #   - c, cb, filters, k, m, matches, ret, vec_l, vec_s, x
    # === End NoemaForge Autodoc Function Header ===
    def search(
        self,
        query_text: str,
        *,
        top_k: Optional[int] = None,
        stream_id: str = "",
        project_id: str = "",
        kind: str = "",
    ) -> Dict[str, Any]:
        """Search memory layers (and casebase if enabled) for similar items."""

        if not self.enabled:
            return {"ok": True, "matches": []}

        ret = self.policy.get("retrieval") or {}
        if not isinstance(ret, dict):
            ret = {}
        k = int(top_k or ret.get("top_k") or 8)
        k = max(1, min(k, 50))

        vec_s = hash_embed(query_text, dims=self.session.embed_dims)
        vec_l = hash_embed(query_text, dims=self.longterm.embed_dims)

        filters: Dict[str, Any] = {}
        if stream_id:
            filters["stream_id"] = stream_id
        if project_id:
            filters["project_id"] = project_id
        if kind:
            filters["kind"] = kind

        matches: List[Dict[str, Any]] = []

        if bool(ret.get("include_session", True)) and self.session.enabled and self._vs_session is not None:
            m = self._vs_session.query(vec_s, dims=self.session.embed_dims, model_id=self.session.embed_model_id, top_k=k, filters=filters).get("matches") or []
            for x in m:
                matches.append({"layer": "session", **x})

        if bool(ret.get("include_longterm", True)) and self.longterm.enabled and self._vs_long is not None:
            m = self._vs_long.query(vec_l, dims=self.longterm.embed_dims, model_id=self.longterm.embed_model_id, top_k=k, filters=filters).get("matches") or []
            for x in m:
                matches.append({"layer": "longterm", **x})

        # Casebase is a separate module; optional
        if bool(ret.get("include_casebase", True)) and bool((self.policy.get("casebase") or {}).get("enabled", True)):
            try:
                import casebase

                cb = casebase.search_cases(query_text, stream_id=stream_id, kind=kind, top_k=min(10, k))
                for c in (cb.get("matches") or []) or []:
                    matches.append({"layer": "casebase", "score": float(c.get("score") or 0.0), "meta": {"case": c}})
            except Exception:
                pass

        # merge + topk by score
        matches.sort(key=lambda x: float(x.get("score") or 0.0), reverse=True)
        return {"ok": True, "matches": matches[:k]}

    # === NoemaForge Autodoc Function Header ===
    # Function: _osmyslenie(self, reason: str = '')
    # Purpose: Categorize session events when the session memory approaches the limit.
    # Inputs:
    #   - self
    #   - reason: str = ''
    # Called by:
    #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
    # Calls:
    #   - float, int, max, _connect, cursor, execute, fetchall, close, _load_categories, min, str, hash_embed
    # Returns / emits: Dict[str, Any]
    # Side effects:
    #   - opens a database or socket connection
    #   - executes SQL or shell-like commands
    # Key locals:
    #   - best_cat, best_score, c, cat_id, categorized, cats, cen, cid, con, cur, eid, items
    # === End NoemaForge Autodoc Function Header ===
    def _osmyslenie(self, *, reason: str = "") -> Dict[str, Any]:
        """Categorize session events when the session memory approaches the limit."""

        if not (self.session.enabled and bool(self.osm_cfg.get("enabled", True))):
            return {"ok": True, "skipped": True}

        thr = float(self.osm_cfg.get("similarity_threshold") or 0.62)
        n_per = int(self.osm_cfg.get("n_per_category") or 3)
        n_per = max(1, min(n_per, 50))
        min_cluster = int(self.osm_cfg.get("min_cluster_size") or 3)

        # Load events without category
        con = _connect(self.session.sqlite_path)
        cur = con.cursor()
        cur.execute("SELECT * FROM events WHERE (category_id IS NULL OR category_id='') ORDER BY ts ASC")
        rows = cur.fetchall()
        con.close()
        if not rows:
            return {"ok": True, "categorized": 0, "reason": "no_uncategorized"}

        # Load categories
        cats = self._load_categories(parent_id="")

        categorized = 0
        for r in rows:
            eid = str(r["event_id"])
            text = str(r["text"] or "")
            kind = str(r["kind"] or "")
            stream_id = str(r["stream_id"] or "")

            vec = hash_embed(text, dims=self.session.embed_dims)

            best_cat = ""
            best_score = -1.0
            for c in cats:
                cen = c.get("centroid") or []
                if not cen:
                    continue
                sc = _cosine(vec, cen)
                if sc > best_score:
                    best_score = sc
                    best_cat = str(c.get("category_id") or "")

            if best_cat and best_score >= thr:
                cat_id = best_cat
            else:
                # create new category
                layer = _classify_first_layer(text, kind=kind, stream_id=stream_id)
                label = f"{layer}/{_label_from_text(text)}"
                cat_id = self._create_category(label=label, centroid=vec, parent_id="", kind="category")
                cats.append({"category_id": cat_id, "label": label, "centroid": vec})

            # update event
            con = _connect(self.session.sqlite_path)
            con.execute("UPDATE events SET category_id=? WHERE event_id=?", (cat_id, eid))
            con.commit()
            con.close()
            categorized += 1

        # Subcategory split when needed
        for c in self._load_categories(parent_id=""):
            cid = str(c.get("category_id") or "")
            if not cid:
                continue
            items = self._events_for_category(cid)
            if len(items) <= n_per:
                continue
            # If already has subcats, skip (SR can later tune)
            if self._load_categories(parent_id=cid):
                continue
            if len(items) < max(min_cluster, 4):
                continue
            self._split_category_into_subcats(cid, items)

        return {"ok": True, "categorized": categorized, "reason": reason or "osmyslenie"}

    # === NoemaForge Autodoc Function Header ===
    # Function: _load_categories(self, parent_id: str)
    # Purpose: Implement the routine ' load categories'.
    # Inputs:
    #   - self
    #   - parent_id: str
    # Called by:
    #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
    # Calls:
    #   - _connect, cursor, execute, fetchall, close, append, str, loads
    # Returns / emits: List[Dict[str, Any]]
    # Side effects:
    #   - opens a database or socket connection
    #   - executes SQL or shell-like commands
    #   - appends to logs or files
    # Key locals:
    #   - cen, con, cur, out, r, rows
    # === End NoemaForge Autodoc Function Header ===
    def _load_categories(self, parent_id: str) -> List[Dict[str, Any]]:
        con = _connect(self.session.sqlite_path)
        cur = con.cursor()
        cur.execute("SELECT * FROM categories WHERE parent_id=?", (str(parent_id),))
        rows = cur.fetchall()
        con.close()
        out: List[Dict[str, Any]] = []
        for r in rows:
            cen = []
            try:
                cen = json.loads(r["centroid_json"] or "[]")
            except Exception:
                cen = []
            out.append({"category_id": str(r["category_id"]), "label": str(r["label"] or ""), "centroid": cen, "parent_id": str(r["parent_id"] or "")})
        return out

    # === NoemaForge Autodoc Function Header ===
    # Function: _create_category(self, label: str, centroid: List[float], parent_id: str, kind: str)
    # Purpose: Implement the routine ' create category'.
    # Inputs:
    #   - self
    #   - label: str
    #   - centroid: List[float]
    #   - parent_id: str
    #   - kind: str
    # Called by:
    #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
    # Calls:
    #   - str, _connect, execute, commit, close, uuid4, dumps, _nowz
    # Returns / emits: str
    # Side effects:
    #   - serializes structured data
    #   - opens a database or socket connection
    #   - executes SQL or shell-like commands
    # Key locals:
    #   - cid, con
    # === End NoemaForge Autodoc Function Header ===
    def _create_category(self, *, label: str, centroid: List[float], parent_id: str, kind: str) -> str:
        cid = str(uuid.uuid4())
        con = _connect(self.session.sqlite_path)
        con.execute(
            "INSERT INTO categories(category_id, parent_id, label, centroid_json, created_at, kind) VALUES(?,?,?,?,?,?)",
            (cid, str(parent_id), str(label), json.dumps(centroid), _nowz(), str(kind)),
        )
        con.commit()
        con.close()
        return cid

    # === NoemaForge Autodoc Function Header ===
    # Function: _events_for_category(self, category_id: str)
    # Purpose: Implement the routine ' events for category'.
    # Inputs:
    #   - self
    #   - category_id: str
    # Called by:
    #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
    # Calls:
    #   - _connect, cursor, execute, fetchall, close, append, str
    # Returns / emits: List[Dict[str, Any]]
    # Side effects:
    #   - opens a database or socket connection
    #   - executes SQL or shell-like commands
    #   - appends to logs or files
    # Key locals:
    #   - con, cur, out, r, rows
    # === End NoemaForge Autodoc Function Header ===
    def _events_for_category(self, category_id: str) -> List[Dict[str, Any]]:
        con = _connect(self.session.sqlite_path)
        cur = con.cursor()
        cur.execute("SELECT event_id, text, kind, stream_id FROM events WHERE category_id=?", (str(category_id),))
        rows = cur.fetchall()
        con.close()
        out: List[Dict[str, Any]] = []
        for r in rows:
            out.append({"event_id": str(r[0]), "text": str(r[1] or ""), "kind": str(r[2] or ""), "stream_id": str(r[3] or "")})
        return out

    # === NoemaForge Autodoc Function Header ===
    # Function: _split_category_into_subcats(self, category_id: str, items: List[Dict[str, Any]])
    # Purpose: Implement the routine ' split category into subcats'.
    # Inputs:
    #   - self
    #   - category_id: str
    #   - items: List[Dict[str, Any]]
    # Called by:
    #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
    # Calls:
    #   - enumerate, _mean_vec, _create_category, _connect, commit, close, hash_embed, append, _label_from_text, str, execute, _cosine
    # Returns / emits: None
    # Side effects:
    #   - opens a database or socket connection
    #   - executes SQL or shell-like commands
    #   - appends to logs or files
    # Key locals:
    #   - c0, c0_vecs, c1, c1_vecs, clusters, con, d, d1, d2, eid, far_d, far_i
    # === End NoemaForge Autodoc Function Header ===
    def _split_category_into_subcats(self, category_id: str, items: List[Dict[str, Any]]) -> None:
        # Deterministic 2-means split.
        vecs = [hash_embed(it["text"], dims=self.session.embed_dims) for it in items]
        if not vecs:
            return

        # seed1 = first item; seed2 = farthest from seed1
        s1 = vecs[0]
        far_i = 0
        far_d = -1.0
        for i, v in enumerate(vecs):
            d = 1.0 - _cosine(s1, v)
            if d > far_d:
                far_d = d
                far_i = i
        s2 = vecs[far_i]

        # one iteration is often enough for coarse split
        clusters = {0: [], 1: []}
        for i, v in enumerate(vecs):
            d1 = 1.0 - _cosine(s1, v)
            d2 = 1.0 - _cosine(s2, v)
            clusters[0 if d1 <= d2 else 1].append(i)

        # avoid degenerate split
        if not clusters[0] or not clusters[1]:
            return

        c0_vecs = [vecs[i] for i in clusters[0]]
        c1_vecs = [vecs[i] for i in clusters[1]]
        c0 = _mean_vec(c0_vecs)
        c1 = _mean_vec(c1_vecs)

        label0 = "sub:" + _label_from_text(items[clusters[0][0]]["text"])
        label1 = "sub:" + _label_from_text(items[clusters[1][0]]["text"])

        sub0 = self._create_category(label=label0, centroid=c0, parent_id=category_id, kind="subcategory")
        sub1 = self._create_category(label=label1, centroid=c1, parent_id=category_id, kind="subcategory")

        # assign events
        con = _connect(self.session.sqlite_path)
        for idx in clusters[0]:
            eid = str(items[idx]["event_id"])
            con.execute("UPDATE events SET subcategory_id=? WHERE event_id=?", (sub0, eid))
        for idx in clusters[1]:
            eid = str(items[idx]["event_id"])
            con.execute("UPDATE events SET subcategory_id=? WHERE event_id=?", (sub1, eid))
        con.commit()
        con.close()


# === NoemaForge Autodoc Function Header ===
# Function: init_memory_system(epoch_dir: str)
# Purpose: Implement the routine 'init memory system'.
# Inputs:
#   - epoch_dir: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - MemorySystem
# Returns / emits: MemorySystem
# === End NoemaForge Autodoc Function Header ===
def init_memory_system(epoch_dir: str) -> MemorySystem:
    return MemorySystem(epoch_dir=epoch_dir)
