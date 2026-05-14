#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/firstboot_eval.py
Zone: release/package
Version: 0.31.13.alpha
Created: 2026-05-14
Modified: 2026-05-14
Purpose: Coordinate first-start model inventory, tournament, staffing and epoch safety checks.
Inputs: Command-line arguments, environment variables, package files and local NoemaForge runtime state as applicable.
Outputs: Structured command output, files, service state or UI state as documented by the caller.
Side effects: Limited to the documented NoemaForge paths, runtime state directories or systemd units used by this file.
Tests: Syntax validation plus the release setup selftest, consistency-audit and targeted smoke checks.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations


# === NoemaForge Autodoc File Header ===
# File: src/firstboot_eval.py
# Purpose: Provide the module 'firstboot_eval'.
# Invoked by / imported from:
#   - src/brainctl.py
# Public API / entry functions:
#   - run
#   - main
# Inputs:
#   - --force
#   - --no-all
#   - --top-k
#   - Environment: NOEMAFORGE_CONTRACTS_ROOT
#   - Common path inputs: /var/lib/noemaforge/.sys/firstboot-model-eval.done, /var/lib/noemaforge/requests/prestart, /workspace/outbox/installer-plan, /var/lib/noemaforge/contracts, /var/lib/modelstore/model_registry.json, /var/lib/noemaforge/model_scorecards, /run/noemaforge/llm/gateway.sock, /run/noemaforge/llm/backends/main.sock
#   - Imports: __future__, argparse, os, time, uuid, typing, yaml, model_registry
# Output formats / side effects:
#   - YAML files
#   - JSON files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""firstboot_eval.py (v0.11.2)

First-boot exception: bootstrap evaluation for the model fleet.

Context
-------
NoemaForge prefers:
- no canaries during runtime
- epoch changes only during PRE-START

But on a truly first boot you often have a chicken-and-egg problem:
you need *some* backend running to evaluate models and propose a clean pre-start plan.

This script is a *one-shot* helper that runs after services are up, once per install:
- it updates ModelStore registry
- ensures at least 'main' backend is started
- optionally starts additional backends temporarily to run scorecards
- writes scorecards (state)
- emits a draft PreStartChangeRequest that suggests:
    - role-model candidates based on scorecards
    - which backends to enable in the next epoch

It does NOT switch epochs and does NOT modify contracts directly.

