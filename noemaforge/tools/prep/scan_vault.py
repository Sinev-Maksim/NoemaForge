#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tools/prep/scan_vault.py
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
# File: tools/prep/scan_vault.py
# Purpose: Prepare or ingest external assets for 'scan_vault'.
# Invoked by / imported from:
#   - No inbound Python import detected; treat as library leaf or direct entrypoint.
# Public API / entry functions:
#   - detect_bucket_roots
#   - manifest_path_for
#   - load_manifest
#   - write_skeleton_manifest
#   - detect_kind
#   - scan
#   - main
# Inputs:
#   - --vault-root
#   - --db-name
#   - --snapshot-name
#   - --auto-manifest
#   - --full-hash
#   - Common path inputs: noemaforge.vault/v1, vault_index/v1, noemaforge.vault_registry/v1
#   - Imports: __future__, sys, argparse, os, sqlite3, typing, prep_common, json
# Output formats / side effects:
#   - JSON files
#   - SQLite databases
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""Incremental Vault scanner (models/adapters/bundles).

Creates/updates:
  - <vault_root>/vault_index.sqlite
  - <vault_root>/model_registry.seed.json (snapshot)

Conventions
-----------
Vault root contains:
  models/    (gguf, etc)
  adapters/
  bundles/
  manifests/ (json manifests; mirrored tree)

A manifest is stored at:
  manifests/<rel_path>.json
Example:
  models/phi-mini/model.gguf
  manifests/models/phi-mini/model.gguf.json

This file only inventories artifacts. Which models are actually used is decided
by epoch policy (role-model-policy / team-model-policy) and SSR/Surgeon.
"""


import sys
sys.dont_write_bytecode = True

import argparse
import os
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from prep_common import (
    ScanStats,
    ensure_dir,
    nowz,
    open_db,
    quick_fingerprint,
    read_json,
    safe_relpath,
    set_meta,
    sha256_file,
    stable_id,
    write_json,
)


# === NoemaForge Autodoc Function Header ===
# Function: detect_bucket_roots(vault_root: str)
# Purpose: Return bucket roots for Vault scanning.
# Inputs:
#   - vault_root: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - sort, _find, listdir, join, isdir, startswith, append, lower, basename
# Returns / emits: Dict[str, List[str]]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - buckets, name, out, p
# === End NoemaForge Autodoc Function Header ===
def detect_bucket_roots(vault_root: str) -> Dict[str, List[str]]:
    """Return bucket roots for Vault scanning.

    Requirement: models may live in N+1 folders (N>=0), e.g.:
      - Vault/models
      - Vault/models-gguf
      - Vault/models-hf

    We extend the same pattern to adapters*/bundles* for future growth.
    """

    # === NoemaForge Autodoc Function Header ===
    # Function: _find(prefix: str, canonical: str)
    # Purpose: Implement the routine ' find'.
    # Inputs:
    #   - prefix: str
    #   - canonical: str
    # Called by:
    #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
    # Calls:
    #   - sort, listdir, join, isdir, startswith, append, lower, basename
    # Returns / emits: List[str]
    # Side effects:
    #   - appends to logs or files
    # Key locals:
    #   - name, out, p
    # === End NoemaForge Autodoc Function Header ===
    def _find(prefix: str, canonical: str) -> List[str]:
        out: List[str] = []
        try:
            for name in os.listdir(vault_root):
                p = os.path.join(vault_root, name)
                if os.path.isdir(p) and name.lower().startswith(prefix):
                    out.append(p)
        except FileNotFoundError:
            return []

        out.sort(
            key=lambda x: (
                0 if os.path.basename(x).lower() == canonical else 1,
                os.path.basename(x).lower(),
            )
        )
        return out

    buckets = {
        "models": _find("models", "models"),
        "adapters": _find("adapters", "adapters"),
        "bundles": _find("bundles", "bundles"),
    }

    # Backward-compatible fallbacks.
    if not buckets["models"]:
        buckets["models"] = [os.path.join(vault_root, "models")]
    if not buckets["adapters"]:
        buckets["adapters"] = [os.path.join(vault_root, "adapters")]
    if not buckets["bundles"]:
        buckets["bundles"] = [os.path.join(vault_root, "bundles")]

    return buckets


# === NoemaForge Autodoc Function Header ===
# Function: _init_schema(conn: sqlite3.Connection)
# Purpose: Implement the routine ' init schema'.
# Inputs:
#   - conn: sqlite3.Connection
# Called by:
#   - src/roadmap.py
#   - src/taskqueue.py
#   - tools/prep/scan_library.py
# Calls:
#   - execute
# Returns / emits: None
# Side effects:
#   - executes SQL or shell-like commands
# === End NoemaForge Autodoc Function Header ===
def _init_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS artifacts (
          rel_path TEXT PRIMARY KEY,
          size INTEGER NOT NULL,
          mtime_ns INTEGER NOT NULL,
          quick_fp TEXT,
          sha256 TEXT,
          status TEXT NOT NULL,
          artifact_id TEXT,
          artifact_kind TEXT,
          manifest_rel_path TEXT,
          trust TEXT,
          model_family TEXT,
          format TEXT,
          intended_roles_json TEXT,
          updated_at TEXT NOT NULL,
          created_at TEXT NOT NULL
        )
        """
    )


