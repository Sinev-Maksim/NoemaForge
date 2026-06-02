#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/invites.py
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
# File: src/invites.py
# Purpose: Provide the module 'invites'.
# Invoked by / imported from:
#   - src/brainctl.py
#   - src/localgateway.py
#   - src/task_runner.py
#   - src/taskqueue.py
# Public API / entry functions:
#   - issue_invite
#   - activate_invite
#   - deactivate_invite
#   - active_token
#   - is_active
#   - active_record
#   - list_active_scopes
#   - cleanup_expired
# Inputs:
#   - Common path inputs: /var/lib/noemaforge/.sys/invites
#   - Imports: __future__, datetime, json, os, typing, caps
# Output formats / side effects:
#   - JSON files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""invites.py (v0.12.8)

User invite / break-glass capability manager.

Why this exists
---------------
Some actions must be *impossible* to run automatically (even for Surgeon),
unless the user explicitly invites them.

Examples
--------
- Surgeon LIVE work "on the running system" ("по живому")

Design
------
- Invites are short-lived tokens stored on disk (spinal zone).
- A separate "active" pointer file enables a scope.
- TaskQueue can skip tasks that require an invite while no invite is active.

Security notes
--------------
- Roles do not see invite state or tokens.
- Invites are stored under /var/lib/noemaforge/.sys/invites (noemaforge-owned).
- Uses caps.py token format for consistency.
"""


import datetime as dt
import json
import os
from typing import Any, Dict, Optional, Tuple

import caps
from platform_paths import DEFAULT_PATHS as _pp


INVITES_ROOT = str(_pp.data_root / ".sys/invites")
TOKENS_DIR = os.path.join(INVITES_ROOT, "tokens")
ACTIVE_DIR = os.path.join(INVITES_ROOT, "active")


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
# Function: _active_path(scope: str)
# Purpose: Implement the routine ' active path'.
# Inputs:
#   - scope: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - lower, replace, makedirs, join, strip, str
# Returns / emits: str
# Side effects:
#   - creates directories
# Key locals:
#   - s
# === End NoemaForge Autodoc Function Header ===
def _active_path(scope: str) -> str:
    s = str(scope or "").strip().lower()
    s = s.replace("/", "_").replace("..", "_")
    os.makedirs(ACTIVE_DIR, exist_ok=True)
    return os.path.join(ACTIVE_DIR, f"{s}.token")


# === NoemaForge Autodoc Function Header ===
# Function: _token_record_path(token_id: str)
# Purpose: Implement the routine ' token record path'.
# Inputs:
#   - token_id: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - join, str
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _token_record_path(token_id: str) -> str:
    return os.path.join(TOKENS_DIR, str(token_id) + ".json")


# === NoemaForge Autodoc Function Header ===
# Function: issue_invite(scope: str, ttl_sec: int = 900, issued_by: str = 'user', comment: str = '')
# Purpose: Issue an invite token (not activated by default).
# Inputs:
#   - scope: str
#   - ttl_sec: int = 900
#   - issued_by: str = 'user'
#   - comment: str = ''
# Called by:
#   - src/brainctl.py
# Calls:
#   - lower, issue_token, ValueError, _token_record_path, replace, strip, int, split, load_record, get, _nowz, open
# Returns / emits: str
# Side effects:
#   - reads or writes files
# Key locals:
#   - f, rec, rp, sc, tid, tmp, token
# === End NoemaForge Autodoc Function Header ===
def issue_invite(
    *,
    scope: str,
    ttl_sec: int = 900,
    issued_by: str = "user",
    comment: str = "",
) -> str:
    """Issue an invite token (not activated by default)."""
    sc = str(scope or "").strip().lower()
    if not sc:
        raise ValueError("missing_scope")

    token = caps.issue_token(
        tokens_dir=TOKENS_DIR,
        issued_to={"actor_type": "user", "actor_id": issued_by, "scope": sc},
        caps=[{"action": f"invite.{sc}"}],
        ttl_sec=int(ttl_sec),
    )

    # Enrich the record with invite metadata (best-effort)
    try:
        tid = token.split(".", 1)[0]
        rp = _token_record_path(tid)
        rec = caps.load_record(TOKENS_DIR, tid) or {}
        rec["invite_scope"] = sc
        rec["comment"] = (comment or "").strip()[:2000]
        rec["issued_at"] = rec.get("issued_at") or _nowz()
        tmp = rp + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False, indent=2)
        os.replace(tmp, rp)
    except Exception:
        pass

    return token


# === NoemaForge Autodoc Function Header ===
# Function: activate_invite(scope: str, token: str)
# Purpose: Activate an invite scope by writing a pointer file.
# Inputs:
#   - scope: str
#   - token: str
# Called by:
#   - src/brainctl.py
# Calls:
#   - lower, verify_token, _active_path, get, any, replace, strip, open, write, chmod, repr, str
# Returns / emits: Tuple[bool, str]
# Side effects:
#   - reads or writes files
# Key locals:
#   - caps_list, f, p, sc, tmp
# === End NoemaForge Autodoc Function Header ===
def activate_invite(*, scope: str, token: str) -> Tuple[bool, str]:
    """Activate an invite scope by writing a pointer file."""
    sc = str(scope or "").strip().lower()
    if not sc:
        return False, "missing_scope"

    ok, rec, reason = caps.verify_token(TOKENS_DIR, token)
    if not ok or not rec:
        return False, reason

    # Ensure token actually carries the invite cap
    caps_list = rec.get("caps") or []
    if not any(isinstance(c, dict) and str(c.get("action") or "") == f"invite.{sc}" for c in caps_list):
        return False, "scope_mismatch"

    p = _active_path(sc)
    tmp = p + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(token.strip() + "\n")
        os.replace(tmp, p)
        try:
            os.chmod(p, 0o600)
        except Exception:
            pass
    except Exception as e:
        return False, repr(e)

    return True, "ok"


# === NoemaForge Autodoc Function Header ===
# Function: deactivate_invite(scope: str)
# Purpose: Implement the routine 'deactivate invite'.
# Inputs:
#   - scope: str
# Called by:
#   - src/brainctl.py
# Calls:
#   - lower, _active_path, exists, strip, remove, str
# Returns / emits: bool
# Key locals:
#   - p, sc
# === End NoemaForge Autodoc Function Header ===
def deactivate_invite(*, scope: str) -> bool:
    sc = str(scope or "").strip().lower()
    if not sc:
        return False
    p = _active_path(sc)
    try:
        if os.path.exists(p):
            os.remove(p)
        return True
    except Exception:
        return False


# === NoemaForge Autodoc Function Header ===
# Function: active_token(scope: str)
# Purpose: Implement the routine 'active token'.
# Inputs:
#   - scope: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _active_path, exists, open, strip, readline
# Returns / emits: str
# Side effects:
#   - reads or writes files
# Key locals:
#   - f, p
# === End NoemaForge Autodoc Function Header ===
def active_token(scope: str) -> str:
    p = _active_path(scope)
    if not os.path.exists(p):
        return ""
    try:
        with open(p, "r", encoding="utf-8") as f:
            return (f.readline() or "").strip()
    except Exception:
        return ""


# === NoemaForge Autodoc Function Header ===
# Function: is_active(scope: str)
# Purpose: Return True if an active pointer exists and verifies.
# Inputs:
#   - scope: str
# Called by:
#   - src/localgateway.py
#   - src/task_runner.py
#   - src/taskqueue.py
# Calls:
#   - active_token, verify_token, lower, any, get, strip, isinstance, str
# Returns / emits: bool
# Key locals:
#   - caps_list, sc, tok
# === End NoemaForge Autodoc Function Header ===
def is_active(scope: str) -> bool:
    """Return True if an active pointer exists and verifies."""
    tok = active_token(scope)
    if not tok:
        return False
    ok, rec, _ = caps.verify_token(TOKENS_DIR, tok)
    if not ok or not rec:
        return False
    sc = str(scope or "").strip().lower()
    caps_list = rec.get("caps") or []
    return any(isinstance(c, dict) and str(c.get("action") or "") == f"invite.{sc}" for c in caps_list)


# === NoemaForge Autodoc Function Header ===
# Function: active_record(scope: str)
# Purpose: Implement the routine 'active record'.
# Inputs:
#   - scope: str
# Called by:
#   - src/brainctl.py
# Calls:
#   - active_token, verify_token
# Returns / emits: Optional[Dict[str, Any]]
# Key locals:
#   - tok
# === End NoemaForge Autodoc Function Header ===
def active_record(scope: str) -> Optional[Dict[str, Any]]:
    tok = active_token(scope)
    if not tok:
        return None
    ok, rec, _ = caps.verify_token(TOKENS_DIR, tok)
    return rec if ok else None


# === NoemaForge Autodoc Function Header ===
# Function: list_active_scopes()
# Purpose: Implement the routine 'list active scopes'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - src/brainctl.py
# Calls:
#   - sorted, isdir, listdir, active_record, endswith, str, get
# Returns / emits: Dict[str, Dict[str, Any]]
# Key locals:
#   - fn, out, rec, scope
# === End NoemaForge Autodoc Function Header ===
def list_active_scopes() -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    if not os.path.isdir(ACTIVE_DIR):
        return out
    for fn in sorted(os.listdir(ACTIVE_DIR)):
        if not fn.endswith(".token"):
            continue
        scope = fn[:-6]
        rec = active_record(scope)
        if rec:
            out[scope] = {
                "expires_at": str(rec.get("expires_at") or ""),
                "issued_to": rec.get("issued_to") or {},
                "comment": str(rec.get("comment") or ""),
            }
    return out


# === NoemaForge Autodoc Function Header ===
# Function: cleanup_expired(keep_days: int = 7)
# Purpose: Implement the routine 'cleanup expired'.
# Inputs:
#   - keep_days: int = 7
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - int, isdir, listdir, cleanup_expired, endswith, is_active, remove, join
# Returns / emits: int
# Key locals:
#   - fn, removed, scope
# === End NoemaForge Autodoc Function Header ===
def cleanup_expired(keep_days: int = 7) -> int:
    # Remove expired records (caps helper)
    removed = 0
    try:
        removed = int(caps.cleanup_expired(TOKENS_DIR, keep_days=int(keep_days)) or 0)
    except Exception:
        removed = 0

    # Remove active pointers that no longer validate
    try:
        if os.path.isdir(ACTIVE_DIR):
            for fn in os.listdir(ACTIVE_DIR):
                if not fn.endswith(".token"):
                    continue
                scope = fn[:-6]
                if not is_active(scope):
                    try:
                        os.remove(os.path.join(ACTIVE_DIR, fn))
                    except Exception:
                        pass
    except Exception:
        pass

    return removed
