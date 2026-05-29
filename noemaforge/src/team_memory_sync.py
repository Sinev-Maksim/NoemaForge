#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/team_memory_sync.py
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
# File: src/team_memory_sync.py
# Purpose: Provide the module 'team_memory_sync'.
# Invoked by / imported from:
#   - src/toolproxy.py
# Public API / entry functions:
#   - scan_bundle
#   - export_bundle
#   - import_bundle
# Inputs:
#   - Common path inputs: /var/lib/noemaforge/outbox/team_memory, /var/lib/noemaforge/memory/team_imports, /var/lib/noemaforge/memory/session
#   - Imports: __future__, datetime, hashlib, json, os, re, typing
# Output formats / side effects:
#   - JSON files
#   - Markdown files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===


import datetime as dt
import hashlib
import json
import os
import re
from typing import Any, Dict, List, Optional

BUNDLE_OUTBOX = "/var/lib/noemaforge/outbox/team_memory"
IMPORTS_DIR = "/var/lib/noemaforge/memory/team_imports"
SESSION_BASE = "/var/lib/noemaforge/memory/session"

SECRET_PATTERNS = [
    ("private_key", re.compile(r"BEGIN [A-Z ]*PRIVATE KEY")),
    ("aws_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("password", re.compile(r"password\s*[:=]\s*[^\s]+", re.IGNORECASE)),
]


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
    return dt.datetime.utcnow().isoformat() + "Z"


# === NoemaForge Autodoc Function Header ===
# Function: _slug()
# Purpose: Implement the routine ' slug'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - src/coordinator_fanout.py
#   - src/worktree_manager.py
# Calls:
#   - strftime, utcnow
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _slug() -> str:
    return dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")


# === NoemaForge Autodoc Function Header ===
# Function: _sha256_text(s: str)
# Purpose: Implement the routine ' sha256 text'.
# Inputs:
#   - s: str
# Called by:
#   - src/pipelines/photos_diary.py
#   - src/telemetry.py
# Calls:
#   - hexdigest, sha256, encode
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


# === NoemaForge Autodoc Function Header ===
# Function: scan_bundle(path: str)
# Purpose: Implement the routine 'scan bundle'.
# Inputs:
#   - path: str
# Called by:
#   - src/toolproxy.py
# Calls:
#   - read, search, append, open
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads or writes files
#   - appends to logs or files
# Key locals:
#   - findings, text
# === End NoemaForge Autodoc Function Header ===
def scan_bundle(path: str) -> Dict[str, Any]:
    findings = []
    try:
        text = open(path, "r", encoding="utf-8").read()
    except Exception as e:
        return {"ok": False, "error": f"read_failed:{e}"}
    for name, rx in SECRET_PATTERNS:
        if rx.search(text):
            findings.append({"kind": name, "severity": "high"})
    return {"ok": True, "findings": findings, "path": path}


# === NoemaForge Autodoc Function Header ===
# Function: export_bundle(project_id: str)
# Purpose: Implement the routine 'export bundle'.
# Inputs:
#   - project_id: str
# Called by:
#   - src/toolproxy.py
# Calls:
#   - join, exists, makedirs, _nowz, read, append, dirname, open, dump, len, _sha256_text, _slug
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads or writes files
#   - serializes structured data
#   - creates directories
#   - appends to logs or files
# Key locals:
#   - content, f, out_path, payload, session_md
# === End NoemaForge Autodoc Function Header ===
def export_bundle(project_id: str) -> Dict[str, Any]:
    session_md = os.path.join(SESSION_BASE, project_id, "session_memory.md")
    payload = {
        "kind": "NoemaForgeTeamMemoryBundle",
        "version": "0.26.0",
        "project_id": project_id,
        "generated_at": _nowz(),
        "files": [],
    }
    if os.path.exists(session_md):
        content = open(session_md, "r", encoding="utf-8").read()
        payload["files"].append({"path": "session_memory.md", "sha256": _sha256_text(content), "content": content})
    out_path = os.path.join(BUNDLE_OUTBOX, project_id, f"{_slug()}.bundle.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return {"ok": True, "bundle_path": out_path, "file_count": len(payload["files"])}


# === NoemaForge Autodoc Function Header ===
# Function: import_bundle(path: str, project_id: str = '')
# Purpose: Implement the routine 'import bundle'.
# Inputs:
#   - path: str
#   - project_id: str = ''
# Called by:
#   - src/toolproxy.py
# Calls:
#   - scan_bundle, get, open, load, str, join, makedirs, append, len, strip, dirname, write
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads or writes files
#   - creates directories
#   - appends to logs or files
# Key locals:
#   - bundle, dest, f, fi, imported, out, project, rel, sc
# === End NoemaForge Autodoc Function Header ===
def import_bundle(path: str, project_id: str = "") -> Dict[str, Any]:
    sc = scan_bundle(path)
    if not sc.get("ok"):
        return sc
    if sc.get("findings"):
        return {"ok": False, "decision": "quarantine", "findings": sc["findings"], "path": path}
    with open(path, "r", encoding="utf-8") as f:
        bundle = json.load(f)
    project = project_id or str(bundle.get("project_id") or "imported")
    imported = []
    for fi in bundle.get("files", []) or []:
        rel = str(fi.get("path") or "").strip() or "unknown.txt"
        dest = os.path.join(IMPORTS_DIR, project, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "w", encoding="utf-8") as out:
            out.write(str(fi.get("content") or ""))
        imported.append(dest)
    return {"ok": True, "project_id": project, "imported": imported, "count": len(imported)}
