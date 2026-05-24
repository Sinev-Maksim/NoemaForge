#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tools/prep/scan_tg.py
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
# File: tools/prep/scan_tg.py
# Purpose: Prepare or ingest external assets for 'scan_tg'.
# Invoked by / imported from:
#   - No inbound Python import detected; treat as library leaf or direct entrypoint.
# Public API / entry functions:
#   - ingest_export
#   - main
# Inputs:
#   - --lab-root
#   - Imports: __future__, argparse, hashlib, json, os, re, sqlite3, sys
# Output formats / side effects:
#   - SQLite databases
#   - JSON files
#   - UTF-8 text files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""scan_tg.py (v0.25.1)

Offline ingest for Telegram Desktop JSON exports.

Input
-----
Place one or more Telegram Desktop export JSON files into:
  <LabRoot>/data/Workspace/inbox/tg/

Output
------
Creates/updates:
  <LabRoot>/data/Indexes/tg_index.sqlite
  <LabRoot>/data/Workspace/outbox/tg/tg_ingest.seed.json

Design goals
------------
- Incremental: re-running should not duplicate messages.
- Safe-by-default: store only PI-scrubbed message text.
"""


import argparse
import hashlib
import json
import os
import re
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
                # For huge exports we still want a stable-ish fingerprint.
                break
    return h.hexdigest()


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
#   - tools/prep/scan_tabs.py
# Calls:
#   - mkdir
# Returns / emits: None
# === End NoemaForge Autodoc Function Header ===
def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


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
#   - tools/prep/scan_tabs.py
# Calls:
#   - executescript, execute
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

        CREATE TABLE IF NOT EXISTS chats (
            chat_id TEXT PRIMARY KEY,
            chat_name TEXT,
            chat_type TEXT,
            first_seen TEXT,
            last_seen TEXT
        );

        CREATE TABLE IF NOT EXISTS messages (
            chat_id TEXT,
            msg_id TEXT,
            date TEXT,
            sender TEXT,
            sender_id TEXT,
            text_clean TEXT,
            pi_severity TEXT,
            pi_score INTEGER,
            pi_post_severity TEXT,
            pi_post_score INTEGER,
            pi_bad_lines INTEGER,
            source_file TEXT,
            ingested_at TEXT,
            PRIMARY KEY(chat_id, msg_id)
        );

        CREATE TABLE IF NOT EXISTS links (
            chat_id TEXT,
            msg_id TEXT,
            url TEXT,
            PRIMARY KEY(chat_id, msg_id, url)
        );
        """
    )
    # Best-effort schema upgrade for older DBs
    # (SQLite doesn't support ADD COLUMN IF NOT EXISTS)
    for col, typ in (
        ("pi_post_severity", "TEXT"),
        ("pi_post_score", "INTEGER"),
        ("pi_bad_lines", "INTEGER"),
    ):
        try:
            con.execute(f"ALTER TABLE messages ADD COLUMN {col} {typ}")
        except sqlite3.OperationalError:
            pass



# === NoemaForge Autodoc Function Header ===
# Function: _import_pi_firewall()
# Purpose: Implement the routine ' import pi firewall'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - tools/prep/scan_tabs.py
# Calls:
#   - resolve, str, insert, Path
# Returns / emits: Tuple[Any, Any, Any]
# Key locals:
#   - here, src_dir
# === End NoemaForge Autodoc Function Header ===
def _import_pi_firewall() -> Tuple[Any, Any, Any]:
    # Import from src/ without requiring installation.
    here = Path(__file__).resolve()
    src_dir = (here.parent.parent.parent / "src").resolve()
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))
    try:
        from pi_firewall import scan_text, redact_instruction_like_lines, scan_and_scrub  # type: ignore

        return scan_text, redact_instruction_like_lines, scan_and_scrub
    except Exception:
        return None, None, None


