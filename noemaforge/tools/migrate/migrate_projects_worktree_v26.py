#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tools/migrate/migrate_projects_worktree_v26.py
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
# File: tools/migrate/migrate_projects_worktree_v26.py
# Purpose: Run one-time migration logic for 'migrate_projects_worktree_v26'.
# Invoked by / imported from:
#   - No inbound Python import detected; treat as library leaf or direct entrypoint.
# Public API / entry functions:
#   - main
# Inputs:
#   - --project-id
#   - Common path inputs: /var/lib/noemaforge/projects
#   - Imports: __future__, argparse, json, os
# Output formats / side effects:
#   - JSON files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

import argparse, json, os
BASE = "/var/lib/noemaforge/projects"
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
#   - ArgumentParser, add_argument, parse_args, print, isdir, sorted, join, makedirs, append, dumps, len, listdir
# Returns / emits: int
# Side effects:
#   - serializes structured data
#   - creates directories
#   - appends to logs or files
# Key locals:
#   - ap, created, ns, p, pid, projects
# === End NoemaForge Autodoc Function Header ===
def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--project-id", default=""); ns = ap.parse_args()
    projects = [ns.project_id] if ns.project_id else []
    if not projects and os.path.isdir(BASE):
        projects = sorted([x for x in os.listdir(BASE) if os.path.isdir(os.path.join(BASE, x))])
    created = []
    for pid in projects:
        p = os.path.join(BASE, pid, "worktrees")
        os.makedirs(p, exist_ok=True)
        created.append(p)
    print(json.dumps({"ok": True, "created": created, "count": len(created)}, ensure_ascii=False, indent=2)); return 0
if __name__ == "__main__": raise SystemExit(main())
