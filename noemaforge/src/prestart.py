#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/prestart.py
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
# File: src/prestart.py
# Purpose: Manage epoch-scoped changes, canary planning, validation, and apply/rollback preparation.
# Invoked by / imported from:
#   - src/bootdoctor.py
#   - src/brainctl.py
#   - src/canary_runner.py
#   - src/firstboot_eval.py
#   - src/llm_backends_manager.py
# Public API / entry functions:
#   - policy_lock_state
#   - set_policy_lock
#   - read_mode
#   - epochs_dir
#   - epoch_path
#   - current_epoch_id
#   - list_epochs
#   - next_epoch_id
#   - class RequestRecord
#   - class ChangeUnit
#   - load_requests
#   - select_requests_for_build
# Inputs:
#   - Environment: NOEMAFORGE_CONTRACTS_ROOT
#   - Common path inputs: /var/lib/noemaforge/contracts, /var/lib/noemaforge/requests/prestart, /var/lib/noemaforge/.sys/policy-lock.state, /run/noemaforge/mode, /var/lib/noemaforge/notifications, overlays/streams_add, /opt/noemaforge/configs, noemaforge.lsm/v1
#   - Imports: __future__, datetime, hashlib, json, os, subprocess, shutil, tempfile
# Output formats / side effects:
#   - JSON files
#   - YAML files
#   - copied filesystem artifacts
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""prestart.py (v0.17.1)

Pre-start Contract Epoch manager.

Core law:
- Runtime is immutable. Contracts/policies change only in PRE-START.

Security posture update (v0.9.2):
- Canary execution is PRE-START ONLY.
- No automatic canaries during runtime.
- Break-glass runtime override is possible only via explicit operator flags.

This module is intentionally conservative and dependency-light.
"""


import datetime as dt
import hashlib
import json
import os
import subprocess
import shutil
import tempfile
import time
import uuid
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import yaml

from toolvault import bundle_paths, prepare_plugin_bundle

try:
    from seclog import append as sel_append
except Exception:  # pragma: no cover
    sel_append = None  # type: ignore


DEFAULT_CONTRACTS_ROOT = os.environ.get("NOEMAFORGE_CONTRACTS_ROOT", "/var/lib/noemaforge/contracts")
DEFAULT_REQUESTS_DIR = "/var/lib/noemaforge/requests/prestart"
DEFAULT_POLICY_LOCK = "/var/lib/noemaforge/.sys/policy-lock.state"
DEFAULT_MODE_FILE = "/run/noemaforge/mode"  # runtime typically writes 'runtime' here
DEFAULT_NOTIFICATIONS_DIR = "/var/lib/noemaforge/notifications"


EPOCH_FILES = [
    "streams.yaml",
    "patterns.yaml",
    "tool-registry.yaml",
    "tool-policy.yaml",
    "sandbox-policy.yaml",
    "supplychain-policy.yaml",
    "bundle-policy.yaml",
    "web-gateway-policy.yaml",
    "local-gateway-policy.yaml",
    "nids-policy.yaml",
    "maintenance-policy.yaml",
    "resource-policy.yaml",
    "storage-policy.yaml",
    "taskqueue-policy.yaml",
    "bootdoctor.yaml",
    "installer-policy.yaml",
    "verifiers.yaml",
    "clarifications.yaml",
    "vstore.yaml",
    "memory-policy.yaml",

    # Embedding generation policy (offline-first hashing; later epochs may add LLM providers).
    "embeddings-policy.yaml",

    # Stage D: Hypergraph knowledge base + realm/trail policy.
    "knowledge-policy.yaml",
    "canary-policy.yaml",
    "security-fixtures.yaml",
    "quarantine-policy.yaml",
    "incident-policy.yaml",
    "lsm-policy.yaml",
    "role-affirmations.yaml",
    "role-roadmaps.yaml",

    # Model fleet routing + eval (epoch-scoped)
    "role-model-policy.yaml",
    "model-eval-suite.yaml",
    "llm-backends-policy.yaml",

    # Observability + prompt kit (epoch-scoped)
    "observability-policy.yaml",
    "metrics-catalog.yaml",
    "promptkit.yaml",

    # Flow/team evaluation + team model overrides (epoch-scoped)
    "flow-catalog.yaml",
    "flow-eval-suite.yaml",
    "team-eval-policy.yaml",
    "team-model-policy.yaml",
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
# Function: _sha256_file(path: str)
# Purpose: Implement the routine ' sha256 file'.
# Inputs:
#   - path: str
# Called by:
#   - src/bootdoctor.py
#   - src/brainctl.py
#   - src/casebase.py
#   - src/doctor.py
#   - src/glove_agent.py
#   - src/localgw_uplink_agent.py
#   - src/model_registry.py
#   - src/pipelines/finance_budget.py
# Calls:
#   - sha256, hexdigest, open, iter, update, read
# Returns / emits: str
# Side effects:
#   - reads or writes files
# Key locals:
#   - chunk, f, h
# === End NoemaForge Autodoc Function Header ===
def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


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
# Function: _save_yaml(path: str, obj)
# Purpose: Implement the routine ' save yaml'.
# Inputs:
#   - path: str
#   - obj
# Called by:
#   - src/noemaforge_core.py
#   - src/tool_onboard.py
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
def _save_yaml(path: str, obj: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(obj, f, sort_keys=False, allow_unicode=True)


# === NoemaForge Autodoc Function Header ===
# Function: _load_any(path: str)
# Purpose: Implement the routine ' load any'.
# Inputs:
#   - path: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - endswith, _load_yaml, open, load
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads or writes files
# Key locals:
#   - f
# === End NoemaForge Autodoc Function Header ===
def _load_any(path: str) -> Dict[str, Any]:
    if path.endswith(".json"):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return _load_yaml(path)


# === NoemaForge Autodoc Function Header ===
# Function: _save_any(path: str, obj)
# Purpose: Implement the routine ' save any'.
# Inputs:
#   - path: str
#   - obj
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - endswith, _save_yaml, makedirs, dirname, open, dump
# Returns / emits: None
# Side effects:
#   - reads or writes files
#   - serializes structured data
#   - creates directories
# Key locals:
#   - f
# === End NoemaForge Autodoc Function Header ===
def _save_any(path: str, obj: Any) -> None:
    if path.endswith(".json"):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
        return
    _save_yaml(path, obj)


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
#   - src/roles/role_entry.py
#   - src/scary_sweep.py
#   - src/sr_cycle.py
# Calls:
#   - makedirs, dirname, open, dump
# Returns / emits: None
# Side effects:
#   - reads or writes files
#   - serializes structured data
#   - creates directories
# Key locals:
#   - f
# === End NoemaForge Autodoc Function Header ===
def _save_json(path: str, obj: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


# === NoemaForge Autodoc Function Header ===
# Function: _deep_merge(base, patch)
# Purpose: Conservative deep merge:
# Inputs:
#   - base
#   - patch
# Called by:
#   - src/webgateway.py
# Calls:
#   - isinstance, dict, items, all, set, _deep_merge, str, bool, get, is_id_obj, add, pop
# Returns / emits: Any
# Key locals:
#   - appended, base_map, base_order, deleted, out, out_list, p, pid
# === End NoemaForge Autodoc Function Header ===
def _deep_merge(base: Any, patch: Any) -> Any:
    """Conservative deep merge:

    - dict + dict: recursive merge (patch wins)
    - list: patch replaces base, EXCEPT: if both lists are dicts with stable 'id', merge by id
    - scalar: patch replaces base

    This is intentionally boring: less clever = fewer surprises.
    """

    if isinstance(base, dict) and isinstance(patch, dict):
        out = dict(base)
        for k, v in patch.items():
            if k in out:
                out[k] = _deep_merge(out[k], v)
            else:
                out[k] = v
        return out

    if isinstance(base, list) and isinstance(patch, list):
        # === NoemaForge Autodoc Function Header ===
        # Function: is_id_obj(x)
        # Purpose: Implement the routine 'is id obj'.
        # Inputs:
        #   - x
        # Called by:
        #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
        # Calls:
        #   - isinstance, get
        # Returns / emits: bool
        # === End NoemaForge Autodoc Function Header ===
        def is_id_obj(x: Any) -> bool:
            return isinstance(x, dict) and isinstance(x.get("id"), (str, int))

        if all(is_id_obj(x) for x in base) and all(is_id_obj(x) for x in patch):
            base_order = [str(x["id"]) for x in base]
            base_map: Dict[str, Any] = {str(x["id"]): x for x in base}
            deleted: set[str] = set()
            appended: List[str] = []

            for p in patch:
                pid = str(p["id"])
                if bool(p.get("_delete")):
                    deleted.add(pid)
                    base_map.pop(pid, None)
                    continue
                if bool(p.get("_replace")):
                    base_map[pid] = {k: v for k, v in p.items() if k not in ("_replace",)}
                    if pid not in base_order and pid not in appended:
                        appended.append(pid)
                    continue
                if pid in base_map:
                    base_map[pid] = _deep_merge(base_map[pid], p)
                else:
                    base_map[pid] = p
                    appended.append(pid)

            out_list: List[Any] = []
            for pid in base_order:
                if pid in deleted:
                    continue
                if pid in base_map:
                    out_list.append(base_map[pid])
            for pid in appended:
                if pid in deleted:
                    continue
                if pid in base_map and pid not in base_order:
                    out_list.append(base_map[pid])
            return out_list

        return patch

    return patch


# === NoemaForge Autodoc Function Header ===
# Function: policy_lock_state(path: str = DEFAULT_POLICY_LOCK)
# Purpose: Implement the routine 'policy lock state'.
# Inputs:
#   - path: str = DEFAULT_POLICY_LOCK
# Called by:
#   - src/brainctl.py
# Calls:
#   - strip, read, open
# Returns / emits: str
# Side effects:
#   - reads or writes files
# === End NoemaForge Autodoc Function Header ===
def policy_lock_state(path: str = DEFAULT_POLICY_LOCK) -> str:
    try:
        return open(path, "r", encoding="utf-8").read().strip() or "LOCKED"
    except Exception:
        return "LOCKED"


# === NoemaForge Autodoc Function Header ===
# Function: set_policy_lock(state: str, path: str = DEFAULT_POLICY_LOCK)
# Purpose: Implement the routine 'set policy lock'.
# Inputs:
#   - state: str
#   - path: str = DEFAULT_POLICY_LOCK
# Called by:
#   - src/brainctl.py
# Calls:
#   - makedirs, chmod, dirname, open, write, upper, strip
# Returns / emits: None
# Side effects:
#   - reads or writes files
#   - creates directories
# Key locals:
#   - f
# === End NoemaForge Autodoc Function Header ===
def set_policy_lock(state: str, path: str = DEFAULT_POLICY_LOCK) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(state.strip().upper() + "\n")
    os.chmod(path, 0o600)


# === NoemaForge Autodoc Function Header ===
# Function: read_mode(path: str = DEFAULT_MODE_FILE)
# Purpose: Implement the routine 'read mode'.
# Inputs:
#   - path: str = DEFAULT_MODE_FILE
# Called by:
#   - src/brainctl.py
# Calls:
#   - lower, strip, read, open
# Returns / emits: str
# Side effects:
#   - reads or writes files
# === End NoemaForge Autodoc Function Header ===
def read_mode(path: str = DEFAULT_MODE_FILE) -> str:
    try:
        return open(path, "r", encoding="utf-8").read().strip().lower() or "unknown"
    except Exception:
        return "unknown"


# === NoemaForge Autodoc Function Header ===
# Function: epochs_dir(contracts_root: str = DEFAULT_CONTRACTS_ROOT)
# Purpose: Implement the routine 'epochs dir'.
# Inputs:
#   - contracts_root: str = DEFAULT_CONTRACTS_ROOT
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - join
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def epochs_dir(contracts_root: str = DEFAULT_CONTRACTS_ROOT) -> str:
    return os.path.join(contracts_root, "epochs")


# === NoemaForge Autodoc Function Header ===
# Function: epoch_path(epoch_id: str, contracts_root: str = DEFAULT_CONTRACTS_ROOT)
# Purpose: Implement the routine 'epoch path'.
# Inputs:
#   - epoch_id: str
#   - contracts_root: str = DEFAULT_CONTRACTS_ROOT
# Called by:
#   - src/brainctl.py
#   - src/firstboot_eval.py
#   - src/llm_backends_manager.py
# Calls:
#   - join, epochs_dir
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def epoch_path(epoch_id: str, contracts_root: str = DEFAULT_CONTRACTS_ROOT) -> str:
    return os.path.join(epochs_dir(contracts_root), epoch_id)


# === NoemaForge Autodoc Function Header ===
# Function: current_epoch_id(contracts_root: str = DEFAULT_CONTRACTS_ROOT)
# Purpose: Implement the routine 'current epoch id'.
# Inputs:
#   - contracts_root: str = DEFAULT_CONTRACTS_ROOT
# Called by:
#   - src/bootdoctor.py
#   - src/brainctl.py
#   - src/caps.py
#   - src/epoch.py
#   - src/firstboot_eval.py
#   - src/llm_backends_manager.py
#   - src/scary_sweep.py
#   - src/sr_cycle.py
# Calls:
#   - join, exists, epochs_dir, strip, basename, realpath, read, open
# Returns / emits: str
# Side effects:
#   - reads or writes files
# Key locals:
#   - p_cur, p_txt, v
# === End NoemaForge Autodoc Function Header ===
def current_epoch_id(contracts_root: str = DEFAULT_CONTRACTS_ROOT) -> str:
    p_txt = os.path.join(epochs_dir(contracts_root), "current_epoch.txt")
    try:
        if os.path.exists(p_txt):
            v = open(p_txt, "r", encoding="utf-8").read().strip()
            return v or "00000"
    except Exception:
        pass
    p_cur = os.path.join(epochs_dir(contracts_root), "current")
    if os.path.exists(p_cur):
        try:
            return os.path.basename(os.path.realpath(p_cur))
        except Exception:
            pass
    return "00000"


# === NoemaForge Autodoc Function Header ===
# Function: list_epochs(contracts_root: str = DEFAULT_CONTRACTS_ROOT)
# Purpose: Implement the routine 'list epochs'.
# Inputs:
#   - contracts_root: str = DEFAULT_CONTRACTS_ROOT
# Called by:
#   - src/brainctl.py
# Calls:
#   - epochs_dir, listdir, sort, isdir, join, endswith, append
# Returns / emits: List[str]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - d, name, out, p
# === End NoemaForge Autodoc Function Header ===
def list_epochs(contracts_root: str = DEFAULT_CONTRACTS_ROOT) -> List[str]:
    d = epochs_dir(contracts_root)
    if not os.path.isdir(d):
        return []
    out: List[str] = []
    for name in os.listdir(d):
        if name in ("current",) or name.endswith(".txt"):
            continue
        p = os.path.join(d, name)
        if os.path.isdir(p):
            out.append(name)
    out.sort()
    return out


# === NoemaForge Autodoc Function Header ===
# Function: next_epoch_id(contracts_root: str = DEFAULT_CONTRACTS_ROOT)
# Purpose: Implement the routine 'next epoch id'.
# Inputs:
#   - contracts_root: str = DEFAULT_CONTRACTS_ROOT
# Called by:
#   - src/brainctl.py
# Calls:
#   - list_epochs, isdigit, max, append, int
# Returns / emits: str
# Side effects:
#   - appends to logs or files
# Key locals:
#   - e, epochs, n, nums
# === End NoemaForge Autodoc Function Header ===
def next_epoch_id(contracts_root: str = DEFAULT_CONTRACTS_ROOT) -> str:
    epochs = list_epochs(contracts_root)
    nums: List[int] = []
    for e in epochs:
        if e.isdigit():
            try:
                nums.append(int(e))
            except Exception:
                pass
    n = max(nums) + 1 if nums else 1
    return f"{n:05d}"[-5:]


@dataclass
class RequestRecord:
    path: str
    obj: Dict[str, Any]



@dataclass
class ChangeUnit:
    """A minimal atomic change inside a PreStartChangeRequest.

    v0.12.10:
    - One request may contain multiple independent changes ("units").
    - Each unit is canary-tested and may be rolled back without discarding the rest of the request.
    - Unit-level blocklist is persisted into request.audit.blocked_units to prevent infinite retries.
    """

    request_id: str
    unit_key: str            # stable within request (e.g. "tool_policy_patch" or "streams_add:foo.yaml")
    change_key: str          # requested_changes key (e.g. tool_policy_patch / streams_add)
    filename: str            # epoch file path (e.g. "tool-policy.yaml" or "overlays/streams_add")
    kind: str                # "yaml_patch" | "file_add"
    patch_obj: Any
    meta: Dict[str, Any]

# === NoemaForge Autodoc Function Header ===
# Function: load_requests(requests_dir: str = DEFAULT_REQUESTS_DIR)
# Purpose: Implement the routine 'load requests'.
# Inputs:
#   - requests_dir: str = DEFAULT_REQUESTS_DIR
# Called by:
#   - src/brainctl.py
# Calls:
#   - sorted, isdir, listdir, startswith, join, _load_any, append, endswith, RequestRecord
# Returns / emits: List[RequestRecord]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - fn, obj, out, p
# === End NoemaForge Autodoc Function Header ===
def load_requests(requests_dir: str = DEFAULT_REQUESTS_DIR) -> List[RequestRecord]:
    if not os.path.isdir(requests_dir):
        return []
    out: List[RequestRecord] = []
    for fn in sorted(os.listdir(requests_dir)):
        if fn.startswith("."):
            continue
        if not (fn.endswith(".yaml") or fn.endswith(".yml") or fn.endswith(".json")):
            continue
        p = os.path.join(requests_dir, fn)
        try:
            obj = _load_any(p)
            out.append(RequestRecord(path=p, obj=obj))
        except Exception:
            continue
    return out


# === NoemaForge Autodoc Function Header ===
# Function: select_requests_for_build(reqs: List[RequestRecord])
# Purpose: Implement the routine 'select requests for build'.
# Inputs:
#   - reqs: List[RequestRecord]
# Called by:
#   - src/brainctl.py
# Calls:
#   - bool, append, lower, get, str
# Returns / emits: List[RequestRecord]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - aud, out, r
# === End NoemaForge Autodoc Function Header ===
def select_requests_for_build(reqs: List[RequestRecord]) -> List[RequestRecord]:
    out: List[RequestRecord] = []
    for r in reqs:
        if str(r.obj.get("status") or "").lower() != "approved":
            continue
        aud = r.obj.get("audit") or {}
        # Unit-level failures can block a request from being applied again automatically.
        # This avoids infinite retry loops while still preserving the request file for human review.
        if bool((aud or {}).get("block_apply")):
            continue
        out.append(r)
    return out


# === NoemaForge Autodoc Function Header ===
# Function: _request_id(r: RequestRecord)
# Purpose: Implement the routine ' request id'.
# Inputs:
#   - r: RequestRecord
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - str, get, splitext, basename
# Returns / emits: str
# Key locals:
#   - obj
# === End NoemaForge Autodoc Function Header ===
def _request_id(r: RequestRecord) -> str:
    obj = r.obj
    return str(obj.get("request_id") or os.path.splitext(os.path.basename(r.path))[0])


# === NoemaForge Autodoc Function Header ===
# Function: _infer_track(obj: Dict[str, Any])
# Purpose: Infer change track.
# Inputs:
#   - obj: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - strip, any, get, bool, lower, str
# Returns / emits: str
# Key locals:
#   - ch, tr
# === End NoemaForge Autodoc Function Header ===
def _infer_track(obj: Dict[str, Any]) -> str:
    """Infer change track.

    Track is a *pre-start* concept used to enforce when epoch switching is allowed.
    - system: tools/streams/patterns/infra-ish contracts
    - policy: tool-policy/quarantine/affirmations/security law
    - user: comment-only manual snapshot/switch
    """
    tr = str(obj.get("track") or "").lower().strip()
    if tr in ("system", "policy", "user"):
        return tr

    ch = (obj.get("requested_changes") or {})
    # Policy-ish patches
    if any(k in ch for k in (
        "tool_policy_patch",
        "canary_policy_patch",
        "security_fixtures_patch",
        "quarantine_policy_patch",
        "role_affirmations_patch",
        "maintenance_policy_patch",
        "resource_policy_patch",
        "taskqueue_policy_patch",
        "bundle_policy_patch",
        "web_gateway_policy_patch",
        "local_gateway_policy_patch",
        "bootdoctor_policy_patch",
        "installer_policy_patch",
    )):
        return "policy"
    # User snapshot
    if bool(obj.get("user_comment")) and not ch:
        return "user"
    return "system"



# === NoemaForge Autodoc Function Header ===
# Function: _requested_epoch_files(obj: Dict[str, Any])
# Purpose: Map a request into a list of epoch files it intends to mutate.
# Inputs:
#   - obj: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - items, sorted, get, append, list, set
# Returns / emits: List[str]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - ch, m, out
# === End NoemaForge Autodoc Function Header ===
def _requested_epoch_files(obj: Dict[str, Any]) -> List[str]:
    """Map a request into a list of epoch files it intends to mutate.

    v0.12.10: keep this mapping aligned with _apply_request_to_epoch_dir().
    """
    ch = (obj.get("requested_changes") or {})

    # requested_changes key -> epoch file
    m = {
        # Core contracts
        "streams_patch": "streams.yaml",
        "patterns_patch": "patterns.yaml",
        "tool_registry_patch": "tool-registry.yaml",
        "tool_policy_patch": "tool-policy.yaml",
        "sandbox_policy_patch": "sandbox-policy.yaml",
        "supplychain_policy_patch": "supplychain-policy.yaml",
        "bundle_policy_patch": "bundle-policy.yaml",
        "web_gateway_policy_patch": "web-gateway-policy.yaml",
        "local_gateway_policy_patch": "local-gateway-policy.yaml",
        "nids_policy_patch": "nids-policy.yaml",
        "bootdoctor_policy_patch": "bootdoctor.yaml",
        "installer_policy_patch": "installer-policy.yaml",
        "verifiers_patch": "verifiers.yaml",
        "clarifications_patch": "clarifications.yaml",
        "vstore_config_patch": "vstore.yaml",
        "memory_policy_patch": "memory-policy.yaml",

        # Ops + safety
        "maintenance_policy_patch": "maintenance-policy.yaml",
        "resource_policy_patch": "resource-policy.yaml",
        "storage_policy_patch": "storage-policy.yaml",
        "taskqueue_policy_patch": "taskqueue-policy.yaml",
        "canary_policy_patch": "canary-policy.yaml",
        "security_fixtures_patch": "security-fixtures.yaml",
        "quarantine_policy_patch": "quarantine-policy.yaml",
        "incident_policy_patch": "incident-policy.yaml",
        "role_affirmations_patch": "role-affirmations.yaml",
        "role_roadmaps_patch": "role-roadmaps.yaml",

        # Model fleet (epoch-scoped)
        "role_model_policy_patch": "role-model-policy.yaml",
        "model_eval_suite_patch": "model-eval-suite.yaml",
        "llm_backends_policy_patch": "llm-backends-policy.yaml",

        # Flow/team (epoch-scoped)
        "flow_catalog_patch": "flow-catalog.yaml",
        "flow_eval_suite_patch": "flow-eval-suite.yaml",
        "team_eval_policy_patch": "team-eval-policy.yaml",
        "team_model_policy_patch": "team-model-policy.yaml",
    }

    out: List[str] = []
    for k, fname in m.items():
        if ch.get(k) is not None:
            out.append(fname)

    # Best-effort: overlays.
    if (ch.get("streams_add") or []) or (ch.get("patterns_add") or []):
        out.append("overlays/*")

    return sorted(list(set(out)))




# requested_changes key -> epoch file (used for unitization)
_CHANGE_KEY_TO_FILE: Dict[str, str] = {
    # Core contracts
    "streams_patch": "streams.yaml",
    "patterns_patch": "patterns.yaml",
    "tool_registry_patch": "tool-registry.yaml",
    "tool_policy_patch": "tool-policy.yaml",
    "sandbox_policy_patch": "sandbox-policy.yaml",
    "supplychain_policy_patch": "supplychain-policy.yaml",
    "bundle_policy_patch": "bundle-policy.yaml",
    "web_gateway_policy_patch": "web-gateway-policy.yaml",
    "local_gateway_policy_patch": "local-gateway-policy.yaml",
        "nids_policy_patch": "nids-policy.yaml",
    "bootdoctor_policy_patch": "bootdoctor.yaml",
    "installer_policy_patch": "installer-policy.yaml",
    "verifiers_patch": "verifiers.yaml",
    "clarifications_patch": "clarifications.yaml",
    "vstore_config_patch": "vstore.yaml",
    "memory_policy_patch": "memory-policy.yaml",

    # Ops + safety
    "maintenance_policy_patch": "maintenance-policy.yaml",
    "resource_policy_patch": "resource-policy.yaml",
    "taskqueue_policy_patch": "taskqueue-policy.yaml",
    "canary_policy_patch": "canary-policy.yaml",
    "security_fixtures_patch": "security-fixtures.yaml",
    "quarantine_policy_patch": "quarantine-policy.yaml",
    "incident_policy_patch": "incident-policy.yaml",
    "role_affirmations_patch": "role-affirmations.yaml",
    "role_roadmaps_patch": "role-roadmaps.yaml",

    # Model fleet (epoch-scoped)
    "role_model_policy_patch": "role-model-policy.yaml",
    "model_eval_suite_patch": "model-eval-suite.yaml",
    "llm_backends_policy_patch": "llm-backends-policy.yaml",

    # Flow/team (epoch-scoped)
    "flow_catalog_patch": "flow-catalog.yaml",
    "flow_eval_suite_patch": "flow-eval-suite.yaml",
    "team_eval_policy_patch": "team-eval-policy.yaml",
    "team_model_policy_patch": "team-model-policy.yaml",
}


# === NoemaForge Autodoc Function Header ===
# Function: _request_blocked_units(obj: Dict[str, Any])
# Purpose: Implement the routine ' request blocked units'.
# Inputs:
#   - obj: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - set, get, isinstance, str, strip
# Returns / emits: set[str]
# Key locals:
#   - aud, raw
# === End NoemaForge Autodoc Function Header ===
def _request_blocked_units(obj: Dict[str, Any]) -> set[str]:
    aud = obj.get("audit") or {}
    raw = (aud.get("blocked_units") or [])
    if not isinstance(raw, list):
        return set()
    return set([str(x) for x in raw if str(x).strip()])


# === NoemaForge Autodoc Function Header ===
# Function: _request_record_unit_audit(obj: Dict[str, Any], unit_key: str, status: str, candidate_epoch_id: str, base_epoch_id: str, track: str, fail_reason: str, suites_run: List[Dict[str, Any]])
# Purpose: Append unit-level audit record onto a request object (in-place).
# Inputs:
#   - obj: Dict[str, Any]
#   - unit_key: str
#   - status: str
#   - candidate_epoch_id: str
#   - base_epoch_id: str
#   - track: str
#   - fail_reason: str
#   - suites_run: List[Dict[str, Any]]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - get, append, isinstance, _request_blocked_units, add, sorted, _nowz, list
# Returns / emits: Dict[str, Any]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - aud, blocked, recs
# === End NoemaForge Autodoc Function Header ===
def _request_record_unit_audit(
    *,
    obj: Dict[str, Any],
    unit_key: str,
    status: str,
    candidate_epoch_id: str,
    base_epoch_id: str,
    track: str,
    fail_reason: str,
    suites_run: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Append unit-level audit record onto a request object (in-place)."""
    aud = obj.get("audit") or {}
    recs = aud.get("unit_results")
    if not isinstance(recs, list):
        recs = []
    recs.append({
        "unit_key": unit_key,
        "status": status,
        "candidate_epoch_id": candidate_epoch_id,
        "base_epoch_id": base_epoch_id,
        "track": track,
        "at": _nowz(),
        "fail_reason": fail_reason,
        "suites_run": suites_run,
    })
    aud["unit_results"] = recs

    # Block unit on rollback to avoid infinite loops.
    if status in ("rolled_back", "failed"):
        blocked = _request_blocked_units(obj)
        blocked.add(unit_key)
        aud["blocked_units"] = sorted(list(blocked))

    obj["audit"] = aud
    return obj


