#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/model_installer_plan.py
Zone: release/package
Version: 0.32.1
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
# File: src/model_installer_plan.py
# Purpose: Provide the module 'model_installer_plan'.
# Invoked by / imported from:
#   - src/brainctl.py
#   - src/firstboot_eval.py
#   - src/surgeon_auto.py
#   - src/team_search.py
# Public API / entry functions:
#   - rank_models_for_role
#   - propose_policy_patches
#   - make_prestart_request
# Inputs:
#   - Common path inputs: noemaforge.rolemodel/v1, noemaforge.llmbackends/v1
#   - Imports: __future__, datetime, json, os, typing, yaml
# Output formats / side effects:
#   - JSON files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""model_installer_plan.py (v0.11.2)

Pre-start "installer plan" for the model fleet.

Why this exists
--------------
NoemaForge wants to stay "thin": start as little as possible, but still have a path
to grow the fleet.

This module takes:
- Model inventory (model_registry.json)
- Surgeon measurements (scorecards)
- Epoch law (role-model-policy.yaml)

…and produces *draft* patches (PreStartChangeRequest) that a human can approve
during PRE-START.

Important design rule
---------------------
- Inventory/scorecards are *state* and may update at runtime.
- Role routing / which backends are enabled are *contracts* and must change only
  via an epoch switch (pre-start).

