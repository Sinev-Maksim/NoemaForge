#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tools/migrate/verify_policy_v26.py
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
# File: tools/migrate/verify_policy_v26.py
# Purpose: Run one-time migration logic for 'verify_policy_v26'.
# Invoked by / imported from:
#   - No inbound Python import detected; treat as library leaf or direct entrypoint.
# Public API / entry functions:
#   - main
# Inputs:
#   - --root
#   - Common path inputs: /opt/noemaforge
#   - Imports: __future__, argparse, json, os, yaml
# Output formats / side effects:
#   - JSON files
#   - YAML files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

import argparse, json, os, yaml
REQUIRED_TOOLS = ["plan.enter","plan.approve","plan.exit","task.create","task.list","task.get","task.update","task.stop","task.output","worktree.enter","worktree.status","worktree.promote","worktree.exit","skills.list","skills.run","notify.emit","notify.list","notify.ack","coordinator.fanout","team_memory.export","team_memory.import","team_memory.scan"]
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
#   - ArgumentParser, add_argument, parse_args, sorted, print, safe_load, str, isinstance, dumps, open, get, join
# Returns / emits: int
# Side effects:
#   - reads or writes files
#   - serializes structured data
# Key locals:
#   - ap, missing, ns, ok, pol, reg, reg_ids
# === End NoemaForge Autodoc Function Header ===
def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--root", default="/opt/noemaforge"); ns = ap.parse_args()
    reg = yaml.safe_load(open(os.path.join(ns.root,"configs","tool-registry.yaml"), "r", encoding="utf-8")) or {}
    pol = yaml.safe_load(open(os.path.join(ns.root,"configs","tool-policy.yaml"), "r", encoding="utf-8")) or {}
    reg_ids = {str(x.get("id") or "") for x in (reg.get("tools") or []) if isinstance(x, dict)}
    missing = sorted([x for x in REQUIRED_TOOLS if x not in reg_ids])
    ok = not missing and isinstance((pol.get("streams") or {}).get("dev.work"), dict)
    print(json.dumps({"ok": ok, "missing_tools": missing}, ensure_ascii=False, indent=2)); return 0 if ok else 1
if __name__ == "__main__": raise SystemExit(main())
