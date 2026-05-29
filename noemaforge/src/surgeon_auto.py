#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/surgeon_auto.py
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
# File: src/surgeon_auto.py
# Purpose: Provide the module 'surgeon_auto'.
# Invoked by / imported from:
#   - No inbound Python import detected; treat as library leaf or direct entrypoint.
# Public API / entry functions:
#   - build_report
#   - main
# Inputs:
#   - Environment: NOEMAFORGE_PRESTART_REQUESTS, NOEMAFORGE_MODELSTORE_ROOT, NOEMAFORGE_MODEL_REGISTRY, NOEMAFORGE_MODEL_SCORECARDS, NOEMAFORGE_TEAM_SCORECARDS, NOEMAFORGE_LLM_GATEWAY_SOCKET
#   - Common path inputs: /var/lib/noemaforge, /var/lib/noemaforge/requests/prestart, /var/lib/modelstore, /var/lib/noemaforge/model_scorecards, /var/lib/noemaforge/team_scorecards, /run/noemaforge/llm/gateway.sock, /run/noemaforge/llm/backends, /opt/noemaforge/configs
#   - Imports: __future__, datetime, json, os, subprocess, time, uuid, typing
# Output formats / side effects:
#   - JSON files
#   - YAML files
#   - Markdown files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""surgeon_auto.py (v0.11.6)

Surgeon (auto) job.

Runs in the SELF_IMPROVE domain during the maintenance idle-cycle.

Design constraints
------------------
- Surgeon may *measure* and *plan* at runtime.
- Surgeon must NOT change contracts/policies of the current epoch.
- Any policy/contract change must be expressed as a *draft* pre-start request,
  to be approved by a human during PRE-START.
- No canaries are run at runtime.

In this MVP, Surgeon focuses on:
- Keeping model inventory fresh
- Evaluating (smoke) ONE newly-seen model per run (cheap & sequential)
- Proposing pre-start patches for role-model routing/backends using scorecards
- Exporting roadmaps (explicit development routes)