# === NoemaForge Autodoc Function Header ===
# Function: _extract_change_units(req: RequestRecord)
# Purpose: Extract unit-level atomic changes from a request.
# Inputs:
#   - req: RequestRecord
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _request_id, _request_blocked_units, items, get, append, ChangeUnit, isinstance, strip, basename, str
# Returns / emits: List[ChangeUnit]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - add_key, blocked, bn, ch, obj, pth, raw, rid, sp, unit_key, units
# === End NoemaForge Autodoc Function Header ===
def _extract_change_units(req: RequestRecord) -> List[ChangeUnit]:
    """Extract unit-level atomic changes from a request."""
    obj = req.obj
    rid = _request_id(req)
    ch = (obj.get("requested_changes") or {})
    blocked = _request_blocked_units(obj)

    units: List[ChangeUnit] = []

    # YAML patch units (1 key = 1 epoch file).
    for ck, fname in _CHANGE_KEY_TO_FILE.items():
        if ch.get(ck) is None:
            continue
        unit_key = ck
        if unit_key in blocked:
            continue
        units.append(
            ChangeUnit(
                request_id=rid,
                unit_key=unit_key,
                change_key=ck,
                filename=fname,
                kind="yaml_patch",
                patch_obj=ch.get(ck),
                meta={},
            )
        )

    # Overlay file adds are separate units per file path.
    for add_key in ("streams_add", "patterns_add"):
        raw = (ch.get(add_key) or []) or []
        if not isinstance(raw, list):
            continue
        for pth in raw:
            sp = str(pth or "").strip()
            if not sp:
                continue
            bn = os.path.basename(sp)
            unit_key = f"{add_key}:{bn}"
            if unit_key in blocked:
                continue
            units.append(
                ChangeUnit(
                    request_id=rid,
                    unit_key=unit_key,
                    change_key=add_key,
                    filename=f"overlays/{add_key}",
                    kind="file_add",
                    patch_obj=sp,
                    meta={"src": sp, "basename": bn},
                )
            )

    return units


# === NoemaForge Autodoc Function Header ===
# Function: _apply_change_unit_to_epoch_dir(cand_dir: str, unit: ChangeUnit)
# Purpose: Apply a single unit to cand_dir. Returns touched files (best-effort).
# Inputs:
#   - cand_dir: str
#   - unit: ChangeUnit
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - join, _deep_merge, _save_yaml, append, strip, makedirs, copy2, exists, _load_yaml, str, get
# Returns / emits: List[str]
# Side effects:
#   - creates directories
#   - copies filesystem artifacts
#   - appends to logs or files
# Key locals:
#   - bn, cur, dst_dir, nxt, p, src, touched
# === End NoemaForge Autodoc Function Header ===
def _apply_change_unit_to_epoch_dir(cand_dir: str, unit: ChangeUnit) -> List[str]:
    """Apply a single unit to cand_dir. Returns touched files (best-effort)."""
    touched: List[str] = []

    if unit.kind == "yaml_patch":
        p = os.path.join(cand_dir, unit.filename)
        cur = _load_yaml(p) if os.path.exists(p) else {}
        nxt = _deep_merge(cur, unit.patch_obj)
        _save_yaml(p, nxt)
        touched.append(unit.filename)
        return touched

    if unit.kind == "file_add":
        src = str(unit.meta.get("src") or "").strip()
        bn = str(unit.meta.get("basename") or "").strip()
        if not src or not bn:
            return touched
        if not os.path.exists(src):
            return touched
        dst_dir = os.path.join(cand_dir, "overlays", unit.change_key)
        os.makedirs(dst_dir, exist_ok=True)
        shutil.copy2(src, os.path.join(dst_dir, bn))
        touched.append(unit.filename)
        return touched

    return touched


# === NoemaForge Autodoc Function Header ===
# Function: _unit_required_suites(law_dir: str, law_policy: Dict[str, Any], track: str, unit: ChangeUnit, risk_level: str, requires_canary: str, request_obj: Dict[str, Any])
# Purpose: Compute ordered list of canary suites for a change unit.
# Inputs:
#   - law_dir: str
#   - law_policy: Dict[str, Any]
#   - track: str
#   - unit: ChangeUnit
#   - risk_level: str
#   - requires_canary: str
#   - request_obj: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - scary_min_suite_for_request, get, sorted, isinstance, strip, bool, append, list, fromkeys, lower, set, str
# Returns / emits: List[str]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - cur, extra, mf, min_suite, mk, plan, requested_files, rmin, rule, rules, s, s1
# === End NoemaForge Autodoc Function Header ===
def _unit_required_suites(
    *,
    law_dir: str,
    law_policy: Dict[str, Any],
    track: str,
    unit: ChangeUnit,
    risk_level: str,
    requires_canary: str,
    request_obj: Dict[str, Any],
) -> List[str]:
    """Compute ordered list of canary suites for a change unit."""

    # Only epoch file names influence default suite rules.
    requested_files = [unit.filename] if unit.filename in EPOCH_FILES else []

    min_suite = scary_min_suite_for_request(
        law_epoch_dir=law_dir,
        track=track,
        requested_files=requested_files,
        risk_level=risk_level,
        requires_canary=requires_canary,
    )

    # Requested suite list (ordered). Allows 1+ canaries per change.
    suites_req = request_obj.get("canary_suites")
    suites: List[str] = []
    if isinstance(suites_req, list) and suites_req:
        suites = [str(x).lower().strip() for x in suites_req if str(x).strip()]
    else:
        plan = request_obj.get("canary_plan") or {}
        s1 = str(plan.get("suite") or requires_canary or "auto").lower().strip()
        suites = [s1] if s1 else ["auto"]

    # Normalize/upgrade.
    suites = [min_suite if s in ("", "auto") else s for s in suites]
    suites = [s for s in suites if s in ("smoke", "full")]
    if not suites:
        suites = [min_suite]

    # Optional policy hook: per-unit upgrades (law epoch).
    # This is deliberately minimal: the request should not be able to weaken the law.
    cur = (law_policy.get("change_unit_rules") or {}) if isinstance(law_policy, dict) else {}
    if isinstance(cur, dict) and bool(cur.get("enabled", False)):
        rules = cur.get("rules") or []
        if isinstance(rules, list):
            for rule in rules:
                if not isinstance(rule, dict):
                    continue
                mk = set([str(x) for x in (rule.get("match_change_keys_any") or []) if str(x).strip()])
                mf = set([str(x) for x in (rule.get("match_files_any") or []) if str(x).strip()])
                if mk and unit.change_key not in mk:
                    continue
                if mf and unit.filename not in mf:
                    continue
                rmin = str(rule.get("min_suite") or "").lower().strip()
                if rmin in ("smoke", "full"):
                    # Scary must not downgrade below computed min_suite
                    if min_suite == "full" or rmin == "full":
                        min_suite = "full"
                    else:
                        min_suite = rmin
                extra = rule.get("extra_suites") or []
                if isinstance(extra, list):
                    for s in extra:
                        ss = str(s).lower().strip()
                        if ss in ("smoke", "full"):
                            suites.append(ss)

    # Scary must not downgrade.
    if min_suite == "full" and "full" not in suites:
        suites.append("full")

    # Prefer smoke before full.
    suites = sorted(list(dict.fromkeys(suites)), key=lambda x: 0 if x == "smoke" else 1)

    return suites

# === NoemaForge Autodoc Function Header ===
# Function: _notify(role_id: str, payload: Dict[str, Any], notifications_dir: str = DEFAULT_NOTIFICATIONS_DIR)
# Purpose: Write a simple file-based notification.
# Inputs:
#   - role_id: str
#   - payload: Dict[str, Any]
#   - notifications_dir: str = DEFAULT_NOTIFICATIONS_DIR
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - strftime, join, makedirs, _save_json, strip, utcnow, uuid4
# Returns / emits: str
# Side effects:
#   - creates directories
# Key locals:
#   - nid, out_dir, path, role_id, ts
# === End NoemaForge Autodoc Function Header ===
def _notify(role_id: str, payload: Dict[str, Any], notifications_dir: str = DEFAULT_NOTIFICATIONS_DIR) -> str:
    """Write a simple file-based notification.

    This seed kit is offline-first and avoids any external dependencies.
    Consumers may tail/poll these directories.
    """
    role_id = (role_id or "unknown").strip() or "unknown"
    ts = dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    nid = f"{ts}-{uuid.uuid4().hex[:10]}"
    out_dir = os.path.join(notifications_dir, role_id)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{nid}.json")
    _save_json(path, payload)
    return path


