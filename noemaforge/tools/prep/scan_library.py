#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tools/prep/scan_library.py
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
# File: tools/prep/scan_library.py
# Purpose: Prepare or ingest external assets for 'scan_library'.
# Invoked by / imported from:
#   - No inbound Python import detected; treat as library leaf or direct entrypoint.
# Public API / entry functions:
#   - manifest_path_for
#   - load_manifest
#   - write_skeleton_manifest
#   - scan
#   - main
# Inputs:
#   - --library-root
#   - --sources-dir
#   - --db-name
#   - --snapshot-name
#   - --auto-manifest
#   - --full-hash
#   - Common path inputs: noemaforge.library/v1, library_index/v1, noemaforge.library_catalog/v1
#   - Imports: __future__, sys, argparse, os, sqlite3, typing, prep_common, json
# Output formats / side effects:
#   - JSON files
#   - SQLite databases
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""Incremental Library scanner.

Creates/updates:
  - <library_root>/library_index.sqlite
  - <library_root>/library_catalog.seed.json (snapshot)

It avoids full hashing for unchanged files.

Conventions
-----------
Library root contains:
  sources/   (content files: pdf, md, etc)
  manifests/ (json manifests; mirrored tree)

A source manifest is stored at:
  manifests/<rel_path>.json
Example:
  sources/books/foo.pdf
  manifests/sources/books/foo.pdf.json

