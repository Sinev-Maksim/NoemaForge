#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/flow_metrics.py
Zone: release/package
Version: 0.32.1
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
# File: src/flow_metrics.py
# Purpose: Provide the module 'flow_metrics'.
# Invoked by / imported from:
#   - src/metrics_snapshot.py
# Public API / entry functions:
#   - taskqueue_db_path
#   - flow_snapshot
# Inputs:
#   - --db
#   - --window-hours
#   - Common path inputs: /opt/noemaforge/configs/taskqueue-policy.yaml, /var/lib/noemaforge/taskqueue/tasks.db, /var/lib/noemaforge/taskqueue
#   - Imports: __future__, datetime, os, sqlite3, typing, yaml, json, argparse
# Output formats / side effects:
#   - SQLite databases
#   - JSON files
#   - YAML files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""flow_metrics.py (v0.20.4)

Compute simple flow metrics from TaskQueue.

Inspired by common delivery/flow metrics (throughput, WIP, cycle time).
Offline-first and deterministic.
"""


import datetime as dt
import os
import sqlite3
from typing import Any, Dict, List, Optional


try:  # pragma: no cover
    import yaml
except Exception:  # pragma: no cover
    yaml = None  # type: ignore


# === NoemaForge Autodoc Function Header ===
# Function: _now()
# Purpose: Implement the routine ' now'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - src/bootdoctor.py
#   - src/localgw_ratelimit.py
#   - src/resource_recovery.py
#   - src/storage_broker.py
#   - tools/autodoc_inject_misc.py
# Calls:
#   - utcnow
# Returns / emits: dt.datetime
# === End NoemaForge Autodoc Function Header ===
def _now() -> dt.datetime:
    return dt.datetime.utcnow()


# === NoemaForge Autodoc Function Header ===
# Function: _parse_ts(ts: str)
# Purpose: Implement the routine ' parse ts'.
# Inputs:
#   - ts: str
# Called by:
#   - src/incident_metrics.py
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
# Function: _percentile(vals: List[float], p: float)
# Purpose: Implement the routine ' percentile'.
# Inputs:
#   - vals: List[float]
#   - p: float
# Called by:
#   - src/observability_metrics.py
# Calls:
#   - sorted, int, min, float, len
# Returns / emits: float
# Key locals:
#   - c, d0, d1, f, k, v
# === End NoemaForge Autodoc Function Header ===
def _percentile(vals: List[float], p: float) -> float:
    if not vals:
        return 0.0
    v = sorted(vals)
    if p <= 0:
        return float(v[0])
    if p >= 100:
        return float(v[-1])
    k = (len(v) - 1) * (p / 100.0)
    f = int(k)
    c = min(len(v) - 1, f + 1)
    if f == c:
        return float(v[f])
    d0 = v[f] * (c - k)
    d1 = v[c] * (k - f)
    return float(d0 + d1)


# === NoemaForge Autodoc Function Header ===
# Function: _load_yaml(path: str)
# Purpose: Implement the routine ' load yaml'.
# Inputs:
#   - path: str
# Called by:
#   - src/brainctl.py
#   - src/noemaforge_core.py
#   - src/canary_runner.py
#   - src/daily_scheduler.py
#   - src/fixture_bundle.py
#   - src/incidents.py
#   - src/knowledge/policy.py
#   - src/llm_backends_manager.py
# Calls:
#   - open, safe_load
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads or writes files
# Key locals:
#   - f
# === End NoemaForge Autodoc Function Header ===
def _load_yaml(path: str) -> Dict[str, Any]:
    if yaml is None:
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


# === NoemaForge Autodoc Function Header ===
# Function: taskqueue_db_path(policy_path: str = '/opt/noemaforge/configs/taskqueue-policy.yaml')
# Purpose: Implement the routine 'taskqueue db path'.
# Inputs:
#   - policy_path: str = '/opt/noemaforge/configs/taskqueue-policy.yaml'
# Called by:
#   - src/metrics_snapshot.py
# Calls:
#   - str, join, _load_yaml, isinstance, get
# Returns / emits: str
# Key locals:
#   - base, fn, pol
# === End NoemaForge Autodoc Function Header ===
def taskqueue_db_path(policy_path: str = "/opt/noemaforge/configs/taskqueue-policy.yaml") -> str:
    pol = _load_yaml(policy_path) or {}
    if not isinstance(pol, dict):
        return "/var/lib/noemaforge/taskqueue/tasks.db"
    base = str((pol.get("storage") or {}).get("base_dir") or "/var/lib/noemaforge/taskqueue")
    fn = str((pol.get("storage") or {}).get("db_file") or "tasks.db")
    return os.path.join(base, fn)


# === NoemaForge Autodoc Function Header ===
# Function: flow_snapshot(db_path: str, window_hours: int = 24, percentiles: Optional[List[int]] = None)
# Purpose: Implement the routine 'flow snapshot'.
# Inputs:
#   - db_path: str
#   - window_hours: int = 24
#   - percentiles: Optional[List[int]] = None
# Called by:
#   - src/metrics_snapshot.py
# Calls:
#   - _now, connect, timedelta, exists, fetchall, close, int, upper, _parse_ts, str, startswith, _dist
# Returns / emits: Dict[str, Any]
# Side effects:
#   - opens a database or socket connection
# Key locals:
#   - by_domain, by_priority, claimed, con, created, cutoff, cycle, daily_done, dom, done, done_rows, exec_t
# === End NoemaForge Autodoc Function Header ===
def flow_snapshot(
    *,
    db_path: str,
    window_hours: int = 24,
    percentiles: Optional[List[int]] = None,
) -> Dict[str, Any]:
    pct = percentiles or [50, 95]
    now = _now()
    cutoff = now - dt.timedelta(hours=max(1, int(window_hours)))

    if not os.path.exists(db_path):
        return {
            "window_hours": int(window_hours),
            "db_path": db_path,
            "status_counts": {},
            "done": 0,
            "throughput": 0,
            "cycle_time_sec": {},
            "lead_time_sec": {},
            "exec_time_sec": {},
            "note": "taskqueue db missing",
        }

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        # Status counts (all time)
        rows = con.execute("SELECT status, COUNT(*) AS n FROM tasks GROUP BY status").fetchall()
        status_counts = {str(r[0] or "").upper(): int(r[1] or 0) for r in rows}

        # DONE tasks in window
        done_rows = con.execute(
            "SELECT created_at, claimed_at, updated_at, domain, priority_class, group_key FROM tasks WHERE status='DONE'"
        ).fetchall()

        cycle: List[float] = []
        lead: List[float] = []
        exec_t: List[float] = []
        done = 0
        by_domain: Dict[str, int] = {}
        by_priority: Dict[str, int] = {}
        daily_done = 0

        for r in done_rows:
            updated = _parse_ts(str(r[2] or ""))
            if updated is None or updated < cutoff:
                continue
            done += 1
            dom = str(r[3] or "UNKNOWN").upper()
            pr = str(r[4] or "").upper()
            gk = str(r[5] or "")
            by_domain[dom] = by_domain.get(dom, 0) + 1
            if pr:
                by_priority[pr] = by_priority.get(pr, 0) + 1
            if gk.startswith("daily."):
                daily_done += 1

            created = _parse_ts(str(r[0] or ""))
            claimed = _parse_ts(str(r[1] or ""))
            if created is not None:
                cycle.append(max(0.0, (updated - created).total_seconds()))
            if created is not None and claimed is not None:
                lead.append(max(0.0, (claimed - created).total_seconds()))
            if claimed is not None:
                exec_t.append(max(0.0, (updated - claimed).total_seconds()))

        # === NoemaForge Autodoc Function Header ===
        # Function: _dist(vals: List[float])
        # Purpose: Implement the routine ' dist'.
        # Inputs:
        #   - vals: List[float]
        # Called by:
        #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
        # Calls:
        #   - _percentile, float, sum, len, int
        # Returns / emits: Dict[str, Any]
        # Key locals:
        #   - out, p
        # === End NoemaForge Autodoc Function Header ===
        def _dist(vals: List[float]) -> Dict[str, Any]:
            out: Dict[str, Any] = {"avg": (sum(vals) / len(vals)) if vals else 0.0}
            for p in pct:
                out[f"p{int(p)}"] = _percentile(vals, float(p))
            return out

        return {
            "window_hours": int(window_hours),
            "db_path": db_path,
            "status_counts": status_counts,
            "throughput": int(done),
            "by_domain": by_domain,
            "by_priority": by_priority,
            "daily_done": int(daily_done),
            "cycle_time_sec": _dist(cycle),
            "lead_time_sec": _dist(lead),
            "exec_time_sec": _dist(exec_t),
        }
    finally:
        con.close()


if __name__ == "__main__":  # pragma: no cover
    import json
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=taskqueue_db_path())
    ap.add_argument("--window-hours", type=int, default=24)
    args = ap.parse_args()
    print(json.dumps(flow_snapshot(db_path=args.db, window_hours=args.window_hours), ensure_ascii=False, indent=2))
