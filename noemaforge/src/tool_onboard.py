#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/tool_onboard.py
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
# File: src/tool_onboard.py
# Purpose: Provide the module 'tool_onboard'.
# Invoked by / imported from:
#   - No inbound Python import detected; treat as library leaf or direct entrypoint.
# Public API / entry functions:
#   - cmd_propose
#   - cmd_validate
#   - cmd_promote
#   - main
# Inputs:
#   - --tool-id
#   - --handler
#   - --risk
#   - --streams
#   - --roles
#   - --data-ro
#   - --data-rw
#   - --gpu-mode
#   - --description
#   - --rollback-plan
# Output formats / side effects:
#   - YAML files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""tool_onboard.py (MVP helper)

This script supports a conservative workflow for adding/enabling tools.

In v0.9.0 it does NOT auto-apply changes to registry/policy.
It validates proposals and prints safe patch suggestions for manual review.

Intended integration (v0.9+):
- runtime can emit a PreStartChangeRequest
- pre-start builds/switches an epoch via brainctl

Rationale:
- tool onboarding is high-risk (supply chain)
- keep changes auditable and intentional

Usage:
  tool_onboard.py propose --tool-id exec.run --handler sandbox_exec --risk critical
  tool_onboard.py validate --proposal /var/lib/noemaforge/tool_proposals/<file>.yaml
  tool_onboard.py promote --proposal ...
