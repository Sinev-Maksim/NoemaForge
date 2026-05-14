#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tools/prep/generate_head_gateway_assets.py
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
# File: tools/prep/generate_head_gateway_assets.py
# Purpose: Prepare or ingest external assets for 'generate_head_gateway_assets'.
# Invoked by / imported from:
#   - No inbound Python import detected; treat as library leaf or direct entrypoint.
# Public API / entry functions:
#   - derive_intent_router
#   - derive_ui_registry
#   - main
# Inputs:
#   - --head
#   - --out-dir
#   - --write-to-configs
#   - Common path inputs: noemaforge.intent_router/v1, noemaforge.ui_registry/v1
#   - Imports: __future__, sys, argparse, os, typing, prep_common
# Output formats / side effects:
#   - JSON files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""Generate intent router + UI registry from head-gateway.json.

Why
---
Your constraint: GUI and intent router are *derived* from Head Gateway and should
expand via it. This tool keeps that relationship explicit and testable.

No external deps.
"""


import sys
sys.dont_write_bytecode = True

import argparse
import os
from typing import Any, Dict, List

from prep_common import ensure_dir, read_json, write_json


# === NoemaForge Autodoc Function Header ===
# Function: derive_intent_router(head: Dict[str, Any])
# Purpose: Implement the routine 'derive intent router'.
# Inputs:
#   - head: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - get, append
# Returns / emits: Dict[str, Any]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - iid, it, routes, target
# === End NoemaForge Autodoc Function Header ===
def derive_intent_router(head: Dict[str, Any]) -> Dict[str, Any]:
    routes = []
    for it in head.get("intents", []) or []:
        iid = it.get("id")
        if not iid:
            continue
        target = it.get("route_hint") or "stream:auto"
        routes.append({"intent_id": iid, "target": target, "default_priority": "normal"})
    return {
        "apiVersion": "noemaforge.intent_router/v1",
        "kind": "IntentRouter",
        "routes": routes,
    }


# === NoemaForge Autodoc Function Header ===
# Function: derive_ui_registry(head: Dict[str, Any])
# Purpose: Implement the routine 'derive ui registry'.
# Inputs:
#   - head: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - get
# Returns / emits: Dict[str, Any]
# === End NoemaForge Autodoc Function Header ===
def derive_ui_registry(head: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "apiVersion": "noemaforge.ui_registry/v1",
        "kind": "UIRegistry",
        "screens": head.get("screens", []) or [],
        "actions": head.get("actions", []) or [],
        "meta": {"derived_from": "head-gateway.json"},
    }


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
#   - ArgumentParser, add_argument, parse_args, read_json, derive_intent_router, derive_ui_registry, ensure_dir, join, write_json, print, dirname, abspath
# Returns / emits: None
# Key locals:
#   - _, ap, args, configs_dir, head, head_dir, p, router, router_path, ui, ui_path
# === End NoemaForge Autodoc Function Header ===
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--head", required=True, help="Path to head-gateway.json")
    ap.add_argument("--out-dir", required=True, help="Output directory")
    ap.add_argument("--write-to-configs", action="store_true", help="Also write into seed/noemaforge/configs if head is inside a seed tree")
    args = ap.parse_args()

    head = read_json(args.head)
    router = derive_intent_router(head)
    ui = derive_ui_registry(head)

    ensure_dir(args.out_dir)
    router_path = os.path.join(args.out_dir, "intent-router.generated.json")
    ui_path = os.path.join(args.out_dir, "ui-registry.generated.json")
    write_json(router_path, router)
    write_json(ui_path, ui)

    if args.write_to_configs:
        # Try to locate configs directory relative to head file.
        head_dir = os.path.dirname(os.path.abspath(args.head))
        configs_dir = head_dir  # head is expected to live in configs
        if os.path.basename(configs_dir) != "configs":
            # search upward
            p = head_dir
            for _ in range(6):
                if os.path.basename(p) == "configs":
                    configs_dir = p
                    break
                p = os.path.dirname(p)
        if os.path.basename(configs_dir) == "configs":
            write_json(os.path.join(configs_dir, "intent-router.json"), router)
            write_json(os.path.join(configs_dir, "ui-registry.json"), ui)

    print("OK")
    print(router_path)
    print(ui_path)


if __name__ == "__main__":
    main()