We intentionally keep the heuristics simple. The first goal is "works offline and
is explainable", not "global optimum".
"""


import datetime as dt
import json
import os
from typing import Any, Dict, List, Tuple

import yaml


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
#   - src/model_registry.py
#   - src/model_router.py
#   - src/roles/role_entry.py
#   - src/scary_sweep.py
#   - src/team_installer_plan.py
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
# Function: _scorecard_path(model_id: str, stream_id: str, role: str, cap: str, scorecards_dir: str)
# Purpose: Implement the routine ' scorecard path'.
# Inputs:
#   - model_id: str
#   - stream_id: str
#   - role: str
#   - cap: str
#   - scorecards_dir: str
# Called by:
#   - src/model_router.py
#   - src/model_scorecards.py
#   - src/surgeon_auto.py
# Calls:
#   - replace, join
# Returns / emits: str
# Key locals:
#   - fname, rid, sid
# === End NoemaForge Autodoc Function Header ===
def _scorecard_path(model_id: str, stream_id: str, role: str, cap: str, scorecards_dir: str) -> str:
    sid = (stream_id or "").replace("/", "_")
    rid = (role or "").replace("/", "_")
    fname = f"{sid}__{rid}__{cap}.json"
    return os.path.join(scorecards_dir, model_id, fname)


# === NoemaForge Autodoc Function Header ===
# Function: _read_scorecard(path: str)
# Purpose: Implement the routine ' read scorecard'.
# Inputs:
#   - path: str
# Called by:
#   - src/model_router.py
# Calls:
#   - exists, _load_json, isinstance
# Returns / emits: Dict[str, Any]
# Key locals:
#   - obj
# === End NoemaForge Autodoc Function Header ===
def _read_scorecard(path: str) -> Dict[str, Any]:
    try:
        if os.path.exists(path):
            obj = _load_json(path)
            if isinstance(obj, dict):
                return obj
    except Exception:
        pass
    return {}


# === NoemaForge Autodoc Function Header ===
# Function: _trust_rank(trust: str)
# Purpose: Implement the routine ' trust rank'.
# Inputs:
#   - trust: str
# Called by:
#   - src/model_router.py
# Calls:
#   - strip, lower, str
# Returns / emits: int
# Key locals:
#   - t
# === End NoemaForge Autodoc Function Header ===
def _trust_rank(trust: str) -> int:
    t = str(trust or "unknown").lower().strip()
    if t == "verified":
        return 3
    if t == "unknown":
        return 2
    if t == "quarantine":
        return 0
    return 1


# === NoemaForge Autodoc Function Header ===
# Function: _policy_rank(min_trust: str)
# Purpose: Implement the routine ' policy rank'.
# Inputs:
#   - min_trust: str
# Called by:
#   - src/model_router.py
# Calls:
#   - strip, lower, str
# Returns / emits: int
# Key locals:
#   - t
# === End NoemaForge Autodoc Function Header ===
def _policy_rank(min_trust: str) -> int:
    t = str(min_trust or "unknown").lower().strip()
    if t == "verified":
        return 3
    if t == "unknown":
        return 2
    if t == "quarantine":
        return 0
    return 2


# === NoemaForge Autodoc Function Header ===
# Function: rank_models_for_role(registry_doc: Dict[str, Any], scorecards_dir: str, stream_id: str, role: str, cap: str = 'llm', min_trust: str = 'unknown', require_scorecard: bool = False)
# Purpose: Return a ranked list of model records with attached scorecard summary.
# Inputs:
#   - registry_doc: Dict[str, Any]
#   - scorecards_dir: str
#   - stream_id: str
#   - role: str
#   - cap: str = 'llm'
#   - min_trust: str = 'unknown'
#   - require_scorecard: bool = False
# Called by:
#   - src/team_search.py
# Calls:
#   - _policy_rank, sort, dict, strip, str, _scorecard_path, _read_scorecard, float, append, get, _trust_rank
# Returns / emits: List[Dict[str, Any]]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - lat, mid, min_rank, out, r, rec, sc, score, sp, trust
# === End NoemaForge Autodoc Function Header ===
def rank_models_for_role(
    *,
    registry_doc: Dict[str, Any],
    scorecards_dir: str,
    stream_id: str,
    role: str,
    cap: str = "llm",
    min_trust: str = "unknown",
    require_scorecard: bool = False,
) -> List[Dict[str, Any]]:
    """Return a ranked list of model records with attached scorecard summary."""
    min_rank = _policy_rank(min_trust)
    out: List[Dict[str, Any]] = []
    for rec in (registry_doc.get("models") or []) or []:
        r = dict(rec or {})
        mid = str(r.get("model_id") or "").strip()
        if not mid:
            continue
        trust = str(r.get("trust") or "unknown")
        if _trust_rank(trust) < min_rank:
            continue
        sp = _scorecard_path(mid, stream_id, role, cap, scorecards_dir)
        sc = _read_scorecard(sp)
        if require_scorecard and not sc:
            continue
        score = float(sc.get("quality_score") or sc.get("overall_score") or 0.0)
        lat = float(sc.get("avg_latency_ms") or 1e9)
        r["_score"] = score
        r["_lat"] = lat
        r["_scorecard"] = sp if sc else ""
        out.append(r)

    out.sort(key=lambda x: (-float(x.get("_score") or 0.0), float(x.get("_lat") or 1e9), str(x.get("model_id") or "")))
    return out


# === NoemaForge Autodoc Function Header ===
# Function: propose_policy_patches(role_model_policy_path: str, llm_backends_policy_path: str, registry_path: str, scorecards_dir: str, roles_to_consider: List[Tuple[str, str]], top_k: int = 2)
# Purpose: Generate patch objects for role-model-policy and llm-backends-policy.
# Inputs:
#   - role_model_policy_path: str
#   - llm_backends_policy_path: str
#   - registry_path: str
#   - scorecards_dir: str
#   - roles_to_consider: List[Tuple[str, str]]
#   - top_k: int = 2
# Called by:
#   - src/brainctl.py
#   - src/firstboot_eval.py
#   - src/surgeon_auto.py
# Calls:
#   - str, bool, exists, _load_yaml, _load_json, get, rank_models_for_role, set, extend, append, strip, add
# Returns / emits: Dict[str, Any]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - backends_patch, chosen, chosen0, d_llm, defaults, final, key, lbp, m, min_trust, picked_models, pm
# === End NoemaForge Autodoc Function Header ===
def propose_policy_patches(
    *,
    role_model_policy_path: str,
    llm_backends_policy_path: str,
    registry_path: str,
    scorecards_dir: str,
    roles_to_consider: List[Tuple[str, str]],  # (stream_id, role)
    top_k: int = 2,
) -> Dict[str, Any]:
    """Generate patch objects for role-model-policy and llm-backends-policy.

    roles_to_consider is the "evaluation surface". We keep it explicit to avoid
    accidentally exploding the search space.
    """
    rmp = _load_yaml(role_model_policy_path) if os.path.exists(role_model_policy_path) else {}
    lbp = _load_yaml(llm_backends_policy_path) if os.path.exists(llm_backends_policy_path) else {}
    reg = _load_json(registry_path) if os.path.exists(registry_path) else {"models": []}

    defaults = (rmp.get("defaults") or {})
    d_llm = (defaults.get("llm") or {})
    min_trust = str(d_llm.get("min_trust") or "unknown")
    require_scorecard = bool(d_llm.get("require_scorecard") or False)

    picked_models: List[str] = []
    role_patch: Dict[str, Any] = {"roles": {}}

    for stream_id, role in roles_to_consider:
        ranked = rank_models_for_role(
            registry_doc=reg,
            scorecards_dir=scorecards_dir,
            stream_id=stream_id,
            role=role,
            cap="llm",
            min_trust=min_trust,
            require_scorecard=require_scorecard,
        )
        chosen = [str(x.get("model_id")) for x in ranked[:max(1, int(top_k))] if str(x.get("model_id") or "").strip()]
        if "main" not in chosen:
            chosen.append("main")
        # Keep order stable and dedup
        seen = set()
        final = []
        for m in chosen:
            if m not in seen:
                seen.add(m)
                final.append(m)
        picked_models.extend(final)

        key = f"{stream_id}/{role}"
        role_patch["roles"][key] = {"llm": {"candidates": final}}

    # Also patch wildcard to include top candidates (global convenience)
    # Use the first role's ranking as a baseline signal if present.
    if roles_to_consider:
        s0, r0 = roles_to_consider[0]
        ranked0 = rank_models_for_role(
            registry_doc=reg,
            scorecards_dir=scorecards_dir,
            stream_id=s0,
            role=r0,
            cap="llm",
            min_trust=min_trust,
            require_scorecard=require_scorecard,
        )
        chosen0 = [str(x.get("model_id")) for x in ranked0[:max(1, int(top_k))] if str(x.get("model_id") or "").strip()]
        if "main" not in chosen0:
            chosen0.append("main")
        seen=set()
        final=[]
        for m in chosen0:
            if m not in seen:
                seen.add(m); final.append(m)
        role_patch["roles"]["*/*"] = {"llm": {"candidates": final}}
        picked_models.extend(final)

    # Build backends patch: enable union of picked models
    # NOTE: we do not disable anything here; conservative enable-only.
    pm: List[str] = []
    for m in picked_models:
        if m and m not in pm:
            pm.append(m)
    if "main" not in pm:
        pm.append("main")

    backends_patch = {
        "backends": [
            {"id": mid, "enabled": True, "model_id": mid, "mode": "cpu"}
            for mid in pm
        ]
    }

    # Ensure schema-ish top keys exist for deep merge (caller may add apiVersion/kind elsewhere)
    if "apiVersion" not in role_patch:
        role_patch = {"apiVersion": "noemaforge.rolemodel/v1", "kind": "RoleModelPolicy", **role_patch}
    if "apiVersion" not in backends_patch:
        backends_patch = {"apiVersion": "noemaforge.llmbackends/v1", "kind": "LLMBackendsPolicy", **backends_patch}

    return {
        "role_model_policy_patch": role_patch,
        "llm_backends_policy_patch": backends_patch,
        "picked_models": pm,
    }


# === NoemaForge Autodoc Function Header ===
# Function: make_prestart_request(request_id: str, created_by: Dict[str, Any], track: str, patches: Dict[str, Any], user_comment: str = '')
# Purpose: Create a draft PreStartChangeRequest object.
# Inputs:
#   - request_id: str
#   - created_by: Dict[str, Any]
#   - track: str
#   - patches: Dict[str, Any]
#   - user_comment: str = ''
# Called by:
#   - src/brainctl.py
#   - src/firstboot_eval.py
#   - src/surgeon_auto.py
# Calls:
#   - _nowz, get
# Returns / emits: Dict[str, Any]
# Key locals:
#   - ch, req
# === End NoemaForge Autodoc Function Header ===
def make_prestart_request(
    *,
    request_id: str,
    created_by: Dict[str, Any],
    track: str,
    patches: Dict[str, Any],
    user_comment: str = "",
) -> Dict[str, Any]:
    """Create a draft PreStartChangeRequest object."""
    req = {
        "schema_version": "v1",
        "request_id": request_id,
        "created_at": _nowz(),
        "created_by": created_by,
        "status": "draft",
        "track": track,
        "requested_changes": {},
    }
    if user_comment:
        req["user_comment"] = user_comment

    ch = req["requested_changes"]
    if patches.get("role_model_policy_patch") is not None:
        ch["role_model_policy_patch"] = patches["role_model_policy_patch"]
    if patches.get("llm_backends_policy_patch") is not None:
        ch["llm_backends_policy_patch"] = patches["llm_backends_policy_patch"]
    # Team model overrides (optional)
    if patches.get("team_model_policy_patch") is not None:
        ch["team_model_policy_patch"] = patches["team_model_policy_patch"]
    # Flow/team eval suite/policy can also be patched via pre-start if needed.
    if patches.get("team_eval_policy_patch") is not None:
        ch["team_eval_policy_patch"] = patches["team_eval_policy_patch"]
    if patches.get("flow_catalog_patch") is not None:
        ch["flow_catalog_patch"] = patches["flow_catalog_patch"]
    if patches.get("flow_eval_suite_patch") is not None:
        ch["flow_eval_suite_patch"] = patches["flow_eval_suite_patch"]

    # Risk hint: enabling extra models is supply-chain-ish; treat as medium by default.
    req["risk_level"] = "medium"
    req["requires_canary"] = "auto"
    return req
