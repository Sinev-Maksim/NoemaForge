#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tools/prep/scan_tabs.py
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
# File: tools/prep/scan_tabs.py
# Purpose: Prepare or ingest external assets for 'scan_tabs'.
# Invoked by / imported from:
#   - No inbound Python import detected; treat as library leaf or direct entrypoint.
# Public API / entry functions:
#   - ingest_file
#   - main
# Inputs:
#   - --lab-root
#   - Imports: __future__, argparse, hashlib, json, os, sqlite3, sys, datetime
# Output formats / side effects:
#   - SQLite databases
#   - JSON files
#   - UTF-8 text files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""scan_tabs.py (v0.25.1)

Offline ingest for reading-list / open-tabs exports.

Input
-----
Place one or more files into:
  <LabRoot>/data/Workspace/inbox/tabs/

Supported formats:
  - .txt : one URL per line
  - .json: list of objects or list of strings

Output
------
Creates/updates:
  <LabRoot>/data/Indexes/tabs_index.sqlite
  <LabRoot>/data/Workspace/outbox/tabs/tabs_ingest.seed.json
"""


import argparse
import hashlib
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


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
#   - strftime, now
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _nowz() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# === NoemaForge Autodoc Function Header ===
# Function: _ensure_parent(path: Path)
# Purpose: Implement the routine ' ensure parent'.
# Inputs:
#   - path: Path
# Called by:
#   - src/dream_cycle.py
#   - src/roadmap.py
#   - src/session_memory_extractor.py
#   - src/task_tools.py
#   - src/taskqueue.py
#   - src/telemetry.py
#   - tools/prep/scan_tg.py
# Calls:
#   - mkdir
# Returns / emits: None
# === End NoemaForge Autodoc Function Header ===
def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


# === NoemaForge Autodoc Function Header ===
# Function: _sha256_file(p: Path, max_bytes: int = 64 * 1024 * 1024)
# Purpose: Implement the routine ' sha256 file'.
# Inputs:
#   - p: Path
#   - max_bytes: int = 64 * 1024 * 1024
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
#   - sha256, hexdigest, open, read, update, len
# Returns / emits: str
# Side effects:
#   - reads or writes files
# Key locals:
#   - b, f, h, n
# === End NoemaForge Autodoc Function Header ===
def _sha256_file(p: Path, *, max_bytes: int = 64 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    n = 0
    with p.open("rb") as f:
        while True:
            b = f.read(1024 * 1024)
            if not b:
                break
            h.update(b)
            n += len(b)
            if n > max_bytes:
                break
    return h.hexdigest()


# === NoemaForge Autodoc Function Header ===
# Function: _connect(db_path: Path)
# Purpose: Implement the routine ' connect'.
# Inputs:
#   - db_path: Path
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
#   - _ensure_parent, connect, execute, str
# Returns / emits: sqlite3.Connection
# Side effects:
#   - opens a database or socket connection
#   - executes SQL or shell-like commands
# Key locals:
#   - con
# === End NoemaForge Autodoc Function Header ===
def _connect(db_path: Path) -> sqlite3.Connection:
    _ensure_parent(db_path)
    con = sqlite3.connect(str(db_path))
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA synchronous=NORMAL;")
    return con


# === NoemaForge Autodoc Function Header ===
# Function: _init_db(con: sqlite3.Connection)
# Purpose: Implement the routine ' init db'.
# Inputs:
#   - con: sqlite3.Connection
# Called by:
#   - src/knowledge/store.py
#   - src/memory_system.py
#   - src/vstore.py
#   - tools/prep/scan_tg.py
# Calls:
#   - executescript
# Returns / emits: None
# Side effects:
#   - executes SQL or shell-like commands
# === End NoemaForge Autodoc Function Header ===
def _init_db(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS source_files (
            path TEXT PRIMARY KEY,
            size INTEGER,
            mtime_ns INTEGER,
            sha256 TEXT,
            indexed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS tabs (
            url TEXT PRIMARY KEY,
            title TEXT,
            source_file TEXT,
            added_at TEXT,
            last_seen_at TEXT,
            status TEXT
        );
        """
    )


# === NoemaForge Autodoc Function Header ===
# Function: _import_pi_firewall()
# Purpose: Implement the routine ' import pi firewall'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - tools/prep/scan_tg.py
# Calls:
#   - resolve, str, insert, Path
# Returns / emits: Tuple[Any, Any]
# Key locals:
#   - here, src_dir
# === End NoemaForge Autodoc Function Header ===
def _import_pi_firewall() -> Tuple[Any, Any]:
    here = Path(__file__).resolve()
    src_dir = (here.parent.parent.parent / "src").resolve()
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))
    try:
        from pi_firewall import scan_text, redact_instruction_like_lines  # type: ignore

        return scan_text, redact_instruction_like_lines
    except Exception:
        return None, None


# === NoemaForge Autodoc Function Header ===
# Function: _iter_urls_from_txt(p: Path)
# Purpose: Implement the routine ' iter urls from txt'.
# Inputs:
#   - p: Path
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - splitlines, strip, read_text, startswith
# Returns / emits: Iterable[Tuple[str, str]]
# Key locals:
#   - ln, s
# === End NoemaForge Autodoc Function Header ===
def _iter_urls_from_txt(p: Path) -> Iterable[Tuple[str, str]]:
    for ln in p.read_text(encoding="utf-8", errors="ignore").splitlines():
        s = (ln or "").strip()
        if not s or s.startswith("#"):
            continue
        yield s, ""


