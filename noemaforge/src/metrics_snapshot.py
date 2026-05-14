#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/metrics_snapshot.py
Zone: release/package
Version: 0.31.13.alpha
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
# File: src/metrics_snapshot.py
# Purpose: Provide the module 'metrics_snapshot'.
# Invoked by / imported from:
#   - src/sr_cycle.py
#   - src/ssr_cycle.py
# Public API / entry functions:
#   - build_snapshot
#   - save_snapshot
#   - main
# Inputs:
#   - --window-hours
#   - --out-dir
#   - Environment: NOEMAFORGE_INCIDENTS_DB
#   - Common path inputs: /var/lib/noemaforge/incidents/incidents.db
#   - Imports: __future__, datetime, json, os, typing, telemetry, observability_metrics, flow_metrics
# Output formats / side effects:
#   - JSON files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""metrics_snapshot.py (v0.20.4)

Build a unified metrics snapshot used by SR/SSR and by debugging.

This is designed to be *safe* and *cheap*:
- reads local telemetry/taskqueue/incidents
- emits one JSON file
"""


import datetime as dt
import json
import os
from typing import Any, Dict, Optional


from telemetry import load_policy as _load_obs_policy, _storage_paths as _obs_paths
from observability_metrics import llm_metrics
from flow_metrics import flow_snapshot, taskqueue_db_path
from incident_metrics import incident_snapshot


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
#   - strftime, utcnow
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _nowz() -> str:
    return dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")


# === NoemaForge Autodoc Function Header ===
# Function: build_snapshot(window_hours: int = 24)
# Purpose: Implement the routine 'build snapshot'.
# Inputs:
#   - window_hours: int = 24
# Called by:
#   - src/brainui.py
# Calls:
#   - _load_obs_policy, _obs_paths, taskqueue_db_path, get, _nowz, int, llm_metrics, flow_snapshot, incident_snapshot
# Returns / emits: Dict[str, Any]
# Key locals:
#   - inc_db, llm_path, out, paths, pct, pol, tq_db
# === End NoemaForge Autodoc Function Header ===
def build_snapshot(*, window_hours: int = 24) -> Dict[str, Any]:
    pol = _load_obs_policy()
    paths = _obs_paths(pol)
    llm_path = paths["llm_calls"]
    tq_db = taskqueue_db_path()
    inc_db = os.environ.get("NOEMAFORGE_INCIDENTS_DB") or "/var/lib/noemaforge/incidents/incidents.db"

    pct = [50, 95]
    try:
        pct = [int(x) for x in ((pol.get("metrics") or {}).get("snapshots") or {}).get("percentiles") or [50, 95]]
    except Exception:
        pct = [50, 95]

    out = {
        "schema_version": "v1",
        "kind": "MetricsSnapshot",
        "created_at": _nowz(),
        "window_hours": int(window_hours),
        "llm": llm_metrics(llm_calls_path=llm_path, window_hours=window_hours, percentiles=pct),
        "flow": flow_snapshot(db_path=tq_db, window_hours=window_hours, percentiles=pct),
        "incidents": incident_snapshot(db_path=inc_db, window_hours=window_hours),
    }
    return out


# === NoemaForge Autodoc Function Header ===
# Function: save_snapshot(window_hours: int = 24, out_dir: Optional[str] = None)
# Purpose: Implement the routine 'save snapshot'.
# Inputs:
#   - window_hours: int = 24
#   - out_dir: Optional[str] = None
# Called by:
#   - src/sr_cycle.py
#   - src/ssr_cycle.py
# Calls:
#   - _load_obs_policy, _obs_paths, makedirs, join, build_snapshot, open, dump, _nowz
# Returns / emits: str
# Side effects:
#   - reads or writes files
#   - serializes structured data
#   - creates directories
# Key locals:
#   - f, fn, path, paths, pol, snap, snap_dir
# === End NoemaForge Autodoc Function Header ===
def save_snapshot(*, window_hours: int = 24, out_dir: Optional[str] = None) -> str:
    pol = _load_obs_policy()
    paths = _obs_paths(pol)
    snap_dir = out_dir or paths["snapshots"]
    os.makedirs(snap_dir, exist_ok=True)
    fn = f"metrics_{_nowz()}.json"
    path = os.path.join(snap_dir, fn)
    snap = build_snapshot(window_hours=window_hours)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(snap, f, ensure_ascii=False, indent=2)
    return path


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
#   - ArgumentParser, add_argument, parse_args, save_snapshot, print
# Returns / emits: int
# Key locals:
#   - ap, args, path
# === End NoemaForge Autodoc Function Header ===
def main() -> int:  # pragma: no cover
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--window-hours", type=int, default=24)
    ap.add_argument("--out-dir", default="")
    args = ap.parse_args()
    path = save_snapshot(window_hours=args.window_hours, out_dir=args.out_dir or None)
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
