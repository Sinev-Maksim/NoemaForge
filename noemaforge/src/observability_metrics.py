#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/observability_metrics.py
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
# File: src/observability_metrics.py
# Purpose: Provide the module 'observability_metrics'.
# Invoked by / imported from:
#   - src/metrics_snapshot.py
# Public API / entry functions:
#   - llm_metrics
#   - main
# Inputs:
#   - --llm-calls
#   - --window-hours
#   - --out
#   - Imports: __future__, argparse, datetime, json, os, typing
# Output formats / side effects:
#   - JSON files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""observability_metrics.py (v0.20.4)

Compute rolling metrics from telemetry logs.

This is a spine-safe module:
- no network
- reads local JSONL
- outputs JSON snapshots
"""


import argparse
import datetime as dt
import json
import os
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
#   - isoformat, utcnow
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _nowz() -> str:
    return dt.datetime.utcnow().isoformat() + "Z"


# === NoemaForge Autodoc Function Header ===
# Function: _parse_ts(ts: str)
# Purpose: Implement the routine ' parse ts'.
# Inputs:
#   - ts: str
# Called by:
#   - src/flow_metrics.py
#   - src/incident_metrics.py
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
        # tolerate microseconds
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
#   - src/flow_metrics.py
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
# Function: _read_jsonl(path: str)
# Purpose: Implement the routine ' read jsonl'.
# Inputs:
#   - path: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - gen, exists, open, strip, loads, isinstance
# Returns / emits: Iterable[Dict[str, Any]]
# Side effects:
#   - reads or writes files
# Key locals:
#   - f, line, obj, t
# === End NoemaForge Autodoc Function Header ===
def _read_jsonl(path: str) -> Iterable[Dict[str, Any]]:
    if not os.path.exists(path):
        return []
    # === NoemaForge Autodoc Function Header ===
    # Function: gen()
    # Purpose: Implement the routine 'gen'.
    # Inputs:
    #   - No explicit parameters.
    # Called by:
    #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
    # Calls:
    #   - open, strip, loads, isinstance
    # Returns / emits: Iterable[Dict[str, Any]]
    # Side effects:
    #   - reads or writes files
    # Key locals:
    #   - f, line, obj, t
    # === End NoemaForge Autodoc Function Header ===
    def gen() -> Iterable[Dict[str, Any]]:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                t = line.strip()
                if not t:
                    continue
                try:
                    obj = json.loads(t)
                    if isinstance(obj, dict):
                        yield obj
                except Exception:
                    continue
    return gen()


# === NoemaForge Autodoc Function Header ===
# Function: llm_metrics(llm_calls_path: str, window_hours: int = 24, percentiles: Optional[List[int]] = None)
# Purpose: Implement the routine 'llm metrics'.
# Inputs:
#   - llm_calls_path: str
#   - window_hours: int = 24
#   - percentiles: Optional[List[int]] = None
# Called by:
#   - src/metrics_snapshot.py
# Calls:
#   - utcnow, _read_jsonl, items, timedelta, _parse_ts, bool, str, setdefault, int, _percentile, get, float
# Returns / emits: Dict[str, Any]
# Key locals:
#   - bm, by_model, calls, ct, cte, cutoff, ent, err_calls, err_rate, lat, lat_ms, model
# === End NoemaForge Autodoc Function Header ===
def llm_metrics(
    *,
    llm_calls_path: str,
    window_hours: int = 24,
    percentiles: Optional[List[int]] = None,
) -> Dict[str, Any]:
    pct = percentiles or [50, 95]
    now = dt.datetime.utcnow()
    cutoff = now - dt.timedelta(hours=max(1, int(window_hours)))

    calls = 0
    ok_calls = 0
    lat_ms: List[float] = []
    tok_in = 0
    tok_out = 0
    tok_in_est = 0
    tok_out_est = 0

    by_model: Dict[str, Dict[str, Any]] = {}

    for obj in _read_jsonl(llm_calls_path):
        ts = _parse_ts(str(obj.get("ts") or ""))
        if ts is not None and ts < cutoff:
            continue
        calls += 1
        ok = bool(obj.get("ok"))
        if ok:
            ok_calls += 1
        try:
            lat = float(obj.get("elapsed_ms") or 0)
        except Exception:
            lat = 0.0
        if lat > 0:
            lat_ms.append(lat)
        model = str(obj.get("model") or "unknown")
        bm = by_model.setdefault(model, {"calls": 0, "ok": 0, "lat_ms": [], "tok_in": 0, "tok_out": 0, "tok_in_est": 0, "tok_out_est": 0})
        bm["calls"] += 1
        if ok:
            bm["ok"] += 1
        if lat > 0:
            bm["lat_ms"].append(lat)

        usage = obj.get("usage") if isinstance(obj.get("usage"), dict) else {}
        try:
            pt = int(usage.get("prompt_tokens") or 0)
        except Exception:
            pt = 0
        try:
            ct = int(usage.get("completion_tokens") or 0)
        except Exception:
            ct = 0
        try:
            pte = int(usage.get("estimated_prompt_tokens") or 0)
        except Exception:
            pte = 0
        try:
            cte = int(usage.get("estimated_completion_tokens") or 0)
        except Exception:
            cte = 0

        tok_in += pt
        tok_out += ct
        tok_in_est += pte
        tok_out_est += cte
        bm["tok_in"] += pt
        bm["tok_out"] += ct
        bm["tok_in_est"] += pte
        bm["tok_out_est"] += cte

    err_calls = calls - ok_calls
    err_rate = (err_calls / calls) if calls else 0.0

    out: Dict[str, Any] = {
        "window_hours": int(window_hours),
        "calls": calls,
        "ok": ok_calls,
        "errors": err_calls,
        "error_rate": err_rate,
        "latency_ms": {"avg": (sum(lat_ms) / len(lat_ms)) if lat_ms else 0.0},
        "tokens": {
            "prompt_tokens": tok_in,
            "completion_tokens": tok_out,
            "estimated_prompt_tokens": tok_in_est,
            "estimated_completion_tokens": tok_out_est,
        },
        "by_model": {},
    }

    for p in pct:
        out["latency_ms"][f"p{int(p)}"] = _percentile(lat_ms, float(p))

    # Summarize by model
    for m, bm in by_model.items():
        lat = bm.get("lat_ms") or []
        ent = {
            "calls": int(bm.get("calls") or 0),
            "ok": int(bm.get("ok") or 0),
            "errors": int(bm.get("calls") or 0) - int(bm.get("ok") or 0),
            "error_rate": ((int(bm.get("calls") or 0) - int(bm.get("ok") or 0)) / int(bm.get("calls") or 1)),
            "latency_ms": {"avg": (sum(lat) / len(lat)) if lat else 0.0},
            "tokens": {
                "prompt_tokens": int(bm.get("tok_in") or 0),
                "completion_tokens": int(bm.get("tok_out") or 0),
                "estimated_prompt_tokens": int(bm.get("tok_in_est") or 0),
                "estimated_completion_tokens": int(bm.get("tok_out_est") or 0),
            },
        }
        for p in pct:
            ent["latency_ms"][f"p{int(p)}"] = _percentile(lat, float(p))
        out["by_model"][m] = ent

    return out


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
#   - ArgumentParser, add_argument, parse_args, llm_metrics, dumps, _nowz, makedirs, print, dirname, open, write
# Returns / emits: int
# Side effects:
#   - reads or writes files
#   - serializes structured data
#   - creates directories
# Key locals:
#   - ap, args, f, m, s, snap
# === End NoemaForge Autodoc Function Header ===
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm-calls", required=True)
    ap.add_argument("--window-hours", type=int, default=24)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    m = llm_metrics(llm_calls_path=args.llm_calls, window_hours=args.window_hours)
    snap = {
        "schema_version": "v1",
        "kind": "LLMMetricsSnapshot",
        "created_at": _nowz(),
        "llm": m,
    }
    s = json.dumps(snap, ensure_ascii=False, indent=2)
    if args.out:
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        with open(args.out, "w", encoding="utf-8", newline="\n") as f:
            f.write(s)
        print(args.out)
    else:
        print(s)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