# === NoemaForge Autodoc Function Header ===
# Function: _iter_urls_from_json(p: Path)
# Purpose: Implement the routine ' iter urls from json'.
# Inputs:
#   - p: Path
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - isinstance, loads, read_text, strip, str, get
# Returns / emits: Iterable[Tuple[str, str]]
# Key locals:
#   - it, obj, title, url
# === End NoemaForge Autodoc Function Header ===
def _iter_urls_from_json(p: Path) -> Iterable[Tuple[str, str]]:
    try:
        obj = json.loads(p.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return
    if isinstance(obj, list):
        for it in obj:
            if isinstance(it, str):
                yield it.strip(), ""
            elif isinstance(it, dict):
                url = str(it.get("url") or it.get("href") or "").strip()
                title = str(it.get("title") or it.get("name") or "").strip()
                if url:
                    yield url, title


# === NoemaForge Autodoc Function Header ===
# Function: ingest_file(con: sqlite3.Connection, p: Path)
# Purpose: Implement the routine 'ingest file'.
# Inputs:
#   - con: sqlite3.Connection
#   - p: Path
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _import_pi_firewall, lower, _iter_urls_from_txt, execute, _iter_urls_from_json, scan_text, str, _nowz, get
# Returns / emits: Dict[str, int]
# Side effects:
#   - executes SQL or shell-like commands
# Key locals:
#   - added, cur, it, rep, sev, skipped, status, url2
# === End NoemaForge Autodoc Function Header ===
def ingest_file(con: sqlite3.Connection, p: Path) -> Dict[str, int]:
    scan_text, redact_lines = _import_pi_firewall()
    added = 0
    skipped = 0

    it: Iterable[Tuple[str, str]]
    if p.suffix.lower() == ".txt":
        it = _iter_urls_from_txt(p)
    elif p.suffix.lower() == ".json":
        it = _iter_urls_from_json(p)
    else:
        return {"files": 1, "tabs_added": 0, "tabs_skipped": 1}

    for url, title in it:
        if not url:
            continue
        url2 = url
        # PI scan on URL string (rare, but can be abused via query strings)
        if scan_text and redact_lines:
            rep = scan_text(url2, source=f"tabs:{p.name}")
            sev = str(rep.get("severity") or "none")
            if sev in ("medium", "high"):
                # keep but mark as needs review
                status = "needs_review"
            else:
                status = "new"
        else:
            status = "new"

        cur = con.execute(
            "INSERT OR IGNORE INTO tabs(url,title,source_file,added_at,last_seen_at,status) VALUES(?,?,?,?,?,?)",
            (url2, title, str(p), _nowz(), _nowz(), status),
        )
        if cur.rowcount and cur.rowcount > 0:
            added += 1
        else:
            # Already known; bump last_seen
            con.execute("UPDATE tabs SET last_seen_at=? WHERE url=?", (_nowz(), url2))
            skipped += 1

    return {"files": 1, "tabs_added": added, "tabs_skipped": skipped}


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
#   - ArgumentParser, add_argument, parse_args, resolve, _ensure_parent, _connect, _init_db, exists, commit, close, write_text, print
# Returns / emits: int
# Side effects:
#   - writes UTF-8 text
#   - opens a database or socket connection
# Key locals:
#   - ap, args, con, db_path, inbox, k, lab, out_seed, p, res, row, seed
# === End NoemaForge Autodoc Function Header ===
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lab-root", required=True)
    args = ap.parse_args()

    lab = Path(args.lab_root).resolve()
    inbox = lab / "data" / "Workspace" / "inbox" / "tabs"
    db_path = lab / "data" / "Indexes" / "tabs_index.sqlite"
    out_seed = lab / "data" / "Workspace" / "outbox" / "tabs" / "tabs_ingest.seed.json"
    _ensure_parent(out_seed)

    con = _connect(db_path)
    _init_db(con)

    total = {"files": 0, "tabs_added": 0, "tabs_skipped": 0}
    if inbox.exists():
        for p in sorted(inbox.iterdir()):
            if not p.is_file():
                continue
            if p.suffix.lower() not in (".txt", ".json"):
                continue
            st = p.stat()
            sha = _sha256_file(p)
            row = con.execute("SELECT sha256, size, mtime_ns FROM source_files WHERE path=?", (str(p),)).fetchone()
            if row and row[0] == sha and int(row[1] or 0) == int(st.st_size) and int(row[2] or 0) == int(st.st_mtime_ns):
                continue
            con.execute(
                "INSERT OR REPLACE INTO source_files(path,size,mtime_ns,sha256,indexed_at) VALUES(?,?,?,?,?)",
                (str(p), int(st.st_size), int(st.st_mtime_ns), sha, _nowz()),
            )
            res = ingest_file(con, p)
            for k in total:
                total[k] += int(res.get(k, 0))
            total["files"] += 1

    con.commit()
    con.close()

    seed = {"ts": _nowz(), "inbox": str(inbox), "db": str(db_path), "counts": total}
    out_seed.write_text(json.dumps(seed, ensure_ascii=False, indent=2), encoding="utf-8")

    print("OK")
    print(str(db_path))
    print(str(out_seed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
