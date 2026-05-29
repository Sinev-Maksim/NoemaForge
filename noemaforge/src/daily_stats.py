#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/daily_stats.py
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
# File: src/daily_stats.py
# Purpose: Provide the module 'daily_stats'.
# Invoked by / imported from:
#   - src/noemaforge_core.py
#   - src/daily_scheduler.py
#   - src/maintenance.py
# Public API / entry functions:
#   - record
#   - mean_sigma
# Inputs:
#   - Common path inputs: /var/lib/noemaforge
#   - Imports: __future__, json, math, os, typing
# Output formats / side effects:
#   - JSON files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""daily_stats.py (v0.11.4)

Stores per-task execution duration statistics (mean + sigma) for daily SLA planning.

We keep this small and robust:
- JSON file updated atomically.
- Welford online algorithm for stable mean/variance.

Used by:
- maintenance.py (SLA start-by calculation)
- noemaforge_core.run_recurring() (stats updates)

Note:
- We only update the SUCCESS stream by default; failures are tracked separately.
"""


import json
import math
import os
from typing import Any, Dict, Tuple

BASE = "/var/lib/noemaforge"
METRICS_DIR = os.path.join(BASE, "metrics")
STATS_PATH = os.path.join(METRICS_DIR, "daily_task_stats.json")


# === NoemaForge Autodoc Function Header ===
# Function: _load()
# Purpose: Implement the routine ' load'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - open, load
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads or writes files
# Key locals:
#   - f
# === End NoemaForge Autodoc Function Header ===
def _load() -> Dict[str, Any]:
    try:
        with open(STATS_PATH, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {"tasks": {}}


# === NoemaForge Autodoc Function Header ===
# Function: _save(obj: Dict[str, Any])
# Purpose: Implement the routine ' save'.
# Inputs:
#   - obj: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - makedirs, replace, dirname, open, dump, chmod
# Returns / emits: None
# Side effects:
#   - reads or writes files
#   - serializes structured data
#   - creates directories
# Key locals:
#   - f, tmp
# === End NoemaForge Autodoc Function Header ===
def _save(obj: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(STATS_PATH), exist_ok=True)
    tmp = STATS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATS_PATH)
    try:
        os.chmod(STATS_PATH, 0o600)
    except Exception:
        pass


# === NoemaForge Autodoc Function Header ===
# Function: _welford_update(n: int, mean: float, m2: float, x: float)
# Purpose: Implement the routine ' welford update'.
# Inputs:
#   - n: int
#   - mean: float
#   - m2: float
#   - x: float
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Returns / emits: Tuple[int, float, float]
# Key locals:
#   - delta, delta2, m2_2, mean2, n2
# === End NoemaForge Autodoc Function Header ===
def _welford_update(n: int, mean: float, m2: float, x: float) -> Tuple[int, float, float]:
    n2 = n + 1
    delta = x - mean
    mean2 = mean + delta / n2
    delta2 = x - mean2
    m2_2 = m2 + delta * delta2
    return n2, mean2, m2_2


# === NoemaForge Autodoc Function Header ===
# Function: record(task_id: str, duration_sec: float, status: str = 'SUCCESS')
# Purpose: Record one execution.
# Inputs:
#   - task_id: str
#   - duration_sec: float
#   - status: str = 'SUCCESS'
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _load, setdefault, _save, int, float, str, _welford_update, get
# Returns / emits: Dict[str, Any]
# Key locals:
#   - counts, m2, mean, n, obj, s, t, tasks
# === End NoemaForge Autodoc Function Header ===
def record(task_id: str, duration_sec: float, status: str = "SUCCESS") -> Dict[str, Any]:
    """Record one execution.

    status: SUCCESS | FAILED | CACHE_HIT | ...

    We update SUCCESS stats only for SUCCESS.
    We still keep counters for other statuses.
    """

    obj = _load()
    tasks = obj.setdefault("tasks", {})
    t = tasks.setdefault(task_id, {
        "counts": {},
        "success": {"n": 0, "mean_sec": 0.0, "m2": 0.0},
        "last": None,
    })

    counts = t.setdefault("counts", {})
    counts[status] = int(counts.get(status, 0) or 0) + 1

    t["last"] = {"duration_sec": float(duration_sec), "status": str(status)}

    if status == "SUCCESS":
        s = t.setdefault("success", {"n": 0, "mean_sec": 0.0, "m2": 0.0})
        n = int(s.get("n", 0) or 0)
        mean = float(s.get("mean_sec", 0.0) or 0.0)
        m2 = float(s.get("m2", 0.0) or 0.0)
        n2, mean2, m2_2 = _welford_update(n, mean, m2, float(duration_sec))
        s["n"] = n2
        s["mean_sec"] = mean2
        s["m2"] = m2_2

    _save(obj)
    return t


# === NoemaForge Autodoc Function Header ===
# Function: mean_sigma(task_id: str)
# Purpose: Return (mean_sec, sigma_sec, n_success).
# Inputs:
#   - task_id: str
# Called by:
#   - src/daily_scheduler.py
# Calls:
#   - _load, int, float, get, sqrt
# Returns / emits: Tuple[float, float, int]
# Key locals:
#   - m2, mean, n, obj, s, sigma, t, var
# === End NoemaForge Autodoc Function Header ===
def mean_sigma(task_id: str) -> Tuple[float, float, int]:
    """Return (mean_sec, sigma_sec, n_success)."""
    obj = _load()
    t = (obj.get("tasks") or {}).get(task_id) or {}
    s = t.get("success") or {}
    n = int(s.get("n", 0) or 0)
    mean = float(s.get("mean_sec", 0.0) or 0.0)
    m2 = float(s.get("m2", 0.0) or 0.0)
    if n < 2:
        return mean, 0.0, n
    var = m2 / (n - 1)
    sigma = math.sqrt(var) if var > 0 else 0.0
    return mean, sigma, n
