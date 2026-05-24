#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/canary_runner.py
Zone: release/package
Version: 0.31.13.alpha-patched1
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
# File: src/canary_runner.py
# Purpose: Provide the module 'canary_runner'.
# Invoked by / imported from:
#   - No inbound Python import detected; treat as library leaf or direct entrypoint.
# Public API / entry functions:
#   - main
# Inputs:
#   - --base
#   - --cand
#   - --law
#   - --suite
#   - --report-path
#   - Imports: __future__, argparse, json, os, resource, sys, typing, yaml
# Output formats / side effects:
#   - JSON files
#   - YAML files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""canary_runner.py (v0.11.0)

Runs canary suites under resource limits.

This is used by brainctl prestart apply-epoch.

Limits are best-effort via RLIMITs; for stronger isolation, run canaries in a microVM/container.
"""


import argparse
import json
import os
import resource
import sys
from typing import Any, Dict

import yaml

import prestart


# === NoemaForge Autodoc Function Header ===
# Function: _load_yaml(path: str)
# Purpose: Implement the routine ' load yaml'.
# Inputs:
#   - path: str
# Called by:
#   - src/brainctl.py
#   - src/noemaforge_core.py
#   - src/daily_scheduler.py
#   - src/fixture_bundle.py
#   - src/flow_metrics.py
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
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# === NoemaForge Autodoc Function Header ===
# Function: _apply_rlimits(profile: Dict[str, Any])
# Purpose: Implement the routine ' apply rlimits'.
# Inputs:
#   - profile: Dict[str, Any]
# Called by:
#   - src/sandbox.py
# Calls:
#   - int, get, setrlimit
# Returns / emits: None
# Key locals:
#   - cpu, fmax_mib, lim, mem_mib, pids
# === End NoemaForge Autodoc Function Header ===
def _apply_rlimits(profile: Dict[str, Any]) -> None:
    # CPU time (seconds)
    cpu = int(profile.get("cpu_time_sec") or 0)
    if cpu > 0:
        try:
            resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
        except Exception:
            pass

    # Address space (bytes)
    mem_mib = int(profile.get("mem_max_mib") or 0)
    if mem_mib > 0:
        lim = mem_mib * 1024 * 1024
        try:
            resource.setrlimit(resource.RLIMIT_AS, (lim, lim))
        except Exception:
            pass

    # Processes
    pids = int(profile.get("pids_max") or 0)
    if pids > 0:
        try:
            resource.setrlimit(resource.RLIMIT_NPROC, (pids, pids))
        except Exception:
            pass

    # File size
    fmax_mib = int(profile.get("file_max_mib") or 0)
    if fmax_mib > 0:
        lim = fmax_mib * 1024 * 1024
        try:
            resource.setrlimit(resource.RLIMIT_FSIZE, (lim, lim))
        except Exception:
            pass


# === NoemaForge Autodoc Function Header ===
# Function: main(argv: list[str])
# Purpose: Implement the routine 'main'.
# Inputs:
#   - argv: list[str]
# Called by:
#   - bootstrap/microvm/noemaforge-microvm-run.py
#   - src/bootdoctor.py
#   - src/brainctl.py
#   - src/noemaforge_core.py
#   - src/brainui.py
#   - src/doctor.py
#   - src/dream_cycle.py
#   - src/firstboot_eval.py
# Calls:
#   - ArgumentParser, add_argument, parse_args, join, _apply_rlimits, canary_run_report, bool, print, strip, exists, _load_yaml, get
# Returns / emits: int
# Side effects:
#   - spawns subprocesses or workers
# Key locals:
#   - ap, args, evt3, f, flat_problems, law_dir, ok, out, policy, policy_path, quotas, report
# === End NoemaForge Autodoc Function Header ===
def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True, help="base epoch dir")
    ap.add_argument("--cand", required=True, help="candidate epoch dir")
    ap.add_argument("--law", default="", help="law epoch dir (policy/fixtures), defaults to --base")
    ap.add_argument("--suite", required=True, choices=["smoke", "full"], help="suite")
    ap.add_argument("--report-path", default="", help="where to persist report (defaults to <cand>/scary_report.json)")
    args = ap.parse_args(argv)

    law_dir = args.law.strip() or args.base

    policy_path = os.path.join(law_dir, "canary-policy.yaml")
    policy = _load_yaml(policy_path) if os.path.exists(policy_path) else {}
    quotas = (policy.get("quota_profiles") or {}).get(args.suite) or {}
    _apply_rlimits(quotas)

    # Run canary and build structured report
    report = prestart.canary_run_report(base_epoch_dir=args.base, cand_epoch_dir=args.cand, law_epoch_dir=law_dir, suite=args.suite, quotas_applied=quotas)

    # Add resource usage
    try:
        ru = resource.getrusage(resource.RUSAGE_SELF)
        report.setdefault("resource_usage", {})
        report["resource_usage"]["ru_maxrss"] = float(getattr(ru, "ru_maxrss", 0.0))
        report["resource_usage"]["ru_utime"] = float(getattr(ru, "ru_utime", 0.0))
        report["resource_usage"]["ru_stime"] = float(getattr(ru, "ru_stime", 0.0))
    except Exception:
        pass

    # Persist report inside the candidate epoch directory
    report_path = args.report_path.strip() or os.path.join(args.cand, "scary_report.json")
    try:
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        # Log that the report was saved
        if getattr(prestart, "sel_append", None):
            evt3 = prestart.sel_append({
                "severity": "info" if report.get("overall_ok") else "high",
                "type": "canary_report_saved",
                "suite": args.suite,
                "base_epoch": os.path.basename(os.path.realpath(args.base)),
                "candidate_epoch": os.path.basename(os.path.realpath(args.cand)),
                "law_epoch": os.path.basename(os.path.realpath(law_dir)),
                "report_path": report_path,
                "decision": report.get("decision"),
            })
            # Attach SEL refs if present
            try:
                report.setdefault("sel_refs", {})
                report["sel_refs"]["saved_evt_id"] = evt3.get("evt_id")
                report["sel_refs"]["saved_sel_hash"] = evt3.get("_sel_hash")
                with open(report_path, "w", encoding="utf-8") as f:
                    json.dump(report, f, ensure_ascii=False, indent=2)
            except Exception:
                pass
    except Exception:
        # If we can't persist the report, we still return it in stdout.
        report_path = ""

    flat_problems = list(report.get("problems") or []) + ["warn:" + w for w in (report.get("warnings") or [])]
    ok = bool(report.get("overall_ok"))

    out = {"ok": ok, "problems": flat_problems, "suite": args.suite, "report_path": report_path, "report": report}
    print(json.dumps(out, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