# === NoemaForge Autodoc Function Header ===
# Function: _allowed_patch_authors()
# Purpose: Implement the routine ' allowed patch authors'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Returns / emits: set[str]
# === End NoemaForge Autodoc Function Header ===
def _allowed_patch_authors() -> set[str]:
    # Runtime requests can propose NEEDS, but patches that mutate contracts must be authored by:
    # human / surgeon / scary / system.
    return {"human", "surgeon", "scary", "system"}


# === NoemaForge Autodoc Function Header ===
# Function: ensure_epoch_initialized(config_dir: str = '/opt/noemaforge/configs', contracts_root: str = DEFAULT_CONTRACTS_ROOT)
# Purpose: Create epoch 00001 from /opt/noemaforge/configs if no epochs exist.
# Inputs:
#   - config_dir: str = '/opt/noemaforge/configs'
#   - contracts_root: str = DEFAULT_CONTRACTS_ROOT
# Called by:
#   - src/brainctl.py
# Calls:
#   - makedirs, list_epochs, epoch_path, build_epoch_manifest, _save_json, join, epochs_dir, current_epoch_id, get, symlink, open, write
# Returns / emits: str
# Side effects:
#   - reads or writes files
#   - creates directories
# Key locals:
#   - cur_link, dst, eid, ep, f, man, manifest, mapping, missing, name, src
# === End NoemaForge Autodoc Function Header ===
def ensure_epoch_initialized(config_dir: str = "/opt/noemaforge/configs", contracts_root: str = DEFAULT_CONTRACTS_ROOT) -> str:
    """Create epoch 00001 from /opt/noemaforge/configs if no epochs exist."""
    os.makedirs(epochs_dir(contracts_root), exist_ok=True)
    if list_epochs(contracts_root):
        # Upgrade-safe: if new epoch files were added in a newer seed-kit,
        # backfill missing files into the CURRENT epoch and rebuild its manifest.
        eid = current_epoch_id(contracts_root)
        ep = epoch_path(eid, contracts_root)

        missing: List[str] = []
        mapping = {name: os.path.join(config_dir, name) for name in EPOCH_FILES}

        for name in EPOCH_FILES:
            dst = os.path.join(ep, name)
            if os.path.exists(dst):
                continue
            src = mapping.get(name)
            if src and os.path.exists(src):
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)
                missing.append(name)
                continue

            # Safe defaults for new files (keep conservative)
            if name == "lsm-policy.yaml":
                _save_yaml(dst, {
                    "apiVersion": "noemaforge.lsm/v1",
                    "kind": "LSMPPolicy",
                    "require": {"mode": "prefer", "fail_closed": False},
                    "apparmor": {"enabled": True, "enforce": False, "profiles": {}},
                    "selinux": {"enabled": True, "enforce": False, "contexts": {}},
                })
                missing.append(name)

            elif name == "installer-policy.yaml":
                _save_yaml(dst, {
                    "apiVersion": "noemaforge.installer/v1",
                    "kind": "InstallerPolicy",
                    "version": 1,
                    "defaults": {"bundles": [], "apt_baseline": []},
                    "bundle_catalog": {},
                    "hardware_rules": {"pci": []},
                    "output": {"plans_dir": "/var/lib/noemaforge/installer/plans", "outbox_dir": "/workspace/outbox/installer-plan", "keep_plans": 50},
                })
                missing.append(name)

            elif name == "role-model-policy.yaml":
                _save_yaml(dst, {
                    "apiVersion": "noemaforge.rolemodel/v1",
                    "kind": "RoleModelPolicy",
                    "defaults": {
                        "selector": {"strategy": "best_score_then_latency"},
                        "llm": {"fallback_model": "main", "min_trust": "unknown", "require_scorecard": False},
                        "embed": {"fallback_model": "main", "min_trust": "unknown", "require_scorecard": False},
                    },
                    "roles": {
                        "*/*": {"llm": {"candidates": ["main"]}, "embed": {"candidates": ["main"]}},
                        "system.guard/surgeon": {"llm": {"candidates": ["main"], "allow_explicit": True}, "embed": {"candidates": ["main"], "allow_explicit": True}},
                    },
                })
                missing.append(name)

            elif name == "model-eval-suite.yaml":
                _save_yaml(dst, {
                    "apiVersion": "noemaforge.modeleval/v1",
                    "kind": "ModelEvalSuite",
                    "suites": {
                        "smoke": {"cases": {"llm": [{"id": "json_min", "messages": [{"role": "system", "content": "Return valid JSON only."}, {"role": "user", "content": "Return {\\\"ok\\\": true}."}], "expect": {"json": True}}]}},
                        "full": {"cases": {"llm": []}},
                    },
                })
                missing.append(name)

            elif name == "maintenance-policy.yaml":
                _save_yaml(dst, {
                    "apiVersion": "noemaforge.maintenance/v1",
                    "kind": "MaintenancePolicy",
                    "idle_trigger_sec": 300,
                    "sr": {"max_events_scan": 600},
                    "daily_sla": {"timezone": "Europe/Lisbon", "fallback_mean_sec": 1800, "fallback_sigma_sec": 600},
                    "recovery": {"max_work_age_sec": 3600, "max_token_age_sec": 86400},
                    "dispatch": {"domain_cycle": ["WORK", "SELF_IMPROVE", "SECURITY", "PLANNED"]},
                })
                missing.append(name)

        if missing:
            # Rebuild manifest in-place (epoch ID stays the same).
            try:
                man = build_epoch_manifest(ep, eid, description=f"migration: add missing files {missing}", base_epoch_id=eid)
                _save_json(os.path.join(ep, "epoch_manifest.json"), man)
            except Exception:
                pass

        return eid

    eid = "00001"
    ep = epoch_path(eid, contracts_root)
    os.makedirs(ep, exist_ok=True)

    mapping = {name: os.path.join(config_dir, name) for name in EPOCH_FILES}

    for name in EPOCH_FILES:
        src = mapping.get(name)
        dst = os.path.join(ep, name)
        if src and os.path.exists(src):
            shutil.copy2(src, dst)
        else:
            # Safe defaults
            if name == "patterns.yaml":
                _save_yaml(dst, {"apiVersion": "noemaforge.patterns/v1", "kind": "PatternCatalog", "patterns": {}})
            elif name == "lsm-policy.yaml":
                _save_yaml(dst, {
                    "apiVersion": "noemaforge.lsm/v1",
                    "kind": "LSMPPolicy",
                    "require": {"mode": "prefer", "fail_closed": False},
                    "apparmor": {"enabled": True, "enforce": False, "profiles": {}},
                    "selinux": {"enabled": True, "enforce": False, "contexts": {}},
                })
            elif name == "verifiers.yaml":
                _save_yaml(dst, {"apiVersion": "noemaforge.verifiers/v1", "kind": "VerifierCatalog", "verifiers": {}})
            elif name == "vstore.yaml":
                _save_yaml(dst, {"apiVersion": "noemaforge.vstore/v1", "kind": "VStoreConfig", "layers": {}})
            elif name == "maintenance-policy.yaml":
                _save_yaml(dst, {
                    "apiVersion": "noemaforge.maintenance/v1",
                    "kind": "MaintenancePolicy",
                    "idle_trigger_sec": 300,
                    "sr": {"max_events_scan": 600},
                    "daily_sla": {"timezone": "Europe/Lisbon", "fallback_mean_sec": 1800, "fallback_sigma_sec": 600},
                    "recovery": {"max_work_age_sec": 3600, "max_token_age_sec": 86400},
                    "dispatch": {"domain_cycle": ["WORK", "SELF_IMPROVE", "SECURITY", "PLANNED"]},
                })
            elif name == "canary-policy.yaml":
                _save_yaml(dst, {"apiVersion": "noemaforge.canary/v1", "kind": "CanaryPolicy", "suites": {"smoke": {"tests": ["manifest_integrity", "static_consistency"]}}, "quota_profiles": {"smoke": {"timeout_sec": 180}}})
            elif name == "security-fixtures.yaml":
                _save_yaml(dst, {"apiVersion": "noemaforge.security/v1", "kind": "SecurityFixtures", "fixtures": []})
            elif name == "quarantine-policy.yaml":
                _save_yaml(
                    dst,
                    {
                        "apiVersion": "noemaforge.security/v1",
                        "kind": "QuarantinePolicy",
                        "enabled": True,
                        "paths": {"quarantine_root": "/var/lib/noemaforge/quarantine/incidents", "role_runs_root": "/workspace/role-runs"},
                        "redaction": {"enabled": True, "debug_roles": ["pm", "surgeon", "scary", "sr", "ssr", "system"], "user_error_denied": "denied", "user_error_quarantine": "quarantine", "user_error_error": "error"},
                        "quarantine_on_denies": ["epoch_mismatch", "issued_to_mismatch", "cap_missing", "policy_deny"],
                        "arg_rules": [],
                        "snapshot": {"capture_request": True, "capture_role_context": True, "capture_file_metadata": True, "max_inline_bytes": 200000, "max_file_sample_bytes": 4096},
                    },
                )
            elif name == "role-affirmations.yaml":
                _save_yaml(
                    dst,
                    {
                        "apiVersion": "noemaforge.roles/v1",
                        "kind": "RoleAffirmations",
                        "default": {"title": "Executor", "affirmation": "I am part of NoemaForge.", "rules": ["Follow policy."]},
                        "roles": {},
                    },
                )
            elif name == "bootdoctor.yaml":
                _save_yaml(dst, {
                    "apiVersion": "noemaforge.bootdoctor/v1",
                    "kind": "BootDoctorPolicy",
                    "enabled": True,
                    "report": {
                        "reports_dir": "/var/lib/noemaforge/boot/reports",
                        "onfailure_dir": "/var/lib/noemaforge/boot/onfailure",
                        "outbox_reports_dir": "/workspace/outbox/bootreports",
                        "outbox_support_dir": "/workspace/outbox/support",
                        "keep_reports": 50,
                        "keep_support_bundles": 20
                    },
                    "collection": {
                        "level": "auto",
                        "journal_lines_boot": 1200,
                        "journal_lines_per_unit": 400,
                        "dmesg_lines": 500
                    },
                    "failure_policy": {
                        "watch_units": ["noemaforge-llm-gateway.service", "noemaforge-toolproxy.service", "noemaforge-memsentinel.service"],
                        "bundle_on_failed_units": True,
                        "onfailure_collect_unit_journal_lines": 900
                    },
                    "first_run": {"force_full": True, "state_file": "/var/lib/noemaforge/.sys/bootdoctor-state.json"},
                    "redaction": {"enabled": True, "patterns": []}
                })
            elif name == "installer-policy.yaml":
                _save_yaml(
                    dst,
                    {
                        "apiVersion": "noemaforge.installer/v1",
                        "kind": "InstallerPolicy",
                        "version": 1,
                        "defaults": {"bundles": [], "apt_baseline": []},
                        "bundle_catalog": {},
                        "hardware_rules": {"pci": []},
                        "output": {"plans_dir": "/var/lib/noemaforge/installer/plans", "outbox_dir": "/workspace/outbox/installer-plan", "keep_plans": 50},
                    },
                )
            elif name == "supplychain-policy.yaml":
                _save_yaml(
                    dst,
                    {
                        "apiVersion": "noemaforge.supplychain/v1",
                        "kind": "SupplyChainPolicy",
                        "enabled": True,
                        "tool_vault": {
                            "root": "/var/lib/noemaforge/toolvault",
                            "manifests_dir": "/var/lib/noemaforge/toolvault/manifests",
                            "artifacts_dir": "/var/lib/noemaforge/toolvault/artifacts",
                        },
                        "enforcement": {
                            "require_attestation_for_enabled_risks": ["high", "critical"],
                            "require_attestation_for_handlers": ["sandbox_exec", "blender", "ffmpeg", "colmap", "slicer", "git"],
                            "fail_in_full_suite": True,
                            "warn_in_smoke_suite": True,
                        },
                    },
                )
            elif name == "role-model-policy.yaml":
                _save_yaml(
                    dst,
                    {
                        "apiVersion": "noemaforge.rolemodel/v1",
                        "kind": "RoleModelPolicy",
                        "defaults": {
                            "selector": {"strategy": "best_score_then_latency"},
                            "llm": {"fallback_model": "main", "min_trust": "unknown", "require_scorecard": False},
                            "embed": {"fallback_model": "main", "min_trust": "unknown", "require_scorecard": False},
                        },
                        "roles": {
                            "*/*": {"llm": {"candidates": ["main"]}, "embed": {"candidates": ["main"]}},
                            "system.guard/surgeon": {"llm": {"candidates": ["main"], "allow_explicit": True}, "embed": {"candidates": ["main"], "allow_explicit": True}},
                        },
                    },
                )
            elif name == "model-eval-suite.yaml":
                _save_yaml(
                    dst,
                    {
                        "apiVersion": "noemaforge.modeleval/v1",
                        "kind": "ModelEvalSuite",
                        "suites": {
                            "smoke": {"cases": {"llm": [{"id": "json_min", "messages": [{"role": "system", "content": "Return valid JSON only."}, {"role": "user", "content": "Return {\\\"ok\\\": true}."}], "expect": {"json": True}}]}},
                            "full": {"cases": {"llm": []}},
                        },
                    },
                )
            else:
                _save_yaml(dst, {})

    manifest = build_epoch_manifest(epoch_id=eid, base_epoch_id="00000", epoch_dir=ep, created_by={"actor_type": "system", "channel": "bootstrap"}, status="current")
    _save_json(os.path.join(ep, "epoch_manifest.json"), manifest)

    # Set current
    cur_link = os.path.join(epochs_dir(contracts_root), "current")
    try:
        if os.path.islink(cur_link) or os.path.exists(cur_link):
            os.remove(cur_link)
        os.symlink(ep, cur_link)
    except Exception:
        pass
    with open(os.path.join(epochs_dir(contracts_root), "current_epoch.txt"), "w", encoding="utf-8") as f:
        f.write(eid + "\n")

    return eid



# === NoemaForge Autodoc Function Header ===
# Function: _manifest_bundle_key(filename: str)
# Purpose: Implement the routine ' manifest bundle key'.
# Inputs:
#   - filename: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - strip, endswith, str, replace, len
# Returns / emits: str
# Key locals:
#   - stem, suf
# === End NoemaForge Autodoc Function Header ===
def _manifest_bundle_key(filename: str) -> str:
    stem = str(filename or "").strip()
    for suf in (".yaml", ".yml", ".json"):
        if stem.endswith(suf):
            stem = stem[: -len(suf)]
            break
    stem = stem.replace("-", "_").replace(".", "_").strip("_")
    return f"{stem}_sha256"


