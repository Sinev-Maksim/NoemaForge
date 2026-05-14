#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/model_router.py
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
# File: src/model_router.py
# Purpose: Provide the module 'model_router'.
# Invoked by / imported from:
#   - src/toolproxy.py
# Public API / entry functions:
#   - load_role_model_policy
#   - load_team_model_policy
#   - load_model_registry
#   - match_role_entry
#   - resolve_cap_policy
#   - select_model
# Inputs:
#   - Environment: NOEMAFORGE_CONTRACTS_ROOT, NOEMAFORGE_MODEL_REGISTRY, NOEMAFORGE_MODEL_SCORECARDS, NOEMAFORGE_TEAM_MODEL_POLICY
#   - Common path inputs: /var/lib/noemaforge/contracts, /var/lib/modelstore/model_registry.json, /var/lib/noemaforge/model_scorecards, /opt/noemaforge/configs/team-model-policy.yaml, noemaforge.rolemodel/v1, noemaforge.teammodel/v1
#   - Imports: __future__, json, os, re, fnmatch, typing, yaml
# Output formats / side effects:
#   - JSON files
#   - YAML files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""model_router.py (v0.11.1)

Role-aware model selection.

Goal
----
At runtime, executors (roles) should not need to hardcode model IDs.
Instead, they declare *who they are* (stream_id + role), and the spine
selects the best allowed model using:

* Contract Epoch policy (role-model-policy.yaml)
* Local inventory (model_registry.json)
* Surgeon scorecards (optional)