# === NoemaForge Autodoc Function Header ===
# Function: manifest_path_for(rel_path: str)
# Purpose: Implement the routine 'manifest path for'.
# Inputs:
#   - rel_path: str
# Called by:
#   - tools/prep/scan_library.py
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def manifest_path_for(rel_path: str) -> str:
    return f"manifests/{rel_path}.json"


# === NoemaForge Autodoc Function Header ===
# Function: load_manifest(vault_root: str, manifest_rel_path: str)
# Purpose: Implement the routine 'load manifest'.
# Inputs:
#   - vault_root: str
#   - manifest_rel_path: str
# Called by:
#   - tools/prep/scan_library.py
# Calls:
#   - join, exists, read_json
# Returns / emits: Optional[Dict[str, Any]]
# Key locals:
#   - mp
# === End NoemaForge Autodoc Function Header ===
def load_manifest(vault_root: str, manifest_rel_path: str) -> Optional[Dict[str, Any]]:
    mp = os.path.join(vault_root, manifest_rel_path)
    if not os.path.exists(mp):
        return None
    try:
        return read_json(mp)
    except Exception:
        return None


# === NoemaForge Autodoc Function Header ===
# Function: write_skeleton_manifest(vault_root: str, manifest_rel_path: str, artifact_id: str, rel_path: str, sha256: Optional[str], artifact_kind: str)
# Purpose: Implement the routine 'write skeleton manifest'.
# Inputs:
#   - vault_root: str
#   - manifest_rel_path: str
#   - artifact_id: str
#   - rel_path: str
#   - sha256: Optional[str]
#   - artifact_kind: str
# Called by:
#   - tools/prep/scan_library.py
# Calls:
#   - join, exists, ensure_dir, write_json, dirname
# Returns / emits: None
# Key locals:
#   - mp, obj
# === End NoemaForge Autodoc Function Header ===
def write_skeleton_manifest(
    vault_root: str,
    manifest_rel_path: str,
    artifact_id: str,
    rel_path: str,
    sha256: Optional[str],
    artifact_kind: str,
) -> None:
    mp = os.path.join(vault_root, manifest_rel_path)
    if os.path.exists(mp):
        return
    ensure_dir(os.path.dirname(mp) or ".")
    obj: Dict[str, Any] = {
        "apiVersion": "noemaforge.vault/v1",
        "kind": "VaultArtifactManifest",
        "artifact_id": artifact_id,
        "artifact_kind": artifact_kind,
        "rel_path": rel_path,
        "sha256": sha256 or "",
        "model_family": "",
        "format": "",
        "trust": "unknown",
        "intended_roles": [],
        "capabilities": {},
        "meta": {},
    }
    write_json(mp, obj)


# === NoemaForge Autodoc Function Header ===
# Function: detect_kind(rel_path: str)
# Purpose: Implement the routine 'detect kind'.
# Inputs:
#   - rel_path: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - replace, startswith
# Returns / emits: str
# Key locals:
#   - p
# === End NoemaForge Autodoc Function Header ===
def detect_kind(rel_path: str) -> str:
    p = rel_path.replace("\\", "/")
    # models may live in models*/ (models, models-gguf, ...)
    if p.startswith("models/") or p.startswith("models-"):
        return "llm"
    if p.startswith("adapters/") or p.startswith("adapters-"):
        return "adapter"
    if p.startswith("bundles/") or p.startswith("bundles-"):
        return "bundle"
    return "other"