# === NoemaForge Autodoc Function Header ===
# Function: build_epoch_manifest(epoch_id: str, base_epoch_id: str, epoch_dir: str, created_by: Optional[Dict[str, Any]] = None, status: str = 'candidate', description: str = '', notes: Optional[List[str]] = None)
# Purpose: Build a content-addressed manifest for an epoch directory.
# Inputs:
#   - epoch_id: str
#   - base_epoch_id: str
#   - epoch_dir: str
#   - created_by: Optional[Dict[str, Any]] = None
#   - status: str = 'candidate'
#   - description: str = ''
#   - notes: Optional[List[str]] = None
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - encode, hexdigest, join, _sha256_file, sha, _nowz, exists, _manifest_bundle_key, dumps, sha256
# Returns / emits: Dict[str, Any]
# Side effects:
#   - serializes structured data
# Key locals:
#   - bundle, fname, man, p, raw
# === End NoemaForge Autodoc Function Header ===
def build_epoch_manifest(
    *,
    epoch_id: str,
    base_epoch_id: str,
    epoch_dir: str,
    created_by: Optional[Dict[str, Any]] = None,
    status: str = "candidate",
    description: str = "",
    notes: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Build a content-addressed manifest for an epoch directory.

    v0.12.10:
    - Bundle covers *all* EPOCH_FILES (previously only a subset).
    - Backward-compatible: verify_epoch_manifest only enforces hashes that exist in the manifest.
    """
    bundle: Dict[str, Any] = {}

    # === NoemaForge Autodoc Function Header ===
    # Function: sha(name: str)
    # Purpose: Implement the routine 'sha'.
    # Inputs:
    #   - name: str
    # Called by:
    #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
    # Calls:
    #   - join, _sha256_file, exists
    # Returns / emits: str
    # Key locals:
    #   - p
    # === End NoemaForge Autodoc Function Header ===
    def sha(name: str) -> str:
        p = os.path.join(epoch_dir, name)
        if not os.path.exists(p):
            return ""
        return _sha256_file(p)

    for fname in EPOCH_FILES:
        bundle[_manifest_bundle_key(fname)] = sha(fname)

    if notes:
        bundle["notes"] = notes

    man: Dict[str, Any] = {
        "schema_version": "v1",
        "epoch_id": epoch_id,
        "status": status,
        "created_at": _nowz(),
        "base_epoch_id": base_epoch_id,
        "created_by": created_by or {"actor_type": "system", "channel": "unknown"},
        "description": description,
        "bundle": bundle,
    }

    raw = json.dumps(man, sort_keys=True, ensure_ascii=False).encode("utf-8")
    man["overall_sha256"] = hashlib.sha256(raw).hexdigest()
    return man



# === NoemaForge Autodoc Function Header ===
# Function: verify_epoch_manifest(epoch_dir: str)
# Purpose: Verify epoch_manifest.json integrity against file hashes.
# Inputs:
#   - epoch_dir: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - join, str, dict, pop, encode, hexdigest, exists, load, append, get, _manifest_bundle_key, _sha256_file
# Returns / emits: Tuple[bool, List[str]]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - bundle, calc, expected, fname, fp, got, key, man, man2, overall, p, problems
# === End NoemaForge Autodoc Function Header ===
def verify_epoch_manifest(epoch_dir: str) -> Tuple[bool, List[str]]:
    """Verify epoch_manifest.json integrity against file hashes.

    v0.12.10:
    - Checks all EPOCH_FILES but only enforces hash matches when the manifest contains a non-empty expected hash.
      This keeps compatibility with older manifests that didn't include all bundle keys.
    """
    problems: List[str] = []
    p = os.path.join(epoch_dir, "epoch_manifest.json")
    if not os.path.exists(p):
        return False, ["missing_epoch_manifest"]
    try:
        man = json.load(open(p, "r", encoding="utf-8"))
    except Exception as e:
        return False, [f"bad_epoch_manifest:{e!r}"]

    # Verify overall hash
    overall = str(man.get("overall_sha256") or "")
    man2 = dict(man)
    man2.pop("overall_sha256", None)
    raw = json.dumps(man2, sort_keys=True, ensure_ascii=False).encode("utf-8")
    calc = hashlib.sha256(raw).hexdigest()
    if overall and overall != calc:
        problems.append("manifest_overall_hash_mismatch")

    bundle = man.get("bundle") or {}

    for fname in EPOCH_FILES:
        key = _manifest_bundle_key(fname)
        expected = str(bundle.get(key) or "")
        fp = os.path.join(epoch_dir, fname)
        if not os.path.exists(fp):
            problems.append(f"manifest_missing_file:{fname}")
            continue
        got = _sha256_file(fp)
        if expected and expected != got:
            problems.append(f"manifest_file_hash_mismatch:{fname}")

    return (len(problems) == 0), problems


# === NoemaForge Autodoc Function Header ===
# Function: static_checks(epoch_dir: str)
# Purpose: Static checks for a candidate epoch.
# Inputs:
#   - epoch_dir: str
# Called by:
#   - src/brainctl.py
# Calls:
#   - items, _load_yaml, str, get, join, exists, _lsm_static_check, len, append, set, isinstance, keys
# Returns / emits: Tuple[bool, List[str]]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - act, allow, cands, cap, caprec, known_roles, mes, mes_path, ok, pol, pol_streams, problems
# === End NoemaForge Autodoc Function Header ===
def static_checks(epoch_dir: str) -> Tuple[bool, List[str]]:
    """Static checks for a candidate epoch.

    - tool-policy allow actions must exist in tool-registry
    - streams listed in tool-policy must exist in streams.yaml

    Returns (ok, problems).
    """
    problems: List[str] = []
    try:
        streams = _load_yaml(os.path.join(epoch_dir, "streams.yaml"))
        pol = _load_yaml(os.path.join(epoch_dir, "tool-policy.yaml"))
        reg = _load_yaml(os.path.join(epoch_dir, "tool-registry.yaml"))
    except Exception as e:
        return False, [f"failed_to_load_contracts:{e!r}"]

    reg_actions = {str(t.get("id") or "") for t in (reg.get("tools") or [])}

    pol_streams = (pol.get("streams") or {})
    stream_defs = (streams.get("streams") or {})

    for sid, srec in pol_streams.items():
        if sid not in stream_defs:
            problems.append(f"policy_stream_unknown:{sid}")
        roles = ((srec or {}).get("roles") or {})
        for rid, rrec in roles.items():
            allow = set((rrec or {}).get("allow") or [])
            for act in allow:
                if act not in reg_actions:
                    problems.append(f"policy_action_unknown:{sid}:{rid}:{act}")

    # RoleModelPolicy sanity (epoch-scoped)
    try:
        rmp_path = os.path.join(epoch_dir, "role-model-policy.yaml")
        if os.path.exists(rmp_path):
            rmp = _load_yaml(rmp_path)
            if not isinstance(rmp, dict) or str(rmp.get("kind") or "") != "RoleModelPolicy":
                problems.append("role_model_policy_invalid_kind")

            roles_map = rmp.get("roles") or {}
            if not isinstance(roles_map, dict):
                problems.append("role_model_policy_roles_not_map")
            else:
                known_roles: set[str] = set()
                for sid, srec in pol_streams.items():
                    roles = ((srec or {}).get("roles") or {})
                    for rid in roles.keys():
                        known_roles.add(f"{sid}/{rid}")

                for rk, rv in roles_map.items():
                    rk_s = str(rk)
                    if "*" not in rk_s and rk_s not in known_roles:
                        problems.append(f"role_model_policy_unknown_role:{rk_s}")
                    if not isinstance(rv, dict):
                        problems.append(f"role_model_policy_role_not_map:{rk_s}")
                        continue
                    for cap in ("llm", "embed"):
                        caprec = rv.get(cap)
                        if caprec is None:
                            continue
                        if not isinstance(caprec, dict):
                            problems.append(f"role_model_policy_cap_not_map:{rk_s}:{cap}")
                            continue
                        cands = caprec.get("candidates")
                        if cands is not None and not (isinstance(cands, list) and all(isinstance(x, (str, int, float)) for x in cands)):
                            problems.append(f"role_model_policy_candidates_invalid:{rk_s}:{cap}")
    except Exception as e:
        problems.append(f"role_model_policy_check_exception:{e!r}")

    # ModelEvalSuite sanity (epoch-scoped)
    try:
        mes_path = os.path.join(epoch_dir, "model-eval-suite.yaml")
        if os.path.exists(mes_path):
            mes = _load_yaml(mes_path)
            if not isinstance(mes, dict) or str(mes.get("kind") or "") != "ModelEvalSuite":
                problems.append("model_eval_suite_invalid_kind")
    except Exception as e:
        problems.append(f"model_eval_suite_check_exception:{e!r}")

    # LSM sanity (epoch-scoped)
    try:
        from lsm import static_check as _lsm_static_check
        ok_lsm, rep = _lsm_static_check(epoch_dir)
        if not ok_lsm:
            problems.append("lsm_required_missing_or_disabled")
    except Exception as e:
        # In prefer-mode we do not fail; keep this as a soft signal.
        # Any hard fail should be expressed by policy (require+fail_closed).
        pass

    ok = len(problems) == 0
    return ok, problems



# === NoemaForge Autodoc Function Header ===
# Function: _storage_policy_sanity_check(epoch_dir: str)
# Purpose: Sanity check for storage-policy.yaml (Stage A).
# Inputs:
#   - epoch_dir: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _load_yaml, strip, lower, isinstance, join, append, startswith, get, enumerate, len, str, any
# Returns / emits: Tuple[bool, str, List[str], List[str]]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - al, dflt, fv, mode, mr, ok, origin, pol, problems, ptu, summary, warnings
# === End NoemaForge Autodoc Function Header ===
def _storage_policy_sanity_check(epoch_dir: str) -> Tuple[bool, str, List[str], List[str]]:
    """Sanity check for storage-policy.yaml (Stage A).

    Returns (ok, summary, problems, warnings).
    """
    problems: List[str] = []
    warnings: List[str] = []
    try:
        pol = _load_yaml(os.path.join(epoch_dir, "storage-policy.yaml"))
        if not isinstance(pol, dict) or not pol:
            problems.append("storage-policy:missing_or_empty")
            return False, "storage-policy missing", problems, warnings
        origin = (pol.get("origin") or {}) if isinstance(pol, dict) else {}
        ptu = str(origin.get("device_ptuuid") or "").strip()
        if not ptu:
            warnings.append("storage-policy:origin_ptuuid_empty")
        if ptu == "SETUP_AUTODETECT":
            warnings.append("storage-policy:origin_ptuuid_autodetect")

        fv = (pol.get("foreign_volumes") or {}) if isinstance(pol, dict) else {}
        dflt = str(fv.get("default") or "deny").strip().lower()
        if dflt not in ("deny", "ro"):
            warnings.append("storage-policy:foreign_default_unusual")
        mr = str(fv.get("mount_root") or "/mnt/foreign").strip()
        if not mr.startswith("/"):
            problems.append("storage-policy:mount_root_not_absolute")

        al = fv.get("allowlist") or []
        if al and not isinstance(al, list):
            problems.append("storage-policy:allowlist_not_list")
        # light validate entries
        if isinstance(al, list):
            for i, ent in enumerate(al):
                if not isinstance(ent, dict):
                    problems.append(f"storage-policy:allowlist_entry_not_object:{i}")
                    continue
                mode = str(ent.get("mode") or "ro").strip().lower()
                if mode not in ("ro", "rw"):
                    warnings.append(f"storage-policy:allowlist_mode_unknown:{i}")
                # must have at least one identifier
                if not any(str(ent.get(k) or "").strip() for k in ("uuid", "partuuid", "serial", "name", "path", "ptuuid")):
                    warnings.append(f"storage-policy:allowlist_entry_no_id:{i}")

        ok = len(problems) == 0
        summary = "storage-policy ok" if ok else "storage-policy problems"
        return ok, summary, problems, warnings
    except Exception as e:
        problems.append("storage-policy:exception")
        return False, "storage-policy exception", problems, warnings

# === NoemaForge Autodoc Function Header ===
# Function: _diff_changed_files(base_dir: str, cand_dir: str)
# Purpose: Implement the routine ' diff changed files'.
# Inputs:
#   - base_dir: str
#   - cand_dir: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - join, exists, _sha256_file, append
# Returns / emits: List[str]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - b, bsha, c, changed, csha, name
# === End NoemaForge Autodoc Function Header ===
def _diff_changed_files(base_dir: str, cand_dir: str) -> List[str]:
    changed: List[str] = []
    for name in EPOCH_FILES:
        b = os.path.join(base_dir, name)
        c = os.path.join(cand_dir, name)
        bsha = _sha256_file(b) if os.path.exists(b) else ""
        csha = _sha256_file(c) if os.path.exists(c) else ""
        if bsha != csha:
            changed.append(name)
    return changed


# === NoemaForge Autodoc Function Header ===
# Function: _load_canary_policy(epoch_dir: str)
# Purpose: Implement the routine ' load canary policy'.
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
def _load_canary_policy(epoch_dir: str) -> Dict[str, Any]:
    p = os.path.join(epoch_dir, "canary-policy.yaml")
    return _load_yaml(p) if os.path.exists(p) else {}


# === NoemaForge Autodoc Function Header ===
# Function: _canary_first_run_state(policy: Dict[str, Any])
# Purpose: Return (enabled, state_path, state_dict).
# Inputs:
#   - policy: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - bool, str, get, exists, load, open
# Returns / emits: Tuple[bool, str, Dict[str, Any]]
# Side effects:
#   - reads or writes files
# Key locals:
#   - enabled, fr, st, state_path
# === End NoemaForge Autodoc Function Header ===
def _canary_first_run_state(policy: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
    """Return (enabled, state_path, state_dict)."""
    fr = policy.get("first_run") or {}
    enabled = bool(fr.get("force_full", False))
    state_path = str(fr.get("state_path") or "/var/lib/noemaforge/.sys/canary-first-run.json")
    st: Dict[str, Any] = {}
    if enabled:
        try:
            if os.path.exists(state_path):
                st = json.load(open(state_path, "r", encoding="utf-8"))
        except Exception:
            st = {}
    return enabled, state_path, st


# === NoemaForge Autodoc Function Header ===
# Function: _canary_first_run_needed(policy: Dict[str, Any])
# Purpose: Implement the routine ' canary first run needed'.
# Inputs:
#   - policy: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _canary_first_run_state, bool, get
# Returns / emits: bool
# Side effects:
#   - spawns subprocesses or workers
# === End NoemaForge Autodoc Function Header ===
def _canary_first_run_needed(policy: Dict[str, Any]) -> bool:
    enabled, _path, st = _canary_first_run_state(policy)
    if not enabled:
        return False
    return not bool(st.get("attempted", False))


# === NoemaForge Autodoc Function Header ===
# Function: _canary_first_run_mark(policy: Dict[str, Any], patch: Dict[str, Any])
# Purpose: Implement the routine ' canary first run mark'.
# Inputs:
#   - policy: Dict[str, Any]
#   - patch: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _canary_first_run_state, dict, update, makedirs, dirname, open, dump
# Returns / emits: None
# Side effects:
#   - reads or writes files
#   - serializes structured data
#   - creates directories
#   - spawns subprocesses or workers
# Key locals:
#   - f, st
# === End NoemaForge Autodoc Function Header ===
def _canary_first_run_mark(policy: Dict[str, Any], patch: Dict[str, Any]) -> None:
    enabled, path, st = _canary_first_run_state(policy)
    if not enabled:
        return
    st = dict(st)
    st.update(patch or {})
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(st, f, ensure_ascii=False, indent=2)
    except Exception:
        return


# === NoemaForge Autodoc Function Header ===
# Function: _load_security_fixtures(epoch_dir: str)
# Purpose: Implement the routine ' load security fixtures'.
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
def _load_security_fixtures(epoch_dir: str) -> Dict[str, Any]:
    p = os.path.join(epoch_dir, "security-fixtures.yaml")
    return _load_yaml(p) if os.path.exists(p) else {"fixtures": []}


# === NoemaForge Autodoc Function Header ===
# Function: _load_supplychain_policy(epoch_dir: str)
# Purpose: Implement the routine ' load supplychain policy'.
# Inputs:
#   - epoch_dir: str
# Called by:
#   - src/toolproxy.py
# Calls:
#   - join, exists, _load_yaml
# Returns / emits: Dict[str, Any]
# Key locals:
#   - p
# === End NoemaForge Autodoc Function Header ===
def _load_supplychain_policy(epoch_dir: str) -> Dict[str, Any]:
    p = os.path.join(epoch_dir, "supplychain-policy.yaml")
    if os.path.exists(p):
        try:
            return _load_yaml(p)
        except Exception:
            pass
    # Safe default (law must not be weakenable by omission)
    return {
        "apiVersion": "noemaforge.supplychain/v1",
        "kind": "SupplyChainPolicy",
        "enabled": True,
        "tool_vault": {
            "root": "/var/lib/noemaforge/toolvault",
            "manifests_dir": "/var/lib/noemaforge/toolvault/manifests",
            "artifacts_dir": "/var/lib/noemaforge/toolvault/artifacts",
        },
        "enforcement": {
            "require_attestation_for_enabled_risks": ["high", "critical"],
            "require_attestation_for_handlers": ["plugin", "sandbox_exec", "blender", "ffmpeg", "colmap", "slicer", "git"],
            "fail_in_full_suite": True,
            "warn_in_smoke_suite": True,
        },
        "attestation": {
            "allowed_kinds": ["internal", "system", "bundle"],
            "bundle": {"require_manifest_sha256": True, "require_artifact_sha256": True, "require_artifact_present": True},
            "system": {"require_lock_ref": True, "allowed_lock_kinds": ["apt-snapshot", "nix-derivation", "manual-inventory"]},
        },
    }


# === NoemaForge Autodoc Function Header ===
# Function: _supplychain_attestation_check(cand_epoch_dir: str, law_epoch_dir: str, suite: str)
# Purpose: Supply-chain attestation checks (policy-layer only).
# Inputs:
#   - cand_epoch_dir: str
#   - law_epoch_dir: str
#   - suite: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _load_supplychain_policy, strip, set, bool, isinstance, get, _load_yaml, len, str, join, append, add_problem
# Returns / emits: Tuple[bool, List[str], List[str], Dict[str, Any]]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - allowed_kinds, allowed_lock_kinds, apath, artifact_sha, artifacts_dir, att, att_bundle, att_system, bundle_id, checked, enabled, enf
# === End NoemaForge Autodoc Function Header ===
def _supplychain_attestation_check(
    *,
    cand_epoch_dir: str,
    law_epoch_dir: str,
    suite: str,
) -> Tuple[bool, List[str], List[str], Dict[str, Any]]:
    """Supply-chain attestation checks (policy-layer only).

    Law is taken from law_epoch_dir, not from candidate epoch.
    Candidate may not self-weaken by disabling the check.
    """

    policy = _load_supplychain_policy(law_epoch_dir)
    if not bool(policy.get("enabled", False)):
        return True, [], ["supplychain_disabled_by_law"], {"checked": 0, "failed": 0, "warnings": 1}

    tv = (policy.get("tool_vault") or {}) if isinstance(policy.get("tool_vault"), dict) else {}
    manifests_dir = str(tv.get("manifests_dir") or "").strip()
    artifacts_dir = str(tv.get("artifacts_dir") or "").strip()

    enf = (policy.get("enforcement") or {}) if isinstance(policy.get("enforcement"), dict) else {}
    req_risks = set([str(x).lower().strip() for x in ((enf.get("require_attestation_for_enabled_risks") or []) or [])])
    req_handlers = set([str(x).strip() for x in ((enf.get("require_attestation_for_handlers") or []) or [])])
    fail_in_full = bool(enf.get("fail_in_full_suite", True))
    warn_in_smoke = bool(enf.get("warn_in_smoke_suite", True))

    att = (policy.get("attestation") or {}) if isinstance(policy.get("attestation"), dict) else {}
    allowed_kinds = set([str(x).lower().strip() for x in ((att.get("allowed_kinds") or []) or [])]) or {"internal", "system", "bundle"}

    att_bundle = (att.get("bundle") or {}) if isinstance(att.get("bundle"), dict) else {}
    req_m_sha = bool(att_bundle.get("require_manifest_sha256", True))
    req_a_sha = bool(att_bundle.get("require_artifact_sha256", True))
    req_a_present = bool(att_bundle.get("require_artifact_present", True))

    att_system = (att.get("system") or {}) if isinstance(att.get("system"), dict) else {}
    req_lock = bool(att_system.get("require_lock_ref", True))
    allowed_lock_kinds = set([str(x).lower().strip() for x in ((att_system.get("allowed_lock_kinds") or []) or [])])

    # Load candidate registry
    try:
        reg = _load_yaml(os.path.join(cand_epoch_dir, "tool-registry.yaml"))
    except Exception as e:
        return False, [f"registry_load_failed:{e!r}"], [], {"checked": 0, "failed": 1, "warnings": 0}

    tools = reg.get("tools") or []
    problems: List[str] = []
    warnings: List[str] = []
    checked = 0

    # === NoemaForge Autodoc Function Header ===
    # Function: add_problem(msg: str)
    # Purpose: Implement the routine 'add problem'.
    # Inputs:
    #   - msg: str
    # Called by:
    #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
    # Calls:
    #   - append
    # Returns / emits: None
    # Side effects:
    #   - appends to logs or files
    # === End NoemaForge Autodoc Function Header ===
    def add_problem(msg: str) -> None:
        if suite == "full" and fail_in_full:
            problems.append(msg)
        else:
            if warn_in_smoke:
                warnings.append(msg)

    for t in tools:
        if not isinstance(t, dict):
            continue
        tid = str(t.get("id") or "").strip()
        if not tid:
            continue
        enabled = bool(t.get("enabled", False))
        risk = str(t.get("risk") or "").lower().strip()
        handler = str(t.get("handler") or "").strip()

        must = False
        if enabled and risk and risk in req_risks:
            must = True
        if enabled and handler and handler in req_handlers:
            must = True
        # Plugins must always be attested (bundle)
        if enabled and (handler == "plugin" or handler.startswith("plugin")):
            must = True
        if not must:
            continue

        checked += 1
        sc = t.get("supply_chain")
        if not isinstance(sc, dict):
            add_problem(f"missing_attestation:{tid}")
            continue

        kind = str(sc.get("kind") or "").lower().strip()
        if kind not in allowed_kinds:
            add_problem(f"bad_attestation_kind:{tid}:{kind or 'missing'}")
            continue

        if kind == "internal":
            continue

        if kind == "system":
            lock_ref = str(sc.get("lock_ref") or "").strip()
            lock_kind = str(sc.get("lock_kind") or "").lower().strip()
            if req_lock and not lock_ref:
                add_problem(f"system_missing_lock_ref:{tid}")
            if lock_kind and allowed_lock_kinds and lock_kind not in allowed_lock_kinds:
                add_problem(f"system_bad_lock_kind:{tid}:{lock_kind}")
            continue

        if kind == "bundle":
            bundle_id = str(sc.get("bundle_id") or tid).strip() or tid
            manifest_sha = str(sc.get("manifest_sha256") or "").strip()
            artifact_sha = str(sc.get("artifact_sha256") or "").strip()

            if req_m_sha and not manifest_sha:
                add_problem(f"bundle_missing_manifest_sha256:{tid}")
            if req_a_sha and not artifact_sha:
                add_problem(f"bundle_missing_artifact_sha256:{tid}")

            mpath = str(sc.get("manifest_path") or "").strip()
            if not mpath and manifests_dir:
                mpath = os.path.join(manifests_dir, f"{bundle_id}.yaml")
            if mpath:
                if not os.path.exists(mpath):
                    add_problem(f"bundle_manifest_missing:{tid}:{mpath}")
                else:
                    got = _sha256_file(mpath)
                    if manifest_sha and got != manifest_sha:
                        add_problem(f"bundle_manifest_sha_mismatch:{tid}")

                    # Optional manifest signature verification (defense-in-depth)
                    sig_cfg = (bundle_cfg.get('signature') if isinstance(bundle_cfg, dict) else {})
                    sig_mode = str((sig_cfg.get('mode') if isinstance(sig_cfg, dict) else None) or 'prefer').strip().lower()
                    if sig_mode not in ('off', 'disabled', '0', 'false', 'no'):
                        try:
                            import toolvault as tv
                            ok_sig, r_sig = tv.verify_manifest_signature(mpath, policy, mode=sig_mode)
                            if not ok_sig:
                                add_problem(f"bundle_manifest_sig_invalid:{tid}:{r_sig}")
                            elif r_sig != 'signature_ok' and sig_mode == 'prefer':
                                warnings.append(f"bundle_manifest_sig_warn:{tid}:{r_sig}")
                        except Exception as e:
                            if sig_mode == 'require':
                                add_problem(f"bundle_manifest_sig_verify_failed:{tid}:{e!r}")
                            else:
                                warnings.append(f"bundle_manifest_sig_verify_warn:{tid}:{e!r}")
            else:
                add_problem(f"bundle_manifest_path_missing:{tid}")

            apath = str(sc.get("artifact_path") or "").strip()
            if not apath and artifacts_dir and artifact_sha:
                apath = os.path.join(artifacts_dir, artifact_sha)
            if req_a_present:
                if not apath:
                    add_problem(f"bundle_artifact_path_missing:{tid}")
                elif not os.path.exists(apath):
                    add_problem(f"bundle_artifact_missing:{tid}:{apath}")
                else:
                    got2 = _sha256_file(apath)
                    if artifact_sha and got2 != artifact_sha:
                        add_problem(f"bundle_artifact_sha_mismatch:{tid}")

            # Extra validation for plugin bundles.
            if handler == "plugin" and mpath and os.path.exists(mpath):
                try:
                    mf = _load_yaml(mpath)
                    if str(mf.get("kind") or "").strip() != "ToolPlugin":
                        add_problem(f"plugin_manifest_kind_bad:{tid}")
                    pid_m = str(mf.get("plugin_id") or "").strip()
                    pid_t = ""
                    try:
                        pid_t = str((t.get("plugin") or {}).get("plugin_id") or "").strip()
                    except Exception:
                        pid_t = ""
                    if pid_t and pid_m and pid_t != pid_m:
                        add_problem(f"plugin_manifest_id_mismatch:{tid}")
                    rt = str(mf.get("runtime") or "python3").strip().lower()
                    if rt not in ("python3", "bash", "sh"):
                        add_problem(f"plugin_manifest_runtime_not_allowed:{tid}:{rt}")
                    ep = str(mf.get("entrypoint") or "").strip()
                    if not ep:
                        add_problem(f"plugin_manifest_entrypoint_missing:{tid}")
                except Exception:
                    add_problem(f"plugin_manifest_parse_failed:{tid}")
            continue

    ok = len(problems) == 0
    summary = {"checked": checked, "failed": len(problems), "warnings": len(warnings)}
    return ok, problems, warnings, summary


# === NoemaForge Autodoc Function Header ===
# Function: prepare_plugins_for_epoch(epoch_dir: str, law_epoch_dir: str)
# Purpose: Pre-start preparation: extract enabled ToolVault plugin bundles.
# Inputs:
#   - epoch_dir: str
#   - law_epoch_dir: str
# Called by:
#   - src/brainctl.py
# Calls:
#   - _load_supplychain_policy, bool, join, isinstance, get, exists, _load_yaml, strip, bundle_paths, prepare_plugin_bundle, sel_append, append
# Returns / emits: Tuple[bool, List[str]]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - _, artifact_sha, artifacts_dir, bundle_id, enabled, handler, manifest_sha, manifests_dir, plugin_cfg, plugin_id, plugins_cfg, policy
# === End NoemaForge Autodoc Function Header ===
def prepare_plugins_for_epoch(*, epoch_dir: str, law_epoch_dir: str) -> Tuple[bool, List[str]]:
    """Pre-start preparation: extract enabled ToolVault plugin bundles.

    Policy is taken from *law_epoch_dir* (current/base epoch), not from epoch_dir,
    so a candidate epoch cannot self-enable risky behavior.

    Default posture:
      SupplyChainPolicy.plugins.runtime_prepare = false
      => ToolProxy refuses to extract at runtime.

    Therefore this runs right before epoch switch.
    """

    policy = _load_supplychain_policy(law_epoch_dir)
    plugins_cfg = (policy.get("plugins") or {}) if isinstance(policy.get("plugins"), dict) else {}
    # Even if runtime_prepare is true, prestart prepare is still fine.
    _ = bool(plugins_cfg.get("runtime_prepare", False))

    reg_path = os.path.join(epoch_dir, "tool-registry.yaml")
    if not os.path.exists(reg_path):
        return True, []

    try:
        reg = _load_yaml(reg_path)
    except Exception as e:
        return False, [f"registry_parse_failed:{e!r}"]

    tools = reg.get("tools") or []
    if not isinstance(tools, list):
        return True, []

    problems: List[str] = []
    prepared = 0

    for t in tools:
        if not isinstance(t, dict):
            continue
        enabled = bool(t.get("enabled", False))
        handler = str(t.get("handler") or "").strip()
        if not enabled or handler != "plugin":
            continue

        tid = str(t.get("id") or "").strip() or "(unknown-tool)"
        plugin_cfg = t.get("plugin")
        sc = t.get("supply_chain")
        if not isinstance(plugin_cfg, dict):
            problems.append(f"{tid}:plugin_block_missing")
            continue
        if not isinstance(sc, dict):
            problems.append(f"{tid}:supply_chain_missing")
            continue
        if str(sc.get("kind") or "").lower().strip() != "bundle":
            problems.append(f"{tid}:supply_chain_kind_not_bundle")
            continue

        plugin_id = str(plugin_cfg.get("plugin_id") or "").strip()
        if not plugin_id:
            problems.append(f"{tid}:plugin_id_missing")
            continue

        bundle_id = str(sc.get("bundle_id") or f"plugin.{plugin_id}").strip() or f"plugin.{plugin_id}"
        manifest_sha = str(sc.get("manifest_sha256") or "").strip()
        artifact_sha = str(sc.get("artifact_sha256") or "").strip()
        if not manifest_sha or not artifact_sha:
            problems.append(f"{tid}:bundle_missing_shas")
            continue

        tv = (policy.get("tool_vault") or {}) if isinstance(policy.get("tool_vault"), dict) else {}
        manifests_dir = str(tv.get("manifests_dir") or "").strip()
        artifacts_dir = str(tv.get("artifacts_dir") or "").strip()
        if not manifests_dir or not artifacts_dir:
            problems.append(f"{tid}:tool_vault_paths_missing")
            continue

        mpath, apath = bundle_paths(
            policy=policy,
            bundle_id=bundle_id,
            manifest_path=str(sc.get("manifest_path") or ""),
            artifact_sha256=artifact_sha,
            artifact_path=str(sc.get("artifact_path") or ""),
        )

        ok_p, reason, _out = prepare_plugin_bundle(
            policy=policy,
            plugin_id=plugin_id,
            bundle_id=bundle_id,
            manifest_path=mpath,
            artifact_path=apath,
            expected_manifest_sha256=manifest_sha,
            expected_artifact_sha256=artifact_sha,
        )
        if not ok_p:
            problems.append(f"{tid}:prepare_failed:{reason}")
        else:
            prepared += 1

    if prepared and sel_append:
        sel_append({"evt": "PLUGIN_PREPARE", "prepared": prepared, "epoch_dir": epoch_dir})

    return (len(problems) == 0), problems


# === NoemaForge Autodoc Function Header ===
# Function: _scary_required_suite(base_epoch_dir: str, cand_epoch_dir: str, approved_requests: List[RequestRecord])
# Purpose: Scary Core: decide minimum canary suite required.
# Inputs:
#   - base_epoch_dir: str
#   - cand_epoch_dir: str
#   - approved_requests: List[RequestRecord]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _load_canary_policy, _canary_first_run_needed, _diff_changed_files, set, any, get, strip, lower, str
# Returns / emits: str
# Side effects:
#   - spawns subprocesses or workers
# Key locals:
#   - changed_files, full_if_files, full_risk_levels, lvl, plan, policy, r, req_can, rules, suites
# === End NoemaForge Autodoc Function Header ===
def _scary_required_suite(
    *,
    base_epoch_dir: str,
    cand_epoch_dir: str,
    approved_requests: List[RequestRecord],
) -> str:
    """Scary Core: decide minimum canary suite required.

    Important: Use the *current/base epoch* canary policy as the law.
    Candidate epoch may attempt to loosen policy; we must not trust it.
    """
    policy = _load_canary_policy(base_epoch_dir)
    # First run on a machine can force FULL regardless of other heuristics.
    if _canary_first_run_needed(policy):
        return "full"
    suites = policy.get("suites") or {}
    if "smoke" not in suites:
        return "smoke"

    rules = policy.get("minimum_suite_rules") or {}

    changed_files = _diff_changed_files(base_epoch_dir, cand_epoch_dir)
    full_if_files = set((rules.get("full_if_files_changed") or []) or [])
    if any(f in full_if_files for f in changed_files):
        return "full"

    full_risk_levels = set((rules.get("full_if_risk_levels") or []) or [])
    for r in approved_requests:
        lvl = str(r.obj.get("risk_level") or "").lower().strip()
        if lvl and lvl in full_risk_levels:
            return "full"
        req_can = str(r.obj.get("requires_canary") or "").lower().strip()
        if req_can == "full":
            return "full"

        plan = r.obj.get("canary_plan") or {}
        if str(plan.get("suite") or "").lower().strip() == "full":
            return "full"

    return "smoke"


# === NoemaForge Autodoc Function Header ===
# Function: scary_min_suite_for_request(law_epoch_dir: str, track: str, requested_files: List[str], risk_level: str, requires_canary: str)
# Purpose: Scary Core minimum suite for a single atomic change.
# Inputs:
#   - law_epoch_dir: str
#   - track: str
#   - requested_files: List[str]
#   - risk_level: str
#   - requires_canary: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _load_canary_policy, _canary_first_run_needed, set, any, get, isinstance, strip, lower, str
# Returns / emits: str
# Side effects:
#   - spawns subprocesses or workers
# Key locals:
#   - full_if_files, full_risk_levels, min_suite, policy, rules, suites, tr, tracks
# === End NoemaForge Autodoc Function Header ===
def scary_min_suite_for_request(
    *,
    law_epoch_dir: str,
    track: str,
    requested_files: List[str],
    risk_level: str,
    requires_canary: str,
) -> str:
    """Scary Core minimum suite for a single atomic change.

    Law is taken from *law_epoch_dir* (typically the current epoch), never from the candidate.
    """
    policy = _load_canary_policy(law_epoch_dir)
    if _canary_first_run_needed(policy):
        return "full"
    suites = policy.get("suites") or {}
    if "smoke" not in suites:
        return "smoke"

    rules = policy.get("minimum_suite_rules") or {}
    tracks = (rules.get("tracks") or {})
    tr = (tracks.get(track) or {}) if isinstance(tracks, dict) else {}

    full_if_files = set((tr.get("full_if_files_changed") or rules.get("full_if_files_changed") or []) or [])
    full_risk_levels = set((tr.get("full_if_risk_levels") or rules.get("full_if_risk_levels") or []) or [])
    min_suite = str(tr.get("min_suite") or "smoke").lower().strip() or "smoke"
    if min_suite not in ("smoke", "full"):
        min_suite = "smoke"

    # Explicit request hint
    if str(requires_canary or "").lower().strip() == "full":
        return "full"

    # Risk level hint
    if str(risk_level or "").lower().strip() in full_risk_levels:
        return "full"

    # Surface rule
    if any(f in full_if_files for f in (requested_files or [])):
        return "full"

    return min_suite


# === NoemaForge Autodoc Function Header ===
# Function: _policy_privilege_diff(base_epoch_dir: str, cand_epoch_dir: str)
# Purpose: Return warnings for privilege widening in tool-policy.
# Inputs:
#   - base_epoch_dir: str
#   - cand_epoch_dir: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - items, _load_yaml, get, join, set, sorted, list, append
# Returns / emits: List[str]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - b, b_allow, bpol, broles, c, c_allow, cpol, croles, new, out
# === End NoemaForge Autodoc Function Header ===
def _policy_privilege_diff(base_epoch_dir: str, cand_epoch_dir: str) -> List[str]:
    """Return warnings for privilege widening in tool-policy."""
    out: List[str] = []
    try:
        bpol = _load_yaml(os.path.join(base_epoch_dir, "tool-policy.yaml"))
        cpol = _load_yaml(os.path.join(cand_epoch_dir, "tool-policy.yaml"))
    except Exception:
        return out

    b = bpol.get("streams") or {}
    c = cpol.get("streams") or {}

    for sid, srec in c.items():
        broles = ((b.get(sid) or {}).get("roles") or {})
        croles = ((srec or {}).get("roles") or {})
        for rid, rrec in croles.items():
            b_allow = set(((broles.get(rid) or {}).get("allow") or []) or [])
            c_allow = set(((rrec or {}).get("allow") or []) or [])
            new = sorted(list(c_allow - b_allow))
            if new:
                out.append(f"warn:privilege_widening:{sid}:{rid}:+{','.join(new)}")
    return out




# === NoemaForge Autodoc Function Header ===
# Function: _policy_privilege_diff_struct(base_epoch_dir: str, cand_epoch_dir: str)
# Purpose: Structured privilege widening diff in tool-policy.
# Inputs:
#   - base_epoch_dir: str
#   - cand_epoch_dir: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - items, _load_yaml, get, join, set, sorted, list, append
# Returns / emits: List[Dict[str, Any]]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - b, b_allow, bpol, broles, c, c_allow, cpol, croles, new, out
# === End NoemaForge Autodoc Function Header ===
def _policy_privilege_diff_struct(base_epoch_dir: str, cand_epoch_dir: str) -> List[Dict[str, Any]]:
    """Structured privilege widening diff in tool-policy."""
    out: List[Dict[str, Any]] = []
    try:
        bpol = _load_yaml(os.path.join(base_epoch_dir, "tool-policy.yaml"))
        cpol = _load_yaml(os.path.join(cand_epoch_dir, "tool-policy.yaml"))
    except Exception:
        return out

    b = bpol.get("streams") or {}
    c = cpol.get("streams") or {}

    for sid, srec in c.items():
        broles = ((b.get(sid) or {}).get("roles") or {})
        croles = ((srec or {}).get("roles") or {})
        for rid, rrec in croles.items():
            b_allow = set(((broles.get(rid) or {}).get("allow") or []) or [])
            c_allow = set(((rrec or {}).get("allow") or []) or [])
            new = sorted(list(c_allow - b_allow))
            if new:
                out.append({"stream_id": sid, "role": rid, "added_actions": new})
    return out


# === NoemaForge Autodoc Function Header ===
# Function: _fixtures_policy_evaluate(epoch_dir: str, fixtures_doc: Dict[str, Any])
# Purpose: Evaluate security fixtures against candidate's policy+registry.
# Inputs:
#   - epoch_dir: str
#   - fixtures_doc: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _load_yaml, str, bool, get, set, decision_for, strip, join, append, lower
# Returns / emits: Tuple[Dict[str, Any], List[str]]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - action, allow, exp, fid, fx, got, mm, pol, pol_streams, problems, reg, reg_map
# === End NoemaForge Autodoc Function Header ===
def _fixtures_policy_evaluate(epoch_dir: str, fixtures_doc: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """Evaluate security fixtures against candidate's policy+registry.

    Returns (summary, problems).

    Summary format:
      { total:int, failed:int, mismatches:[{fixture_id,got,want,stream_id,role,action}, ...] }

    This remains policy-layer only (no tool execution).
    """
    summary: Dict[str, Any] = {"total": 0, "failed": 0, "mismatches": []}
    problems: List[str] = []
    try:
        pol = _load_yaml(os.path.join(epoch_dir, "tool-policy.yaml"))
        reg = _load_yaml(os.path.join(epoch_dir, "tool-registry.yaml"))
        streams = _load_yaml(os.path.join(epoch_dir, "streams.yaml"))
    except Exception as e:
        return summary, [f"fixtures_failed_to_load_contracts:{e!r}"]

    reg_map = {str(t.get("id") or ""): bool(t.get("enabled", False)) for t in (reg.get("tools") or [])}
    pol_streams = pol.get("streams") or {}
    stream_defs = streams.get("streams") or {}

    # === NoemaForge Autodoc Function Header ===
    # Function: decision_for(stream_id: str, role: str, action: str)
    # Purpose: Implement the routine 'decision for'.
    # Inputs:
    #   - stream_id: str
    #   - role: str
    #   - action: str
    # Called by:
    #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
    # Calls:
    #   - set, get
    # Returns / emits: str
    # Key locals:
    #   - allow, roles, rrec, srec
    # === End NoemaForge Autodoc Function Header ===
    def decision_for(stream_id: str, role: str, action: str) -> str:
        if action not in reg_map:
            return "deny"  # unknown tool
        if not reg_map.get(action):
            return "deny"  # disabled tool
        if stream_id not in stream_defs:
            return "deny"
        srec = pol_streams.get(stream_id) or {}
        roles = srec.get("roles") or {}
        rrec = roles.get(role) or {}
        allow = set((rrec.get("allow") or []) or [])
        return "allow" if action in allow else "deny"

    for fx in (fixtures_doc.get("fixtures") or []) or []:
        fid = str(fx.get("id") or "")
        req = fx.get("request") or {}
        exp = fx.get("expected") or {}

        sid = str(req.get("stream_id") or "")
        role = str(req.get("role") or "")
        action = str(req.get("action") or "")

        summary["total"] += 1

        if not (fid and sid and role and action):
            summary["failed"] += 1
            problems.append(f"fixture_invalid:{fid or 'unknown'}")
            continue

        got = decision_for(sid, role, action)
        want = str(exp.get("decision") or "deny").lower().strip()

        # quarantine is modeled as "must not allow" at this layer
        if want == "quarantine":
            want = "deny"

        if got != want:
            summary["failed"] += 1
            mm = {"fixture_id": fid, "got": got, "want": want, "stream_id": sid, "role": role, "action": action}
            summary["mismatches"].append(mm)
            problems.append(f"fixture_mismatch:{fid}:got={got}:want={want}:{sid}:{role}:{action}")

    return summary, problems

# === NoemaForge Autodoc Function Header ===
# Function: _fixtures_policy_checks(epoch_dir: str, fixtures_doc: Dict[str, Any])
# Purpose: Validate security fixtures against candidate's policy+registry.
# Inputs:
#   - epoch_dir: str
#   - fixtures_doc: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _fixtures_policy_evaluate, int, len, get, startswith
# Returns / emits: Tuple[bool, List[str]]
# Key locals:
#   - ok
# === End NoemaForge Autodoc Function Header ===
def _fixtures_policy_checks(epoch_dir: str, fixtures_doc: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Validate security fixtures against candidate's policy+registry.

    This is intentionally policy-layer only (no tool execution).

    Returns (ok, problems).
    """
    summary, problems = _fixtures_policy_evaluate(epoch_dir, fixtures_doc)
    ok = (int(summary.get("failed") or 0) == 0) and (len([p for p in problems if p.startswith("fixtures_failed_to_load_contracts") or p.startswith("fixture_invalid")]) == 0)
    return ok, problems


# === NoemaForge Autodoc Function Header ===
# Function: _fixtures_monotonicity_check(law_fixtures: Dict[str, Any], cand_fixtures: Dict[str, Any])
# Purpose: Ensure candidate fixtures do not remove or mutate existing law fixtures.
# Inputs:
#   - law_fixtures: Dict[str, Any]
#   - cand_fixtures: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _by_id, items, len, dumps, append, _canon, get, isinstance, str
# Returns / emits: Tuple[bool, Dict[str, Any], List[str]]
# Side effects:
#   - serializes structured data
#   - appends to logs or files
# Key locals:
#   - cand_map, fx, law_map, missing, modified, ok, out, problems, summary
# === End NoemaForge Autodoc Function Header ===
def _fixtures_monotonicity_check(law_fixtures: Dict[str, Any], cand_fixtures: Dict[str, Any]) -> Tuple[bool, Dict[str, Any], List[str]]:
    """Ensure candidate fixtures do not remove or mutate existing law fixtures.

    Rationale
    ---------
    To allow *adding* new canary scenarios (fixtures) in the same epoch switch,
    we evaluate fixtures from the candidate epoch during FULL canary.

    But we must prevent a candidate from weakening security by altering or deleting
    previously established fixtures. This check enforces:

    - candidate is a superset of law fixtures by id
    - fixtures with the same id are byte-stable after canonicalization
    """

    # === NoemaForge Autodoc Function Header ===
    # Function: _by_id(doc: Dict[str, Any])
    # Purpose: Implement the routine ' by id'.
    # Inputs:
    #   - doc: Dict[str, Any]
    # Called by:
    #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
    # Calls:
    #   - get, isinstance, str
    # Returns / emits: Dict[str, Any]
    # Key locals:
    #   - fx, out
    # === End NoemaForge Autodoc Function Header ===
    def _by_id(doc: Dict[str, Any]) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for fx in (doc.get("fixtures") or []) or []:
            if isinstance(fx, dict) and isinstance(fx.get("id"), (str, int)):
                out[str(fx.get("id"))] = fx
        return out

    # === NoemaForge Autodoc Function Header ===
    # Function: _canon(obj)
    # Purpose: Implement the routine ' canon'.
    # Inputs:
    #   - obj
    # Called by:
    #   - src/quarantine_samples.py
    # Calls:
    #   - dumps, str
    # Returns / emits: str
    # Side effects:
    #   - serializes structured data
    # === End NoemaForge Autodoc Function Header ===
    def _canon(obj: Any) -> str:
        try:
            return json.dumps(obj, ensure_ascii=False, sort_keys=True)
        except Exception:
            return str(obj)

    law_map = _by_id(law_fixtures or {})
    cand_map = _by_id(cand_fixtures or {})

    missing: List[str] = []
    modified: List[str] = []
    problems: List[str] = []

    for fid, law_fx in law_map.items():
        if fid not in cand_map:
            missing.append(fid)
            problems.append(f"fixture_missing_in_candidate:{fid}")
            continue
        if _canon(law_fx) != _canon(cand_map.get(fid)):
            modified.append(fid)
            problems.append(f"fixture_modified_in_candidate:{fid}")

    summary = {
        "law_total": len(law_map),
        "candidate_total": len(cand_map),
        "missing": missing,
        "modified": modified,
    }
    ok = (len(missing) == 0 and len(modified) == 0)
    return ok, summary, problems


# === NoemaForge Autodoc Function Header ===
# Function: _fixture_sample_store_dirs(epoch_dir: str)
# Purpose: Resolve allowed sample store dirs for fixture sample_ref validation.
# Inputs:
#   - epoch_dir: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - set, strip, _load_yaml, isinstance, get, append, add, join, str
# Returns / emits: List[str]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - d, fx, out, paths, pol, seen, uniq
# === End NoemaForge Autodoc Function Header ===
def _fixture_sample_store_dirs(epoch_dir: str) -> List[str]:
    """Resolve allowed sample store dirs for fixture sample_ref validation."""
    out: List[str] = []
    try:
        pol = _load_yaml(os.path.join(epoch_dir, "incident-policy.yaml")) or {}
        fx = pol.get("fixtures") if isinstance(pol, dict) else None
        paths = fx.get("paths") if isinstance(fx, dict) and isinstance(fx.get("paths"), dict) else {}
        d = str(paths.get("quarantine_sample_store_dir") or "").strip()
        if d:
            out.append(d)
    except Exception:
        pass
    # Dedup
    seen: set[str] = set()
    uniq: List[str] = []
    for d in out:
        if d and d not in seen:
            seen.add(d)
            uniq.append(d)
    return uniq


# === NoemaForge Autodoc Function Header ===
# Function: _fixtures_sample_ref_check(epoch_dir: str, fixtures_doc: Dict[str, Any])
# Purpose: Validate that sample_ref references point to existing slim samples.
# Inputs:
#   - epoch_dir: str
#   - fixtures_doc: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _fixture_sample_store_dirs, compile, isinstance, get, lower, strip, append, join, exists, str, match
# Returns / emits: Tuple[Dict[str, Any], List[str], List[str]]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - d, dirs, fid, fixtures, found, fx, kind, missing, ok, p, problems, sha
# === End NoemaForge Autodoc Function Header ===
def _fixtures_sample_ref_check(epoch_dir: str, fixtures_doc: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str], List[str]]:
    """Validate that sample_ref references point to existing slim samples.

    Returns (summary, problems, warnings). This is WARN-only by default.
    """
    problems: List[str] = []
    warnings: List[str] = []
    total = 0
    ok = 0
    missing = 0

    dirs = _fixture_sample_store_dirs(epoch_dir)
    fixtures = fixtures_doc.get("fixtures") if isinstance(fixtures_doc, dict) else None
    if not isinstance(fixtures, list) or not fixtures:
        return ({"total": 0, "ok": 0, "missing": 0, "dirs": dirs}, problems, warnings)

    import re

    sha_re = re.compile(r"^[a-f0-9]{32,64}$")
    for fx in fixtures:
        if not isinstance(fx, dict):
            continue
        sr = fx.get("sample_ref") if isinstance(fx.get("sample_ref"), dict) else None
        if not isinstance(sr, dict):
            continue
        total += 1

        kind = str(sr.get("kind") or "").strip().lower()
        sha = str(sr.get("sha256") or "").strip().lower()
        fid = str(fx.get("id") or "").strip()

        if not sha or not sha_re.match(sha):
            warnings.append(f"fixture_sample_ref_invalid:{fid}")
            continue

        if kind not in ("quarantine_slim/v1", "quarantine_slim"):
            warnings.append(f"fixture_sample_ref_unknown_kind:{fid}:{kind}")
            continue

        found = False
        for d in dirs:
            p = os.path.join(d, f"{sha}.json.gz")
            if os.path.exists(p):
                found = True
                break

        if found:
            ok += 1
        else:
            missing += 1
            warnings.append(f"fixture_sample_ref_missing:{fid}:{sha}")

    summary = {"total": total, "ok": ok, "missing": missing, "dirs": dirs}
    return summary, problems, warnings


