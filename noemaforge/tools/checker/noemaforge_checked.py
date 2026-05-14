#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tools/checker/noemaforge_checked.py
Zone: release/package
Version: 0.31.13.alpha
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
# File: tools/checker/noemaforge_checked.py
# Purpose: Run offline integrity or attestation checks for 'noemaforge_checked'.
# Invoked by / imported from:
#   - No inbound Python import detected; treat as library leaf or direct entrypoint.
# Public API / entry functions:
#   - main
# Inputs:
#   - --root
#   - --out
#   - --zip
#   - Common path inputs: noemaforge.checker/v1, noemaforge.checked/v1
#   - Imports: __future__, argparse, datetime, hashlib, json, os, platform, re
# Output formats / side effects:
#   - JSON files
#   - YAML files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""noemaforge_checked.py (v0.24.0)

Create a single "checked" attestation file for a NoemaForge seed release.

Why
---
The seed kit has many moving parts (PowerShell wrappers, configs, contracts).
For first-run sanity — especially on Windows machines without WSL/network — it is
useful to have one file that:
  - embeds a full `noemaforge_check.py --deep` report
  - includes load-bearing hashes (manifest + SHA256SUMS)
  - optionally includes the release zip sha256

The output format is JSON (UTF-8). The extension is intentionally spelled
".chexked" to avoid collisions with OS "checked" markers.

Usage
-----
  python tools/checker/noemaforge_checked.py --root <noemaforge_root> --out 24.chexked

Optional:
  --zip <noemaforge-flat-vX.Y.Z.zip>   include zip sha256

Exit codes
----------
  0 = generated and check report has no FAIL
  1 = generated but WARN present
  2 = generated but FAIL present