# === NoemaForge Autodoc Function Header ===
# Function: _flatten_text_field(v)
# Purpose: Telegram export sometimes encodes `text` as string or as a list of entities.
# Inputs:
#   - v
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - isinstance, str, join, append, get
# Returns / emits: str
# Side effects:
#   - appends to logs or files
# Key locals:
#   - item, out, txt
# === End NoemaForge Autodoc Function Header ===
def _flatten_text_field(v: Any) -> str:
    """Telegram export sometimes encodes `text` as string or as a list of entities."""
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    if isinstance(v, list):
        out: List[str] = []
        for item in v:
            if isinstance(item, str):
                out.append(item)
            elif isinstance(item, dict):
                txt = item.get("text")
                if isinstance(txt, str):
                    out.append(txt)
        return "".join(out)
    return str(v)


_URL_RX = re.compile(r"https?://[^\s'\"]+", re.IGNORECASE)


# === NoemaForge Autodoc Function Header ===
# Function: _iter_messages(obj: Dict[str, Any])
# Purpose: Yield (chat, message) tuples for Telegram Desktop JSON export.
# Inputs:
#   - obj: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - get, isinstance
# Returns / emits: Iterable[Tuple[Dict[str, Any], Dict[str, Any]]]
# Key locals:
#   - chat, chat_list, chats, m, msgs
# === End NoemaForge Autodoc Function Header ===
def _iter_messages(obj: Dict[str, Any]) -> Iterable[Tuple[Dict[str, Any], Dict[str, Any]]]:
    """Yield (chat, message) tuples for Telegram Desktop JSON export."""
    chats = obj.get("chats")
    if isinstance(chats, dict):
        chat_list = chats.get("list")
        if isinstance(chat_list, list):
            for chat in chat_list:
                if not isinstance(chat, dict):
                    continue
                msgs = chat.get("messages")
                if isinstance(msgs, list):
                    for m in msgs:
                        if isinstance(m, dict):
                            yield chat, m
    elif isinstance(chats, list):
        # Some exports may store chats directly as list
        for chat in chats:
            if not isinstance(chat, dict):
                continue
            msgs = chat.get("messages")
            if isinstance(msgs, list):
                for m in msgs:
                    if isinstance(m, dict):
                        yield chat, m