# === NoemaForge Autodoc Function Header ===
# Function: _fixtures_change_coverage_check(canary_policy: Dict[str, Any], changed_files: List[str], fixtures_doc: Dict[str, Any])
# Purpose: Check that security fixtures *cover* the policy surfaces that changed.
# Inputs:
#   - canary_policy: Dict[str, Any]
#   - changed_files: List[str]
#   - fixtures_doc: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - get, set, isinstance, bool, len, strip, any, join, append, lower, add, str
# Returns / emits: Tuple[bool, Dict[str, Any], List[str], List[str]]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - c, cats, changed, cov, files, fx, fx_list, msg, need_any, ok, problems, rid
# === End NoemaForge Autodoc Function Header ===
def _fixtures_change_coverage_check(
    *,
    canary_policy: Dict[str, Any],
    changed_files: List[str],
    fixtures_doc: Dict[str, Any],
) -> Tuple[bool, Dict[str, Any], List[str], List[str]]:
    """Check that security fixtures *cover* the policy surfaces that changed.

    This is a pragmatic guardrail to reduce the chance we ship a change with
    no relevant canary scenarios.

    The rules are defined in CanaryPolicy.coverage.rules (law epoch), never
    in the candidate epoch.

    Returns (ok, summary, problems, warnings).
    """

    problems: List[str] = []
    warnings: List[str] = []
    summary: Dict[str, Any] = {"checked": 0, "missing": 0, "rules_fired": []}

    cov = canary_policy.get("coverage") if isinstance(canary_policy, dict) else None
    if not isinstance(cov, dict):
        return True, summary, problems, warnings
    if not bool(cov.get("enabled", True)):
        return True, summary, problems, warnings

    rules = cov.get("rules")
    if not isinstance(rules, list) or not rules:
        return True, summary, problems, warnings

    # Gather fixture categories present in the suite we're about to run.
    cats: set[str] = set()
    fx_list = fixtures_doc.get("fixtures") if isinstance(fixtures_doc, dict) else None
    if isinstance(fx_list, list):
        for fx in fx_list:
            if not isinstance(fx, dict):
                continue
            c = str(fx.get("category") or "").strip()
            if c:
                cats.add(c)

    changed = set([str(x).strip() for x in (changed_files or []) if str(x).strip()])

    for rule in rules:
        if not isinstance(rule, dict):
            continue
        files = rule.get("files")
        if not isinstance(files, list) or not files:
            continue
        files = [str(f).strip() for f in files if str(f).strip()]
        if not files:
            continue
        if not any(f in changed for f in files):
            continue

        summary["checked"] += 1
        rid = str(rule.get("id") or "").strip() or "|".join(files)

        need_any = rule.get("require_fixture_categories_any")
        if not isinstance(need_any, list):
            need_any = []
        need_any = [str(x).strip() for x in need_any if str(x).strip()]
        if not need_any:
            summary["rules_fired"].append({"id": rid, "files": files, "status": "noop"})
            continue

        if not (set(need_any) & cats):
            sev = str(rule.get("severity") or "fail").strip().lower()
            msg = f"fixture_coverage_missing:{rid}:need_any={','.join(need_any)}:have={','.join(sorted(list(cats)))}"
            summary["missing"] += 1
            summary["rules_fired"].append({"id": rid, "files": files, "status": "missing", "need_any": need_any})
            if sev in ("warn", "warning"):
                warnings.append(msg)
            else:
                problems.append(msg)
        else:
            summary["rules_fired"].append({"id": rid, "files": files, "status": "ok"})

    ok = len(problems) == 0
    return ok, summary, problems, warnings