This is intentionally deterministic and explainable.
"""


import datetime as dt
import json
import os
import subprocess
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

import yaml

from seclog import append as sel_append

import epoch
import model_installer_plan
import model_registry
import model_scorecards
import roadmap
import team_installer_plan
import team_scorecards
import team_search

BASE = "/var/lib/noemaforge"
PACKETS_DIR = os.path.join(BASE, "packets", "surgeon")
REQUESTS_DIR = os.environ.get("NOEMAFORGE_PRESTART_REQUESTS", "/var/lib/noemaforge/requests/prestart")
MODELSTORE_ROOT = os.environ.get("NOEMAFORGE_MODELSTORE_ROOT", "/var/lib/modelstore")
REGISTRY_PATH = os.environ.get("NOEMAFORGE_MODEL_REGISTRY", os.path.join(MODELSTORE_ROOT, "model_registry.json"))
SCORECARDS_DIR = os.environ.get("NOEMAFORGE_MODEL_SCORECARDS", "/var/lib/noemaforge/model_scorecards")
TEAM_SCORECARDS_DIR = os.environ.get("NOEMAFORGE_TEAM_SCORECARDS", "/var/lib/noemaforge/team_scorecards")
GATEWAY_SOCKET = os.environ.get("NOEMAFORGE_LLM_GATEWAY_SOCKET", "/run/noemaforge/llm/gateway.sock")

BACKENDS_SOCK_DIR = "/run/noemaforge/llm/backends"

# "Evaluation surface" (who we care about when routing models)
# Keep explicit to avoid exploding complexity.
EVAL_SURFACE: List[Tuple[str, str]] = [
    ("dev.work", "pm"),
    ("dev.work", "solution_architect"),
    ("dev.work", "dev"),
    ("dev.work", "qa"),
    ("writing.story", "writer"),
    ("writing.story", "tropemaster"),
    ("writing.story", "world_keeper"),
    ("writing.story", "fact_checker"),
    ("writing.story", "editor.literary"),
    ("writing.story", "critic"),
    ("writing.story", "formatter"),
    ("system.guard", "surgeon"),
]


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
# Function: _ts_id()
# Purpose: Implement the routine ' ts id'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - src/fixture_bundle.py
#   - src/scary_sweep.py
#   - src/sr_cycle.py
#   - src/ssr_cycle.py
# Calls:
#   - strftime, utcnow
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _ts_id() -> str:
    return dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")


# === NoemaForge Autodoc Function Header ===
# Function: _save_json(path: str, obj)
# Purpose: Implement the routine ' save json'.
# Inputs:
#   - path: str
#   - obj
# Called by:
#   - src/audit_remediation.py
#   - src/noemaforge_core.py
#   - src/fixture_bundle.py
#   - src/model_registry.py
#   - src/model_scorecards.py
#   - src/prestart.py
#   - src/roles/role_entry.py
#   - src/scary_sweep.py
# Calls:
#   - makedirs, replace, dirname, open, dump
# Returns / emits: None
# Side effects:
#   - reads or writes files
#   - serializes structured data
#   - creates directories
# Key locals:
#   - f, tmp
# === End NoemaForge Autodoc Function Header ===
def _save_json(path: str, obj: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


# === NoemaForge Autodoc Function Header ===
# Function: _save_md(path: str, text: str)
# Purpose: Implement the routine ' save md'.
# Inputs:
#   - path: str
#   - text: str
# Called by:
#   - src/sr_cycle.py
#   - src/ssr_cycle.py
# Calls:
#   - makedirs, dirname, open, write
# Returns / emits: None
# Side effects:
#   - reads or writes files
#   - creates directories
# Key locals:
#   - f
# === End NoemaForge Autodoc Function Header ===
def _save_md(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


# === NoemaForge Autodoc Function Header ===
# Function: _epoch_paths()
# Purpose: Return (epoch_dir, role_model_policy_path, llm_backends_policy_path, team_model_policy_path).
# Inputs:
#   - No explicit parameters.
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - join, current_epoch_dir
# Returns / emits: Tuple[str, str, str, str]
# Key locals:
#   - e_dir, lbp, rmp, tmp
# === End NoemaForge Autodoc Function Header ===
def _epoch_paths() -> Tuple[str, str, str, str]:
    """Return (epoch_dir, role_model_policy_path, llm_backends_policy_path, team_model_policy_path)."""
    e_dir = epoch.current_epoch_dir() or "/opt/noemaforge/configs"
    rmp = os.path.join(e_dir, "role-model-policy.yaml")
    lbp = os.path.join(e_dir, "llm-backends-policy.yaml")
    tmp = os.path.join(e_dir, "team-model-policy.yaml")
    return e_dir, rmp, lbp, tmp


# === NoemaForge Autodoc Function Header ===
# Function: _scorecard_path(model_id: str, stream_id: str, role: str, cap: str = 'llm')
# Purpose: Implement the routine ' scorecard path'.
# Inputs:
#   - model_id: str
#   - stream_id: str
#   - role: str
#   - cap: str = 'llm'
# Called by:
#   - src/model_installer_plan.py
#   - src/model_router.py
#   - src/model_scorecards.py
# Calls:
#   - replace, join
# Returns / emits: str
# Key locals:
#   - rid, sid
# === End NoemaForge Autodoc Function Header ===
def _scorecard_path(model_id: str, stream_id: str, role: str, cap: str = "llm") -> str:
    sid = (stream_id or "").replace("/", "_")
    rid = (role or "").replace("/", "_")
    return os.path.join(SCORECARDS_DIR, model_id, f"{sid}__{rid}__{cap}.json")


# === NoemaForge Autodoc Function Header ===
# Function: _trust_to_float(t_raw)
# Purpose: Convert trust label/number to float in [0..1].
# Inputs:
#   - t_raw
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - float, lower, strip, str
# Returns / emits: float
# Key locals:
#   - t
# === End NoemaForge Autodoc Function Header ===
def _trust_to_float(t_raw: Any) -> float:
    """Convert trust label/number to float in [0..1]."""
    try:
        return float(t_raw)
    except Exception:
        t = str(t_raw or "unknown").strip().lower()
        if t == "local":
            return 0.6
        if t == "imported":
            return 0.75
        if t == "verified":
            return 0.9
        return 0.0


# === NoemaForge Autodoc Function Header ===
# Function: _compute_role_progress(role_model_policy: Dict[str, Any], registry: Dict[str, Any], eval_surface: List[Tuple[str, str]], cap: str = 'llm', min_ok_count_for_passing: int = 1)
# Purpose: Compute progress per (stream, role) using current registry + scorecards.
# Inputs:
#   - role_model_policy: Dict[str, Any]
#   - registry: Dict[str, Any]
#   - eval_surface: List[Tuple[str, str]]
#   - cap: str = 'llm'
#   - min_ok_count_for_passing: int = 1
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - sorted, get, _trust_to_float, len, append, strip, isinstance, _scorecard_path, exists, str, load, int
# Returns / emits: Dict[str, Any]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - cands, caps, cov, eligible, m, mid, min_trust_f, min_trust_raw, okc, passing, pol, reg_models
# === End NoemaForge Autodoc Function Header ===
def _compute_role_progress(
    *,
    role_model_policy: Dict[str, Any],
    registry: Dict[str, Any],
    eval_surface: List[Tuple[str, str]],
    cap: str = "llm",
    min_ok_count_for_passing: int = 1,
) -> Dict[str, Any]:
    """Compute progress per (stream, role) using current registry + scorecards."""
    reg_models = registry.get("models") or []

    # Build quick lookup: model_id -> trust_float
    trust_map: Dict[str, float] = {}
    for m in reg_models:
        try:
            mid = str(m.get("model_id") or "").strip()
        except Exception:
            continue
        if not mid:
            continue
        trust_map[mid] = _trust_to_float(m.get("trust"))

    rows: List[Dict[str, Any]] = []
    for stream_id, role in eval_surface:
        caps = (
            (role_model_policy.get("streams") or {})
            .get(stream_id, {})
            .get("roles", {})
            .get(role, {})
        )
        pol = (caps.get(cap) or {}) if isinstance(caps.get(cap), dict) else {}
        cands = pol.get("candidates") or []
        if not isinstance(cands, list):
            cands = []

        min_trust_raw = pol.get("min_trust")
        min_trust_f = _trust_to_float(min_trust_raw)

        eligible: List[str] = []
        for mid in cands:
            mid = str(mid or "").strip()
            if not mid:
                continue
            if trust_map.get(mid, 0.0) >= min_trust_f:
                eligible.append(mid)

        tested = 0
        passing = 0
        for mid in eligible:
            sp = _scorecard_path(mid, stream_id=stream_id, role=role, cap=cap)
            if os.path.exists(sp):
                tested += 1
                try:
                    sc = json.load(open(sp, "r", encoding="utf-8"))
                    okc = int(((sc.get("summary") or {}).get("ok_count")) or 0)
                    if okc >= int(min_ok_count_for_passing):
                        passing += 1
                except Exception:
                    pass

        total = len(eligible)
        cov = (tested / total) if total else 0.0
        rows.append(
            {
                "stream_id": stream_id,
                "role": role,
                "cap": cap,
                "min_trust": min_trust_raw,
                "min_trust_float": min_trust_f,
                "eligible_total": total,
                "tested": tested,
                "passing": passing,
                "coverage": cov,
            }
        )

    rows_sorted = sorted(
        rows,
        key=lambda r: (
            r.get("tested", 0),
            r.get("coverage", 0.0),
            -r.get("eligible_total", 0),
            r.get("passing", 0),
            r.get("stream_id", ""),
            r.get("role", ""),
        ),
    )
    suggested = rows_sorted[0] if rows_sorted else None
    return {"rows": rows, "suggested_next": suggested}


# === NoemaForge Autodoc Function Header ===
# Function: _backend_sock(model_id: str)
# Purpose: Implement the routine ' backend sock'.
# Inputs:
#   - model_id: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - join
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _backend_sock(model_id: str) -> str:
    return os.path.join(BACKENDS_SOCK_DIR, f"{model_id}.sock")


# === NoemaForge Autodoc Function Header ===
# Function: _wait_sock(path: str, timeout_sec: float = 25.0)
# Purpose: Implement the routine ' wait sock'.
# Inputs:
#   - path: str
#   - timeout_sec: float = 25.0
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - time, exists, sleep
# Returns / emits: bool
# Key locals:
#   - t0
# === End NoemaForge Autodoc Function Header ===
def _wait_sock(path: str, timeout_sec: float = 25.0) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout_sec:
        if os.path.exists(path):
            return True
        time.sleep(0.25)
    return False


# === NoemaForge Autodoc Function Header ===
# Function: _start_backend(model_id: str)
# Purpose: Implement the routine ' start backend'.
# Inputs:
#   - model_id: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _wait_sock, run, _backend_sock, repr, strip
# Returns / emits: Tuple[bool, str]
# Side effects:
#   - spawns subprocesses or workers
# Key locals:
#   - ok, p, unit
# === End NoemaForge Autodoc Function Header ===
def _start_backend(model_id: str) -> Tuple[bool, str]:
    unit = f"noemaforge-llama@{model_id}.service"
    try:
        p = subprocess.run(["/usr/bin/systemctl", "start", unit], capture_output=True, text=True)
        if p.returncode != 0:
            return False, (p.stderr or p.stdout or "").strip()[:2000]
    except Exception as e:
        return False, repr(e)

    ok = _wait_sock(_backend_sock(model_id))
    return ok, "ok" if ok else "socket_timeout"


# === NoemaForge Autodoc Function Header ===
# Function: _enable_models_in_backends_patch(backends_patch: Dict[str, Any], model_ids: List[str])
# Purpose: Ensure a set of model_ids is enabled in llm-backends-policy patch.
# Inputs:
#   - backends_patch: Dict[str, Any]
#   - model_ids: List[str]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - set, isinstance, get, strip, add, append, str, dict
# Returns / emits: Dict[str, Any]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - b, bid, cur, m, mid, out_list, seen
# === End NoemaForge Autodoc Function Header ===
def _enable_models_in_backends_patch(backends_patch: Dict[str, Any], model_ids: List[str]) -> Dict[str, Any]:
    """Ensure a set of model_ids is enabled in llm-backends-policy patch."""
    if not isinstance(backends_patch, dict):
        return backends_patch
    cur = backends_patch.get("backends") or []
    out_list: List[Dict[str, Any]] = []
    seen = set()
    if isinstance(cur, list):
        for b in cur:
            if isinstance(b, dict) and b.get("id"):
                bid = str(b.get("id"))
                if bid:
                    seen.add(bid)
                    out_list.append(dict(b))
    for mid in model_ids:
        m = str(mid or "").strip()
        if not m or m in seen:
            continue
        seen.add(m)
        out_list.append({"id": m, "enabled": True, "model_id": m, "mode": "cpu"})
    backends_patch["backends"] = out_list
    return backends_patch


# === NoemaForge Autodoc Function Header ===
# Function: _pick_unscored_model(reg: Dict[str, Any], role_model_policy_doc: Dict[str, Any], cap: str = 'llm')
# Purpose: Pick next (stream, role, model) to evaluate.
# Inputs:
#   - reg: Dict[str, Any]
#   - role_model_policy_doc: Dict[str, Any]
#   - cap: str = 'llm'
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - get, isinstance, strip, append, float, _min_trust_for, sort, len, int, _scorecard_path, exists, str
# Returns / emits: Optional[Dict[str, Any]]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - best, cand_total, cands, cap_pol, default_mt, default_mtf, defaults, key, m, mid, model_rows, models
# === End NoemaForge Autodoc Function Header ===
def _pick_unscored_model(
    *,
    reg: Dict[str, Any],
    role_model_policy_doc: Dict[str, Any],
    cap: str = "llm",
) -> Optional[Dict[str, Any]]:
    """Pick next (stream, role, model) to evaluate.

    Variant 2 (idle self-reflection):
      - Re-indexing is done earlier; this function consumes current registry.
      - Iterate surface roles in a round‑robin way by selecting the role with
        the smallest number of already-tested models.
      - For the selected role, pick the highest-trust untested model.
    """

    models = (reg.get("models") or []) if isinstance(reg, dict) else []

    # Pre-index model trust values.
    model_rows: List[Tuple[str, float, int]] = []  # (model_id, trust_f, mtime)
    for m in models:
        if not isinstance(m, dict):
            continue
        mid = str(m.get("model_id") or "").strip()
        if not mid:
            continue
        t_raw = m.get("trust")
        try:
            trust_f = float(t_raw)
        except Exception:
            # fall back to rank (verified/unknown/untrusted) if trust is non-numeric
            t = str(t_raw or "unknown").lower().strip()
            trust_f = 2.0 if t == "verified" else 1.0 if t == "unknown" else 0.0
        try:
            mtime = int(m.get("mtime") or 0)
        except Exception:
            mtime = 0
        model_rows.append((mid, trust_f, mtime))

    # Defaults for trust filtering.
    defaults = (role_model_policy_doc.get("defaults") or {}).get(cap, {})
    default_mt = defaults.get("min_trust", 0.0)
    try:
        default_mtf = float(default_mt)
    except Exception:
        default_mtf = 0.0

    # === NoemaForge Autodoc Function Header ===
    # Function: _min_trust_for(stream_id: str, role: str)
    # Purpose: Implement the routine ' min trust for'.
    # Inputs:
    #   - stream_id: str
    #   - role: str
    # Called by:
    #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
    # Calls:
    #   - get, float
    # Returns / emits: float
    # Key locals:
    #   - cap_pol, key, mt, pol
    # === End NoemaForge Autodoc Function Header ===
    def _min_trust_for(stream_id: str, role: str) -> float:
        key = f"{stream_id}__{role}"
        pol = (role_model_policy_doc.get("roles") or {}).get(key, {})
        cap_pol = (pol.get(cap) or {})
        mt = cap_pol.get("min_trust", default_mt)
        try:
            return float(mt)
        except Exception:
            return default_mtf

    best: Optional[Dict[str, Any]] = None

    for stream_id, role in EVAL_SURFACE:
        mtf = _min_trust_for(stream_id, role)

        # Candidate models by trust.
        cands = [(mid, trust_f, mtime) for (mid, trust_f, mtime) in model_rows if trust_f >= mtf]
        if not cands:
            continue
        cands.sort(key=lambda x: (-x[1], -x[2], x[0]))

        tested = 0
        pick_mid: Optional[str] = None
        for mid, _trust_f, _mtime in cands:
            sp = _scorecard_path(mid, stream_id, role, cap)
            if os.path.exists(sp):
                tested += 1
                continue
            if pick_mid is None:
                pick_mid = mid

        if pick_mid is None:
            continue

        cand_total = len(cands)
        if best is None:
            best = {"stream_id": stream_id, "role": role, "model_id": pick_mid, "tested": tested, "total": cand_total, "min_trust": mtf}
            continue

        if tested < int(best.get("tested", 10**9)):
            best = {"stream_id": stream_id, "role": role, "model_id": pick_mid, "tested": tested, "total": cand_total, "min_trust": mtf}
            continue

        if tested == int(best.get("tested", 10**9)) and cand_total > int(best.get("total", -1)):
            best = {"stream_id": stream_id, "role": role, "model_id": pick_mid, "tested": tested, "total": cand_total, "min_trust": mtf}

    return best


# === NoemaForge Autodoc Function Header ===
# Function: _load_role_roadmap_snippets(epoch_dir: str)
# Purpose: Implement the routine ' load role roadmap snippets'.
# Inputs:
#   - epoch_dir: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - load_role_roadmaps, isinstance, get, pick_items, str, append
# Returns / emits: Dict[str, Any]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - it, items, out, rm, roles, s, sa, scary
# === End NoemaForge Autodoc Function Header ===
def _load_role_roadmap_snippets(epoch_dir: str) -> Dict[str, Any]:
    rm = roadmap.load_role_roadmaps(epoch_dir) or {}
    roles = (rm.get("roles") or {}) if isinstance(rm, dict) else {}
    s = roles.get("surgeon") or {}
    scary = roles.get("scary") or {}
    sa = roles.get("solution_architect") or {}

    # === NoemaForge Autodoc Function Header ===
    # Function: pick_items(role_obj: Dict[str, Any], ids: List[str])
    # Purpose: Implement the routine 'pick items'.
    # Inputs:
    #   - role_obj: Dict[str, Any]
    #   - ids: List[str]
    # Called by:
    #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
    # Calls:
    #   - get, isinstance, str, append
    # Returns / emits: List[Dict[str, Any]]
    # Side effects:
    #   - appends to logs or files
    # Key locals:
    #   - it, items, out
    # === End NoemaForge Autodoc Function Header ===
    def pick_items(role_obj: Dict[str, Any], ids: List[str]) -> List[Dict[str, Any]]:
        items = role_obj.get("work_items") or []
        out = []
        for it in items:
            if not isinstance(it, dict):
                continue
            if str(it.get("id") or "") in ids:
                out.append({"id": it.get("id"), "title": it.get("title"), "details": it.get("details")})
        return out

    return {
        "surgeon": pick_items(s, ["surgeon.hygiene.v1", "surgeon.attentive_gaze.v1", "surgeon.prestart_discipline.v1"]),
        "scary": pick_items(scary, ["scary.fixtures.v1", "scary.gloves.v1"]),
        "solution_architect": pick_items(sa, ["arch.pipelines.v1", "arch.vector_memory.v1"]),
    }


# === NoemaForge Autodoc Function Header ===
# Function: build_report()
# Purpose: Implement the routine 'build report'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - makedirs, current_epoch_id, _epoch_paths, update_registry, load_registry, _pick_unscored_model, _load_role_roadmap_snippets, _ts_id, join, _save_json, replace, append
# Returns / emits: Dict[str, Any]
# Side effects:
#   - creates directories
#   - appends to logs or files
# Key locals:
#   - card, draft_req_path, eid, eval_mid, eval_res, eval_role, eval_stream, export_all, export_sa, export_surgeon, f, it
# === End NoemaForge Autodoc Function Header ===
def build_report() -> Dict[str, Any]:
    os.makedirs(PACKETS_DIR, exist_ok=True)
    os.makedirs(REQUESTS_DIR, exist_ok=True)

    eid = epoch.current_epoch_id()
    e_dir, rmp_path, lbp_path, tmp_path = _epoch_paths()

    # 1) Refresh inventory (models may appear outside of runtime)
    inv_changed, inv_summary = model_registry.update_registry(modelstore_root=MODELSTORE_ROOT, registry_path=REGISTRY_PATH, emit_sel=True)
    reg = model_registry.load_registry(REGISTRY_PATH)

    # Load role-model-policy (for min_trust/allowlist when planning team eval)
    try:
        with open(rmp_path, "r", encoding="utf-8") as f:
            rmp_doc = yaml.safe_load(f) or {}
    except Exception:
        rmp_doc = {}

    # 2) Evaluate ONE unscored model (cheap, sequential)
    sel = _pick_unscored_model(reg=reg, role_model_policy_doc=rmp_doc, cap="llm")
    eval_res: Dict[str, Any] = {"ran": False}
    if sel:
        eval_mid = str(sel.get("model_id") or "")
        eval_stream = str(sel.get("stream_id") or "")
        eval_role = str(sel.get("role") or "")
        # Start backend temporarily if needed.
        if not os.path.exists(_backend_sock(eval_mid)):
            ok, reason = _start_backend(eval_mid)
        else:
            ok, reason = True, "already_running"

        if ok:
            try:
                card = model_scorecards.run_scorecard(
                    epoch_dir=e_dir,
                    model_id=eval_mid,
                    stream_id=eval_stream,
                    role=eval_role,
                    cap="llm",
                    suite="smoke",
                    emit_sel=True,
                )
                eval_res = {
                    "ran": True,
                    "model_id": eval_mid,
                    "stream_id": eval_stream,
                    "role": eval_role,
                    "ok": True,
                    "progress": {"tested": sel.get("tested"), "total": sel.get("total"), "min_trust": sel.get("min_trust")},
                    "scorecard": card,
                }
            except Exception as e:
                eval_res = {
                    "ran": True,
                    "model_id": eval_mid,
                    "stream_id": eval_stream,
                    "role": eval_role,
                    "ok": False,
                    "progress": {"tested": sel.get("tested"), "total": sel.get("total"), "min_trust": sel.get("min_trust")},
                    "error": repr(e),
                }
        else:
            eval_res = {
                "ran": True,
                "model_id": eval_mid,
                "stream_id": eval_stream,
                "role": eval_role,
                "ok": False,
                "progress": {"tested": sel.get("tested"), "total": sel.get("total"), "min_trust": sel.get("min_trust")},
                "error": f"backend_start_failed:{reason}",
            }

    # 2b) Evaluate ONE team-config (combinatorics) per run (policy controlled)
    team_eval_res: Dict[str, Any] = {"ran": False}
    try:
        todo = team_search.pick_next_team_eval(
            epoch_dir=e_dir,
            registry_doc=reg,
            scorecards_dir=SCORECARDS_DIR,
            team_scorecards_dir=TEAM_SCORECARDS_DIR,
            role_model_policy_doc=rmp_doc,
            target_role=(str(sel.get("role")) if sel else None),
        )
        if todo:
            # Ensure all required backends are running
            needed = set([str(todo.get("judge_model") or "main")])
            for m in (todo.get("role_models") or {}).values():
                needed.add(str(m))
            started: List[Dict[str, Any]] = []
            for m in sorted(list(needed)):
                if not m:
                    continue
                if os.path.exists(_backend_sock(m)):
                    started.append({"model": m, "ok": True, "reason": "already_running"})
                    continue
                ok, reason = _start_backend(m)
                started.append({"model": m, "ok": bool(ok), "reason": reason})

            # Run end-to-end scorecard
            tsc = team_scorecards.run_team_scorecard(
                epoch_dir=e_dir,
                flow_id=str(todo.get("flow_id")),
                nodes=list(todo.get("nodes") or []),
                role_models=dict(todo.get("role_models") or {}),
                judge_model=str(todo.get("judge_model") or "main"),
                suite=str(todo.get("suite") or "smoke"),
                gateway_socket=GATEWAY_SOCKET,
                scorecards_dir=TEAM_SCORECARDS_DIR,
            )
            team_eval_res = {
                "ran": True,
                "flow_id": todo.get("flow_id"),
                "suite": todo.get("suite"),
                "hash": todo.get("hash"),
                "role_models": todo.get("role_models"),
                "started_backends": started,
                "ok": bool(tsc.get("ok")),
                "scorecard": str(tsc.get("scorecard_path") or ""),
            }
    except Exception as e:
        team_eval_res = {"ran": True, "ok": False, "error": repr(e)}

    # 3) Propose pre-start patches for role routing/backends based on scorecards
    patches: Dict[str, Any] = {}
    draft_req_path = ""
    try:
        patches = model_installer_plan.propose_policy_patches(
            role_model_policy_path=rmp_path,
            llm_backends_policy_path=lbp_path,
            registry_path=REGISTRY_PATH,
            scorecards_dir=SCORECARDS_DIR,
            roles_to_consider=list(EVAL_SURFACE),
            top_k=2,
        )

        # If we have team scorecards, propose enabling team-model overrides (draft only).
        team_patch_rec = team_installer_plan.propose_team_model_policy_patch(
            team_model_policy_path=tmp_path,
            team_scorecards_dir=TEAM_SCORECARDS_DIR,
            flow_id="dev.work",
            suite="smoke",
        )
        if bool(team_patch_rec.get("ok")):
            patches["team_model_policy_patch"] = team_patch_rec.get("patch")
            # Ensure the enabled backends include team-picked models.
            try:
                rm = (((team_patch_rec.get("patch") or {}).get("teams") or {}).get("dev.work") or {}).get("roles") or {}
                mids: List[str] = []
                if isinstance(rm, dict):
                    for _, vv in rm.items():
                        if isinstance(vv, dict) and vv.get("llm"):
                            mids.append(str(vv.get("llm")))
                if mids:
                    patches["llm_backends_policy_patch"] = _enable_models_in_backends_patch(
                        patches.get("llm_backends_policy_patch") or {},
                        mids,
                    )
            except Exception:
                pass
        req = model_installer_plan.make_prestart_request(
            request_id=f"surgeon-auto-{_ts_id()}",
            created_by={"role": "surgeon", "mode": "auto", "epoch_id": eid},
            track="policies",
            patches=patches,
            user_comment="Auto-draft: update role-model routing + enabled backends using latest scorecards. Review in PRE-START.",
        )
        draft_req_path = os.path.join(REQUESTS_DIR, f"{req['request_id']}.json")
        _save_json(draft_req_path, req)
    except Exception as e:
        patches = {"ok": False, "error": repr(e)}

    # 4) Roadmap exports and top items
    try:
        export_all = roadmap.export_report(epoch_dir=e_dir, target_role=None, include_role_roadmaps=True, limit=80)
        export_sa = roadmap.export_report(epoch_dir=e_dir, target_role="solution_architect", include_role_roadmaps=True, limit=50)
        export_surgeon = roadmap.export_report(epoch_dir=e_dir, target_role="surgeon", include_role_roadmaps=True, limit=50)
    except Exception as e:
        export_all = {"ok": False, "error": repr(e)}
        export_sa = {"ok": False, "error": repr(e)}
        export_surgeon = {"ok": False, "error": repr(e)}

    # 5) Role roadmap snippets (to remove "magic" and keep it in artifacts)
    snippets = _load_role_roadmap_snippets(e_dir)

    rid = uuid.uuid4().hex
    ts = _ts_id()

    report: Dict[str, Any] = {
        "schema_version": "v1",
        "kind": "SurgeonAutoReport",
        "report_id": rid,
        "created_at": _nowz(),
        "epoch_id": eid,
        "epoch_dir": e_dir,
        "inventory": {
            "registry_path": REGISTRY_PATH,
            "changed": bool(inv_changed),
            "summary": inv_summary,
            "models_count": int(len((reg.get("models") or []) if isinstance(reg, dict) else [])),
        },
        "evaluation": eval_res,
        "team_evaluation": team_eval_res,
        "prestart_draft": {
            "path": draft_req_path,
            "track": "policies",
            "notes": [
                "Draft only: apply during PRE-START with canaries.",
                "No runtime contract/policy changes. Current epoch remains immutable.",
            ],
        },
        "roadmaps": {
            "all": {"report_path": export_all.get("report_path"), "md": export_all.get("markdown_path"), "ok": export_all.get("ok", True)},
            "solution_architect": {"report_path": export_sa.get("report_path"), "md": export_sa.get("markdown_path"), "ok": export_sa.get("ok", True)},
            "surgeon": {"report_path": export_surgeon.get("report_path"), "md": export_surgeon.get("markdown_path"), "ok": export_surgeon.get("ok", True)},
        },
        "roadmap_snippets": snippets,
        "default_duties": [
            "(lowest priority duty) Analyze model fleet vs internal success metrics and propose a prioritized improvement plan for PRE-START approval.",
            "Maintain sterility via gloves (amnesic one-shot SLM) when analyzing untrusted inputs.",
            "For high-stakes decisions, perform a second pass and compare conclusions.",
        ],
        "notes": [
            "This run performs at most ONE model eval to keep resource usage predictable.",
            "If multiple streams request the same Solution Architect item, repetition increases its priority via roadmap signals.",
        ],
    }

    out_json = os.path.join(PACKETS_DIR, f"{ts}_surgeon_auto.json")
    _save_json(out_json, report)

    out_md = out_json.replace(".json", ".md")
    md_lines: List[str] = []
    md_lines.append(f"# Surgeon auto report ({ts})\n\n")
    md_lines.append(f"epoch_id: {eid}\n\n")
    md_lines.append("## Inventory\n")
    md_lines.append(f"- registry: {REGISTRY_PATH}\n")
    md_lines.append(f"- changed: {inv_changed}\n")
    md_lines.append(f"- models_count: {report['inventory']['models_count']}\n\n")

    md_lines.append("## Evaluation (one-step)\n")
    if eval_res.get("ran"):
        md_lines.append(f"- model: {eval_res.get('model_id')}\n")
        md_lines.append(f"- ok: {eval_res.get('ok')}\n")
    else:
        md_lines.append("- (no unscored models found or eval skipped)\n")
    md_lines.append("\n")

    md_lines.append("## Team evaluation (one-step)\n")
    if team_eval_res.get("ran"):
        md_lines.append(f"- flow: {team_eval_res.get('flow_id')}\n")
        md_lines.append(f"- suite: {team_eval_res.get('suite')}\n")
        md_lines.append(f"- ok: {team_eval_res.get('ok')}\n")
        md_lines.append(f"- scorecard: {team_eval_res.get('scorecard') or '(none)'}\n")
    else:
        md_lines.append("- (no pending team configs or policy disabled)\n")
    md_lines.append("\n")

    md_lines.append("## Pre-start draft\n")
    md_lines.append(f"- draft: {draft_req_path or '(none)'}\n")
    md_lines.append("\n")

    md_lines.append("## Roadmaps\n")
    md_lines.append(f"- ALL: {export_all.get('report_path') if export_all.get('ok') else '(failed)'}\n")
    md_lines.append(f"- solution_architect: {export_sa.get('report_path') if export_sa.get('ok') else '(failed)'}\n")
    md_lines.append(f"- surgeon: {export_surgeon.get('report_path') if export_surgeon.get('ok') else '(failed)'}\n")

    md_lines.append("\n## Surgeon reminders (from role roadmap)\n")
    for it in snippets.get("surgeon", []) or []:
        md_lines.append(f"- **{it.get('title')}** ({it.get('id')})\n")
    md_lines.append("\n")

    _save_md(out_md, "".join(md_lines))

    # SEL
    try:
        sel_append(
            {
                "evt_id": os.urandom(8).hex(),
                "ts": report["created_at"],
                "severity": "S1",
                "type": "SURGEON_AUTO_REPORT",
                "actor": {"role": "surgeon", "mode": "auto"},
                "decision": "emit",
                "trace_id": os.urandom(8).hex(),
                "report": out_json,
                "prestart_draft": draft_req_path,
                "evaluated_model": eval_mid or "",
                "evaluated_team": {
                    "ran": bool(team_eval_res.get("ran")),
                    "flow_id": team_eval_res.get("flow_id"),
                    "suite": team_eval_res.get("suite"),
                    "ok": team_eval_res.get("ok"),
                },
            }
        )
    except Exception:
        pass

    return {"ok": True, "report": out_json, "markdown": out_md, "draft_prestart": draft_req_path, "evaluated": eval_mid or ""}


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
#   - build_report, print, get
# Returns / emits: int
# Key locals:
#   - rep
# === End NoemaForge Autodoc Function Header ===
def main() -> int:
    rep = build_report()
    print(rep.get("report"))
    return 0 if rep.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
