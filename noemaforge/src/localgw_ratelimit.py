#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/localgw_ratelimit.py
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
# File: src/localgw_ratelimit.py
# Purpose: Provide the module 'localgw_ratelimit'.
# Invoked by / imported from:
#   - src/localgateway.py
# Public API / entry functions:
#   - check_and_increment
# Inputs:
#   - Common path inputs: /var/lib/noemaforge/localgw/ratelimit.sqlite
#   - Imports: __future__, os, sqlite3, time, typing
# Output formats / side effects:
#   - SQLite databases
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""localgw_ratelimit.py (v0.16.0)

Rate limiting for LocalGateway connector calls.

Why
----
LocalGateway is a privileged window into the LAN. Even without Internet,
repeated calls can become a side-channel or an availability attack
(e.g., hammer OctoPrint or a printer).

We implement an offline-friendly fixed-window counter using SQLite.
This is deliberately simple and auditable.

Policy
------
Configured via local-gateway-policy.yaml:

rate_limits:
  enabled: true
  db_path: /var/lib/noemaforge/localgw/ratelimit.sqlite
  default:
    window_sec: 60
    max_calls: 60
  overrides:
    octoprint.upload_gcode:
      window_sec: 300
      max_calls: 3

Keying
------
Key = device_uid + connector + method (+ optional "scope" in the future)

Return
------
(check_ok, info)
"""


import os
import sqlite3
import time
from typing import Any, Dict, Tuple


# === NoemaForge Autodoc Function Header ===
# Function: _now()
# Purpose: Implement the routine ' now'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - src/bootdoctor.py
#   - src/flow_metrics.py
#   - src/resource_recovery.py
#   - src/storage_broker.py
#   - tools/autodoc_inject_misc.py
# Calls:
#   - int, time
# Returns / emits: int
# === End NoemaForge Autodoc Function Header ===
def _now() -> int:
    return int(time.time())


# === NoemaForge Autodoc Function Header ===
# Function: _db_init(path: str)
# Purpose: Implement the routine ' db init'.
# Inputs:
#   - path: str
# Called by:
#   - src/localgateway.py
# Calls:
#   - makedirs, connect, dirname, execute, commit, close
# Returns / emits: None
# Side effects:
#   - opens a database or socket connection
#   - executes SQL or shell-like commands
#   - creates directories
# Key locals:
#   - con
# === End NoemaForge Autodoc Function Header ===
def _db_init(path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    con = sqlite3.connect(path)
    try:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS counters (
              k TEXT PRIMARY KEY,
              window_start INTEGER NOT NULL,
              window_sec INTEGER NOT NULL,
              max_calls INTEGER NOT NULL,
              count INTEGER NOT NULL,
              updated_at INTEGER NOT NULL
            )
            """
        )
        con.commit()
    finally:
        con.close()


# === NoemaForge Autodoc Function Header ===
# Function: _get_limits(pol: Dict[str, Any], connector: str, method: str)
# Purpose: Implement the routine ' get limits'.
# Inputs:
#   - pol: Dict[str, Any]
#   - connector: str
#   - method: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - int, get, isinstance, max, min
# Returns / emits: Tuple[int, int]
# Key locals:
#   - default, key, max_calls, ov, overrides, rcfg, window_sec
# === End NoemaForge Autodoc Function Header ===
def _get_limits(pol: Dict[str, Any], connector: str, method: str) -> Tuple[int, int]:
    rcfg = (pol.get("rate_limits") or {}) if isinstance(pol, dict) else {}
    default = (rcfg.get("default") or {}) if isinstance(rcfg.get("default"), dict) else {}
    window_sec = int(default.get("window_sec") or 60)
    max_calls = int(default.get("max_calls") or 60)

    overrides = (rcfg.get("overrides") or {}) if isinstance(rcfg.get("overrides"), dict) else {}
    key = f"{connector}.{method}"
    ov = overrides.get(key)
    if isinstance(ov, dict):
        window_sec = int(ov.get("window_sec") or window_sec)
        max_calls = int(ov.get("max_calls") or max_calls)

    # Safety floor/ceil
    window_sec = max(1, min(window_sec, 24 * 3600))
    max_calls = max(1, min(max_calls, 100000))
    return window_sec, max_calls


# === NoemaForge Autodoc Function Header ===
# Function: check_and_increment(policy: Dict[str, Any], device_uid: str, connector: str, method: str)
# Purpose: Check rate limits and increment counter if allowed.
# Inputs:
#   - policy: Dict[str, Any]
#   - device_uid: str
#   - connector: str
#   - method: str
# Called by:
#   - src/localgateway.py
# Calls:
#   - str, _get_limits, _now, _db_init, connect, isinstance, bool, cursor, execute, fetchone, commit, close
# Returns / emits: Tuple[bool, Dict[str, Any]]
# Side effects:
#   - opens a database or socket connection
#   - executes SQL or shell-like commands
# Key locals:
#   - cnt, cnt2, con, cur, db_path, key, now, rcfg, retry_after, row, win_start
# === End NoemaForge Autodoc Function Header ===
def check_and_increment(
    *,
    policy: Dict[str, Any],
    device_uid: str,
    connector: str,
    method: str,
) -> Tuple[bool, Dict[str, Any]]:
    """Check rate limits and increment counter if allowed."""

    rcfg = (policy.get("rate_limits") or {}) if isinstance(policy, dict) else {}
    if not bool(rcfg.get("enabled", False)):
        return True, {"ok": True, "skipped": True}

    db_path = str(rcfg.get("db_path") or "/var/lib/noemaforge/localgw/ratelimit.sqlite")
    window_sec, max_calls = _get_limits(policy, connector, method)

    key = f"{device_uid}|{connector}|{method}"
    now = _now()
    win_start = now - (now % window_sec)

    _db_init(db_path)
    con = sqlite3.connect(db_path)
    try:
        cur = con.cursor()
        cur.execute("SELECT window_start, window_sec, max_calls, count FROM counters WHERE k=?", (key,))
        row = cur.fetchone()

        if row:
            prev_start, prev_w, prev_m, cnt = int(row[0]), int(row[1]), int(row[2]), int(row[3])
            # If window config changed, treat as a new window.
            if prev_start != win_start or prev_w != window_sec or prev_m != max_calls:
                cnt = 0
            if cnt >= max_calls:
                retry_after = (win_start + window_sec) - now
                return False, {
                    "ok": False,
                    "reason": "rate_limited",
                    "retry_after_sec": max(1, int(retry_after)),
                    "window_sec": int(window_sec),
                    "max_calls": int(max_calls),
                    "count": int(cnt),
                    "db_path": db_path,
                }
            cnt2 = cnt + 1
            cur.execute(
                "UPDATE counters SET window_start=?, window_sec=?, max_calls=?, count=?, updated_at=? WHERE k=?",
                (win_start, window_sec, max_calls, cnt2, now, key),
            )
            con.commit()
            return True, {
                "ok": True,
                "window_sec": int(window_sec),
                "max_calls": int(max_calls),
                "count": int(cnt2),
                "db_path": db_path,
            }

        # No row yet
        cur.execute(
            "INSERT INTO counters(k, window_start, window_sec, max_calls, count, updated_at) VALUES(?,?,?,?,?,?)",
            (key, win_start, window_sec, max_calls, 1, now),
        )
        con.commit()
        return True, {"ok": True, "window_sec": int(window_sec), "max_calls": int(max_calls), "count": 1, "db_path": db_path}

    finally:
        con.close()