# === NoemaForge Autodoc Function Header ===
# Function: _apply_request_to_epoch_dir(cand_dir: str, req: RequestRecord)
# Purpose: Apply a single PreStartChangeRequest into cand_dir.
# Inputs:
#   - cand_dir: str
#   - req: RequestRecord
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - strip, patch_file, sorted, get, _allowed_patch_authors, join, _deep_merge, _save_yaml, list, lower, exists, _load_yaml
# Returns / emits: List[str]
# Key locals:
#   - allow_patches, author, ch, cur, dst_dir, key, nxt, obj, p, pth, sp, touched
# === End NoemaForge Autodoc Function Header ===
def _apply_request_to_epoch_dir(cand_dir: str, req: RequestRecord) -> List[str]:
    """Apply a single PreStartChangeRequest into cand_dir.

    Returns list of epoch files that were touched (best-effort).
    """
    obj = req.obj
    ch = (obj.get("requested_changes") or {})
    author = str(((obj.get("created_by") or {}).get("actor_type") or "")).lower().strip()
    allow_patches = author in _allowed_patch_authors()

    touched: List[str] = []

    # === NoemaForge Autodoc Function Header ===
    # Function: patch_file(filename: str, patch_obj)
    # Purpose: Implement the routine 'patch file'.
    # Inputs:
    #   - filename: str
    #   - patch_obj
    # Called by:
    #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
    # Calls:
    #   - join, _deep_merge, _save_yaml, exists, _load_yaml, append
    # Returns / emits: None
    # Side effects:
    #   - appends to logs or files
    # Key locals:
    #   - cur, nxt, p
    # === End NoemaForge Autodoc Function Header ===
    def patch_file(filename: str, patch_obj: Any) -> None:
        nonlocal touched
        if patch_obj is None:
            return
        if not allow_patches:
            return
        p = os.path.join(cand_dir, filename)
        cur = _load_yaml(p) if os.path.exists(p) else {}
        nxt = _deep_merge(cur, patch_obj)
        _save_yaml(p, nxt)
        if filename in EPOCH_FILES:
            touched.append(filename)

    patch_file("streams.yaml", ch.get("streams_patch"))
    patch_file("patterns.yaml", ch.get("patterns_patch"))
    patch_file("tool-registry.yaml", ch.get("tool_registry_patch"))
    patch_file("tool-policy.yaml", ch.get("tool_policy_patch"))
    patch_file("sandbox-policy.yaml", ch.get("sandbox_policy_patch"))
    patch_file("supplychain-policy.yaml", ch.get("supplychain_policy_patch"))
    patch_file("bundle-policy.yaml", ch.get("bundle_policy_patch"))
    patch_file("web-gateway-policy.yaml", ch.get("web_gateway_policy_patch"))
    patch_file("local-gateway-policy.yaml", ch.get("local_gateway_policy_patch"))
    patch_file("nids-policy.yaml", ch.get("nids_policy_patch"))

    # Model fleet contracts (epoch-scoped)
    patch_file("role-model-policy.yaml", ch.get("role_model_policy_patch"))
    patch_file("model-eval-suite.yaml", ch.get("model_eval_suite_patch"))
    patch_file("llm-backends-policy.yaml", ch.get("llm_backends_policy_patch"))

    # Flow/team contracts (epoch-scoped)
    patch_file("flow-catalog.yaml", ch.get("flow_catalog_patch"))
    patch_file("flow-eval-suite.yaml", ch.get("flow_eval_suite_patch"))
    patch_file("team-eval-policy.yaml", ch.get("team_eval_policy_patch"))
    patch_file("team-model-policy.yaml", ch.get("team_model_policy_patch"))
    patch_file("bootdoctor.yaml", ch.get("bootdoctor_policy_patch"))
    patch_file("installer-policy.yaml", ch.get("installer_policy_patch"))
    patch_file("maintenance-policy.yaml", ch.get("maintenance_policy_patch"))
    patch_file("resource-policy.yaml", ch.get("resource_policy_patch"))
    patch_file("taskqueue-policy.yaml", ch.get("taskqueue_policy_patch"))
    patch_file("clarifications.yaml", ch.get("clarifications_patch"))
    patch_file("vstore.yaml", ch.get("vstore_config_patch"))
    patch_file("verifiers.yaml", ch.get("verifiers_patch"))
    patch_file("canary-policy.yaml", ch.get("canary_policy_patch"))
    patch_file("security-fixtures.yaml", ch.get("security_fixtures_patch"))
    patch_file("quarantine-policy.yaml", ch.get("quarantine_policy_patch"))
    patch_file("incident-policy.yaml", ch.get("incident_policy_patch"))
    patch_file("role-affirmations.yaml", ch.get("role_affirmations_patch"))
    patch_file("role-roadmaps.yaml", ch.get("role_roadmaps_patch"))

    # Streams/patterns add: copy referenced files into overlays/
    for key in ("streams_add", "patterns_add"):
        for pth in (ch.get(key) or []) or []:
            try:
                sp = str(pth)
                if not sp:
                    continue
                if os.path.exists(sp):
                    dst_dir = os.path.join(cand_dir, "overlays", key)
                    os.makedirs(dst_dir, exist_ok=True)
                    shutil.copy2(sp, os.path.join(dst_dir, os.path.basename(sp)))
                    touched.append("overlays/" + key)
            except Exception:
                continue

    return sorted(list(set(touched)))