"""


import argparse
import datetime as dt
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
from typing import Any, Dict, Optional


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
#   - strftime, now
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _nowz() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


# === NoemaForge Autodoc Function Header ===
# Function: _sha256_file(path: str)
# Purpose: Implement the routine ' sha256 file'.
# Inputs:
#   - path: str
# Called by:
#   - src/bootdoctor.py
#   - src/brainctl.py
#   - src/casebase.py
#   - src/doctor.py
#   - src/glove_agent.py
#   - src/localgw_uplink_agent.py
#   - src/model_registry.py
#   - src/pipelines/finance_budget.py
# Calls:
#   - sha256, hexdigest, open, iter, update, read
# Returns / emits: str
# Side effects:
#   - reads or writes files
# Key locals:
#   - chunk, f, h
# === End NoemaForge Autodoc Function Header ===
def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


# === NoemaForge Autodoc Function Header ===
# Function: _load_manifest_minimal(path: str)
# Purpose: Parse only top-level scalar keys from manifest.yaml without PyYAML.
# Inputs:
#   - path: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - splitlines, match, strip, startswith, read, group, len, open
# Returns / emits: Dict[str, str]
# Side effects:
#   - reads or writes files
# Key locals:
#   - k, ln, m, out, raw, v
# === End NoemaForge Autodoc Function Header ===
def _load_manifest_minimal(path: str) -> Dict[str, str]:
    """Parse only top-level scalar keys from manifest.yaml without PyYAML."""
    out: Dict[str, str] = {}
    try:
        raw = open(path, "r", encoding="utf-8").read().splitlines()
    except Exception:
        return out

    # Very small YAML subset: `key: value` (no nesting)
    for ln in raw:
        if not ln or ln.startswith("#") or ln.startswith(" ") or ln.startswith("\t"):
            continue
        m = re.match(r"^([A-Za-z0-9_\-]+)\s*:\s*(.*)$", ln)
        if not m:
            continue
        k = m.group(1).strip()
        v = m.group(2).strip()
        # strip quotes
        if len(v) >= 2 and ((v[0] == v[-1] == "'") or (v[0] == v[-1] == '"')):
            v = v[1:-1]
        out[k] = v
    return out


# === NoemaForge Autodoc Function Header ===
# Function: _run_noemaforge_check(root: str)
# Purpose: Run noemaforge_check.py as a subprocess and return parsed JSON report.
# Inputs:
#   - root: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - join, dirname, exists, FileNotFoundError, NamedTemporaryFile, run, int, strip, loads, read, open
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads or writes files
#   - spawns subprocesses or workers
# Key locals:
#   - checker, cmd, out_path, p, rep, tf
# === End NoemaForge Autodoc Function Header ===
def _run_noemaforge_check(root: str) -> Dict[str, Any]:
    """Run noemaforge_check.py as a subprocess and return parsed JSON report."""
    checker = os.path.join(os.path.dirname(__file__), "noemaforge_check.py")
    if not os.path.exists(checker):
        raise FileNotFoundError(f"noemaforge_check.py not found: {checker}")

    with tempfile.NamedTemporaryFile(prefix="noemaforge_check_", suffix=".json", delete=False) as tf:
        out_path = tf.name

    try:
        cmd = [sys.executable, checker, "--root", root, "--out", out_path, "--deep"]
        p = subprocess.run(cmd, capture_output=True, text=True)
        # noemaforge_check always writes JSON even on failure; keep stdout/stderr for debugging.
        rep: Dict[str, Any] = {}
        try:
            rep = json.loads(open(out_path, "r", encoding="utf-8").read())
        except Exception:
            rep = {"apiVersion": "noemaforge.checker/v1", "kind": "SeedCheckReport", "summary": {"fails": 1, "warns": 0}, "steps": []}
        rep["_checker_exit"] = int(p.returncode)
        if p.stdout.strip():
            rep["_checker_stdout"] = p.stdout[-4000:]
        if p.stderr.strip():
            rep["_checker_stderr"] = p.stderr[-4000:]
        rep["_checker_report_path"] = out_path
        return rep
    finally:
        # Keep the JSON report for audit; the chexked file will reference it.
        pass


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
#   - ArgumentParser, add_argument, parse_args, abspath, join, _load_manifest_minimal, _run_noemaforge_check, int, makedirs, exists, SystemExit, get
# Returns / emits: int
# Side effects:
#   - creates directories
#   - spawns subprocesses or workers
# Key locals:
#   - ap, args, att, check_report, f, fails, manifest, manifest_path, n_sums, out_path, root, summary
# === End NoemaForge Autodoc Function Header ===
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="Path to NoemaForge root (seed/noemaforge)")
    ap.add_argument("--out", required=True, help="Output .chexked file path")
    ap.add_argument("--zip", default="", help="Optional release zip to hash")
    args = ap.parse_args()

    root = os.path.abspath(args.root)
    out_path = os.path.abspath(args.out)

    manifest_path = os.path.join(root, "manifest.yaml")
    sums_path = os.path.join(root, "checksums", "SHA256SUMS")
    if not os.path.exists(manifest_path):
        raise SystemExit(f"manifest.yaml not found under root: {manifest_path}")
    if not os.path.exists(sums_path):
        raise SystemExit(f"SHA256SUMS not found under root: {sums_path}")

    manifest = _load_manifest_minimal(manifest_path)

    check_report = _run_noemaforge_check(root)
    summary = check_report.get("summary") or {}
    fails = int(summary.get("fails") or 0)
    warns = int(summary.get("warns") or 0)

    # Count SHA256SUMS entries
    try:
        n_sums = sum(1 for ln in open(sums_path, "r", encoding="utf-8") if ln.strip())
    except Exception:
        n_sums = 0

    zip_info: Optional[Dict[str, Any]] = None
    if args.zip and args.zip.strip():
        zpath = os.path.abspath(args.zip)
        if os.path.exists(zpath):
            zip_info = {"path": zpath, "sha256": _sha256_file(zpath), "size": os.path.getsize(zpath)}
        else:
            zip_info = {"path": zpath, "error": "not_found"}

    att = {
        "apiVersion": "noemaforge.checked/v1",
        "kind": "SeedChecked",
        "created_at": _nowz(),
        "seed": {
            "root": root,
            "noemaforge_version": manifest.get("noemaforge_version", ""),
            "version": manifest.get("version", ""),
            "codename": manifest.get("codename", ""),
            "manifest_sha256": _sha256_file(manifest_path),
            "sha256sums_sha256": _sha256_file(sums_path),
            "sha256sums_entries": n_sums,
        },
        "artifacts": {
            "seed_zip": zip_info,
        },
        "checks": {
            "checker": "tools/checker/noemaforge_check.py --deep",
            "summary": {"fails": fails, "warns": warns},
            "report": check_report,
        },
        "environment": {
            "python": sys.version.replace("\n", " "),
            "platform": platform.platform(),
        },
        "notes": [
            "This file is an offline attestation. Re-run noemaforge_check on the target machine to confirm.",
            "If the ZIP sha256 is present above, you can verify the downloaded archive before unpacking.",
        ],
    }

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(att, f, ensure_ascii=False, indent=2)
        f.write("\n")

    # Exit code mirrors noemaforge_check semantics
    if fails > 0:
        return 2
    if warns > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
