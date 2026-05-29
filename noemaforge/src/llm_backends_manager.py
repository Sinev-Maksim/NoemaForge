#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/llm_backends_manager.py
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
# File: src/llm_backends_manager.py
# Purpose: Single-active-model backend manager for NoemaForge llama-server instances.
# Version: 0.28.13 runtime_desired_count invariant hotfix.
# Invoked by:
#   - noemaforge-llm-backends-manager.service
#   - sudo noemaforge manager reconcile
# Inputs:
#   - --reconcile
#   - --plan
#   - --runtime-desired-count N
#   - Policy: /var/lib/noemaforge/contracts/.../llm-backends-policy.yaml or /opt/noemaforge/configs/llm-backends-policy.yaml
# Output:
#   - YAML summary to stdout; systemd starts/stops noemaforge-llama@*.service unless --plan.
# Safety invariant:
#   - Runtime Desired Count defaults to 1.
#   - More models may exist in inventory/modelstore/role shortlists, but at most runtime_desired_count llama backends may be active.
#   - TODO(parallel-model-runtime): future releases may support runtime_desired_count > 1 with explicit resource scheduling.
# === End NoemaForge Autodoc File Header ===

"""NoemaForge LLM Backends Manager.

This manager intentionally separates *available* models from *desired runtime*
models:

- Inventory / ModelStore may contain many safe models.
- Role tournaments may rank top-k models per role.
- Runtime desired state is limited by `runtime_desired_count`, default 1.

The invariant is conservative on purpose: never start a fleet of LLM backends
just because many safe model artifacts are available.  Parallel model runtime is
kept as an explicit TODO/future mode, not an accidental behaviour.
"""


import argparse
import os
import re
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple

import yaml

try:
    import runtime_safety
except Exception:  # pragma: no cover
    runtime_safety = None  # type: ignore

try:
    from seclog import append as sel_append
except Exception:  # pragma: no cover
    sel_append = None  # type: ignore


DEFAULT_CONTRACTS_ROOT = os.environ.get("NOEMAFORGE_CONTRACTS_ROOT", "/var/lib/noemaforge/contracts")
DEFAULT_POLICY_FALLBACK = "/opt/noemaforge/configs/llm-backends-policy.yaml"
DEFAULT_SOCK_DIR = "/run/noemaforge/llm/backends"
DEFAULT_MODELSTORE_ROOT = os.environ.get("NOEMAFORGE_MODELSTORE_ROOT", "/var/lib/modelstore")
DEFAULT_RUNTIME_DESIRED_COUNT = int(os.environ.get("NOEMAFORGE_RUNTIME_DESIRED_COUNT", "1"))

_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,120}$")
_UNIT_RE = re.compile(r"^noemaforge-llama@(.+)\.service$")


def _safe_id(s: str) -> bool:
    return bool(_SAFE_ID_RE.match(str(s or "").strip()))