# === NoemaForge Autodoc Function Header ===
# Function: _clone_tree(src_dir: str)
# Purpose: Implement the routine ' clone tree'.
# Inputs:
#   - src_dir: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - mkdtemp, rmtree, copytree
# Returns / emits: str
# Key locals:
#   - tmp
# === End NoemaForge Autodoc Function Header ===
def _clone_tree(src_dir: str) -> str:
    tmp = tempfile.mkdtemp(prefix="noemaforge-prestart-snap-")
    shutil.rmtree(tmp, ignore_errors=True)
    shutil.copytree(src_dir, tmp)
    return tmp


# === NoemaForge Autodoc Function Header ===
# Function: _restore_tree(src_dir: str, dst_dir: str)
# Purpose: Restore dst_dir to match src_dir.
# Inputs:
#   - src_dir: str
#   - dst_dir: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - rmtree, copytree, rename
# Returns / emits: None
# Key locals:
#   - tmp
# === End NoemaForge Autodoc Function Header ===
def _restore_tree(src_dir: str, dst_dir: str) -> None:
    """Restore dst_dir to match src_dir."""
    # Brutal but simple: replace directory contents.
    tmp = dst_dir + ".restore_tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    shutil.copytree(src_dir, tmp)
    shutil.rmtree(dst_dir)
    os.rename(tmp, dst_dir)


# === NoemaForge Autodoc Function Header ===
# Function: build_candidate_epoch(desired_epoch_id: str, contracts_root: str = DEFAULT_CONTRACTS_ROOT, base_epoch_id: Optional[str] = None, requests: Optional[List[RequestRecord]] = None, created_by: Optional[Dict[str, Any]] = None, description: str = '', user_comment: str = '', notifications_dir: str = DEFAULT_NOTIFICATIONS_DIR)
# Purpose: Build a candidate epoch by applying approved requests *one by one*.
# Inputs:
#   - desired_epoch_id: str
#   - contracts_root: str = DEFAULT_CONTRACTS_ROOT
#   - base_epoch_id: Optional[str] = None
#   - requests: Optional[List[RequestRecord]] = None
#   - created_by: Optional[Dict[str, Any]] = None
#   - description: str = ''
#   - user_comment: str = ''
#   - notifications_dir: str = DEFAULT_NOTIFICATIONS_DIR
# Called by:
#   - src/brainctl.py
# Calls:
#   - epoch_path, exists, makedirs, build_epoch_manifest, _save_json, _load_canary_policy, sorted, join, any, bool, _scary_required_suite, int
# Returns / emits: str
# Side effects:
#   - creates directories
# Key locals:
#   - allow_patches, any_applied, applied_request_ids, approved_for_suite, author, base_dir, base_epoch_id, build_id, build_report, cand_dir, changes_log, cp
# === End NoemaForge Autodoc Function Header ===
def build_candidate_epoch(
    *,
    desired_epoch_id: str,
    contracts_root: str = DEFAULT_CONTRACTS_ROOT,
    base_epoch_id: Optional[str] = None,
    requests: Optional[List[RequestRecord]] = None,
    created_by: Optional[Dict[str, Any]] = None,
    description: str = "",
    user_comment: str = "",
    notifications_dir: str = DEFAULT_NOTIFICATIONS_DIR,
) -> str:
    """Build a candidate epoch by applying approved requests *one by one*.

    New rule (v0.9.4): epoch switching is only allowed when triggered by:
      a) system change(s)
      b) policy/affirmations change(s)
      c) explicit user-driven request with a manual comment

    Each request is treated as an *atomic parameter change*.
    Each request may run 1+ canary suites. If any canary fails, the request is rolled back.
    """

    base_epoch_id = base_epoch_id or current_epoch_id(contracts_root)
    base_dir = epoch_path(base_epoch_id, contracts_root)
    if not os.path.isdir(base_dir):
        raise RuntimeError(f"base_epoch_missing:{base_epoch_id}")

    cand_dir = epoch_path(desired_epoch_id, contracts_root)
    if os.path.exists(cand_dir):
        raise RuntimeError(f"epoch_already_exists:{desired_epoch_id}")

    # Trigger guard: refuse to build a pointless epoch.
    reqs = requests or []
    if not reqs and not str(user_comment or "").strip():
        raise RuntimeError("refusing_no_changes_and_no_user_comment")

    os.makedirs(cand_dir, exist_ok=False)

    # Copy baseline contracts
    for name in EPOCH_FILES:
        src = os.path.join(base_dir, name)
        dst = os.path.join(cand_dir, name)
        if os.path.exists(src):
            shutil.copy2(src, dst)
        else:
            _save_yaml(dst, {})

    # Initial manifest
    man0 = build_epoch_manifest(
        epoch_id=desired_epoch_id,
        base_epoch_id=base_epoch_id,
        epoch_dir=cand_dir,
        created_by=created_by or {"actor_type": "human", "channel": "brainctl"},
        status="candidate",
        description=description or f"candidate from {base_epoch_id}",
        notes=[f"user_comment:{str(user_comment)[:120]}" if str(user_comment or "").strip() else ""],
    )
    _save_json(os.path.join(cand_dir, "epoch_manifest.json"), man0)

    law_dir = base_dir  # fixed law for the whole build (candidate must not self-weaken)
    law_policy = _load_canary_policy(law_dir)

    epoch_creator = created_by or {"actor_type": "human", "channel": "brainctl"}

    # Order: system -> policy -> user (stable)
    # === NoemaForge Autodoc Function Header ===
    # Function: order_key(r: RequestRecord)
    # Purpose: Implement the routine 'order key'.
    # Inputs:
    #   - r: RequestRecord
    # Called by:
    #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
    # Calls:
    #   - _infer_track, get, _request_id
    # Returns / emits: Tuple[int, str]
    # Key locals:
    #   - o, tr
    # === End NoemaForge Autodoc Function Header ===
    def order_key(r: RequestRecord) -> Tuple[int, str]:
        tr = _infer_track(r.obj)
        o = {"system": 0, "policy": 1, "user": 2}.get(tr, 9)
        return (o, _request_id(r))

    reqs_sorted = sorted(reqs, key=order_key)

    build_id = uuid.uuid4().hex
    changes_log: List[Dict[str, Any]] = []
    notifications: List[str] = []

    runner = os.path.join(os.path.dirname(__file__), "canary_runner.py")

    applied_request_ids: List[str] = []

    
    for r in reqs_sorted:
        rid = _request_id(r)
        obj = r.obj
        track = _infer_track(obj)

        # v0.12.10: split each request into unit-level atomic changes.
        units = _extract_change_units(r)

        if not units:
            changes_log.append(
                {
                    "request_id": rid,
                    "track": track,
                    "created_by": obj.get("created_by") or {},
                    "status": "skipped",
                    "reason": "no_effective_units",
                    "units": [],
                    "changed_files": [],
                    "suites_run": [],
                }
            )
            continue

        # Common hints (request-level)
        risk_level = str(obj.get("risk_level") or "").lower().strip()
        requires_canary = str(obj.get("requires_canary") or "auto").lower().strip()

        # Permission gate: only certain actor types may patch contracts automatically.
        author = str(((obj.get("created_by") or {}).get("actor_type") or "")).lower().strip()
        allow_patches = author in _allowed_patch_authors()

        req_created_by = obj.get("created_by") or {}
        requester_role = str(req_created_by.get("role") or "").strip() or ""

        touched_all: List[str] = []
        unit_logs: List[Dict[str, Any]] = []
        any_applied = False

        for unit in units:
            # Snapshot includes any previously accepted units from this request.
            snap = _clone_tree(cand_dir)

            if not allow_patches:
                # Skip unit, but keep trace.
                unit_logs.append(
                    {
                        "unit_key": unit.unit_key,
                        "change_key": unit.change_key,
                        "file": unit.filename,
                        "status": "skipped",
                        "reason": "patches_not_allowed",
                        "suites_run": [],
                    }
                )
                shutil.rmtree(snap, ignore_errors=True)
                continue

            touched = _apply_change_unit_to_epoch_dir(cand_dir, unit)
            if touched:
                touched_all.extend(touched)

            # If nothing changed (missing file/empty patch), treat as no-op.
            if not touched:
                unit_logs.append(
                    {
                        "unit_key": unit.unit_key,
                        "change_key": unit.change_key,
                        "file": unit.filename,
                        "status": "noop",
                        "reason": "no_effective_mutation",
                        "suites_run": [],
                    }
                )
                shutil.rmtree(snap, ignore_errors=True)
                continue

            # Refresh manifest after unit mutation (required for manifest_integrity canary).
            man_step = build_epoch_manifest(
                epoch_id=desired_epoch_id,
                base_epoch_id=base_epoch_id,
                epoch_dir=cand_dir,
                created_by=epoch_creator,
                status="candidate",
                description=description or f"candidate from {base_epoch_id}",
                notes=[f"step_applied_unit:{rid}:{unit.unit_key}"],
            )
            _save_json(os.path.join(cand_dir, "epoch_manifest.json"), man_step)

            suites = _unit_required_suites(
                law_dir=law_dir,
                law_policy=law_policy or {},
                track=track,
                unit=unit,
                risk_level=risk_level,
                requires_canary=requires_canary,
                request_obj=obj,
            )

            # Run suites.
            per_suite_results: List[Dict[str, Any]] = []
            ok_all = True
            fail_reason = ""

            reports_dir = os.path.join(cand_dir, "canary_reports")
            os.makedirs(reports_dir, exist_ok=True)

            safe_unit = re.sub(r"[^A-Za-z0-9_.-]+", "_", unit.unit_key)

            for suite in suites:
                # Quotas come from LAW epoch.
                q = ((law_policy.get("quota_profiles") or {}).get(suite) or {})
                timeout_sec = int(q.get("timeout_sec") or (180 if suite == "smoke" else 3600))
                report_path = os.path.join(reports_dir, f"{rid}--{safe_unit}--{suite}.json")

                try:
                    cp = subprocess.run(
                        [
                            sys.executable,
                            runner,
                            "--base",
                            snap,
                            "--cand",
                            cand_dir,
                            "--law",
                            law_dir,
                            "--suite",
                            suite,
                            "--report-path",
                            report_path,
                        ],
                        capture_output=True,
                        text=True,
                        timeout=timeout_sec,
                    )
                    payload = json.loads((cp.stdout or "{}").strip() or "{}")
                    ok = bool(payload.get("ok"))
                    probs = list(payload.get("problems") or [])
                except Exception as e:
                    ok = False
                    probs = [f"canary_runner_exception:{e!r}"]

                per_suite_results.append({"suite": suite, "decision": "pass" if ok else "fail", "report_path": report_path, "problems": probs})
                if not ok:
                    ok_all = False
                    fail_reason = f"canary_failed:{suite}"
                    break

            if ok_all:
                any_applied = True
                shutil.rmtree(snap, ignore_errors=True)
                unit_logs.append(
                    {
                        "unit_key": unit.unit_key,
                        "change_key": unit.change_key,
                        "file": unit.filename,
                        "status": "applied",
                        "changed_files": touched,
                        "suites_run": per_suite_results,
                    }
                )
            else:
                # Roll back THIS unit only (restore to pre-unit snapshot).
                _restore_tree(snap, cand_dir)
                shutil.rmtree(snap, ignore_errors=True)

                # Persist unit blocklist/audit on the request itself.
                try:
                    obj2 = dict(obj)
                    _request_record_unit_audit(
                        obj=obj2,
                        unit_key=unit.unit_key,
                        status="rolled_back",
                        candidate_epoch_id=desired_epoch_id,
                        base_epoch_id=base_epoch_id,
                        track=track,
                        fail_reason=fail_reason,
                        suites_run=per_suite_results,
                    )
                    _save_any(r.path, obj2)
                    # Keep local view in sync for subsequent units.
                    obj = obj2
                except Exception:
                    pass

                unit_logs.append(
                    {
                        "unit_key": unit.unit_key,
                        "change_key": unit.change_key,
                        "file": unit.filename,
                        "status": "rolled_back",
                        "changed_files": touched,
                        "suites_run": per_suite_results,
                        "rollback_reason": fail_reason,
                    }
                )

                payload = {
                    "type": "prestart_change_unit_rolled_back",
                    "at": _nowz(),
                    "request_id": rid,
                    "unit_key": unit.unit_key,
                    "change_key": unit.change_key,
                    "file": unit.filename,
                    "track": track,
                    "candidate_epoch_id": desired_epoch_id,
                    "base_epoch_id": base_epoch_id,
                    "reason": fail_reason,
                    "suites_run": per_suite_results,
                }
                try:
                    notifications.append(_notify("scary", payload, notifications_dir=notifications_dir))
                except Exception:
                    pass
                try:
                    notifications.append(_notify("surgeon", payload, notifications_dir=notifications_dir))
                except Exception:
                    pass
                if requester_role:
                    try:
                        notifications.append(_notify(requester_role, payload, notifications_dir=notifications_dir))
                    except Exception:
                        pass

                # Log to SEL
                if sel_append:
                    try:
                        sel_append({
                            "severity": "high",
                            "type": "prestart_change_unit_rolled_back",
                            "request_id": rid,
                            "unit_key": unit.unit_key,
                            "track": track,
                            "candidate_epoch": desired_epoch_id,
                            "base_epoch": base_epoch_id,
                            "reason": fail_reason,
                        })
                    except Exception:
                        pass

        if any_applied:
            applied_request_ids.append(rid)

        # Summarize request-level outcome.
        changes_log.append(
            {
                "request_id": rid,
                "track": track,
                "created_by": obj.get("created_by") or {},
                "status": "applied" if any_applied else "skipped",
                "units": unit_logs,
                "changed_files": sorted(list(set([x for x in touched_all if str(x).strip()]))),
            }
        )

    # Determine triggers for epoch switching.
    system_changes = any((c.get("track") == "system" and c.get("status") == "applied") for c in changes_log)
    policy_changes = any((c.get("track") == "policy" and c.get("status") == "applied") for c in changes_log)
    user_req = bool(str(user_comment or "").strip())

    # Run final integration canary (single suite) against CURRENT base.
    # Use existing Scary logic for the combined surface.
    # Note: only consider *approved* requests as hints; rolled-back ones already excluded.
    # Build a synthetic list for suite selection.
    approved_for_suite: List[RequestRecord] = [r for r in reqs_sorted if _request_id(r) in applied_request_ids]
    # First, write a final manifest that includes applied request notes.
    man_final = build_epoch_manifest(
        epoch_id=desired_epoch_id,
        base_epoch_id=base_epoch_id,
        epoch_dir=cand_dir,
        created_by=epoch_creator,
        status="candidate",
        description=description or f"candidate from {base_epoch_id} + {len(applied_request_ids)} applied change(s)",
        notes=[f"applied_request:{x}" for x in applied_request_ids] + ([f"user_comment:{str(user_comment)[:120]}"] if user_req else []),
    )
    _save_json(os.path.join(cand_dir, "epoch_manifest.json"), man_final)

    final_suite = _scary_required_suite(base_epoch_dir=law_dir, cand_epoch_dir=cand_dir, approved_requests=approved_for_suite)
    if final_suite not in ("smoke", "full"):
        final_suite = "smoke"

    # Run final canary (writes scary_report.json)
    qf = ((law_policy.get("quota_profiles") or {}).get(final_suite) or {})
    timeout_final = int(qf.get("timeout_sec") or (180 if final_suite == "smoke" else 3600))
    try:
        cp = subprocess.run(
            [
                sys.executable,
                runner,
                "--base",
                law_dir,
                "--cand",
                cand_dir,
                "--law",
                law_dir,
                "--suite",
                final_suite,
            ],
            capture_output=True,
            text=True,
            timeout=timeout_final,
        )
        payload = json.loads((cp.stdout or "{}").strip() or "{}")
        ok_final = bool(payload.get("ok"))
        probs_final = list(payload.get("problems") or [])
        report_path_final = str(payload.get("report_path") or os.path.join(cand_dir, "scary_report.json"))
    except Exception as e:
        ok_final = False
        probs_final = [f"final_canary_exception:{e!r}"]
        report_path_final = os.path.join(cand_dir, "scary_report.json")

    final_canary = {"suite": final_suite, "decision": "pass" if ok_final else "fail", "report_path": report_path_final, "problems": probs_final}

    overall_ok = bool(ok_final) and (system_changes or policy_changes or user_req)

    build_report: Dict[str, Any] = {
        "schema_version": "v1",
        "build_id": build_id,
        "created_at": _nowz(),
        "base_epoch_id": base_epoch_id,
        "candidate_epoch_id": desired_epoch_id,
        "trigger": {
            "system_changes": bool(system_changes),
            "policy_changes": bool(policy_changes),
            "user_request": bool(user_req),
            "user_comment": str(user_comment or "").strip(),
        },
        "changes": changes_log,
        "final_canary": final_canary,
        "notifications": notifications,
        "overall_decision": "pass" if overall_ok else "fail",
    }

    _save_json(os.path.join(cand_dir, "prestart_build_report.json"), build_report)

    # If final canary failed, notify operator roles.
    if not overall_ok:
        payload = {
            "type": "prestart_build_failed",
            "at": _nowz(),
            "candidate_epoch_id": desired_epoch_id,
            "base_epoch_id": base_epoch_id,
            "final_canary": final_canary,
        }
        try:
            notifications.append(_notify("scary", payload, notifications_dir=notifications_dir))
        except Exception:
            pass
        try:
            notifications.append(_notify("surgeon", payload, notifications_dir=notifications_dir))
        except Exception:
            pass
        if sel_append:
            try:
                sel_append({
                    "severity": "high",
                    "type": "prestart_build_failed",
                    "candidate_epoch": desired_epoch_id,
                    "base_epoch": base_epoch_id,
                    "final_suite": final_suite,
                    "problems": probs_final,
                })
            except Exception:
                pass

        # Persist updated notification list
        try:
            build_report["notifications"] = notifications
            _save_json(os.path.join(cand_dir, "prestart_build_report.json"), build_report)
        except Exception:
            pass

    return desired_epoch_id


