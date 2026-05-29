#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/caps.py
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
# File: src/caps.py
# Purpose: Provide the module 'caps'.
# Invoked by / imported from:
#   - src/noemaforge_core.py
#   - src/invites.py
#   - src/toolproxy.py
# Public API / entry functions:
#   - issue_token
#   - load_record
#   - verify_token
#   - cleanup_expired
# Inputs:
#   - Imports: __future__, base64, datetime, hashlib, json, os, secrets, uuid
# Output formats / side effects:
#   - JSON files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""caps.py

Short-lived capability tokens (MVP).

Threat model (MVP):
- Roles must not have 'god tokens'.
- A role gets a short-lived token scoped to a run_id + role + project_id.
- ToolProxy enforces capabilities; roles only talk to ToolProxy.

Token format given to roles:
  <token_id>.<secret>

Stored token record on disk (noemaforge-owned dir):
  /var/lib/noemaforge/.sys/cap_tokens/<token_id>.json

We store only sha256(secret) in the record.

NOTE: This is not meant to be cryptographically fancy; it's meant to be
operationally safe and auditable for an offline-first MVP.
"""


import base64
import datetime as dt
import hashlib
import json
import os
import secrets
import uuid
from typing import Any, Dict, List, Optional, Tuple

from epoch import current_epoch_id


# === NoemaForge Autodoc Function Header ===
# Function: _nowz()
# Purpose: Implement the routine ' nowz'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - src/audit_remediation.py
#   - src/noemaforge_core.py
#   - src/bundles.py
#   - src/casebase.py
#   - src/coordinator_fanout.py
#   - src/dream_cycle.py
#   - src/fixture_bundle.py
#   - src/glove_agent.py
# Calls:
#   - isoformat, utcnow
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _nowz() -> str:
    return dt.datetime.utcnow().isoformat() + "Z"


# === NoemaForge Autodoc Function Header ===
# Function: _sha256_hex(s: str)
# Purpose: Implement the routine ' sha256 hex'.
# Inputs:
#   - s: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - hexdigest, sha256, encode
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


# === NoemaForge Autodoc Function Header ===
# Function: _parse_token(token: str)
# Purpose: Implement the routine ' parse token'.
# Inputs:
#   - token: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - strip, split
# Returns / emits: Optional[Tuple[str, str]]
# Key locals:
#   - secret, tid, token
# === End NoemaForge Autodoc Function Header ===
def _parse_token(token: str) -> Optional[Tuple[str, str]]:
    token = (token or "").strip()
    if not token or "." not in token:
        return None
    tid, secret = token.split(".", 1)
    tid = tid.strip()
    secret = secret.strip()
    if not tid or not secret:
        return None
    return tid, secret


# === NoemaForge Autodoc Function Header ===
# Function: issue_token(tokens_dir: str, issued_to: Dict[str, str], caps: List[Dict[str, Any]], ttl_sec: int = 600, trace_id: Optional[str] = None)
# Purpose: Create a token record and return the bearer token string.
# Inputs:
#   - tokens_dir: str
#   - issued_to: Dict[str, str]
#   - caps: List[Dict[str, Any]]
#   - ttl_sec: int = 600
#   - trace_id: Optional[str] = None
# Called by:
#   - src/noemaforge_core.py
#   - src/invites.py
# Calls:
#   - makedirs, str, rstrip, join, replace, uuid4, utcnow, timedelta, _sha256_hex, current_epoch_id, _nowz, open
# Returns / emits: str
# Side effects:
#   - reads or writes files
#   - creates directories
# Key locals:
#   - exp, f, path, rec, secret, tmp, token_id
# === End NoemaForge Autodoc Function Header ===
def issue_token(
    tokens_dir: str,
    issued_to: Dict[str, str],
    caps: List[Dict[str, Any]],
    ttl_sec: int = 600,
    trace_id: Optional[str] = None,
) -> str:
    """Create a token record and return the bearer token string."""
    os.makedirs(tokens_dir, exist_ok=True)

    token_id = str(uuid.uuid4())
    secret = base64.urlsafe_b64encode(secrets.token_bytes(24)).decode("ascii").rstrip("=")

    exp = dt.datetime.utcnow() + dt.timedelta(seconds=int(ttl_sec))
    rec = {
        "token_id": token_id,
        "secret_sha256": _sha256_hex(secret),
        "issued_to": issued_to,
        "epoch_id": current_epoch_id(),
        "expires_at": exp.isoformat() + "Z",
        "caps": caps,
        "trace_id": trace_id or str(uuid.uuid4()),
        "issued_at": _nowz(),
    }

    tmp = os.path.join(tokens_dir, token_id + ".json.tmp")
    path = os.path.join(tokens_dir, token_id + ".json")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

    return token_id + "." + secret


# === NoemaForge Autodoc Function Header ===
# Function: load_record(tokens_dir: str, token_id: str)
# Purpose: Implement the routine 'load record'.
# Inputs:
#   - tokens_dir: str
#   - token_id: str
# Called by:
#   - src/invites.py
# Calls:
#   - join, exists, open, load
# Returns / emits: Optional[Dict[str, Any]]
# Side effects:
#   - reads or writes files
# Key locals:
#   - f, path
# === End NoemaForge Autodoc Function Header ===
def load_record(tokens_dir: str, token_id: str) -> Optional[Dict[str, Any]]:
    path = os.path.join(tokens_dir, token_id + ".json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


# === NoemaForge Autodoc Function Header ===
# Function: verify_token(tokens_dir: str, token: str)
# Purpose: Return (ok, record, reason).
# Inputs:
#   - tokens_dir: str
#   - token: str
# Called by:
#   - src/invites.py
#   - src/toolproxy.py
# Calls:
#   - _parse_token, load_record, _sha256_hex, str, fromisoformat, utcnow, replace, get
# Returns / emits: Tuple[bool, Optional[Dict[str, Any]], str]
# Key locals:
#   - exp, parsed, rec
# === End NoemaForge Autodoc Function Header ===
def verify_token(tokens_dir: str, token: str) -> Tuple[bool, Optional[Dict[str, Any]], str]:
    """Return (ok, record, reason)."""
    parsed = _parse_token(token)
    if not parsed:
        return False, None, "bad_token_format"
    token_id, secret = parsed

    rec = load_record(tokens_dir, token_id)
    if not rec:
        return False, None, "unknown_token"

    if _sha256_hex(secret) != str(rec.get("secret_sha256") or ""):
        return False, None, "secret_mismatch"

    try:
        exp = dt.datetime.fromisoformat(str(rec.get("expires_at") or "").replace("Z", ""))
    except Exception:
        return False, None, "bad_expiry"

    if exp < dt.datetime.utcnow():
        return False, None, "expired"

    return True, rec, "ok"


# === NoemaForge Autodoc Function Header ===
# Function: cleanup_expired(tokens_dir: str, keep_days: int = 7)
# Purpose: Remove expired token files older than keep_days (best-effort).
# Inputs:
#   - tokens_dir: str
#   - keep_days: int = 7
# Called by:
#   - src/invites.py
# Calls:
#   - utcnow, listdir, isdir, timedelta, join, endswith, fromisoformat, int, open, load, replace, remove
# Returns / emits: int
# Side effects:
#   - reads or writes files
# Key locals:
#   - cutoff, exp, f, fn, now, path, rec, removed
# === End NoemaForge Autodoc Function Header ===
def cleanup_expired(tokens_dir: str, keep_days: int = 7) -> int:
    """Remove expired token files older than keep_days (best-effort)."""
    if not os.path.isdir(tokens_dir):
        return 0
    now = dt.datetime.utcnow()
    cutoff = now - dt.timedelta(days=int(keep_days))
    removed = 0
    for fn in os.listdir(tokens_dir):
        if not fn.endswith(".json"):
            continue
        path = os.path.join(tokens_dir, fn)
        try:
            with open(path, "r", encoding="utf-8") as f:
                rec = json.load(f)
            exp = dt.datetime.fromisoformat(str(rec.get("expires_at") or "").replace("Z", ""))
            if exp < cutoff:
                os.remove(path)
                removed += 1
        except Exception:
            continue
    return removed
