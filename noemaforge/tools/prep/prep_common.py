#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tools/prep/prep_common.py
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
# File: tools/prep/prep_common.py
# Purpose: Prepare or ingest external assets for 'prep_common'.
# Invoked by / imported from:
#   - tools/prep/generate_head_gateway_assets.py
#   - tools/prep/process_inbox.py
#   - tools/prep/scan_library.py
#   - tools/prep/scan_vault.py
# Public API / entry functions:
#   - nowz
#   - ensure_dir
#   - read_json
#   - write_json
#   - sha256_file
#   - quick_fingerprint
#   - safe_relpath
#   - stable_id
#   - is_probably_binary
#   - open_db
#   - set_meta
#   - get_meta
# Inputs:
#   - Imports: __future__, dataclasses, datetime, hashlib, json, os, sqlite3, stat
# Output formats / side effects:
#   - SQLite databases
#   - JSON files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""NoemaForge Windows preparation helpers.

These tools are meant to run on Windows *without* WSL and without requiring any
non-standard Python packages.

Design goals:
- incremental scanning (no full re-hash unless file changed)
- deterministic IDs (stable unless user overrides via manifest)
- tombstones (we do not silently forget removed files)
"""


import dataclasses
import datetime as dt
import hashlib
import json
import os
import sqlite3
import stat
from typing import Any, Dict, Iterable, Optional, Tuple


# === NoemaForge Autodoc Function Header ===
# Function: nowz()
# Purpose: Implement the routine 'nowz'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - tools/prep/process_inbox.py
#   - tools/prep/scan_library.py
#   - tools/prep/scan_vault.py
# Calls:
#   - strftime, utcnow
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def nowz() -> str:
    return dt.datetime.now(dt.UTC).replace(tzinfo=None).strftime("%Y%m%dT%H%M%SZ")


# === NoemaForge Autodoc Function Header ===
# Function: ensure_dir(path: str)
# Purpose: Implement the routine 'ensure dir'.
# Inputs:
#   - path: str
# Called by:
#   - tools/prep/generate_head_gateway_assets.py
#   - tools/prep/process_inbox.py
#   - tools/prep/scan_library.py
#   - tools/prep/scan_vault.py
# Calls:
#   - makedirs
# Returns / emits: None
# Side effects:
#   - creates directories
# === End NoemaForge Autodoc Function Header ===
def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


# === NoemaForge Autodoc Function Header ===
# Function: read_json(path: str)
# Purpose: Implement the routine 'read json'.
# Inputs:
#   - path: str
# Called by:
#   - tools/prep/generate_head_gateway_assets.py
#   - tools/prep/scan_library.py
#   - tools/prep/scan_vault.py
# Calls:
#   - loads, open, read, decode
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads or writes files
# Key locals:
#   - b, f
# === End NoemaForge Autodoc Function Header ===
def read_json(path: str) -> Dict[str, Any]:
    with open(path, "rb") as f:
        b = f.read()
    return json.loads(b.decode("utf-8"))


# === NoemaForge Autodoc Function Header ===
# Function: write_json(path: str, obj)
# Purpose: Implement the routine 'write json'.
# Inputs:
#   - path: str
#   - obj
# Called by:
#   - tools/prep/generate_head_gateway_assets.py
#   - tools/prep/process_inbox.py
#   - tools/prep/scan_library.py
#   - tools/prep/scan_vault.py
# Calls:
#   - ensure_dir, replace, open, write, dirname, encode, dumps
# Returns / emits: None
# Side effects:
#   - reads or writes files
#   - serializes structured data
# Key locals:
#   - f, tmp
# === End NoemaForge Autodoc Function Header ===
def write_json(path: str, obj: Any) -> None:
    ensure_dir(os.path.dirname(path) or ".")
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(json.dumps(obj, indent=2, sort_keys=True).encode("utf-8"))
    os.replace(tmp, path)


# === NoemaForge Autodoc Function Header ===
# Function: sha256_file(path: str)
# Purpose: Implement the routine 'sha256 file'.
# Inputs:
#   - path: str
# Called by:
#   - src/knowledge_maintainer.py
#   - src/offline_apt.py
#   - src/toolvault.py
#   - src/webgateway.py
#   - tools/prep/scan_library.py
#   - tools/prep/scan_vault.py
# Calls:
#   - sha256, hexdigest, open, iter, update, read
# Returns / emits: str
# Side effects:
#   - reads or writes files
# Key locals:
#   - chunk, f, h
# === End NoemaForge Autodoc Function Header ===
def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


# === NoemaForge Autodoc Function Header ===
# Function: quick_fingerprint(path: str, block_size: int = 64 * 1024)
# Purpose: Fast-ish content fingerprint: hash of first+last blocks plus size.
# Inputs:
#   - path: str
#   - block_size: int = 64 * 1024
# Called by:
#   - tools/prep/process_inbox.py
#   - tools/prep/scan_library.py
#   - tools/prep/scan_vault.py
# Calls:
#   - stat, int, sha256, update, hexdigest, encode, open, read, str, seek, max
# Returns / emits: str
# Side effects:
#   - reads or writes files
# Key locals:
#   - f, h, head, size, st, tail
# === End NoemaForge Autodoc Function Header ===
def quick_fingerprint(path: str, block_size: int = 64 * 1024) -> str:
    """Fast-ish content fingerprint: hash of first+last blocks plus size.

    This avoids full hashing for huge files.
    """
    st = os.stat(path)
    size = int(st.st_size)
    h = hashlib.sha256()
    h.update(str(size).encode("utf-8"))
    with open(path, "rb") as f:
        head = f.read(block_size)
        h.update(head)
        if size > block_size:
            try:
                f.seek(max(0, size - block_size))
                tail = f.read(block_size)
                h.update(tail)
            except Exception:
                # Some virtual filesystems can throw; keep head-only.
                pass
    return h.hexdigest()


# === NoemaForge Autodoc Function Header ===
# Function: safe_relpath(path: str, root: str)
# Purpose: Implement the routine 'safe relpath'.
# Inputs:
#   - path: str
#   - root: str
# Called by:
#   - tools/prep/process_inbox.py
#   - tools/prep/scan_library.py
#   - tools/prep/scan_vault.py
# Calls:
#   - relpath, replace
# Returns / emits: str
# Key locals:
#   - rel
# === End NoemaForge Autodoc Function Header ===
def safe_relpath(path: str, root: str) -> str:
    rel = os.path.relpath(path, root)
    rel = rel.replace("\\", "/")
    return rel


# === NoemaForge Autodoc Function Header ===
# Function: stable_id(prefix: str, key: str, n: int = 12)
# Purpose: Deterministic ID from a string key (usually rel_path).
# Inputs:
#   - prefix: str
#   - key: str
#   - n: int = 12
# Called by:
#   - tools/prep/process_inbox.py
#   - tools/prep/scan_library.py
#   - tools/prep/scan_vault.py
# Calls:
#   - hexdigest, sha256, encode
# Returns / emits: str
# Key locals:
#   - h
# === End NoemaForge Autodoc Function Header ===
def stable_id(prefix: str, key: str, n: int = 12) -> str:
    """Deterministic ID from a string key (usually rel_path)."""
    h = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return f"{prefix}_{h[:n]}"


# === NoemaForge Autodoc Function Header ===
# Function: is_probably_binary(path: str)
# Purpose: Implement the routine 'is probably binary'.
# Inputs:
#   - path: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - count, open, read
# Returns / emits: bool
# Side effects:
#   - reads or writes files
# Key locals:
#   - b, f, nul
# === End NoemaForge Autodoc Function Header ===
def is_probably_binary(path: str) -> bool:
    # Heuristic: many NUL bytes in first 8KB.
    try:
        with open(path, "rb") as f:
            b = f.read(8192)
        if not b:
            return False
        nul = b.count(b"\x00")
        return nul > 0
    except Exception:
        return False


# === NoemaForge Autodoc Function Header ===
# Function: open_db(path: str)
# Purpose: Implement the routine 'open db'.
# Inputs:
#   - path: str
# Called by:
#   - tools/prep/scan_library.py
#   - tools/prep/scan_vault.py
# Calls:
#   - ensure_dir, connect, execute, dirname
# Returns / emits: sqlite3.Connection
# Side effects:
#   - opens a database or socket connection
#   - executes SQL or shell-like commands
# Key locals:
#   - conn
# === End NoemaForge Autodoc Function Header ===
def open_db(path: str) -> sqlite3.Connection:
    ensure_dir(os.path.dirname(path) or ".")
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


# === NoemaForge Autodoc Function Header ===
# Function: set_meta(conn: sqlite3.Connection, key: str, value: str)
# Purpose: Implement the routine 'set meta'.
# Inputs:
#   - conn: sqlite3.Connection
#   - key: str
#   - value: str
# Called by:
#   - tools/prep/scan_library.py
#   - tools/prep/scan_vault.py
# Calls:
#   - execute
# Returns / emits: None
# Side effects:
#   - executes SQL or shell-like commands
# === End NoemaForge Autodoc Function Header ===
def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT NOT NULL)"
    )
    conn.execute(
        "INSERT INTO meta(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
        (key, value),
    )


# === NoemaForge Autodoc Function Header ===
# Function: get_meta(conn: sqlite3.Connection, key: str)
# Purpose: Implement the routine 'get meta'.
# Inputs:
#   - conn: sqlite3.Connection
#   - key: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - execute, fetchone
# Returns / emits: Optional[str]
# Side effects:
#   - executes SQL or shell-like commands
# Key locals:
#   - cur, row
# === End NoemaForge Autodoc Function Header ===
def get_meta(conn: sqlite3.Connection, key: str) -> Optional[str]:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT NOT NULL)"
    )
    cur = conn.execute("SELECT v FROM meta WHERE k=?", (key,))
    row = cur.fetchone()
    return row[0] if row else None


@dataclasses.dataclass
class ScanStats:
    scanned: int = 0
    unchanged: int = 0
    hashed_full: int = 0
    hashed_quick: int = 0
    new_files: int = 0
    changed_files: int = 0
    tombstoned: int = 0
    errors: int = 0

    # === NoemaForge Autodoc Function Header ===
    # Function: as_dict(self)
    # Purpose: Implement the routine 'as dict'.
    # Inputs:
    #   - self
    # Called by:
    #   - tools/prep/scan_library.py
    #   - tools/prep/scan_vault.py
    # Calls:
    #   - asdict
    # Returns / emits: Dict[str, Any]
    # === End NoemaForge Autodoc Function Header ===
    def as_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)