# === NoemaForge Autodoc Function Header ===
# Function: switch_current_epoch(epoch_id: str, contracts_root: str = DEFAULT_CONTRACTS_ROOT)
# Purpose: Implement the routine 'switch current epoch'.
# Inputs:
#   - epoch_id: str
#   - contracts_root: str = DEFAULT_CONTRACTS_ROOT
# Called by:
#   - src/brainctl.py
# Calls:
#   - epoch_path, join, makedirs, isdir, RuntimeError, epochs_dir, dirname, symlink, open, write, islink, exists
# Returns / emits: None
# Side effects:
#   - reads or writes files
#   - creates directories
# Key locals:
#   - cur_link, ep, f
# === End NoemaForge Autodoc Function Header ===
def switch_current_epoch(epoch_id: str, contracts_root: str = DEFAULT_CONTRACTS_ROOT) -> None:
    ep = epoch_path(epoch_id, contracts_root)
    if not os.path.isdir(ep):
        raise RuntimeError(f"epoch_missing:{epoch_id}")

    cur_link = os.path.join(epochs_dir(contracts_root), "current")
    os.makedirs(os.path.dirname(cur_link), exist_ok=True)

    try:
        if os.path.islink(cur_link) or os.path.exists(cur_link):
            os.remove(cur_link)
        os.symlink(ep, cur_link)
    except Exception:
        pass

    with open(os.path.join(epochs_dir(contracts_root), "current_epoch.txt"), "w", encoding="utf-8") as f:
        f.write(epoch_id + "\n")


# === NoemaForge Autodoc Function Header ===
# Function: mark_requests_applied(reqs: List[RequestRecord], applied_epoch_id: str, only_request_ids: Optional[List[str]] = None)
# Purpose: Implement the routine 'mark requests applied'.
# Inputs:
#   - reqs: List[RequestRecord]
#   - applied_epoch_id: str
#   - only_request_ids: Optional[List[str]] = None
# Called by:
#   - src/brainctl.py
# Calls:
#   - set, _request_id, _nowz, _save_any, lower, get, str
# Returns / emits: None
# Key locals:
#   - allow, aud, obj, r, rid
# === End NoemaForge Autodoc Function Header ===
def mark_requests_applied(reqs: List[RequestRecord], applied_epoch_id: str, only_request_ids: Optional[List[str]] = None) -> None:
    allow = set([str(x) for x in (only_request_ids or []) if str(x)]) if only_request_ids else None
    for r in reqs:
        obj = r.obj
        rid = _request_id(r)
        if allow is not None and rid not in allow:
            continue
        if str(obj.get("status") or "").lower() != "approved":
            continue
        obj["status"] = "applied"
        aud = obj.get("audit") or {}
        aud["applied_epoch_id"] = applied_epoch_id
        aud["applied_at"] = _nowz()
        obj["audit"] = aud
        _save_any(r.path, obj)


# === NoemaForge Autodoc Function Header ===
# Function: canary_run_report(base_epoch_dir: str, cand_epoch_dir: str, law_epoch_dir: Optional[str] = None, suite: str, quotas_applied: Optional[Dict[str, Any]] = None)
# Purpose: Run canary suite and return a structured ScaryReport-like object.
# Inputs:
#   - base_epoch_dir: str
#   - cand_epoch_dir: str
#   - law_epoch_dir: Optional[str] = None
#   - suite: str
#   - quotas_applied: Optional[Dict[str, Any]] = None
# Called by:
#   - src/canary_runner.py
# Calls:
#   - time, set, basename, _diff_changed_files, any, _load_canary_policy, _canary_first_run_needed, strip, isinstance, get, add, append
# Returns / emits: Dict[str, Any]
# Side effects:
#   - spawns subprocesses or workers
#   - appends to logs or files
# Key locals:
#   - base_id, cand_fx, cand_id, changed_files, coverage_summary, decision, evt, evt2, fixtures_summary, fixtures_to_run, forced_first_run, law_epoch_dir
# === End NoemaForge Autodoc Function Header ===
def canary_run_report(
    *,
    base_epoch_dir: str,
    cand_epoch_dir: str,
    law_epoch_dir: Optional[str] = None,
    suite: str,
    quotas_applied: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run canary suite and return a structured ScaryReport-like object.

    PRE-START ONLY.

    v0.12.9:
    - Suite execution follows CanaryPolicy.suites.<suite>.tests (law epoch).
    - Adds fixture change-coverage guardrail (law epoch).
    """

    start_wall = time.time()

    law_epoch_dir = law_epoch_dir or base_epoch_dir

    # First-run posture: force FULL once per machine to establish a baseline.
    forced_first_run = False
    law_policy: Dict[str, Any] = {}
    try:
        law_policy = _load_canary_policy(law_epoch_dir)
        if _canary_first_run_needed(law_policy):
            forced_first_run = True
            suite = "full"
            _canary_first_run_mark(law_policy, {"attempted": True, "started_at": _nowz(), "suite": suite})
    except Exception:
        law_policy = {}

    suite = str(suite or "smoke").lower().strip() or "smoke"
    if suite not in ("smoke", "full"):
        suite = "smoke"

    # Determine ordered test plan from law epoch.
    suites = law_policy.get("suites") if isinstance(law_policy, dict) else None
    suite_obj = (suites.get(suite) or {}) if isinstance(suites, dict) else {}
    plan = suite_obj.get("tests") if isinstance(suite_obj, dict) else None
    if not isinstance(plan, list) or not plan:
        plan = ["manifest_integrity", "static_consistency"]
        if suite == "full":
            plan += [
                "supply_chain_attestation",
                "security_fixtures_monotonicity",
                "security_fixtures_sample_refs",
                "security_fixtures_change_coverage",
                "security_fixtures_policy",
                "policy_privilege_diff",
            ]

    # Normalize & dedup while preserving order.
    seen: set[str] = set()
    tests_plan: List[str] = []
    for t in plan:
        tid = str(t or "").strip()
        if not tid or tid in seen:
            continue
        seen.add(tid)
        tests_plan.append(tid)

    base_id = os.path.basename(os.path.realpath(base_epoch_dir))
    cand_id = os.path.basename(os.path.realpath(cand_epoch_dir))
    law_id = os.path.basename(os.path.realpath(law_epoch_dir))

    sel_refs: Dict[str, Any] = {}

    # Log start
    if sel_append:
        evt = sel_append({
            "severity": "info",
            "type": "canary_start",
            "suite": suite,
            "base_epoch": base_id,
            "candidate_epoch": cand_id,
            "law_epoch": law_id,
            "tests": tests_plan,
        })
        sel_refs["start_evt_id"] = evt.get("evt_id")
        sel_refs["start_sel_hash"] = evt.get("_sel_hash")

    changed_files = _diff_changed_files(base_epoch_dir, cand_epoch_dir)

    tests: List[Dict[str, Any]] = []
    problems: List[str] = []
    warnings: List[str] = []

    fixtures_summary: Optional[Dict[str, Any]] = None
    privilege_struct: List[Dict[str, Any]] = []
    coverage_summary: Optional[Dict[str, Any]] = None

    # Preload fixtures if requested by plan.
    need_fx = any(str(t).startswith("security_fixtures") for t in tests_plan)
    law_fx: Dict[str, Any] = {}
    cand_fx: Dict[str, Any] = {}
    fixtures_to_run: Dict[str, Any] = {}
    if need_fx:
        try:
            law_fx = _load_security_fixtures(law_epoch_dir) or {}
        except Exception:
            law_fx = {}
        try:
            cand_fx = _load_security_fixtures(cand_epoch_dir) or {}
        except Exception:
            cand_fx = {}
        fixtures_to_run = cand_fx if (cand_fx.get("fixtures") or []) else law_fx

    for tid in tests_plan:
        if tid == "manifest_integrity":
            okm, pm = verify_epoch_manifest(cand_epoch_dir)
            tests.append({
                "id": "manifest_integrity",
                "ok": bool(okm),
                "severity": "fail" if not okm else "info",
                "details": [str(x) for x in (pm or [])],
                "summary": "epoch_manifest.json matches file hashes" if okm else "manifest mismatch",
            })
            if not okm:
                problems.extend([f"manifest:{x}" for x in (pm or [])])
            continue

        if tid == "static_consistency":
            oks, ps = static_checks(cand_epoch_dir)
            tests.append({
                "id": "static_consistency",
                "ok": bool(oks),
                "severity": "fail" if not oks else "info",
                "details": [str(x) for x in (ps or [])],
                "summary": "policy references known streams/tools" if oks else "static policy consistency failed",
            })
            if not oks:
                problems.extend([f"static:{x}" for x in (ps or [])])
            continue

        
        if tid == "storage_policy_sanity":
            ok_sp, sp_summary, sp_problems, sp_warnings = _storage_policy_sanity_check(cand_epoch_dir)
            tests.append({
                "id": "storage_policy_sanity",
                "ok": bool(ok_sp),
                "severity": "fail" if not ok_sp else ("warn" if (sp_warnings or []) else "info"),
                "details": [str(x) for x in (sp_problems or [])] + ["warn:" + str(w) for w in (sp_warnings or [])],
                "summary": str(sp_summary),
            })
            if not ok_sp:
                problems.extend([f"storage:{x}" for x in (sp_problems or [])])
            for w in (sp_warnings or []):
                warnings.append(f"storage:{w}")
            continue

        if tid == "supply_chain_attestation":
            ok_sc, p_sc, w_sc, sc_summary = _supplychain_attestation_check(cand_epoch_dir=cand_epoch_dir, law_epoch_dir=law_epoch_dir, suite=suite)
            tests.append({
                "id": "supply_chain_attestation",
                "ok": bool(ok_sc),
                "severity": "fail" if not ok_sc else ("warn" if w_sc else "info"),
                "details": [str(x) for x in (p_sc or [])] + ["warn:" + str(x) for x in (w_sc or [])],
                "summary": f"supply-chain ok (checked={sc_summary.get('checked')})" if ok_sc else f"supply-chain failed (checked={sc_summary.get('checked')}, failed={sc_summary.get('failed')})",
            })
            if not ok_sc:
                problems.extend([f"supplychain:{x}" for x in (p_sc or [])])
            if w_sc:
                warnings.extend([f"supplychain:{x}" for x in (w_sc or [])])
            continue

        if tid == "security_fixtures_monotonicity":
            mono_ok, mono_summary, mono_problems = _fixtures_monotonicity_check(law_fx, cand_fx)
            tests.append({
                "id": "security_fixtures_monotonicity",
                "ok": bool(mono_ok),
                "severity": "fail" if not mono_ok else "info",
                "details": [str(x) for x in (mono_problems or [])],
                "summary": f"fixtures monotonic (law={mono_summary.get('law_total')}, cand={mono_summary.get('candidate_total')})" if mono_ok else "fixtures were modified/removed",
            })
            if not mono_ok:
                problems.extend([f"fixtures:{x}" for x in (mono_problems or [])])
            continue

        if tid == "security_fixtures_sample_refs":
            sr_summary, sr_problems, sr_warnings = _fixtures_sample_ref_check(cand_epoch_dir, fixtures_to_run)
            tests.append({
                "id": "security_fixtures_sample_refs",
                "ok": True if not sr_problems else False,
                "severity": "warn" if (sr_warnings or sr_problems) else "info",
                "details": [str(x) for x in (sr_problems or [])] + ["warn:" + str(x) for x in (sr_warnings or [])],
                "summary": f"fixture sample refs checked (total={sr_summary.get('total')}, missing={sr_summary.get('missing')})" if not sr_problems else "fixture sample ref check failed",
            })
            if sr_problems:
                warnings.extend([f"fixture_sample_ref:{x}" for x in (sr_problems or [])])
            if sr_warnings:
                warnings.extend([f"fixture_sample_ref:{x}" for x in (sr_warnings or [])])
            continue

        if tid == "security_fixtures_change_coverage":
            cov_ok, cov_summary, cov_problems, cov_warnings = _fixtures_change_coverage_check(
                canary_policy=law_policy or {},
                changed_files=list(changed_files),
                fixtures_doc=fixtures_to_run,
            )
            coverage_summary = cov_summary
            tests.append({
                "id": "security_fixtures_change_coverage",
                "ok": bool(cov_ok),
                "severity": "fail" if cov_problems else ("warn" if cov_warnings else "info"),
                "details": [str(x) for x in (cov_problems or [])] + ["warn:" + str(x) for x in (cov_warnings or [])],
                "summary": f"fixture coverage ok (checked={cov_summary.get('checked')}, missing={cov_summary.get('missing')})" if cov_ok else "fixture change coverage failed",
            })
            if cov_problems:
                problems.extend([f"fixtures:{x}" for x in cov_problems])
            if cov_warnings:
                warnings.extend([f"fixtures:{x}" for x in cov_warnings])
            continue

        if tid == "security_fixtures_policy":
            fixtures_summary, fixture_problems = _fixtures_policy_evaluate(cand_epoch_dir, fixtures_to_run)
            okf = int((fixtures_summary or {}).get("failed") or 0) == 0
            tests.append({
                "id": "security_fixtures_policy",
                "ok": bool(okf),
                "severity": "fail" if not okf else "info",
                "details": [str(x) for x in (fixture_problems or [])],
                "summary": "fixtures match allow/deny expectations" if okf else "fixtures mismatched",
            })
            if not okf:
                problems.extend([f"fixtures:{x}" for x in (fixture_problems or [])])
            continue

        if tid == "policy_privilege_diff":
            privilege_struct = _policy_privilege_diff_struct(base_epoch_dir, cand_epoch_dir)
            if privilege_struct:
                for rec in privilege_struct:
                    warnings.append(
                        f"privilege_widening:{rec.get('stream_id')}:{rec.get('role')}:+{','.join(rec.get('added_actions') or [])}"
                    )
                tests.append({
                    "id": "policy_privilege_diff",
                    "ok": True,
                    "severity": "warn",
                    "details": list(warnings),
                    "summary": "privilege widening detected (review recommended)",
                })
            else:
                tests.append({
                    "id": "policy_privilege_diff",
                    "ok": True,
                    "severity": "info",
                    "details": [],
                    "summary": "no privilege widening",
                })
            continue

        warnings.append(f"unknown_test:{tid}")
        tests.append({
            "id": tid,
            "ok": True,
            "severity": "warn",
            "details": [f"unknown_test:{tid}"],
            "summary": "unknown test id (skipped)",
        })

    overall_ok = len(problems) == 0
    decision = "pass" if overall_ok else "fail"

    # Log result
    if sel_append:
        evt2 = sel_append({
            "severity": "info" if overall_ok else "high",
            "type": "canary_result",
            "suite": suite,
            "ok": overall_ok,
            "problems": problems + ["warn:" + w for w in warnings],
            "base_epoch": base_id,
            "candidate_epoch": cand_id,
            "law_epoch": law_id,
        })
        sel_refs["result_evt_id"] = evt2.get("evt_id")
        sel_refs["result_sel_hash"] = evt2.get("_sel_hash")

    report: Dict[str, Any] = {
        "schema_version": "v1",
        "report_id": str(uuid.uuid4()),
        "created_at": _nowz(),
        "base_epoch_id": base_id,
        "candidate_epoch_id": cand_id,
        "law_epoch_id": law_id,
        "suite": suite,
        "first_run_forced_full": bool(forced_first_run),
        "decision": decision,
        "overall_ok": bool(overall_ok),
        "changed_files": list(changed_files),
        "tests": tests,
        "fixtures": fixtures_summary or {"total": 0, "failed": 0, "mismatches": []},
        "fixture_coverage": coverage_summary or {"checked": 0, "missing": 0, "rules_fired": []},
        "privilege_diff": privilege_struct,
        "problems": problems,
        "warnings": warnings,
        "sel_refs": sel_refs,
        "quotas_applied": quotas_applied or {},
        "resource_usage": {"wall_time_sec": float(time.time() - start_wall)},
    }

    # Update first-run record with outcome.
    if forced_first_run:
        try:
            law_policy = _load_canary_policy(law_epoch_dir)
            _canary_first_run_mark(law_policy, {"finished_at": _nowz(), "overall_ok": bool(overall_ok), "decision": decision})
        except Exception:
            pass

    return report


# === NoemaForge Autodoc Function Header ===
# Function: canary_checks(base_epoch_dir: str, cand_epoch_dir: str, law_epoch_dir: Optional[str] = None, suite: str)
# Purpose: Run canary suite (pre-start only).
# Inputs:
#   - base_epoch_dir: str
#   - cand_epoch_dir: str
#   - law_epoch_dir: Optional[str] = None
#   - suite: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - canary_run_report, list, bool, get
# Returns / emits: Tuple[bool, List[str]]
# Side effects:
#   - spawns subprocesses or workers
# Key locals:
#   - flat, rep
# === End NoemaForge Autodoc Function Header ===
def canary_checks(
    *,
    base_epoch_dir: str,
    cand_epoch_dir: str,
    law_epoch_dir: Optional[str] = None,
    suite: str,
) -> Tuple[bool, List[str]]:
    """Run canary suite (pre-start only).

    Compatibility wrapper returning (ok, flat_problems).
    """
    rep = canary_run_report(base_epoch_dir=base_epoch_dir, cand_epoch_dir=cand_epoch_dir, law_epoch_dir=law_epoch_dir, suite=suite)
    flat = list(rep.get("problems") or []) + ["warn:" + w for w in (rep.get("warnings") or [])]
    return bool(rep.get("overall_ok")), flat


# === NoemaForge Autodoc Function Header ===
# Function: scary_select_suite_for_candidate(contracts_root: str, candidate_epoch_id: str, approved_requests: List[RequestRecord])
# Purpose: Compute minimum suite per Scary Core, using current epoch policy as law.
# Inputs:
#   - contracts_root: str
#   - candidate_epoch_id: str
#   - approved_requests: List[RequestRecord]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - current_epoch_id, epoch_path, _load_canary_policy, _scary_required_suite
# Returns / emits: Tuple[str, Dict[str, Any]]
# Key locals:
#   - base_dir, base_id, cand_dir, policy, suite
# === End NoemaForge Autodoc Function Header ===
def scary_select_suite_for_candidate(
    *,
    contracts_root: str,
    candidate_epoch_id: str,
    approved_requests: List[RequestRecord],
) -> Tuple[str, Dict[str, Any]]:
    """Compute minimum suite per Scary Core, using current epoch policy as law."""

    base_id = current_epoch_id(contracts_root)
    base_dir = epoch_path(base_id, contracts_root)
    cand_dir = epoch_path(candidate_epoch_id, contracts_root)

    policy = _load_canary_policy(base_dir)
    suite = _scary_required_suite(base_epoch_dir=base_dir, cand_epoch_dir=cand_dir, approved_requests=approved_requests)

    return suite, policy