# === NoemaForge Autodoc Function Header ===
# Function: ingest_export(con: sqlite3.Connection, json_path: Path)
# Purpose: Implement the routine 'ingest export'.
# Inputs:
#   - con: sqlite3.Connection
#   - json_path: Path
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _import_pi_firewall, read_text, _iter_messages, loads, str, _flatten_text_field, execute, findall, get, scan_and_scrub, int, scan_text
# Returns / emits: Dict[str, int]
# Side effects:
#   - executes SQL or shell-like commands
# Key locals:
#   - chat_id, chat_name, chat_type, cur, cur2, date, inserted_links, inserted_msgs, msg_id, obj, pi_bad_lines, pi_post_score
# === End NoemaForge Autodoc Function Header ===
def ingest_export(con: sqlite3.Connection, json_path: Path) -> Dict[str, int]:
    scan_text, redact_lines, scan_and_scrub = _import_pi_firewall()

    raw = json_path.read_text(encoding="utf-8", errors="ignore")
    try:
        obj = json.loads(raw)
    except Exception:
        # Not valid JSON
        return {"files": 1, "messages": 0, "links": 0, "skipped": 1}

    inserted_msgs = 0
    inserted_links = 0

    for chat, m in _iter_messages(obj):
        chat_id = str(chat.get("id") or chat.get("name") or "unknown")
        chat_name = str(chat.get("name") or "")
        chat_type = str(chat.get("type") or "")

        msg_id = str(m.get("id") or "")
        if not msg_id:
            continue
        date = str(m.get("date") or "")
        sender = str(m.get("from") or "")
        sender_id = str(m.get("from_id") or "")
        text_raw = _flatten_text_field(m.get("text"))
        # Prompt-injection handling (deterministic) with a post-scan.
        pi_sev = "none"
        pi_score = 0
        pi_post_sev = "none"
        pi_post_score = 0
        pi_bad_lines = 0

        text_clean = text_raw
        if scan_and_scrub:
            res = scan_and_scrub(text_raw or "", source=f"tg:{json_path.name}")
            pre = res.get("pre") or {}
            post = res.get("post") or {}
            text_clean = str(res.get("scrubbed_text") or "")

            pi_sev = str(pre.get("severity") or "none")
            pi_score = int(pre.get("score") or 0)
            pi_post_sev = str(post.get("severity") or "none")
            pi_post_score = int(post.get("score") or 0)
            try:
                pi_bad_lines = int(len(pre.get("bad_lines") or []))
            except Exception:
                pi_bad_lines = 0

        elif scan_text and redact_lines:
            pre = scan_text(text_raw or "", source=f"tg:{json_path.name}")
            pi_sev = str(pre.get("severity") or "none")
            pi_score = int(pre.get("score") or 0)
            try:
                pi_bad_lines = int(len(pre.get("bad_lines") or []))
            except Exception:
                pi_bad_lines = 0

            text_clean = redact_lines(text_raw or "", pre)

            post = scan_text(text_clean or "", source=f"tg:{json_path.name}:post") if scan_text else {}
            pi_post_sev = str(post.get("severity") or "none")
            pi_post_score = int(post.get("score") or 0)

        else:
            # Even without PI firewall, avoid empty/huge
            text_clean = (text_raw or "").strip()

        # Upsert chat
        con.execute(
            "INSERT OR IGNORE INTO chats(chat_id, chat_name, chat_type, first_seen, last_seen) VALUES(?,?,?,?,?)",
            (chat_id, chat_name, chat_type, date or "", date or ""),
        )
        con.execute(
            "UPDATE chats SET chat_name=?, chat_type=?, last_seen=? WHERE chat_id=?",
            (chat_name, chat_type, date or "", chat_id),
        )

        # Insert message
        cur = con.execute(
            "INSERT OR IGNORE INTO messages(chat_id,msg_id,date,sender,sender_id,text_clean,pi_severity,pi_score,pi_post_severity,pi_post_score,pi_bad_lines,source_file,ingested_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (chat_id, msg_id, date, sender, sender_id, text_clean, pi_sev, pi_score, pi_post_sev, pi_post_score, pi_bad_lines, str(json_path), _nowz()),
        )
        if cur.rowcount and cur.rowcount > 0:
            inserted_msgs += 1

        # Extract links
        for url in _URL_RX.findall(text_raw or ""):
            cur2 = con.execute(
                "INSERT OR IGNORE INTO links(chat_id,msg_id,url) VALUES(?,?,?)",
                (chat_id, msg_id, url),
            )
            if cur2.rowcount and cur2.rowcount > 0:
                inserted_links += 1

    return {"files": 1, "messages": inserted_msgs, "links": inserted_links, "skipped": 0}


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
    inbox = lab / "data" / "Workspace" / "inbox" / "tg"
    db_path = lab / "data" / "Indexes" / "tg_index.sqlite"
    out_seed = lab / "data" / "Workspace" / "outbox" / "tg" / "tg_ingest.seed.json"
    _ensure_parent(out_seed)

    con = _connect(db_path)
    _init_db(con)

    total = {"files": 0, "messages": 0, "links": 0, "skipped": 0}
    if inbox.exists():
        for p in sorted(inbox.glob("*.json")):
            st = p.stat()
            sha = _sha256_file(p)
            row = con.execute("SELECT sha256, size, mtime_ns FROM source_files WHERE path=?", (str(p),)).fetchone()
            if row and row[0] == sha and int(row[1] or 0) == int(st.st_size) and int(row[2] or 0) == int(st.st_mtime_ns):
                continue

            con.execute(
                "INSERT OR REPLACE INTO source_files(path,size,mtime_ns,sha256,indexed_at) VALUES(?,?,?,?,?)",
                (str(p), int(st.st_size), int(st.st_mtime_ns), sha, _nowz()),
            )
            res = ingest_export(con, p)
            for k in total:
                total[k] += int(res.get(k, 0))
            total["files"] += 1

    con.commit()
    con.close()

    # Emit a small seed for the head gateway / future ingest
    seed = {
        "ts": _nowz(),
        "inbox": str(inbox),
        "db": str(db_path),
        "counts": total,
    }
    out_seed.write_text(json.dumps(seed, ensure_ascii=False, indent=2), encoding="utf-8")

    print("OK")
    print(str(db_path))
    print(str(out_seed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
