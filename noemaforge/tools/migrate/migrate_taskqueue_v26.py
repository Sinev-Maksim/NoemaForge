#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tools/migrate/migrate_taskqueue_v26.py
Zone: release/package
Version: 0.31.13.alpha
Created: 2026-05-14
Modified: 2026-05-14
Purpose: Manage NoemaForge task queue and task execution surfaces.
Inputs: Command-line arguments, environment variables, package files and local NoemaForge runtime state as applicable.
Outputs: Structured command output, files, service state or UI state as documented by the caller.
Side effects: Limited to the documented NoemaForge paths, runtime state directories or systemd units used by this file.
Tests: Syntax validation plus the release setup selftest, consistency-audit and targeted smoke checks.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

# === NoemaForge Autodoc File Header ===
# File: tools/migrate/migrate_taskqueue_v26.py
# Purpose: Run one-time migration logic for 'migrate_taskqueue_v26'.
# Invoked by / imported from:
#   - No inbound Python import detected; treat as library leaf or direct entrypoint.
# Public API / entry functions:
#   - main
# Inputs:
#   - --dry-run
#   - Imports: __future__, argparse, json, task_tools
# Output formats / side effects:
#   - JSON files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

import argparse, json
import task_tools
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
#   - ArgumentParser, add_argument, parse_args, print, bool, update, dumps, init_v26_schema
# Returns / emits: int
# Side effects:
#   - serializes structured data
# Key locals:
#   - ap, ns, out
# === End NoemaForge Autodoc Function Header ===
def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--dry-run", action="store_true"); ns = ap.parse_args()
    out = {"ok": True, "dry_run": bool(ns.dry_run)}
    if not ns.dry_run:
        out.update(task_tools.init_v26_schema())
    print(json.dumps(out, ensure_ascii=False, indent=2)); return 0
if __name__ == "__main__": raise SystemExit(main())