def _load_yaml(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _evt(kind: str, msg: str, extra: Dict[str, Any]) -> None:
    if not sel_append:
        return
    try:
        sel_append({"ts": time.time(), "kind": kind, "msg": msg, "extra": extra})
    except Exception:
        pass


def _current_epoch_dir() -> str:
    try:
        import prestart  # type: ignore
        eid = prestart.current_epoch_id(DEFAULT_CONTRACTS_ROOT)
        return prestart.epoch_path(eid, DEFAULT_CONTRACTS_ROOT)
    except Exception:
        return os.path.join(DEFAULT_CONTRACTS_ROOT, "epochs", "current")


def _policy_path() -> str:
    p = os.path.join(_current_epoch_dir(), "llm-backends-policy.yaml")
    if os.path.exists(p):
        return p
    return DEFAULT_POLICY_FALLBACK


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(str(value).strip())
    except Exception:
        return default


def _runtime_desired_count(pol: Dict[str, Any], override: Optional[int] = None) -> int:
    """Return the allowed number of simultaneously active LLM backends.

    This is intentionally *not* `len(modelstore)` and not `safe_count`.
    Default is 1.  Parallel model runtime is a TODO, not an implicit mode.
    """
    if override is not None:
        raw = override
    else:
        defaults = pol.get("defaults") or {}
        raw = (
            os.environ.get("NOEMAFORGE_RUNTIME_DESIRED_COUNT")
            or defaults.get("runtime_desired_count")
            or defaults.get("runtime_desired_backends")
            or defaults.get("max_active_backends")
            or DEFAULT_RUNTIME_DESIRED_COUNT
        )
    n = _coerce_int(raw, 1)
    if n < 0:
        n = 0
    # Keep future parallel mode bounded even when explicitly requested.
    if n > 8:
        n = 8
    return n


def _preferred_backend_id(pol: Dict[str, Any]) -> str:
    defaults = pol.get("defaults") or {}
    return str(defaults.get("preferred_backend_id") or defaults.get("primary_backend_id") or "main").strip() or "main"


def _desired_backends(pol: Dict[str, Any]) -> List[Dict[str, Any]]:
    defaults = pol.get("defaults") or {}
    enforce_main = bool(defaults.get("enforce_main_present", True))
    out: List[Dict[str, Any]] = []

    for b in (pol.get("backends") or []) or []:
        rec = dict(b or {})
        bid = str(rec.get("id") or "").strip()
        mid = str(rec.get("model_id") or bid).strip()
        en = bool(rec.get("enabled", True))
        if not en:
            continue
        if not bid or not _safe_id(bid) or not _safe_id(mid):
            continue
        if runtime_safety is not None:
            if not runtime_safety.safe_backend_id(bid) or not runtime_safety.safe_backend_id(mid):
                _evt("backend_policy_blocked", "blocked unsafe non-head backend id from policy", {"backend_id": bid, "model_id": mid})
                continue
        rec["id"] = bid
        rec["model_id"] = mid
        out.append(rec)

    if enforce_main and not any(x.get("id") == "main" for x in out):
        out.insert(0, {"id": "main", "model_id": "main", "enabled": True, "mode": "cpu", "notes": "auto-inserted main"})

    return out


def _select_active_desired(pol: Dict[str, Any], desired_all: List[Dict[str, Any]], runtime_count: int) -> List[Dict[str, Any]]:
    if runtime_count <= 0:
        return []

    preferred = _preferred_backend_id(pol)
    ordered = list(desired_all)

    # In single-active mode, prefer `main`/preferred backend even if an epoch
    # policy contains a long enabled list.  Other entries remain candidates, not
    # active runtime targets.
    if runtime_count == 1:
        for i, rec in enumerate(ordered):
            if rec.get("id") == preferred:
                ordered.insert(0, ordered.pop(i))
                break

    return ordered[:runtime_count]


def _systemctl(args: List[str]) -> Tuple[int, str]:
    try:
        out = subprocess.check_output(["systemctl"] + args, stderr=subprocess.STDOUT)
        return 0, out.decode("utf-8", errors="replace")
    except subprocess.CalledProcessError as e:
        return int(e.returncode), (e.output or b"").decode("utf-8", errors="replace")
    except Exception as e:
        return 1, repr(e)


def _running_llama_units() -> List[Dict[str, str]]:
    rc, out = _systemctl(["list-units", "--all", "--plain", "--no-legend", "noemaforge-llama@*.service"])
    units: List[Dict[str, str]] = []
    if rc != 0:
        return units
    for line in out.splitlines():
        parts = line.split(None, 4)
        if not parts:
            continue
        unit = parts[0]
        m = _UNIT_RE.match(unit)
        if not m:
            continue
        units.append({
            "unit": unit,
            "backend_id": m.group(1),
            "load": parts[1] if len(parts) > 1 else "",
            "active": parts[2] if len(parts) > 2 else "",
            "sub": parts[3] if len(parts) > 3 else "",
        })
    return units


def _wait_for_socket(path: str, timeout_sec: float = 20.0) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout_sec:
        if os.path.exists(path):
            return True
        time.sleep(0.2)
    return False


def _validate_backend(bid: str) -> Tuple[bool, str, Dict[str, Any]]:
    if runtime_safety is None:
        return True, "runtime_safety_unavailable", {}
    return runtime_safety.validate_modelstore_backend(DEFAULT_MODELSTORE_ROOT, bid)


def reconcile(*, stop_extra: bool = True, runtime_desired_count: Optional[int] = None, plan: bool = False) -> Dict[str, Any]:
    pol_path = _policy_path()
    try:
        pol = _load_yaml(pol_path)
    except Exception:
        pol = {}

    desired_all = _desired_backends(pol)
    desired_count = _runtime_desired_count(pol, runtime_desired_count)
    desired_active = _select_active_desired(pol, desired_all, desired_count)
    desired_ids = [str(x.get("id")) for x in desired_active if str(x.get("id") or "").strip()]
    desired_all_ids = [str(x.get("id")) for x in desired_all if str(x.get("id") or "").strip()]

    running_before = _running_llama_units()
    running_before_ids = [x["backend_id"] for x in running_before]

    started: List[str] = []
    failed: List[Dict[str, Any]] = []
    blocked: List[Dict[str, Any]] = []
    stopped: List[Dict[str, Any]] = []
    would_stop: List[Dict[str, Any]] = []
    would_start: List[str] = []

    # Enforce the runtime_desired_count invariant by stopping anything outside
    # desired_ids.  This is the key difference from earlier versions where
    # ModelStore availability could accidentally become runtime desired state.
    if stop_extra:
        for rec in running_before:
            bid = rec["backend_id"]
            invalid = False
            reason = "not_desired"
            if runtime_safety is not None:
                ok_safe, r, _ = _validate_backend(bid)
                invalid = not ok_safe
                if invalid:
                    reason = f"runtime_safety:{r}"
            if bid in desired_ids and not invalid:
                continue
            item = {"backend_id": bid, "unit": rec["unit"], "reason": reason, "active": rec.get("active", "")}
            if plan:
                would_stop.append(item)
                continue
            rc, out = _systemctl(["stop", rec["unit"]])
            item["status"] = "stopped" if rc == 0 else "stop_failed"
            if rc != 0:
                item["error"] = out.strip()[:2000]
            stopped.append(item)
            _evt("backend_stopped_extra", "stopped backend outside runtime desired set", item)

    for bid in desired_ids:
        ok_safe, reason, meta = _validate_backend(bid)
        if not ok_safe:
            blocked.append({"backend_id": bid, "reason": reason, "meta": meta})
            _evt("backend_start_blocked_runtime_safety", "blocked backend before start", {"backend_id": bid, "reason": reason})
            continue
        unit = f"noemaforge-llama@{bid}.service"
        if plan:
            would_start.append(bid)
            continue
        rc, out = _systemctl(["start", unit])
        if rc != 0:
            failed.append({"backend_id": bid, "unit": unit, "error": out.strip()[:4000]})
            _evt("backend_start_failed", "failed to start backend", {"backend_id": bid, "unit": unit})
            continue
        sock = os.path.join(DEFAULT_SOCK_DIR, f"{bid}.sock")
        ok = _wait_for_socket(sock, timeout_sec=20.0)
        started.append(bid)
        _evt("backend_started", "backend started or confirmed", {"backend_id": bid, "unit": unit, "sock_ready": ok})

    running_after = _running_llama_units() if not plan else running_before
    active_after = [x for x in running_after if x.get("active") == "active"]
    active_after_ids = [x["backend_id"] for x in active_after]

    invariant_ok = len(active_after_ids) <= desired_count if not plan else True
    if not invariant_ok:
        failed.append({
            "backend_id": "runtime_desired_count",
            "unit": "noemaforge-llama@*.service",
            "error": f"active backends {active_after_ids} exceed runtime_desired_count={desired_count}",
        })

    deferred_by_runtime_limit = [x for x in desired_all_ids if x not in desired_ids]

    summary = {
        "ok": len(failed) == 0 and invariant_ok,
        "policy_path": pol_path,
        "runtime_desired_count": desired_count,
        "preferred_backend_id": _preferred_backend_id(pol),
        "desired_all": desired_all_ids,
        "desired_active": desired_ids,
        "deferred_by_runtime_limit": deferred_by_runtime_limit,
        "running_before": running_before,
        "running_after": running_after,
        "active_after": active_after_ids,
        "started": started,
        "failed": failed,
        "blocked": blocked,
        "stopped": stopped,
        "would_stop": would_stop,
        "would_start": would_start,
        "stop_extra": stop_extra,
        "plan": plan,
        "invariant": "single-active-model unless runtime_desired_count explicitly changed",
        "todo": "parallel-model-runtime requires explicit scheduler/resource guard; do not infer from ModelStore safe_count",
    }
    _evt("backends_reconcile", "reconciled backends with runtime desired count", summary)
    return summary


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reconcile", action="store_true", help="reconcile backends once (default)")
    ap.add_argument("--stop-extra", action="store_true", default=True, help="stop backends outside runtime desired set (default)")
    ap.add_argument("--no-stop-extra", action="store_true", help="diagnostic only: do not stop extra backends")
    ap.add_argument("--runtime-desired-count", type=int, default=None, help="max simultaneously active llama backends; default/policy is 1")
    ap.add_argument("--plan", "--dry-run", action="store_true", help="print start/stop plan without changing services")
    args = ap.parse_args()

    res = reconcile(
        stop_extra=not bool(args.no_stop_extra),
        runtime_desired_count=args.runtime_desired_count,
        plan=bool(args.plan),
    )
    print(yaml.safe_dump(res, sort_keys=False, allow_unicode=True))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