Safety posture
--------------
- Runs as root via a locked-down systemd oneshot unit.
- Creates a marker file to ensure one-time execution.
- Default: enable-only plan (no disabling anything).
"""


import argparse
import os
import time
import uuid
from typing import Any, Dict, List, Tuple

import yaml

import model_registry
import model_scorecards
import model_installer_plan

try:
    import runtime_safety
except Exception:  # pragma: no cover
    runtime_safety = None  # type: ignore

try:
    from seclog import append as sel_append
except Exception:  # pragma: no cover
    sel_append = None  # type: ignore


DEFAULT_MARKER = "/var/lib/noemaforge/.sys/firstboot-model-eval.done"
DEFAULT_REQUESTS_DIR = "/var/lib/noemaforge/requests/prestart"
DEFAULT_OUTBOX_DIR = "/workspace/outbox/installer-plan"
DEFAULT_CONTRACTS_ROOT = os.environ.get("NOEMAFORGE_CONTRACTS_ROOT", "/var/lib/noemaforge/contracts")
DEFAULT_ROLE_DATASETS = os.environ.get("NOEMAFORGE_ROLE_EVAL_DATASETS", "/opt/noemaforge/configs/role-eval-datasets.yaml")


def _role_eval_dataset_candidates() -> List[str]:
    here = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", "configs", "role-eval-datasets.yaml"))
    return [DEFAULT_ROLE_DATASETS, here]


def default_eval_surface() -> List[Tuple[str, str]]:
    """Return the default first-boot role surface for model selection.

    The surface is loaded from the role-eval dataset catalog so that the legacy helper
    and the firstboot orchestrator operate on the same declared role inventory.
    """
    for cand in _role_eval_dataset_candidates():
        try:
            if not os.path.exists(cand):
                continue
            with open(cand, 'r', encoding='utf-8') as f:
                doc = yaml.safe_load(f) or {}
            roles = []
            for key in sorted((doc.get('roles') or {}).keys()):
                if '/' not in str(key):
                    continue
                stream_id, role = str(key).split('/', 1)
                roles.append((stream_id, role))
            if roles:
                return roles
        except Exception:
            continue
    return [
        ("operator.admin", "administrator"),
        ("dev.work", "executor"),
        ("system.guard", "surgeon"),
    ]


# === NoemaForge Autodoc Function Header ===
# Function: _evt(kind: str, msg: str, extra: Dict[str, Any])
# Purpose: Implement the routine ' evt'.
# Inputs:
#   - kind: str
#   - msg: str
#   - extra: Dict[str, Any]
# Called by:
#   - src/bundles.py
#   - src/llm_backends_manager.py
#   - src/localgateway.py
#   - src/nids_lite.py
#   - src/toolproxy.py
#   - src/webgateway.py
# Calls:
#   - sel_append, time
# Returns / emits: None
# Side effects:
#   - appends to logs or files
# === End NoemaForge Autodoc Function Header ===
def _evt(kind: str, msg: str, extra: Dict[str, Any]) -> None:
    if not sel_append:
        return
    try:
        sel_append({"ts": time.time(), "kind": kind, "msg": msg, "extra": extra})
    except Exception:
        pass


# === NoemaForge Autodoc Function Header ===
# Function: _current_epoch_dir()
# Purpose: Implement the routine ' current epoch dir'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - src/llm_backends_manager.py
#   - src/role_runner.py
# Calls:
#   - current_epoch_id, epoch_path, join
# Returns / emits: str
# Key locals:
#   - eid
# === End NoemaForge Autodoc Function Header ===
def _current_epoch_dir() -> str:
    try:
        import prestart  # type: ignore
        eid = prestart.current_epoch_id(DEFAULT_CONTRACTS_ROOT)
        return prestart.epoch_path(eid, DEFAULT_CONTRACTS_ROOT)
    except Exception:
        return os.path.join(DEFAULT_CONTRACTS_ROOT, "epochs", "current")


# === NoemaForge Autodoc Function Header ===
# Function: _wait_for_socket(path: str, timeout_sec: float = 25.0)
# Purpose: Implement the routine ' wait for socket'.
# Inputs:
#   - path: str
#   - timeout_sec: float = 25.0
# Called by:
#   - src/llm_backends_manager.py
# Calls:
#   - time, exists, sleep
# Returns / emits: bool
# Key locals:
#   - t0
# === End NoemaForge Autodoc Function Header ===
def _wait_for_socket(path: str, timeout_sec: float = 25.0) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout_sec:
        if os.path.exists(path):
            return True
        time.sleep(0.2)
    return False


# === NoemaForge Autodoc Function Header ===
# Function: _systemctl(args: List[str])
# Purpose: Implement the routine ' systemctl'.
# Inputs:
#   - args: List[str]
# Called by:
#   - src/llm_backends_manager.py
# Calls:
#   - check_call
# Returns / emits: bool
# === End NoemaForge Autodoc Function Header ===
def _systemctl(args: List[str]) -> bool:
    import subprocess
    try:
        subprocess.check_call(["systemctl"] + args)
        return True
    except Exception:
        return False


# === NoemaForge Autodoc Function Header ===
# Function: run(marker_path: str = DEFAULT_MARKER, registry_path: str = '/var/lib/modelstore/model_registry.json', scorecards_dir: str = '/var/lib/noemaforge/model_scorecards', gateway_sock: str = '/run/noemaforge/llm/gateway.sock', outbox_dir: str = DEFAULT_OUTBOX_DIR, requests_dir: str = DEFAULT_REQUESTS_DIR, eval_all_models: bool = True, top_k: int = 2)
# Purpose: Implement the routine 'run'.
# Inputs:
#   - marker_path: str = DEFAULT_MARKER
#   - registry_path: str = '/var/lib/modelstore/model_registry.json'
#   - scorecards_dir: str = '/var/lib/noemaforge/model_scorecards'
#   - gateway_sock: str = '/run/noemaforge/llm/gateway.sock'
#   - outbox_dir: str = DEFAULT_OUTBOX_DIR
#   - requests_dir: str = DEFAULT_REQUESTS_DIR
#   - eval_all_models: bool = True
#   - top_k: int = 2
# Called by:
#   - src/bootdoctor.py
#   - src/brainctl.py
#   - src/hwscan.py
#   - src/knowledge_maintainer.py
#   - src/lan_discovery.py
#   - src/localgateway.py
#   - src/localgw_connectors/ipp.py
#   - src/lsm.py
# Calls:
#   - exists, makedirs, update_registry, load_registry, _evt, _systemctl, _wait_for_socket, _current_epoch_dir, join, propose_policy_patches, make_prestart_request, chmod
# Returns / emits: Dict[str, Any]
# Side effects:
#   - creates directories
# Key locals:
#   - epoch_dir, eval_surface, f, llm_backends_policy_path, mid, models, patches, q_path, ran, reg, req, req_path
# === End NoemaForge Autodoc Function Header ===
def run(
    *,
    marker_path: str = DEFAULT_MARKER,
    registry_path: str = "/var/lib/modelstore/model_registry.json",
    scorecards_dir: str = "/var/lib/noemaforge/model_scorecards",
    gateway_sock: str = "/run/noemaforge/llm/gateway.sock",
    outbox_dir: str = DEFAULT_OUTBOX_DIR,
    requests_dir: str = DEFAULT_REQUESTS_DIR,
    eval_all_models: bool = True,
    top_k: int = 2,
) -> Dict[str, Any]:
    if os.path.exists(marker_path):
        return {"ok": True, "skipped": True, "reason": "marker_exists", "marker": marker_path}

    os.makedirs(os.path.dirname(marker_path), exist_ok=True)
    os.makedirs(outbox_dir, exist_ok=True)
    os.makedirs(requests_dir, exist_ok=True)

    # 1) Update ModelStore registry
    changed, summary = model_registry.update_registry(registry_path=registry_path, emit_sel=True)
    reg = model_registry.load_registry(registry_path)

    raw_models = [str(m.get("model_id") or "") for m in (reg.get("models") or []) if str(m.get("model_id") or "").strip()]
    models: List[str] = []
    blocked_models: List[Dict[str, Any]] = []
    for mid in raw_models:
        if runtime_safety is not None:
            ok_safe, reason, meta = runtime_safety.validate_modelstore_backend("/var/lib/modelstore", mid)
            if not ok_safe:
                blocked_models.append({"model_id": mid, "reason": reason, "meta": meta})
                continue
        models.append(mid)

    _evt("firstboot_eval_registry", "model registry refreshed", {"changed": changed, "models": models, "blocked_models": blocked_models})

    # 2) Ensure baseline backend
    _systemctl(["start", "noemaforge-llama@main.service"])
    _wait_for_socket("/run/noemaforge/llm/backends/main.sock", timeout_sec=25.0)

    # 3) Evaluate models (scorecards)
    epoch_dir = _current_epoch_dir()
    eval_surface: List[Tuple[str, str]] = default_eval_surface()

    ran: List[Dict[str, Any]] = []
    for mid in models:
        if (not eval_all_models) and mid != "main":
            continue

        # Start backend for this model if absent (firstboot exception).
        if runtime_safety is not None:
            ok_safe, reason, meta = runtime_safety.validate_modelstore_backend("/var/lib/modelstore", mid)
            if not ok_safe:
                ran.append({"model": mid, "ok": False, "error": f"runtime_safety_blocked:{reason}", "meta": meta})
                continue
        sock = f"/run/noemaforge/llm/backends/{mid}.sock"
        if not os.path.exists(sock):
            _systemctl(["start", f"noemaforge-llama@{mid}.service"])
            _wait_for_socket(sock, timeout_sec=25.0)

        for stream_id, role in eval_surface:
            # First time: use FULL; otherwise SMOKE.
            sc_path = os.path.join(scorecards_dir, mid, f"{stream_id.replace('/','_')}__{role.replace('/','_')}__llm.json")
            suite = "full" if not os.path.exists(sc_path) else "smoke"
            try:
                res = model_scorecards.run_scorecard(
                    epoch_dir=epoch_dir,
                    model_id=mid,
                    stream_id=stream_id,
                    role=role,
                    cap="llm",
                    suite=suite,
                    gateway_socket=gateway_sock,
                    scorecards_dir=scorecards_dir,
                    emit_sel=True,
                )
                ran.append({"model": mid, "stream": stream_id, "role": role, "suite": suite, "ok": bool(res.get("ok", True)), "quality_score": res.get("quality_score")})
            except Exception as e:
                ran.append({"model": mid, "stream": stream_id, "role": role, "suite": suite, "ok": False, "error": repr(e)})

    _evt("firstboot_eval_scorecards", "scorecards computed", {"ran": ran})

    # 4) Propose pre-start patches (draft request)
    role_model_policy_path = os.path.join(epoch_dir, "role-model-policy.yaml")
    llm_backends_policy_path = os.path.join(epoch_dir, "llm-backends-policy.yaml")
    if not os.path.exists(llm_backends_policy_path):
        llm_backends_policy_path = "/opt/noemaforge/configs/llm-backends-policy.yaml"

    patches = model_installer_plan.propose_policy_patches(
        role_model_policy_path=role_model_policy_path,
        llm_backends_policy_path=llm_backends_policy_path,
        registry_path=registry_path,
        scorecards_dir=scorecards_dir,
        roles_to_consider=eval_surface,
        top_k=top_k,
    )

    rid = f"firstboot-{time.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    req = model_installer_plan.make_prestart_request(
        request_id=rid,
        created_by={"actor_type": "system", "actor_id": "firstboot_eval"},
        track="policy",
        patches=patches,
        user_comment="First-boot model fleet proposal (draft). Review in PRE-START.",
    )

    req_path = os.path.join(outbox_dir, f"{rid}.prestart_request.yaml")
    with open(req_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(req, f, sort_keys=False, allow_unicode=True)

    # Also drop into requests queue as DRAFT (will not be applied until approved)
    q_path = os.path.join(requests_dir, f"{rid}.yaml")
    with open(q_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(req, f, sort_keys=False, allow_unicode=True)

    _evt("firstboot_eval_plan", "draft pre-start request written", {"outbox": req_path, "queue": q_path, "picked_models": patches.get("picked_models")})

    # 5) Mark done
    with open(marker_path, "w", encoding="utf-8") as f:
        f.write("done\n")
    os.chmod(marker_path, 0o600)

    return {
        "ok": True,
        "models": models,
        "ran": ran,
        "request_outbox": req_path,
        "request_queue": q_path,
        "marker": marker_path,
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
#   - ArgumentParser, add_argument, parse_args, run, print, exists, safe_dump, get, remove, int, bool
# Returns / emits: int
# Side effects:
#   - serializes structured data
#   - spawns subprocesses or workers
# Key locals:
#   - ap, args, marker, res
# === End NoemaForge Autodoc Function Header ===
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="ignore marker and run anyway")
    ap.add_argument("--no-all", action="store_true", help="only evaluate main model")
    ap.add_argument("--top-k", type=int, default=2)
    args = ap.parse_args()

    marker = DEFAULT_MARKER
    if args.force and os.path.exists(marker):
        try:
            os.remove(marker)
        except Exception:
            pass

    res = run(eval_all_models=not bool(args.no_all), top_k=int(args.top_k))
    print(yaml.safe_dump(res, sort_keys=False, allow_unicode=True))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
