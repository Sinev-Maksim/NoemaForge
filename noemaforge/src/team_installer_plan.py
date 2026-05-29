#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/team_installer_plan.py
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
# File: src/team_installer_plan.py
# Purpose: Provide the module 'team_installer_plan'.
# Invoked by / imported from:
#   - src/surgeon_auto.py
# Public API / entry functions:
#   - list_team_scorecards
#   - pick_best_team
#   - propose_team_model_policy_patch
# Inputs:
#   - Common path inputs: noemaforge.teammodel/v1
#   - Imports: __future__, json, os, typing, yaml
# Output formats / side effects:
#   - JSON files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""team_installer_plan.py (v0.11.6)

Build pre-start patches for team-model-policy based on team scorecards.

This is intentionally conservative:
- We only propose *enable/override* for a flow when we have at least one
  team scorecard.
- We do not remove candidates from role-model-policy here.
"""


import json
import os
from typing import Any, Dict, List, Optional, Tuple

import yaml


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
# Function: _load_json(path: str)
# Purpose: Implement the routine ' load json'.
# Inputs:
#   - path: str
# Called by:
#   - src/noemaforge_core.py
#   - src/fixture_bundle.py
#   - src/glove_agent.py
#   - src/model_installer_plan.py
#   - src/model_registry.py
#   - src/model_router.py
#   - src/roles/role_entry.py
#   - src/scary_sweep.py
# Calls:
#   - open, load
# Returns / emits: Any
# Side effects:
#   - reads or writes files
# Key locals:
#   - f
# === End NoemaForge Autodoc Function Header ===
def _load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# === NoemaForge Autodoc Function Header ===
# Function: list_team_scorecards(team_scorecards_dir: str, flow_id: str, suite: str = 'smoke')
# Purpose: Read all scorecards for (flow, suite).
# Inputs:
#   - team_scorecards_dir: str
#   - flow_id: str
#   - suite: str = 'smoke'
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - join, sorted, sort, isdir, listdir, endswith, _load_json, isinstance, append, float, get
# Returns / emits: List[Dict[str, Any]]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - d, fn, obj, out, p
# === End NoemaForge Autodoc Function Header ===
def list_team_scorecards(
    *,
    team_scorecards_dir: str,
    flow_id: str,
    suite: str = "smoke",
) -> List[Dict[str, Any]]:
    """Read all scorecards for (flow, suite)."""
    out: List[Dict[str, Any]] = []
    d = os.path.join(team_scorecards_dir, flow_id)
    if not os.path.isdir(d):
        return []
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".json"):
            continue
        if f"team__{suite}__" not in fn:
            continue
        p = os.path.join(d, fn)
        try:
            obj = _load_json(p)
            if isinstance(obj, dict) and obj.get("kind") == "TeamScorecard":
                obj["_path"] = p
                out.append(obj)
        except Exception:
            continue
    out.sort(key=lambda x: float(x.get("overall_score") or 0.0), reverse=True)
    return out


# === NoemaForge Autodoc Function Header ===
# Function: pick_best_team(team_scorecards_dir: str, flow_id: str, suite: str = 'smoke')
# Purpose: Implement the routine 'pick best team'.
# Inputs:
#   - team_scorecards_dir: str
#   - flow_id: str
#   - suite: str = 'smoke'
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - list_team_scorecards
# Returns / emits: Optional[Dict[str, Any]]
# Key locals:
#   - cards
# === End NoemaForge Autodoc Function Header ===
def pick_best_team(
    *,
    team_scorecards_dir: str,
    flow_id: str,
    suite: str = "smoke",
) -> Optional[Dict[str, Any]]:
    cards = list_team_scorecards(team_scorecards_dir=team_scorecards_dir, flow_id=flow_id, suite=suite)
    if not cards:
        return None
    return cards[0]


# === NoemaForge Autodoc Function Header ===
# Function: propose_team_model_policy_patch(team_model_policy_path: str, team_scorecards_dir: str, flow_id: str, suite: str = 'smoke')
# Purpose: Propose patch for team-model-policy.yaml from best team scorecard.
# Inputs:
#   - team_model_policy_path: str
#   - team_scorecards_dir: str
#   - flow_id: str
#   - suite: str = 'smoke'
# Called by:
#   - src/surgeon_auto.py
# Calls:
#   - pick_best_team, str, exists, _load_yaml, get, basename, isinstance, replace, split, items
# Returns / emits: Dict[str, Any]
# Key locals:
#   - base, best, p, patch, roles, team_id, tmp
# === End NoemaForge Autodoc Function Header ===
def propose_team_model_policy_patch(
    *,
    team_model_policy_path: str,
    team_scorecards_dir: str,
    flow_id: str,
    suite: str = "smoke",
) -> Dict[str, Any]:
    """Propose patch for team-model-policy.yaml from best team scorecard."""
    tmp = _load_yaml(team_model_policy_path) if os.path.exists(team_model_policy_path) else {}
    best = pick_best_team(team_scorecards_dir=team_scorecards_dir, flow_id=flow_id, suite=suite)
    if not best:
        return {"ok": False, "reason": "no_team_scorecards"}

    roles = best.get("role_models") or {}
    if not isinstance(roles, dict) or not roles:
        return {"ok": False, "reason": "bad_scorecard"}

    # Extract team id from filename, if present.
    team_id = ""
    p = str(best.get("_path") or "")
    if p:
        base = os.path.basename(p)
        # team__suite__HASH.json
        try:
            team_id = base.split("__")[-1].replace(".json", "")
        except Exception:
            team_id = ""

    patch = {
        "apiVersion": "noemaforge.teammodel/v1",
        "kind": "TeamModelPolicy",
        "defaults": {"enabled": True, "selection": {"strategy": "selected"}},
        "teams": {
            flow_id: {
                "enabled": True,
                "selected_team_id": team_id,
                "roles": {k: {"llm": str(v)} for k, v in roles.items()},
            }
        },
    }

    return {"ok": True, "patch": patch, "best_scorecard": best.get("_path"), "team_id": team_id, "overall": best.get("overall_score")}
