#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/team_search.py
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
# File: src/team_search.py
# Purpose: Provide the module 'team_search'.
# Invoked by / imported from:
#   - src/surgeon_auto.py
# Public API / entry functions:
#   - load_team_eval_policy
#   - flow_policy
#   - scorecard_exists
#   - build_role_candidates
#   - enumerate_team_configs
#   - pick_next_team_eval
# Inputs:
#   - Common path inputs: noemaforge.teameval/v1
#   - Imports: __future__, hashlib, json, os, itertools, typing, yaml, flow_catalog
# Output formats / side effects:
#   - JSON files
#   - YAML files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""team_search.py (v0.11.6)

Deterministic planner for team-model combinatorics.

We keep it simple:
- For each enabled flow, build a small candidate list per role.
- Enumerate combinations (cartesian product), but cap total configs.
- Pick the next not-yet-evaluated config (based on scorecard existence).

Over time, Surgeon will explore the space incrementally.
"""


import hashlib
import json
import os
from itertools import product
from typing import Any, Dict, List, Optional, Tuple

import yaml

import flow_catalog
import model_installer_plan


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
# Function: load_team_eval_policy(epoch_dir: str)
# Purpose: Implement the routine 'load team eval policy'.
# Inputs:
#   - epoch_dir: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - join, exists, _load_yaml
# Returns / emits: Dict[str, Any]
# Key locals:
#   - p
# === End NoemaForge Autodoc Function Header ===
def load_team_eval_policy(epoch_dir: str) -> Dict[str, Any]:
    p = os.path.join(epoch_dir, "team-eval-policy.yaml")
    if not os.path.exists(p):
        return {"apiVersion": "noemaforge.teameval/v1", "kind": "TeamEvalPolicy", "defaults": {"enabled": False}, "flows": {}}
    try:
        return _load_yaml(p)
    except Exception:
        return {"apiVersion": "noemaforge.teameval/v1", "kind": "TeamEvalPolicy", "defaults": {"enabled": False}, "flows": {}}


# === NoemaForge Autodoc Function Header ===
# Function: _team_scorecard_path(team_scorecards_dir: str, flow_id: str, suite: str, h: str)
# Purpose: Implement the routine ' team scorecard path'.
# Inputs:
#   - team_scorecards_dir: str
#   - flow_id: str
#   - suite: str
#   - h: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - join
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _team_scorecard_path(team_scorecards_dir: str, flow_id: str, suite: str, h: str) -> str:
    return os.path.join(team_scorecards_dir, flow_id, f"team__{suite}__{h}.json")


# === NoemaForge Autodoc Function Header ===
# Function: _team_search_state_path(team_scorecards_dir: str, flow_id: str, suite: str)
# Purpose: Implement the routine ' team search state path'.
# Inputs:
#   - team_scorecards_dir: str
#   - flow_id: str
#   - suite: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - join
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _team_search_state_path(team_scorecards_dir: str, flow_id: str, suite: str) -> str:
    # Persist k-expansion progress next to scorecards (survives restarts).
    return os.path.join(team_scorecards_dir, flow_id, f".team_search_state__{suite}.json")


# === NoemaForge Autodoc Function Header ===
# Function: _load_team_search_state(team_scorecards_dir: str, flow_id: str, suite: str)
# Purpose: Implement the routine ' load team search state'.
# Inputs:
#   - team_scorecards_dir: str
#   - flow_id: str
#   - suite: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _team_search_state_path, exists, open, load, isinstance
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads or writes files
# Key locals:
#   - f, p, v
# === End NoemaForge Autodoc Function Header ===
def _load_team_search_state(team_scorecards_dir: str, flow_id: str, suite: str) -> Dict[str, Any]:
    p = _team_search_state_path(team_scorecards_dir, flow_id, suite)
    if not os.path.exists(p):
        return {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            v = json.load(f)
        return v if isinstance(v, dict) else {}
    except Exception:
        return {}


# === NoemaForge Autodoc Function Header ===
# Function: _save_team_search_state(team_scorecards_dir: str, flow_id: str, suite: str, state: Dict[str, Any])
# Purpose: Implement the routine ' save team search state'.
# Inputs:
#   - team_scorecards_dir: str
#   - flow_id: str
#   - suite: str
#   - state: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _team_search_state_path, makedirs, replace, dirname, open, dump
# Returns / emits: None
# Side effects:
#   - reads or writes files
#   - serializes structured data
#   - creates directories
# Key locals:
#   - f, p, tmp
# === End NoemaForge Autodoc Function Header ===
def _save_team_search_state(team_scorecards_dir: str, flow_id: str, suite: str, state: Dict[str, Any]) -> None:
    p = _team_search_state_path(team_scorecards_dir, flow_id, suite)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, p)


# === NoemaForge Autodoc Function Header ===
# Function: _models_seen_in_team_scorecards(team_scorecards_dir: str, flow_id: str, suite: str)
# Purpose: Return role -> set(model_id) used in existing team scorecards.
# Inputs:
#   - team_scorecards_dir: str
#   - flow_id: str
#   - suite: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - join, isdir, listdir, items, startswith, endswith, open, load, get, isinstance, add, str
# Returns / emits: Dict[str, set]
# Side effects:
#   - reads or writes files
# Key locals:
#   - d, data, f, name, names, out, p, role_models
# === End NoemaForge Autodoc Function Header ===
def _models_seen_in_team_scorecards(team_scorecards_dir: str, flow_id: str, suite: str) -> Dict[str, set]:
    """Return role -> set(model_id) used in existing team scorecards.

    Used for role‑round‑robin exploration and to avoid repeating already-tested
    role→model choices in team context.
    """

    out: Dict[str, set] = {}
    d = os.path.join(team_scorecards_dir, flow_id)
    if not os.path.isdir(d):
        return out
    try:
        names = os.listdir(d)
    except Exception:
        return out
    for name in names:
        if not (name.startswith(f"team__{suite}__") and name.endswith(".json")):
            continue
        p = os.path.join(d, name)
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            role_models = data.get("role_models") or data.get("models") or {}
            if not isinstance(role_models, dict):
                continue
            for r, mid in role_models.items():
                out.setdefault(str(r), set()).add(str(mid))
        except Exception:
            continue
    return out


# === NoemaForge Autodoc Function Header ===
# Function: _merge_defaults(defs: Dict[str, Any], ov: Dict[str, Any])
# Purpose: Implement the routine ' merge defaults'.
# Inputs:
#   - defs: Dict[str, Any]
#   - ov: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - dict, items
# Returns / emits: Dict[str, Any]
# Key locals:
#   - out
# === End NoemaForge Autodoc Function Header ===
def _merge_defaults(defs: Dict[str, Any], ov: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(defs or {})
    for k, v in (ov or {}).items():
        out[k] = v
    return out


# === NoemaForge Autodoc Function Header ===
# Function: flow_policy(doc: Dict[str, Any], flow_id: str)
# Purpose: Implement the routine 'flow policy'.
# Inputs:
#   - doc: Dict[str, Any]
#   - flow_id: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _merge_defaults, get, isinstance
# Returns / emits: Dict[str, Any]
# Key locals:
#   - defaults, flows, ov
# === End NoemaForge Autodoc Function Header ===
def flow_policy(doc: Dict[str, Any], flow_id: str) -> Dict[str, Any]:
    defaults = doc.get("defaults") or {}
    flows = doc.get("flows") or {}
    ov = flows.get(flow_id) if isinstance(flows, dict) else {}
    ov = ov if isinstance(ov, dict) else {}
    return _merge_defaults(defaults, ov)


# === NoemaForge Autodoc Function Header ===
# Function: _hash_team_config(flow_id: str, role_models: Dict[str, str], suite: str)
# Purpose: Implement the routine ' hash team config'.
# Inputs:
#   - flow_id: str
#   - role_models: Dict[str, str]
#   - suite: str
# Called by:
#   - src/team_scorecards.py
# Calls:
#   - join, hexdigest, sorted, keys, sha256, encode
# Returns / emits: str
# Key locals:
#   - items, s
# === End NoemaForge Autodoc Function Header ===
def _hash_team_config(flow_id: str, role_models: Dict[str, str], suite: str) -> str:
    items = [f"{k}={role_models[k]}" for k in sorted(role_models.keys())]
    s = f"flow={flow_id}|suite={suite}|" + "|".join(items)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


# === NoemaForge Autodoc Function Header ===
# Function: scorecard_exists(team_scorecards_dir: str, flow_id: str, suite: str, h: str)
# Purpose: Implement the routine 'scorecard exists'.
# Inputs:
#   - team_scorecards_dir: str
#   - flow_id: str
#   - suite: str
#   - h: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - join, exists
# Returns / emits: bool
# Key locals:
#   - p
# === End NoemaForge Autodoc Function Header ===
def scorecard_exists(team_scorecards_dir: str, flow_id: str, suite: str, h: str) -> bool:
    p = os.path.join(team_scorecards_dir, flow_id, f"team__{suite}__{h}.json")
    return os.path.exists(p)


# === NoemaForge Autodoc Function Header ===
# Function: _team_role_run_counts(team_scorecards_dir: str, flow_id: str, suite: str)
# Purpose: Count how many historical team scorecards touched each role.
# Inputs:
#   - team_scorecards_dir: str
#   - flow_id: str
#   - suite: str
# Called by:
#   - _coordinate_pick_next_config
# Returns / emits: Dict[str, int]
# Side effects:
#   - reads files
# === End NoemaForge Autodoc Function Header ===
def _team_role_run_counts(team_scorecards_dir: str, flow_id: str, suite: str) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    d = os.path.join(team_scorecards_dir, flow_id)
    if not os.path.isdir(d):
        return counts
    try:
        names = os.listdir(d)
    except Exception:
        return counts
    for name in names:
        if not (name.startswith(f"team__{suite}__") and name.endswith(".json")):
            continue
        p = os.path.join(d, name)
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            role_models = data.get("role_models") or data.get("models") or {}
            if not isinstance(role_models, dict):
                continue
            for r in role_models.keys():
                rid = str(r or "").strip()
                if rid:
                    counts[rid] = int(counts.get(rid, 0)) + 1
        except Exception:
            continue
    return counts


# === NoemaForge Autodoc Function Header ===
# Function: _failed_role_models(scorecards_dir: str, flow_id: str, role_ids: List[str], quality_floor: float = 0.34, json_floor: float = 0.34)
# Purpose: Remember role->model pairings that performed poorly in individual scorecards.
# Inputs:
#   - scorecards_dir: str
#   - flow_id: str
#   - role_ids: List[str]
#   - quality_floor: float = 0.34
#   - json_floor: float = 0.34
# Called by:
#   - pick_next_team_eval
# Returns / emits: Dict[str, set]
# Side effects:
#   - reads files
# === End NoemaForge Autodoc Function Header ===
def _failed_role_models(
    scorecards_dir: str,
    flow_id: str,
    role_ids: List[str],
    quality_floor: float = 0.34,
    json_floor: float = 0.34,
) -> Dict[str, set]:
    out: Dict[str, set] = {}
    sid = (flow_id or "").replace("/", "_")
    for role in role_ids:
        rid = (role or "").replace("/", "_")
        fname = f"{sid}__{rid}__llm.json"
        try:
            model_dirs = os.listdir(scorecards_dir)
        except Exception:
            model_dirs = []
        for model_id in model_dirs:
            p = os.path.join(scorecards_dir, model_id, fname)
            if not os.path.exists(p):
                continue
            try:
                with open(p, "r", encoding="utf-8") as f:
                    card = json.load(f)
                qmetrics = card.get("quality_metrics") if isinstance(card.get("quality_metrics"), dict) else {}
                quality = float(card.get("quality_score") or card.get("pass_rate") or qmetrics.get("stability_score") or 0.0)
                json_rate = float(card.get("json_parse_rate") or qmetrics.get("step_success_rate") or 0.0)
            except Exception:
                continue
            if quality < float(quality_floor) or json_rate < float(json_floor):
                out.setdefault(role, set()).add(str(model_id))
    return out


# === NoemaForge Autodoc Function Header ===
# Function: build_role_candidates(registry_doc: Dict[str, Any], scorecards_dir: str, flow_id: str, role_ids: List[str], per_role_top_k: int, min_trust: str = 'unknown', failed_role_models: Optional[Dict[str, set]] = None)
# Purpose: Build ordered candidate models per role with lightweight failed-pair memory.
# Inputs:
#   - registry_doc: Dict[str, Any]
#   - scorecards_dir: str
#   - flow_id: str
#   - role_ids: List[str]
#   - per_role_top_k: int
#   - min_trust: str = 'unknown'
#   - failed_role_models: Optional[Dict[str, set]] = None
# Called by:
#   - pick_next_team_eval
# Returns / emits: Dict[str, List[str]]
# Side effects:
#   - appends to logs or files
# === End NoemaForge Autodoc Function Header ===
def build_role_candidates(
    *,
    registry_doc: Dict[str, Any],
    scorecards_dir: str,
    flow_id: str,
    role_ids: List[str],
    per_role_top_k: int,
    min_trust: str = "unknown",
    failed_role_models: Optional[Dict[str, set]] = None,
) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    failed_role_models = failed_role_models if isinstance(failed_role_models, dict) else {}
    for role in role_ids:
        ranked = model_installer_plan.rank_models_for_role(
            registry_doc=registry_doc,
            scorecards_dir=scorecards_dir,
            stream_id=flow_id,
            role=role,
            cap="llm",
            min_trust=min_trust,
            require_scorecard=False,
        )
        all_ranked = [str(x.get("model_id")) for x in ranked if str(x.get("model_id") or "").strip()]
        chosen = [m for m in all_ranked if m not in (failed_role_models.get(role) or set())][: max(1, int(per_role_top_k))]
        if not chosen:
            chosen = all_ranked[: max(1, int(per_role_top_k))]
        if "main" not in chosen:
            chosen.append("main")
        seen = set()
        final: List[str] = []
        for m in chosen:
            if m and m not in seen:
                seen.add(m)
                final.append(m)
        out[role] = final
    return out


# === NoemaForge Autodoc Function Header ===
# Function: _coordinate_pick_next_config(team_scorecards_dir: str, flow_id: str, suite: str, role_ids: List[str], role_candidates: Dict[str, List[str]], target_role: str | None = None, failed_role_models: Optional[Dict[str, set]] = None)
# Purpose: Pick the next team config using a coverage-aware role-round-robin strategy.
# Inputs:
#   - team_scorecards_dir: str
#   - flow_id: str
#   - suite: str
#   - role_ids: List[str]
#   - role_candidates: Dict[str, List[str]]
#   - target_role: str | None = None
#   - failed_role_models: Optional[Dict[str, set]] = None
# Called by:
#   - pick_next_team_eval
# Returns / emits: Dict[str, Any] | None
# === End NoemaForge Autodoc Function Header ===
def _coordinate_pick_next_config(
    *,
    team_scorecards_dir: str,
    flow_id: str,
    suite: str,
    role_ids: List[str],
    role_candidates: Dict[str, List[str]],
    target_role: str | None = None,
    failed_role_models: Optional[Dict[str, set]] = None,
) -> Dict[str, Any] | None:
    """Pick the next team config using a coverage-aware role-round-robin strategy."""
    failed_role_models = failed_role_models if isinstance(failed_role_models, dict) else {}

    baseline: Dict[str, str] = {}
    for r in role_ids:
        cands = [str(x) for x in (role_candidates.get(r) or []) if str(x).strip()]
        preferred = [m for m in cands if m not in (failed_role_models.get(r) or set())]
        baseline[r] = str((preferred or cands or ["main"])[0])

    seen = _models_seen_in_team_scorecards(team_scorecards_dir, flow_id, suite)
    role_runs = _team_role_run_counts(team_scorecards_dir, flow_id, suite)

    if target_role and target_role in role_ids:
        role_order = [target_role] + [r for r in role_ids if r != target_role]
    else:
        role_order = sorted(role_ids, key=lambda r: (len(seen.get(r, set())), int(role_runs.get(r, 0)), r))

    for role in role_order:
        cands = [str(x) for x in (role_candidates.get(role) or []) if str(x).strip()]
        preferred = [m for m in cands if m not in (failed_role_models.get(role) or set())] or cands
        for mid in preferred:
            if mid in seen.get(role, set()):
                continue
            role_models = dict(baseline)
            role_models[role] = mid
            h = _hash_team_config(flow_id, role_models, suite)
            if not scorecard_exists(team_scorecards_dir, flow_id, suite, h):
                return {"flow_id": flow_id, "suite": suite, "role_models": role_models, "hash": h, "focus_role": role}

    return None


# === NoemaForge Autodoc Function Header ===
# Function: enumerate_team_configs(role_candidates: Dict[str, List[str]], max_team_configs: int)
# Purpose: Implement the routine 'enumerate team configs'.
# Inputs:
#   - role_candidates: Dict[str, List[str]]
#   - max_team_configs: int
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - sorted, product, keys, append, str, len, max, range, int
# Returns / emits: List[Dict[str, str]]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - cfg, combo, out, pools, roles
# === End NoemaForge Autodoc Function Header ===
def enumerate_team_configs(
    *,
    role_candidates: Dict[str, List[str]],
    max_team_configs: int,
) -> List[Dict[str, str]]:
    roles = sorted(role_candidates.keys())
    pools = [role_candidates[r] for r in roles]
    out: List[Dict[str, str]] = []
    for combo in product(*pools):
        cfg = {roles[i]: str(combo[i]) for i in range(len(roles))}
        out.append(cfg)
        if len(out) >= max(1, int(max_team_configs)):
            break
    return out


# === NoemaForge Autodoc Function Header ===
# Function: pick_next_team_eval(epoch_dir: str, registry_doc: Dict[str, Any], scorecards_dir: str, team_scorecards_dir: str, role_model_policy_doc: Dict[str, Any], target_role: str | None = None)
# Purpose: Pick next team config to evaluate.
# Inputs:
#   - epoch_dir: str
#   - registry_doc: Dict[str, Any]
#   - scorecards_dir: str
#   - team_scorecards_dir: str
#   - role_model_policy_doc: Dict[str, Any]
#   - target_role: str | None = None
# Called by:
#   - src/surgeon_auto.py
# Calls:
#   - load_team_eval_policy, load_flow_catalog, sorted, bool, get, isinstance, lower, list, list_flow_ids, flow_policy, int, get_flow
# Returns / emits: Optional[Dict[str, Any]]
# Key locals:
#   - auto_expand_k, configs, d_llm, defaults, deferred, f, fc, fid, flow, flow_id, flow_ids, fp
# === End NoemaForge Autodoc Function Header ===
def pick_next_team_eval(
    *,
    epoch_dir: str,
    registry_doc: Dict[str, Any],
    scorecards_dir: str,
    team_scorecards_dir: str,
    role_model_policy_doc: Dict[str, Any],
    target_role: str | None = None,
) -> Optional[Dict[str, Any]]:
    """Pick next team config to evaluate.

    Returns:
      {
        flow_id,
        suite,
        judge_model,
        nodes,
        role_models,
        hash
      }
    """
    pol = load_team_eval_policy(epoch_dir)
    if not bool((pol.get("defaults") or {}).get("enabled") or False):
        return None

    # min_trust from role-model-policy defaults
    defaults = role_model_policy_doc.get("defaults") or {}
    d_llm = (defaults.get("llm") or {}) if isinstance(defaults, dict) else {}
    min_trust = str(d_llm.get("min_trust") or "unknown").strip().lower() or "unknown"

    fc = flow_catalog.load_flow_catalog(epoch_dir)
    flow_ids = sorted(list((pol.get("flows") or {}).keys()))
    if not flow_ids:
        flow_ids = flow_catalog.list_flow_ids(fc)

    # If caller provides target_role, prefer flows that include it.
    if target_role:
        preferred: List[str] = []
        deferred: List[str] = []
        for fid in flow_ids:
            f = flow_catalog.get_flow(fc, fid)
            roles = [str(n.get("role") or "").strip() for n in (flow_catalog.flow_nodes(f) or [])]
            if target_role in roles:
                preferred.append(fid)
            else:
                deferred.append(fid)
        flow_ids = preferred + deferred

    for flow_id in flow_ids:
        fp = flow_policy(pol, flow_id)
        if not bool(fp.get("enabled") or False):
            continue
        suite = str(fp.get("suite") or (pol.get("defaults") or {}).get("suite") or "smoke").strip().lower() or "smoke"
        judge_model = str(fp.get("judge_model") or (pol.get("defaults") or {}).get("judge_model") or "main").strip() or "main"
        per_role_top_k = int(fp.get("per_role_top_k") or (pol.get("defaults") or {}).get("per_role_top_k") or 3)
        max_team_configs = int(fp.get("max_team_configs") or (pol.get("defaults") or {}).get("max_team_configs") or 16)

        planner_mode = str(fp.get("planner_mode") or (pol.get("defaults") or {}).get("planner_mode") or "cartesian").strip().lower() or "cartesian"
        auto_expand_k = bool(fp.get("auto_expand_k") if "auto_expand_k" in fp else (pol.get("defaults") or {}).get("auto_expand_k", True))
        k_start = int(fp.get("k_start") or (pol.get("defaults") or {}).get("k_start") or per_role_top_k)
        k_max = int(fp.get("k_max") or (pol.get("defaults") or {}).get("k_max") or 2048)
        k_step = int(fp.get("adaptive_k_step") or (pol.get("defaults") or {}).get("adaptive_k_step") or 1)
        quality_floor = float(fp.get("quality_floor") or (pol.get("defaults") or {}).get("quality_floor") or 0.34)
        json_floor = float(fp.get("json_floor") or (pol.get("defaults") or {}).get("json_floor") or 0.34)

        flow = flow_catalog.get_flow(fc, flow_id)
        nodes = flow_catalog.flow_nodes(flow)
        if not nodes:
            continue
        role_ids = [str(n.get("role")) for n in nodes if n.get("role")]

        failed_pairs = _failed_role_models(scorecards_dir, flow_id, role_ids, quality_floor=quality_floor, json_floor=json_floor)

        # Planner modes
        if planner_mode == "coordinate":
            state = _load_team_search_state(team_scorecards_dir, flow_id, suite)
            k_current = int(state.get("k_current", 0))
            if k_current < 1:
                k_current = k_start

            while True:
                k_current = min(k_current, k_max)
                role_cands = build_role_candidates(
                    registry_doc=registry_doc,
                    scorecards_dir=scorecards_dir,
                    flow_id=flow_id,
                    role_ids=role_ids,
                    per_role_top_k=k_current,
                    min_trust=min_trust,
                    failed_role_models=failed_pairs,
                )
                nxt = _coordinate_pick_next_config(
                    team_scorecards_dir=team_scorecards_dir,
                    flow_id=flow_id,
                    suite=suite,
                    role_ids=role_ids,
                    role_candidates=role_cands,
                    target_role=target_role,
                    failed_role_models=failed_pairs,
                )
                if nxt:
                    state["k_current"] = k_current
                    state["focus_role"] = str(nxt.get("focus_role") or "")
                    state["failed_role_models"] = {k: sorted(list(v)) for k, v in failed_pairs.items()}
                    _save_team_search_state(team_scorecards_dir, flow_id, suite, state)
                    return {
                        "flow_id": flow_id,
                        "suite": suite,
                        "judge_model": judge_model,
                        "nodes": nodes,
                        "role_models": nxt["role_models"],
                        "hash": nxt["hash"],
                        "focus_role": nxt.get("focus_role"),
                        "k_current": k_current,
                        "role_candidates": role_cands,
                    }

                if (not auto_expand_k) or k_current >= k_max:
                    state["k_current"] = k_current
                    _save_team_search_state(team_scorecards_dir, flow_id, suite, state)
                    break

                # Expand k by 1; stop if candidates no longer change.
                role_cands_next = build_role_candidates(
                    registry_doc=registry_doc,
                    scorecards_dir=scorecards_dir,
                    flow_id=flow_id,
                    role_ids=role_ids,
                    per_role_top_k=min(k_current + max(1, k_step), k_max),
                    min_trust=min_trust,
                    failed_role_models=failed_pairs,
                )
                if role_cands_next == role_cands:
                    state["k_current"] = k_current
                    _save_team_search_state(team_scorecards_dir, flow_id, suite, state)
                    break
                k_current += max(1, k_step)

            # No more configs for this flow at current limits; try next flow.
            continue

        # Legacy cartesian planner
        role_cands = build_role_candidates(
            registry_doc=registry_doc,
            scorecards_dir=scorecards_dir,
            flow_id=flow_id,
            role_ids=role_ids,
            per_role_top_k=per_role_top_k,
            min_trust=min_trust,
            failed_role_models=failed_pairs,
        )
        configs = enumerate_team_configs(role_candidates=role_cands, max_team_configs=max_team_configs)
        for rcfg in configs:
            h = _hash_team_config(flow_id, rcfg, suite)
            if scorecard_exists(team_scorecards_dir, flow_id, suite, h):
                continue
            return {
                "flow_id": flow_id,
                "suite": suite,
                "judge_model": judge_model,
                "nodes": nodes,
                "role_models": rcfg,
                "hash": h,
                "role_candidates": role_cands,
            }

    return None