This mirroring makes the mapping deterministic and avoids collisions.
"""


import sys
sys.dont_write_bytecode = True

import argparse
import os
import sqlite3
from typing import Any, Dict, List, Optional

from prep_common import (
    ScanStats,
    ensure_dir,
    get_meta,
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
# Function: _init_schema(conn: sqlite3.Connection)
# Purpose: Implement the routine ' init schema'.
# Inputs:
#   - conn: sqlite3.Connection
# Called by:
#   - src/roadmap.py
#   - src/taskqueue.py
#   - tools/prep/scan_vault.py
# Calls:
#   - execute
# Returns / emits: None
# Side effects:
#   - executes SQL or shell-like commands
# === End NoemaForge Autodoc Function Header ===
def _init_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS files (
          rel_path TEXT PRIMARY KEY,
          size INTEGER NOT NULL,
          mtime_ns INTEGER NOT NULL,
          quick_fp TEXT,
          sha256 TEXT,
          status TEXT NOT NULL,
          source_id TEXT,
          manifest_rel_path TEXT,
          last_seen_at TEXT NOT NULL,
          created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sources (
          source_id TEXT PRIMARY KEY,
          title TEXT,
          source_kind TEXT,
          language TEXT,
          tags_json TEXT,
          trust TEXT,
          ingest_status TEXT,
          rel_path TEXT,
          sha256 TEXT,
          manifest_rel_path TEXT,
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
#   - tools/prep/scan_vault.py
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def manifest_path_for(rel_path: str) -> str:
    # Mirror the tree.
    return f"manifests/{rel_path}.json"


# === NoemaForge Autodoc Function Header ===
# Function: load_manifest(library_root: str, manifest_rel_path: str)
# Purpose: Implement the routine 'load manifest'.
# Inputs:
#   - library_root: str
#   - manifest_rel_path: str
# Called by:
#   - tools/prep/scan_vault.py
# Calls:
#   - join, exists, read_json
# Returns / emits: Optional[Dict[str, Any]]
# Key locals:
#   - mp
# === End NoemaForge Autodoc Function Header ===
def load_manifest(library_root: str, manifest_rel_path: str) -> Optional[Dict[str, Any]]:
    mp = os.path.join(library_root, manifest_rel_path)
    if not os.path.exists(mp):
        return None
    try:
        return read_json(mp)
    except Exception:
        return None


# === NoemaForge Autodoc Function Header ===
# Function: write_skeleton_manifest(library_root: str, manifest_rel_path: str, source_id: str, rel_path: str, sha256: Optional[str])
# Purpose: Implement the routine 'write skeleton manifest'.
# Inputs:
#   - library_root: str
#   - manifest_rel_path: str
#   - source_id: str
#   - rel_path: str
#   - sha256: Optional[str]
# Called by:
#   - tools/prep/scan_vault.py
# Calls:
#   - join, exists, ensure_dir, write_json, dirname
# Returns / emits: None
# Key locals:
#   - mp, obj
# === End NoemaForge Autodoc Function Header ===
def write_skeleton_manifest(
    library_root: str,
    manifest_rel_path: str,
    source_id: str,
    rel_path: str,
    sha256: Optional[str],
) -> None:
    mp = os.path.join(library_root, manifest_rel_path)
    if os.path.exists(mp):
        return
    ensure_dir(os.path.dirname(mp) or ".")
    obj: Dict[str, Any] = {
        "apiVersion": "noemaforge.library/v1",
        "kind": "LibraryManifest",
        "source_id": source_id,
        "rel_path": rel_path,
        "sha256": sha256 or "",
        "title": "",
        "source_kind": "other",
        "language": "",
        "tags": [],
        "trust": "unknown",
        "ingest": {"status": "new"},
    }
    write_json(mp, obj)


# === NoemaForge Autodoc Function Header ===
# Function: scan(args: argparse.Namespace)
# Purpose: Implement the routine 'scan'.
# Inputs:
#   - args: argparse.Namespace
# Called by:
#   - tools/prep/scan_vault.py
# Calls:
#   - abspath, join, open_db, _init_schema, set_meta, ScanStats, walk, execute, set, sorted, commit, fetchall
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads or writes files
#   - executes SQL or shell-like commands
# Key locals:
#   - abs_path, conn, created_at, cur, db_path, fn, ing, ingest_status, items, language, library_root, m
# === End NoemaForge Autodoc Function Header ===
def scan(args: argparse.Namespace) -> Dict[str, Any]:
    library_root = os.path.abspath(args.library_root)
    sources_root = os.path.join(library_root, args.sources_dir)
    db_path = os.path.join(library_root, args.db_name)
    snapshot_path = os.path.join(library_root, args.snapshot_name)

    if not os.path.isdir(sources_root):
        raise SystemExit(f"Sources dir not found: {sources_root}")

    conn = open_db(db_path)
    _init_schema(conn)

    set_meta(conn, "schema", "library_index/v1")
    set_meta(conn, "library_root", library_root)
    set_meta(conn, "sources_dir", args.sources_dir)
    set_meta(conn, "last_scan_started_at", nowz())

    stats = ScanStats()
    seen: List[str] = []

    for dp, _, fns in os.walk(sources_root):
        for fn in fns:
            # Skip temp files.
            if fn.startswith("~") or fn.endswith(".tmp"):
                continue
            abs_path = os.path.join(dp, fn)
            rel_path = safe_relpath(abs_path, library_root)
            seen.append(rel_path)
            stats.scanned += 1

            st = os.stat(abs_path)
            size = int(st.st_size)
            mtime_ns = int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9)))

            cur = conn.execute(
                "SELECT size, mtime_ns, quick_fp, sha256, status, source_id FROM files WHERE rel_path=?",
                (rel_path,),
            )
            row = cur.fetchone()

            manifest_rel = manifest_path_for(rel_path)

            if row and row[0] == size and row[1] == mtime_ns and (row[4] == "present"):
                stats.unchanged += 1
                conn.execute(
                    "UPDATE files SET last_seen_at=? WHERE rel_path=?",
                    (nowz(), rel_path),
                )
                continue

            # New or changed.
            prev_sha = row[3] if row else None
            prev_source_id = row[5] if row else None

            qfp = quick_fingerprint(abs_path)
            stats.hashed_quick += 1

            need_full = args.full_hash
            if not need_full:
                if not prev_sha:
                    need_full = True
                else:
                    # If quick_fp changed, we should update sha.
                    prev_qfp = row[2] if row else None
                    if prev_qfp != qfp:
                        need_full = True

            sha = prev_sha
            if need_full:
                sha = sha256_file(abs_path)
                stats.hashed_full += 1

            # Source id: from manifest -> existing -> derived.
            m = load_manifest(library_root, manifest_rel)
            source_id = None
            if m and isinstance(m, dict) and m.get("source_id"):
                source_id = str(m.get("source_id"))
            if not source_id:
                source_id = prev_source_id or stable_id("src", rel_path)

            created_at = row[0] if row and row[0] else nowz()

            if row:
                stats.changed_files += 1
                conn.execute(
                    """
                    UPDATE files
                    SET size=?, mtime_ns=?, quick_fp=?, sha256=?, status='present', source_id=?, manifest_rel_path=?, last_seen_at=?
                    WHERE rel_path=?
                    """,
                    (size, mtime_ns, qfp, sha, source_id, manifest_rel, nowz(), rel_path),
                )
            else:
                stats.new_files += 1
                conn.execute(
                    """
                    INSERT INTO files(rel_path,size,mtime_ns,quick_fp,sha256,status,source_id,manifest_rel_path,last_seen_at,created_at)
                    VALUES(?,?,?,?,?,'present',?,?,?,?)
                    """,
                    (rel_path, size, mtime_ns, qfp, sha, source_id, manifest_rel, nowz(), nowz()),
                )

            if args.auto_manifest:
                write_skeleton_manifest(library_root, manifest_rel, source_id, rel_path, sha)

            # Update sources table from manifest if present.
            m = load_manifest(library_root, manifest_rel)
            title = (m or {}).get("title") if isinstance(m, dict) else None
            source_kind = (m or {}).get("source_kind") if isinstance(m, dict) else None
            language = (m or {}).get("language") if isinstance(m, dict) else None
            tags = (m or {}).get("tags") if isinstance(m, dict) else None
            trust = (m or {}).get("trust") if isinstance(m, dict) else None
            ingest_status = None
            if isinstance(m, dict):
                ing = m.get("ingest")
                if isinstance(ing, dict):
                    ingest_status = ing.get("status")

            import json

            conn.execute(
                """
                INSERT INTO sources(source_id,title,source_kind,language,tags_json,trust,ingest_status,rel_path,sha256,manifest_rel_path,updated_at,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(source_id) DO UPDATE SET
                  title=excluded.title,
                  source_kind=excluded.source_kind,
                  language=excluded.language,
                  tags_json=excluded.tags_json,
                  trust=excluded.trust,
                  ingest_status=excluded.ingest_status,
                  rel_path=excluded.rel_path,
                  sha256=excluded.sha256,
                  manifest_rel_path=excluded.manifest_rel_path,
                  updated_at=excluded.updated_at
                """,
                (
                    source_id,
                    title or "",
                    source_kind or "other",
                    language or "",
                    json.dumps(tags or []),
                    trust or "unknown",
                    ingest_status or "new",
                    rel_path,
                    sha or "",
                    manifest_rel,
                    nowz(),
                    nowz(),
                ),
            )

    # Tombstone anything not seen.
    cur = conn.execute("SELECT rel_path FROM files WHERE status='present'")
    present = {r[0] for r in cur.fetchall()}
    seen_set = set(seen)
    missing = sorted(list(present - seen_set))
    for rel_path in missing:
        stats.tombstoned += 1
        conn.execute(
            "UPDATE files SET status='tombstoned', last_seen_at=? WHERE rel_path=?",
            (nowz(), rel_path),
        )

    set_meta(conn, "last_scan_finished_at", nowz())
    conn.commit()

    # Snapshot
    cur = conn.execute(
        "SELECT source_id,title,source_kind,language,tags_json,trust,ingest_status,rel_path,sha256,manifest_rel_path,updated_at FROM sources"
    )
    rows = cur.fetchall()

    import json

    items: List[Dict[str, Any]] = []
    for r in rows:
        items.append(
            {
                "source_id": r[0],
                "title": r[1],
                "source_kind": r[2],
                "language": r[3],
                "tags": json.loads(r[4] or "[]"),
                "trust": r[5],
                "ingest_status": r[6],
                "rel_path": r[7],
                "sha256": r[8],
                "manifest_rel_path": r[9],
                "updated_at": r[10],
            }
        )

    snap = {
        "apiVersion": "noemaforge.library_catalog/v1",
        "kind": "LibraryCatalogSnapshot",
        "created_at": nowz(),
        "library_root": library_root.replace("\\", "/"),
        "sources_dir": args.sources_dir,
        "count": len(items),
        "items": items,
        "scan_stats": stats.as_dict(),
    }

    write_json(snapshot_path, snap)

    return {
        "db_path": db_path,
        "snapshot_path": snapshot_path,
        "stats": stats.as_dict(),
    }


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
    ap.add_argument("--library-root", required=True, help="Path to Library root")
    ap.add_argument("--sources-dir", default="sources", help="Subdir under library-root")
    ap.add_argument("--db-name", default="library_index.sqlite")
    ap.add_argument("--snapshot-name", default="library_catalog.seed.json")
    ap.add_argument("--auto-manifest", action="store_true", help="Create skeleton manifests for new files")
    ap.add_argument("--full-hash", action="store_true", help="Force sha256 for all files")
    args = ap.parse_args()

    out = scan(args)
    print("OK")
    print(out["db_path"])
    print(out["snapshot_path"])


if __name__ == "__main__":
    main()
