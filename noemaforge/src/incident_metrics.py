#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/incident_metrics.py
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-14
Modified: 2026-05-14
Purpose: Collect or report NoemaForge telemetry and metric snapshots.
Inputs: Command-line arguments, environment variables, package files and local NoemaForge runtime state as applicable.
Outputs: Structured command output, files, service state or UI state as documented by the caller.
Side effects: Limited to the documented NoemaForge paths, runtime state directories or systemd units used by this file.
Tests: Syntax validation plus the release setup selftest, consistency-audit and targeted smoke checks.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations


# === NoemaForge Autodoc File Header ===
# File: src/incident_metrics.py
# Purpose: Provide the module 'incident_metrics'.
# Invoked by / imported from:
#   - src/metrics_snapshot.py
# Public API / entry functions:
#   - incident_snapshot
# Inputs:
#   - --db
#   - --window-hours
#   - Common path inputs: /var/lib/noemaforge/incidents/incidents.db
#   - Imports: __future__, datetime, json, os, sqlite3, typing, incidents, argparse
# Output formats / side effects:
#   - SQLite databases
#   - JSON files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""incident_metrics.py (v0.20.4)

Compute incident metrics (counts + MTTA/MTTR) from incidents DB.

Offline-first; reads local sqlite + JSON incident objects.
"""


import datetime as dt
import json
import os
import sqlite3
from typing import Any, Dict, List, Optional


try:  # pragma: no cover
    from incidents import DB_PATH as INCIDENTS_DB
except Exception:  # pragma: no cover
    INCIDENTS_DB = "/var/lib/noemaforge/incidents/incidents.db"


# === NoemaForge Autodoc Function Header ===
# Function: _parse_ts(ts: str)
# Purpose: Implement the routine ' parse ts'.
# Inputs:
#   - ts: str
# Called by:
#   - src/flow_metrics.py
#   - src/observability_metrics.py
# Calls:
#   - endswith, fromisoformat
# Returns / emits: Optional[dt.datetime]
# Key locals:
#   - ts
# === End NoemaForge Autodoc Function Header ===
def _parse_ts(ts: str) -> Optional[dt.datetime]:
    try:
        if ts.endswith("Z"):
            ts = ts[:-1]
        return dt.datetime.fromisoformat(ts)
    except Exception:
        return None


# === NoemaForge Autodoc Function Header ===
# Function: _read_json(path: str)
# Purpose: Implement the routine ' read json'.
# Inputs:
#   - path: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - open, load, isinstance
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads or writes files
# Key locals:
#   - f, obj
# === End NoemaForge Autodoc Function Header ===
def _read_json(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


# === NoemaForge Autodoc Function Header ===
# Function: _mean(vals: List[float])
# Purpose: Implement the routine ' mean'.
# Inputs:
#   - vals: List[float]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - sum, len
# Returns / emits: float
# === End NoemaForge Autodoc Function Header ===
def _mean(vals: List[float]) -> float:
    return (sum(vals) / len(vals)) if vals else 0.0


# === NoemaForge Autodoc Function Header ===
# Function: incident_snapshot(db_path: str = INCIDENTS_DB, window_hours: int = 24)
# Purpose: Implement the routine 'incident snapshot'.
# Inputs:
#   - db_path: str = INCIDENTS_DB
#   - window_hours: int = 24
# Called by:
#   - src/metrics_snapshot.py
# Calls:
#   - utcnow, connect, timedelta, exists, fetchall, close, _parse_ts, str, int, get, _read_json, _mean
# Returns / emits: Dict[str, Any]
# Side effects:
#   - opens a database or socket connection
# Key locals:
#   - act, by_kind, by_sev, con, created, cutoff, h, hist, key, kind, mtta, mttr
# === End NoemaForge Autodoc Function Header ===
def incident_snapshot(*, db_path: str = INCIDENTS_DB, window_hours: int = 24) -> Dict[str, Any]:
    now = dt.datetime.utcnow()
    cutoff = now - dt.timedelta(hours=max(1, int(window_hours)))

    if not os.path.exists(db_path):
        return {"window_hours": int(window_hours), "db_path": db_path, "note": "incidents db missing"}

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            "SELECT incident_id, kind, severity, status, title, created_at, updated_at, path FROM incidents"
        ).fetchall()
    finally:
        con.close()

    open_counts: Dict[str, int] = {}
    by_kind: Dict[str, int] = {}
    by_sev: Dict[str, int] = {}
    repeats = 0
    mtta: List[float] = []
    mttr: List[float] = []

    for r in rows:
        created = _parse_ts(str(r[5] or ""))
        updated = _parse_ts(str(r[6] or ""))
        if created is None:
            continue
        if created < cutoff and (updated is None or updated < cutoff):
            # skip old incidents outside window unless updated recently
            continue

        kind = str(r[1] or "unknown")
        sev = str(r[2] or "unknown")
        status = str(r[3] or "unknown")
        by_kind[kind] = by_kind.get(kind, 0) + 1
        by_sev[sev] = by_sev.get(sev, 0) + 1

        if status != "CLOSED":
            key = f"{sev}:{kind}"
            open_counts[key] = open_counts.get(key, 0) + 1

        path = str(r[7] or "")
        if path and os.path.exists(path):
            obj = _read_json(path)
            repeats += int(obj.get("repeats") or 0)
            hist = obj.get("history") if isinstance(obj.get("history"), list) else []

            # MTTA: open -> first ack
            t_open = None
            t_ack = None
            t_close = None
            for h in hist:
                if not isinstance(h, dict):
                    continue
                act = str(h.get("action") or "")
                ts = _parse_ts(str(h.get("ts") or ""))
                if ts is None:
                    continue
                if act == "open" and t_open is None:
                    t_open = ts
                if act == "ack" and t_ack is None:
                    t_ack = ts
                if act == "close":
                    t_close = ts
            if t_open and t_ack:
                mtta.append(max(0.0, (t_ack - t_open).total_seconds() / 3600.0))
            if t_open and t_close:
                mttr.append(max(0.0, (t_close - t_open).total_seconds() / 3600.0))

    return {
        "window_hours": int(window_hours),
        "db_path": db_path,
        "open_counts": open_counts,
        "by_kind": by_kind,
        "by_severity": by_sev,
        "repeats": int(repeats),
        "mtta_hours": {"avg": _mean(mtta), "n": len(mtta)},
        "mttr_hours": {"avg": _mean(mttr), "n": len(mttr)},
    }


if __name__ == "__main__":  # pragma: no cover
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=INCIDENTS_DB)
    ap.add_argument("--window-hours", type=int, default=24)
    args = ap.parse_args()
    print(json.dumps(incident_snapshot(db_path=args.db, window_hours=args.window_hours), ensure_ascii=False, indent=2))