"""


import argparse
import datetime as dt
import os
import re
import sys
from typing import Any, Dict, List, Tuple

import yaml

CFG_DIR = "/opt/noemaforge/configs"
REG_PATH = os.path.join(CFG_DIR, "tool-registry.yaml")
POL_PATH = os.path.join(CFG_DIR, "tool-policy.yaml")
STR_PATH = os.path.join(CFG_DIR, "streams.yaml")

DEFAULT_PROPOSALS_DIR = "/var/lib/noemaforge/tool_proposals"

TOOL_ID_RE = re.compile(r"^[a-z0-9]+(\.[a-z0-9_-]+)+$")


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
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


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
#   - src/flow_metrics.py
#   - src/incidents.py
#   - src/knowledge/policy.py
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
# Function: _save_yaml(path: str, obj: Dict[str, Any])
# Purpose: Implement the routine ' save yaml'.
# Inputs:
#   - path: str
#   - obj: Dict[str, Any]
# Called by:
#   - src/noemaforge_core.py
#   - src/prestart.py
# Calls:
#   - makedirs, dirname, open, safe_dump
# Returns / emits: None
# Side effects:
#   - reads or writes files
#   - serializes structured data
#   - creates directories
# Key locals:
#   - f
# === End NoemaForge Autodoc Function Header ===
def _save_yaml(path: str, obj: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(obj, f, sort_keys=False, allow_unicode=True)


# === NoemaForge Autodoc Function Header ===
# Function: _registry_tools(reg: Dict[str, Any])
# Purpose: Implement the routine ' registry tools'.
# Inputs:
#   - reg: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - get, strip, dict, str
# Returns / emits: Dict[str, Dict[str, Any]]
# Key locals:
#   - out, t, tid
# === End NoemaForge Autodoc Function Header ===
def _registry_tools(reg: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for t in reg.get("tools", []) or []:
        tid = str(t.get("id") or "").strip()
        if tid:
            out[tid] = dict(t)
    return out


# === NoemaForge Autodoc Function Header ===
# Function: _streams(cat: Dict[str, Any])
# Purpose: Implement the routine ' streams'.
# Inputs:
#   - cat: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - sorted, list, keys, get
# Returns / emits: List[str]
# === End NoemaForge Autodoc Function Header ===
def _streams(cat: Dict[str, Any]) -> List[str]:
    return sorted(list((cat.get("streams") or {}).keys()))


# === NoemaForge Autodoc Function Header ===
# Function: _validate_proposal(prop: Dict[str, Any], reg: Dict[str, Any], pol: Dict[str, Any], cat: Dict[str, Any])
# Purpose: Implement the routine ' validate proposal'.
# Inputs:
#   - prop: Dict[str, Any]
#   - reg: Dict[str, Any]
#   - pol: Dict[str, Any]
#   - cat: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - strip, list, _registry_tools, set, append, _streams, str, get, match, len
# Returns / emits: Tuple[bool, List[str]]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - errs, existing, handler, known_streams, risk, s, target_roles, target_streams, tool_id
# === End NoemaForge Autodoc Function Header ===
def _validate_proposal(prop: Dict[str, Any], reg: Dict[str, Any], pol: Dict[str, Any], cat: Dict[str, Any]) -> Tuple[bool, List[str]]:
    errs: List[str] = []

    tool_id = str(prop.get("tool_id") or "").strip()
    handler = str(prop.get("handler") or "").strip()
    risk = str(prop.get("risk") or "").strip()
    target_streams = list(prop.get("streams") or [])
    target_roles = list(prop.get("roles") or [])

    if not tool_id or not TOOL_ID_RE.match(tool_id):
        errs.append("bad_or_missing_tool_id")

    if not handler:
        errs.append("missing_handler")

    if risk not in ("low", "medium", "high", "critical"):
        errs.append("risk_must_be_low|medium|high|critical")

    existing = _registry_tools(reg)
    if tool_id in existing:
        errs.append("tool_id_already_in_registry")

    known_streams = set(_streams(cat))
    for s in target_streams:
        if str(s) not in known_streams:
            errs.append(f"unknown_stream:{s}")

    if not target_streams:
        errs.append("no_streams_specified")

    if not target_roles:
        errs.append("no_roles_specified")

    # Conservative: require a rollback plan text
    if not str(prop.get("rollback_plan") or "").strip():
        errs.append("missing_rollback_plan")

    # Conservative: require explicit data access list (can be empty)
    if "data_ro" not in prop or "data_rw" not in prop:
        errs.append("missing_data_ro_or_data_rw")

    # Note: we do not parse/validate paths deeply in MVP.

    return (len(errs) == 0), errs


# === NoemaForge Autodoc Function Header ===
# Function: cmd_propose(args: argparse.Namespace)
# Purpose: Implement the routine 'cmd propose'.
# Inputs:
#   - args: argparse.Namespace
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - strip, join, _save_yaml, print, match, _nowz, strftime, utcnow, replace
# Returns / emits: int
# Key locals:
#   - fn, handler, out_dir, path, prop, risk, tool_id
# === End NoemaForge Autodoc Function Header ===
def cmd_propose(args: argparse.Namespace) -> int:
    tool_id = args.tool_id.strip()
    handler = args.handler.strip()
    risk = args.risk.strip()

    if not TOOL_ID_RE.match(tool_id):
        print("ERROR: tool-id must look like 'exec.run' or 'fs.read'", file=sys.stderr)
        return 2

    prop: Dict[str, Any] = {
        "apiVersion": "noemaforge.toolproposal/v1",
        "kind": "ToolProposal",
        "tool_id": tool_id,
        "handler": handler,
        "risk": risk,
        "streams": args.streams or [],
        "roles": args.roles or [],
        "data_ro": args.data_ro or [],
        "data_rw": args.data_rw or [],
        "resources": {"gpu": args.gpu_mode or "never"},
        "description": args.description or "",
        "rollback_plan": args.rollback_plan or "",
        "created_at": _nowz(),
    }

    out_dir = args.out_dir or DEFAULT_PROPOSALS_DIR
    fn = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + f"_{tool_id.replace('.', '_')}.yaml"
    path = os.path.join(out_dir, fn)
    _save_yaml(path, prop)

    print(path)
    return 0


# === NoemaForge Autodoc Function Header ===
# Function: cmd_validate(args: argparse.Namespace)
# Purpose: Implement the routine 'cmd validate'.
# Inputs:
#   - args: argparse.Namespace
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _load_yaml, _validate_proposal, print
# Returns / emits: int
# Key locals:
#   - cat, e, pol, prop, reg
# === End NoemaForge Autodoc Function Header ===
def cmd_validate(args: argparse.Namespace) -> int:
    prop = _load_yaml(args.proposal)
    reg = _load_yaml(REG_PATH)
    pol = _load_yaml(POL_PATH)
    cat = _load_yaml(STR_PATH)

    ok, errs = _validate_proposal(prop, reg, pol, cat)
    if ok:
        print("OK")
        return 0
    print("INVALID")
    for e in errs:
        print("-", e)
    return 3


# === NoemaForge Autodoc Function Header ===
# Function: cmd_promote(args: argparse.Namespace)
# Purpose: Implement the routine 'cmd promote'.
# Inputs:
#   - args: argparse.Namespace
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _load_yaml, _validate_proposal, str, print, list, safe_dump, get
# Returns / emits: int
# Side effects:
#   - serializes structured data
# Key locals:
#   - cat, e, handler, pol, prop, r, reg, risk, roles, s, streams, tool_id
# === End NoemaForge Autodoc Function Header ===
def cmd_promote(args: argparse.Namespace) -> int:
    prop = _load_yaml(args.proposal)
    reg = _load_yaml(REG_PATH)
    pol = _load_yaml(POL_PATH)
    cat = _load_yaml(STR_PATH)

    ok, errs = _validate_proposal(prop, reg, pol, cat)
    if not ok:
        print("INVALID")
        for e in errs:
            print("-", e)
        return 3

    tool_id = str(prop.get("tool_id") or "")
    handler = str(prop.get("handler") or "")
    risk = str(prop.get("risk") or "")

    # Print patch suggestions. We keep it manual in MVP.
    print("# Suggested registry entry (append to configs/tool-registry.yaml tools list):")
    print(yaml.safe_dump({"id": tool_id, "handler": handler, "enabled": False, "risk": risk, "description": prop.get("description") or ""}, sort_keys=False, allow_unicode=True))

    print("# Suggested policy additions (edit configs/tool-policy.yaml):")
    streams = list(prop.get("streams") or [])
    roles = list(prop.get("roles") or [])
    for s in streams:
        for r in roles:
            print(f"- stream: {s} role: {r} allow += ['{tool_id}']")

    print("# IMPORTANT: In MVP, enable tool only after canary tests.")
    return 0


# === NoemaForge Autodoc Function Header ===
# Function: main(argv: List[str])
# Purpose: Implement the routine 'main'.
# Inputs:
#   - argv: List[str]
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
#   - ArgumentParser, add_subparsers, add_parser, add_argument, set_defaults, parse_args, int, fn
# Returns / emits: int
# Key locals:
#   - ap, ap_m, ap_p, ap_v, args, sub
# === End NoemaForge Autodoc Function Header ===
def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    ap_p = sub.add_parser("propose")
    ap_p.add_argument("--tool-id", required=True)
    ap_p.add_argument("--handler", required=True)
    ap_p.add_argument("--risk", default="high")
    ap_p.add_argument("--streams", nargs="*", default=[])
    ap_p.add_argument("--roles", nargs="*", default=[])
    ap_p.add_argument("--data-ro", nargs="*", default=[])
    ap_p.add_argument("--data-rw", nargs="*", default=[])
    ap_p.add_argument("--gpu-mode", default="never")
    ap_p.add_argument("--description", default="")
    ap_p.add_argument("--rollback-plan", default="")
    ap_p.add_argument("--out-dir", default=DEFAULT_PROPOSALS_DIR)
    ap_p.set_defaults(fn=cmd_propose)

    ap_v = sub.add_parser("validate")
    ap_v.add_argument("--proposal", required=True)
    ap_v.set_defaults(fn=cmd_validate)

    ap_m = sub.add_parser("promote")
    ap_m.add_argument("--proposal", required=True)
    ap_m.set_defaults(fn=cmd_promote)

    args = ap.parse_args(argv)
    return int(args.fn(args))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