# === NoemaForge Autodoc Function Header ===
# Function: scan(args: argparse.Namespace)
# Purpose: Implement the routine 'scan'.
# Inputs:
#   - args: argparse.Namespace
# Called by:
#   - tools/prep/scan_library.py
# Calls:
#   - abspath, join, open_db, _init_schema, set_meta, ScanStats, detect_bucket_roots, extend, list, execute, sorted, commit
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads or writes files
#   - executes SQL or shell-like commands
# Key locals:
#   - abs_path, artifact_id, artifact_kind, buckets, conn, cur, db_path, fmt, fn, intended_roles, items, m
# === End NoemaForge Autodoc Function Header ===
def scan(args: argparse.Namespace) -> Dict[str, Any]:
    vault_root = os.path.abspath(args.vault_root)
    db_path = os.path.join(vault_root, args.db_name)
    snapshot_path = os.path.join(vault_root, args.snapshot_name)

    conn = open_db(db_path)
    _init_schema(conn)

    set_meta(conn, "schema", "vault_index/v1")
    set_meta(conn, "vault_root", vault_root)
    set_meta(conn, "last_scan_started_at", nowz())

    stats = ScanStats()
    seen: List[str] = []

    # N+1 bucket roots (models*, adapters*, bundles*)
    buckets = detect_bucket_roots(vault_root)
    roots: List[str] = []
    roots.extend(buckets.get("models", []))
    roots.extend(buckets.get("adapters", []))
    roots.extend(buckets.get("bundles", []))

    # De-dup and keep deterministic order.
    roots = [os.path.abspath(p) for p in roots]
    roots = list(dict.fromkeys(roots).keys())

    for r in roots:
        if not os.path.isdir(r):
            continue
        for dp, _, fns in os.walk(r):
            for fn in fns:
                if fn.startswith("~") or fn.endswith(".tmp"):
                    continue
                abs_path = os.path.join(dp, fn)
                rel_path = safe_relpath(abs_path, vault_root)
                seen.append(rel_path)
                stats.scanned += 1

                st = os.stat(abs_path)
                size = int(st.st_size)
                mtime_ns = int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9)))

                cur = conn.execute(
                    "SELECT size, mtime_ns, quick_fp, sha256, status, artifact_id, artifact_kind FROM artifacts WHERE rel_path=?",
                    (rel_path,),
                )
                row = cur.fetchone()

                if row and row[0] == size and row[1] == mtime_ns and (row[4] == "present"):
                    stats.unchanged += 1
                    continue

                qfp = quick_fingerprint(abs_path)
                stats.hashed_quick += 1

                prev_sha = row[3] if row else None
                prev_qfp = row[2] if row else None

                need_full = args.full_hash
                if not need_full:
                    if not prev_sha:
                        need_full = True
                    elif prev_qfp != qfp:
                        need_full = True

                sha = prev_sha
                if need_full:
                    sha = sha256_file(abs_path)
                    stats.hashed_full += 1

                manifest_rel = manifest_path_for(rel_path)
                m = load_manifest(vault_root, manifest_rel)

                artifact_kind = None
                if isinstance(m, dict) and m.get("artifact_kind"):
                    artifact_kind = str(m.get("artifact_kind"))
                if not artifact_kind:
                    artifact_kind = detect_kind(rel_path)

                artifact_id = None
                if isinstance(m, dict) and m.get("artifact_id"):
                    artifact_id = str(m.get("artifact_id"))
                if not artifact_id:
                    artifact_id = (row[5] if row else None) or stable_id("art", rel_path)

                import json

                model_family = (m or {}).get("model_family") if isinstance(m, dict) else None
                fmt = (m or {}).get("format") if isinstance(m, dict) else None
                trust = (m or {}).get("trust") if isinstance(m, dict) else None
                intended_roles = (m or {}).get("intended_roles") if isinstance(m, dict) else None

                if row:
                    stats.changed_files += 1
                    conn.execute(
                        """
                        UPDATE artifacts
                        SET size=?, mtime_ns=?, quick_fp=?, sha256=?, status='present', artifact_id=?, artifact_kind=?, manifest_rel_path=?, trust=?, model_family=?, format=?, intended_roles_json=?, updated_at=?
                        WHERE rel_path=?
                        """,
                        (
                            size,
                            mtime_ns,
                            qfp,
                            sha,
                            artifact_id,
                            artifact_kind,
                            manifest_rel,
                            trust or "unknown",
                            model_family or "",
                            fmt or "",
                            json.dumps(intended_roles or []),
                            nowz(),
                            rel_path,
                        ),
                    )
                else:
                    stats.new_files += 1
                    conn.execute(
                        """
                        INSERT INTO artifacts(rel_path,size,mtime_ns,quick_fp,sha256,status,artifact_id,artifact_kind,manifest_rel_path,trust,model_family,format,intended_roles_json,updated_at,created_at)
                        VALUES(?,?,?,?,?,'present',?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            rel_path,
                            size,
                            mtime_ns,
                            qfp,
                            sha,
                            artifact_id,
                            artifact_kind,
                            manifest_rel,
                            trust or "unknown",
                            model_family or "",
                            fmt or "",
                            json.dumps(intended_roles or []),
                            nowz(),
                            nowz(),
                        ),
                    )

                if args.auto_manifest:
                    write_skeleton_manifest(vault_root, manifest_rel, artifact_id, rel_path, sha, artifact_kind)

    # Tombstone anything present but not seen.
    cur = conn.execute("SELECT rel_path FROM artifacts WHERE status='present'")
    present = {r[0] for r in cur.fetchall()}
    missing = sorted(list(present - set(seen)))
    for rel_path in missing:
        stats.tombstoned += 1
        conn.execute(
            "UPDATE artifacts SET status='tombstoned', updated_at=? WHERE rel_path=?",
            (nowz(), rel_path),
        )

    set_meta(conn, "last_scan_finished_at", nowz())
    conn.commit()

    # Snapshot
    cur = conn.execute(
        "SELECT artifact_id, artifact_kind, rel_path, sha256, trust, model_family, format, intended_roles_json, status, updated_at FROM artifacts"
    )
    rows = cur.fetchall()

    import json

    items: List[Dict[str, Any]] = []
    for r in rows:
        items.append(
            {
                "artifact_id": r[0],
                "artifact_kind": r[1],
                "rel_path": r[2],
                "sha256": r[3],
                "trust": r[4],
                "model_family": r[5],
                "format": r[6],
                "intended_roles": json.loads(r[7] or "[]"),
                "status": r[8],
                "updated_at": r[9],
            }
        )

    snap = {
        "apiVersion": "noemaforge.vault_registry/v1",
        "kind": "VaultRegistrySnapshot",
        "created_at": nowz(),
        "vault_root": vault_root.replace("\\", "/"),
        "count": len(items),
        "items": items,
        "scan_stats": stats.as_dict(),
    }

    write_json(snapshot_path, snap)
    conn.close()

    return {"db_path": db_path, "snapshot_path": snapshot_path, "stats": stats.as_dict()}


# === NoemaForge Autodoc Function Header ===
# Function: main()
# Purpose: Implement the routine 'main'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - bootstrap/microvm/noemaforge-microvm-run.py
#   - src/bootdoctor.py
#   - src/brainctl.py
#   - src/noemaforge_core.py
#   - src/brainui.py
#   - src/canary_runner.py
#   - src/doctor.py
#   - src/dream_cycle.py
# Calls:
#   - ArgumentParser, add_argument, parse_args, scan, print
# Returns / emits: None
# Key locals:
#   - ap, args, out
# === End NoemaForge Autodoc Function Header ===
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault-root", required=True, help="Path to Vault root")
    ap.add_argument("--db-name", default="vault_index.sqlite")
    ap.add_argument("--snapshot-name", default="model_registry.seed.json")
    ap.add_argument("--auto-manifest", action="store_true")
    ap.add_argument("--full-hash", action="store_true")
    args = ap.parse_args()

    out = scan(args)
    print("OK")
    print(out["db_path"])
    print(out["snapshot_path"])


if __name__ == "__main__":
    main()