Contracts/policies may change only in pre-start; scorecards and registry may
update without changing the epoch (they're state, not law).
"""


import json
import os
import re
import fnmatch
from typing import Any, Dict, List, Optional, Tuple

import yaml


DEFAULT_CONTRACTS_ROOT = os.environ.get("NOEMAFORGE_CONTRACTS_ROOT", "/var/lib/noemaforge/contracts")
DEFAULT_MODEL_REGISTRY = os.environ.get("NOEMAFORGE_MODEL_REGISTRY", "/var/lib/modelstore/model_registry.json")
DEFAULT_SCORECARDS_DIR = os.environ.get("NOEMAFORGE_MODEL_SCORECARDS", "/var/lib/noemaforge/model_scorecards")


DEFAULT_TEAM_MODEL_POLICY = os.environ.get("NOEMAFORGE_TEAM_MODEL_POLICY", "/opt/noemaforge/configs/team-model-policy.yaml")


_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")


# === NoemaForge Autodoc Function Header ===
# Function: _safe_id(s: str)
# Purpose: Implement the routine ' safe id'.
# Inputs:
#   - s: str
# Called by:
#   - src/llm_backends_manager.py
#   - src/localgw_secrets.py
# Calls:
#   - bool, match, strip, str
# Returns / emits: bool
# === End NoemaForge Autodoc Function Header ===
def _safe_id(s: str) -> bool:
    return bool(_SAFE_ID_RE.match(str(s or "").strip()))


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
# Function: load_role_model_policy(path: str)
# Purpose: Implement the routine 'load role model policy'.
# Inputs:
#   - path: str
# Called by:
#   - src/toolproxy.py
# Calls:
#   - exists, _load_yaml, isinstance
# Returns / emits: Dict[str, Any]
# Key locals:
#   - obj
# === End NoemaForge Autodoc Function Header ===
def load_role_model_policy(path: str) -> Dict[str, Any]:
    try:
        if os.path.exists(path):
            obj = _load_yaml(path)
            if isinstance(obj, dict):
                return obj
    except Exception:
        pass
    return {
        "apiVersion": "noemaforge.rolemodel/v1",
        "kind": "RoleModelPolicy",
        "defaults": {
            "llm": {"fallback_model": "main", "min_trust": "unknown", "require_scorecard": False},
            "embed": {"fallback_model": "main", "min_trust": "unknown", "require_scorecard": False},
            "selector": {"strategy": "best_score_then_latency"},
        },
        "roles": {"*/*": {"llm": {"candidates": ["main"]}, "embed": {"candidates": ["main"]}}},
    }


# === NoemaForge Autodoc Function Header ===
# Function: load_team_model_policy(path: str)
# Purpose: Load TeamModelPolicy.
# Inputs:
#   - path: str
# Called by:
#   - src/toolproxy.py
# Calls:
#   - exists, _load_yaml, isinstance
# Returns / emits: Dict[str, Any]
# Key locals:
#   - obj
# === End NoemaForge Autodoc Function Header ===
def load_team_model_policy(path: str) -> Dict[str, Any]:
    """Load TeamModelPolicy.

    Team policy is optional; when disabled it should be a no-op.
    """
    try:
        if path and os.path.exists(path):
            obj = _load_yaml(path)
            if isinstance(obj, dict):
                return obj
    except Exception:
        pass
    return {
        "apiVersion": "noemaforge.teammodel/v1",
        "kind": "TeamModelPolicy",
        "defaults": {"enabled": False, "selection": {"strategy": "selected"}},
        "teams": {},
    }


# === NoemaForge Autodoc Function Header ===
# Function: load_model_registry(path: str = DEFAULT_MODEL_REGISTRY)
# Purpose: Implement the routine 'load model registry'.
# Inputs:
#   - path: str = DEFAULT_MODEL_REGISTRY
# Called by:
#   - src/toolproxy.py
# Calls:
#   - exists, _load_json, isinstance
# Returns / emits: Dict[str, Any]
# Key locals:
#   - obj
# === End NoemaForge Autodoc Function Header ===
def load_model_registry(path: str = DEFAULT_MODEL_REGISTRY) -> Dict[str, Any]:
    try:
        if os.path.exists(path):
            obj = _load_json(path)
            if isinstance(obj, dict):
                return obj
    except Exception:
        pass
    return {"models": []}


# === NoemaForge Autodoc Function Header ===
# Function: _registry_map(reg: Dict[str, Any])
# Purpose: Implement the routine ' registry map'.
# Inputs:
#   - reg: Dict[str, Any]
# Called by:
#   - src/toolproxy.py
# Calls:
#   - strip, get, dict, str
# Returns / emits: Dict[str, Dict[str, Any]]
# Key locals:
#   - m, mid, out
# === End NoemaForge Autodoc Function Header ===
def _registry_map(reg: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for m in (reg.get("models") or []) or []:
        mid = str(m.get("model_id") or "").strip()
        if mid:
            out[mid] = dict(m)
    return out


# === NoemaForge Autodoc Function Header ===
# Function: _trust_rank(trust: str)
# Purpose: Implement the routine ' trust rank'.
# Inputs:
#   - trust: str
# Called by:
#   - src/model_installer_plan.py
# Calls:
#   - strip, lower, str
# Returns / emits: int
# Key locals:
#   - t
# === End NoemaForge Autodoc Function Header ===
def _trust_rank(trust: str) -> int:
    t = str(trust or "unknown").lower().strip()
    # higher is better
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
#   - src/model_installer_plan.py
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
# Function: _has_wildcards(pat: str)
# Purpose: Implement the routine ' has wildcards'.
# Inputs:
#   - pat: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - str
# Returns / emits: bool
# Key locals:
#   - p
# === End NoemaForge Autodoc Function Header ===
def _has_wildcards(pat: str) -> bool:
    p = str(pat or "")
    return ("*" in p) or ("?" in p) or ("[" in p)


# === NoemaForge Autodoc Function Header ===
# Function: _role_matches(role_pat: str, role_id: str)
# Purpose: Role pattern matching with specialization inheritance.
# Inputs:
#   - role_pat: str
#   - role_id: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _has_wildcards, startswith, strip, fnmatch, str
# Returns / emits: bool
# Key locals:
#   - rid, rp
# === End NoemaForge Autodoc Function Header ===
def _role_matches(role_pat: str, role_id: str) -> bool:
    """Role pattern matching with specialization inheritance.

    Rules:
    - Wildcard patterns use fnmatch (e.g., dev.*)
    - Exact patterns match either exact role_id OR any specialization child
      (dev matches dev.python and dev.python.sql).
    """
    rp = str(role_pat or "").strip() or "*"
    rid = str(role_id or "").strip() or "*"
    if rp == "*":
        return True
    if _has_wildcards(rp):
        return fnmatch.fnmatch(rid, rp)
    if rid == rp:
        return True
    # specialization inheritance
    return rid.startswith(rp + ".")


# === NoemaForge Autodoc Function Header ===
# Function: _stream_matches(stream_pat: str, stream_id: str)
# Purpose: Implement the routine ' stream matches'.
# Inputs:
#   - stream_pat: str
#   - stream_id: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _has_wildcards, strip, fnmatch, str
# Returns / emits: bool
# Key locals:
#   - sid, sp
# === End NoemaForge Autodoc Function Header ===
def _stream_matches(stream_pat: str, stream_id: str) -> bool:
    sp = str(stream_pat or "").strip() or "*"
    sid = str(stream_id or "").strip() or "*"
    if sp == "*":
        return True
    if _has_wildcards(sp):
        return fnmatch.fnmatch(sid, sp)
    return sid == sp


# === NoemaForge Autodoc Function Header ===
# Function: _specificity(stream_pat: str, role_pat: str)
# Purpose: Return a tuple where larger is better.
# Inputs:
#   - stream_pat: str
#   - role_pat: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - str, len, _has_wildcards, replace
# Returns / emits: Tuple[int, int, int, int]
# Key locals:
#   - rp, rp_len, rp_wc, sp, sp_len, sp_wc
# === End NoemaForge Autodoc Function Header ===
def _specificity(stream_pat: str, role_pat: str) -> Tuple[int, int, int, int]:
    """Return a tuple where larger is better."""
    sp = str(stream_pat or "")
    rp = str(role_pat or "")
    sp_wc = 1 if _has_wildcards(sp) else 0
    rp_wc = 1 if _has_wildcards(rp) else 0
    sp_len = len(sp.replace("*", "").replace("?", ""))
    rp_len = len(rp.replace("*", "").replace("?", ""))
    # Prefer exact over wildcard; prefer longer patterns.
    # stream weight is higher because it scopes policies.
    return (
        1 - sp_wc,
        sp_len,
        1 - rp_wc,
        rp_len,
    )


# === NoemaForge Autodoc Function Header ===
# Function: match_role_entry(policy_doc: Dict[str, Any], stream_id: str, role_id: str)
# Purpose: Pick the best matching roles-map entry.
# Inputs:
#   - policy_doc: Dict[str, Any]
#   - stream_id: str
#   - role_id: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - items, get, isinstance, strip, split, _specificity, _stream_matches, _role_matches, str, dict
# Returns / emits: Tuple[str, Dict[str, Any]]
# Key locals:
#   - best_cfg, best_key, best_score, rid, roles_map, score, sid
# === End NoemaForge Autodoc Function Header ===
def match_role_entry(policy_doc: Dict[str, Any], stream_id: str, role_id: str) -> Tuple[str, Dict[str, Any]]:
    """Pick the best matching roles-map entry.

    Supports specialization inheritance (dev matches dev.python).
    """
    roles_map = policy_doc.get("roles") or {}
    if not isinstance(roles_map, dict):
        return "", {}

    best_key = ""
    best_cfg: Dict[str, Any] = {}
    best_score: Tuple[int, int, int, int] = (-1, -1, -1, -1)

    sid = str(stream_id or "").strip() or "*"
    rid = str(role_id or "").strip() or "*"

    for k, cfg in roles_map.items():
        if not isinstance(k, str):
            continue
        if "/" not in k:
            continue
        sp, rp = k.split("/", 1)
        if not _stream_matches(sp, sid):
            continue
        if not _role_matches(rp, rid):
            continue
        score = _specificity(sp, rp)
        if score > best_score:
            best_score = score
            best_key = k
            best_cfg = dict(cfg or {}) if isinstance(cfg, dict) else {}

    return best_key, best_cfg


# === NoemaForge Autodoc Function Header ===
# Function: _cap_key(action: str)
# Purpose: Implement the routine ' cap key'.
# Inputs:
#   - action: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - lower, strip, str
# Returns / emits: str
# Key locals:
#   - a
# === End NoemaForge Autodoc Function Header ===
def _cap_key(action: str) -> str:
    a = str(action or "").strip().lower()
    if a == "llm.embed":
        return "embed"
    return "llm"


# === NoemaForge Autodoc Function Header ===
# Function: resolve_cap_policy(policy_doc: Dict[str, Any], stream_id: str, role: str, cap: str)
# Purpose: Resolve merged cap policy for (stream, role, cap).
# Inputs:
#   - policy_doc: Dict[str, Any]
#   - stream_id: str
#   - role: str
#   - cap: str
# Called by:
#   - src/toolproxy.py
# Calls:
#   - bool, match_role_entry, dict, lower, get, strip, str
# Returns / emits: Dict[str, Any]
# Key locals:
#   - allow_explicit, candidates, cap, cap_cfg, dcap, defaults, fallback, min_trust, require_scorecard
# === End NoemaForge Autodoc Function Header ===
def resolve_cap_policy(
    *,
    policy_doc: Dict[str, Any],
    stream_id: str,
    role: str,
    cap: str,
) -> Dict[str, Any]:
    """Resolve merged cap policy for (stream, role, cap).

    Returns:
      {
        "cap": "llm"|"embed",
        "matched_key": "...",
        "fallback_model": "main",
        "min_trust": "unknown",
        "require_scorecard": false,
        "allow_explicit": false,
        "candidates": [..]
      }
    """
    cap = (cap or "llm").strip().lower() or "llm"
    defaults = (policy_doc.get("defaults") or {})
    dcap = (defaults.get(cap) or {})
    fallback = str(dcap.get("fallback_model") or "main").strip() or "main"
    min_trust = str(dcap.get("min_trust") or "unknown").strip().lower() or "unknown"
    require_scorecard = bool(dcap.get("require_scorecard") or False)

    matched_key, chosen_cfg = match_role_entry(policy_doc, stream_id, role)
    cap_cfg = dict((chosen_cfg.get(cap) or {}))

    candidates = [str(x).strip() for x in (cap_cfg.get("candidates") or []) if str(x).strip()]
    if not candidates:
        candidates = [fallback]

    if "min_trust" in cap_cfg:
        min_trust = str(cap_cfg.get("min_trust") or min_trust).strip().lower() or min_trust
    if "require_scorecard" in cap_cfg:
        require_scorecard = bool(cap_cfg.get("require_scorecard"))
    allow_explicit = bool(cap_cfg.get("allow_explicit") or False)

    return {
        "cap": cap,
        "matched_key": matched_key,
        "fallback_model": fallback,
        "min_trust": min_trust,
        "require_scorecard": require_scorecard,
        "allow_explicit": allow_explicit,
        "candidates": candidates,
    }


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
#   - src/model_installer_plan.py
#   - src/model_scorecards.py
#   - src/surgeon_auto.py
# Calls:
#   - replace, join
# Returns / emits: str
# Key locals:
#   - fname, rid, sid
# === End NoemaForge Autodoc Function Header ===
def _scorecard_path(model_id: str, stream_id: str, role: str, cap: str, scorecards_dir: str) -> str:
    # Stable key: stream and role matter (different contracts/affirmations).
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
#   - src/model_installer_plan.py
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
# Function: select_model(action: str, stream_id: str, role: str, policy_doc: Dict[str, Any], registry_doc: Dict[str, Any], scorecards_dir: str = DEFAULT_SCORECARDS_DIR, team_policy_doc: Optional[Dict[str, Any]] = None)
# Purpose: Return (model_id, explain).
# Inputs:
#   - action: str
#   - stream_id: str
#   - role: str
#   - policy_doc: Dict[str, Any]
#   - registry_doc: Dict[str, Any]
#   - scorecards_dir: str = DEFAULT_SCORECARDS_DIR
#   - team_policy_doc: Optional[Dict[str, Any]] = None
# Called by:
#   - src/toolproxy.py
# Calls:
#   - _cap_key, resolve_cap_policy, str, bool, list, _registry_map, _policy_rank, get, _scorecard_path, _read_scorecard, float, append
# Returns / emits: Tuple[str, Dict[str, Any]]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - best, cand_role, cands, cap, cap_pol, explain, fallback, latency, mid, min_rank, min_trust, picked
# === End NoemaForge Autodoc Function Header ===
def select_model(
    *,
    action: str,
    stream_id: str,
    role: str,
    policy_doc: Dict[str, Any],
    registry_doc: Dict[str, Any],
    scorecards_dir: str = DEFAULT_SCORECARDS_DIR,
    team_policy_doc: Optional[Dict[str, Any]] = None,
) -> Tuple[str, Dict[str, Any]]:
    """Return (model_id, explain).

    This function is intentionally deterministic and conservative:

    - Only candidates declared by the epoch policy are eligible.
    - Trust thresholds gate candidates.
    - Scorecards are used only if present and requested.
    - Always returns a fallback model.
    """
    cap = _cap_key(action)
    cap_pol = resolve_cap_policy(policy_doc=policy_doc, stream_id=stream_id, role=role, cap=cap)
    fallback = str(cap_pol.get("fallback_model") or "main")
    min_trust = str(cap_pol.get("min_trust") or "unknown")
    require_scorecard = bool(cap_pol.get("require_scorecard") or False)
    cands = list(cap_pol.get("candidates") or [])

    reg_map = _registry_map(registry_doc)
    min_rank = _policy_rank(min_trust)

    scored: List[Tuple[float, float, str, Dict[str, Any]]] = []  # (score, latency, model_id, explain)
    reasons: Dict[str, Any] = {
        "eligible": [],
        "rejected": [],
        "cap": cap,
        "min_trust": min_trust,
        "require_scorecard": require_scorecard,
        "role_policy_match": str(cap_pol.get("matched_key") or ""),
    }

    # Team override (optional) — evaluated first, but only if it passes trust + allowlist.
    try:
        if team_policy_doc is None:
            team_policy_doc = None
        tdoc = team_policy_doc or {}
        tdef = (tdoc.get("defaults") or {}) if isinstance(tdoc, dict) else {}
        t_enabled = bool(tdef.get("enabled") or False)
        if t_enabled:
            teams = (tdoc.get("teams") or {}) if isinstance(tdoc.get("teams"), dict) else {}
            trec = teams.get(stream_id) or {}
            if isinstance(trec, dict) and bool(trec.get("enabled") or False):
                roles_map_t = trec.get("roles") or {}
                picked = None
                # role inheritance: dev matches dev.python
                if isinstance(roles_map_t, dict):
                    for cand_role in [role] + [".".join(role.split(".")[:i]) for i in range(len(role.split(".")) - 1, 0, -1)]:
                        rr = roles_map_t.get(cand_role)
                        if isinstance(rr, dict) and rr.get(cap):
                            picked = str(rr.get(cap) or "").strip()
                            break
                if picked:
                    # Team-picked model must be within allowlist candidates or be the fallback.
                    if picked in set(cands + [fallback]):
                        # Validate via trust/registry. We do not require scorecard for team override (yet).
                        tmp_policy = {
                            "defaults": {cap: {"fallback_model": fallback, "min_trust": min_trust, "require_scorecard": False}},
                            "roles": {"*/*": {cap: {"candidates": [picked], "min_trust": min_trust, "require_scorecard": False}}},
                        }
                        mid, _ = select_model(
                            action=action,
                            stream_id=stream_id,
                            role=role,
                            policy_doc=tmp_policy,
                            registry_doc=registry_doc,
                            scorecards_dir=scorecards_dir,
                            team_policy_doc=None,
                        )
                        if mid == picked:
                            explain = {"picked": picked, "team_override": True, "team_stream": stream_id}
                            return picked, explain
                        reasons["rejected"].append({"model_id": picked, "reason": "team_override_rejected_by_trust_or_registry"})
                    else:
                        reasons["rejected"].append({"model_id": picked, "reason": "team_override_not_in_allowlist"})
    except Exception:
        # Team override must never break normal routing.
        pass

    for mid in cands:
        if not _safe_id(mid):
            reasons["rejected"].append({"model_id": mid, "reason": "unsafe_model_id"})
            continue

        rec = reg_map.get(mid)
        if not rec:
            reasons["rejected"].append({"model_id": mid, "reason": "not_in_registry"})
            continue

        trust = str(rec.get("trust") or "unknown")
        if _trust_rank(trust) < min_rank:
            reasons["rejected"].append({"model_id": mid, "reason": "trust_below_min", "trust": trust})
            continue

        sp = _scorecard_path(mid, stream_id, role, cap, scorecards_dir)
        sc = _read_scorecard(sp)
        if require_scorecard and not sc:
            reasons["rejected"].append({"model_id": mid, "reason": "missing_scorecard", "scorecard": sp})
            continue

        score = float(sc.get("quality_score") or sc.get("overall_score") or 0.0)
        latency = float(sc.get("avg_latency_ms") or 1e9)

        reasons["eligible"].append({"model_id": mid, "trust": trust, "score": score, "avg_latency_ms": latency, "scorecard": sp if sc else ""})
        scored.append((score, latency, mid, {"trust": trust, "scorecard": sp if sc else ""}))

    if scored:
        # Best score first, then lowest latency
        scored.sort(key=lambda t: (-t[0], t[1], t[2]))
        best = scored[0]
        explain = {"picked": best[2], "score": best[0], "avg_latency_ms": best[1], "reasons": reasons}
        return best[2], explain

    # Fallback (even if not in registry; caller may still run legacy setup)
    explain = {"picked": fallback, "fallback": True, "reasons": reasons}
    return fallback, explain
