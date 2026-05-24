#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/resource_recovery.py
Zone: release/package
Version: 0.31.13.alpha-patched1
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
# File: src/resource_recovery.py
# Purpose: Provide the module 'resource_recovery'.
# Invoked by / imported from:
#   - src/maintenance.py
# Public API / entry functions:
#   - cleanup
#   - main
# Inputs:
#   - Common path inputs: /var/lib/noemaforge, /run/noemaforge/llm/backends, /opt/noemaforge/configs/llm-backends-policy.yaml
#   - Imports: __future__, datetime, os, subprocess, typing, epoch, yaml, shutil
# Output formats / side effects:
#   - YAML files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""resource_recovery.py (v0.11.5)

Post-SR resource recovery.

Why:
- SR/SSR can transiently create workdirs, tokens, helper processes.
- After the idle-cycle we want a "cool-down": free RAM, reduce background churn.

In MVP we do:
- Remove old RoleRunner workdirs
- Remove old capability tokens
- (Optional) Stop *extra* LLM backends not enabled by the current epoch policy

We avoid risky operations like dropping kernel caches.
"""


import datetime as dt
import os
import subprocess
from typing import Any, Dict, List, Optional

import epoch

BASE = "/var/lib/noemaforge"
ROLE_WORKDIR = os.path.join(BASE, "roles", "work")
TOKENS_DIR = os.path.join(BASE, "tokens")

# Runtime sockets (backends expose /run/noemaforge/llm/backends/<id>.sock)
BACKENDS_SOCK_DIR = "/run/noemaforge/llm/backends"


# === NoemaForge Autodoc Function Header ===
# Function: _now()
# Purpose: Implement the routine ' now'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - src/bootdoctor.py
#   - src/flow_metrics.py
#   - src/localgw_ratelimit.py
#   - src/storage_broker.py
#   - tools/autodoc_inject_misc.py
# Calls:
#   - timestamp, utcnow
# Returns / emits: float
# === End NoemaForge Autodoc Function Header ===
def _now() -> float:
    return dt.datetime.utcnow().timestamp()


# === NoemaForge Autodoc Function Header ===
# Function: _age_sec(path: str)
# Purpose: Implement the routine ' age sec'.
# Inputs:
#   - path: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - stat, _now, float
# Returns / emits: Optional[float]
# Key locals:
#   - st
# === End NoemaForge Autodoc Function Header ===
def _age_sec(path: str) -> Optional[float]:
    try:
        st = os.stat(path)
        return _now() - float(st.st_mtime)
    except Exception:
        return None


# === NoemaForge Autodoc Function Header ===
# Function: _cleanup_dir(root: str, max_age_sec: int)
# Purpose: Implement the routine ' cleanup dir'.
# Inputs:
#   - root: str
#   - max_age_sec: int
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - listdir, isdir, join, _age_sec, float, rmtree, remove
# Returns / emits: int
# Key locals:
#   - age, name, p, removed
# === End NoemaForge Autodoc Function Header ===
def _cleanup_dir(root: str, max_age_sec: int) -> int:
    removed = 0
    if not os.path.isdir(root):
        return 0
    for name in os.listdir(root):
        p = os.path.join(root, name)
        age = _age_sec(p)
        if age is None:
            continue
        if age >= float(max_age_sec):
            try:
                if os.path.isdir(p):
                    import shutil

                    shutil.rmtree(p, ignore_errors=True)
                else:
                    os.remove(p)
                removed += 1
            except Exception:
                continue
    return removed


# === NoemaForge Autodoc Function Header ===
# Function: _load_policy_enabled_backends()
# Purpose: Return backend IDs that are enabled in the current epoch policy.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - current_epoch_dir, append, set, join, add, exists, safe_load, strip, open, get, isinstance, bool
# Returns / emits: List[str]
# Side effects:
#   - reads or writes files
#   - appends to logs or files
# Key locals:
#   - b, bid, candidates, e_dir, obj, out, p, paths, seen, x
# === End NoemaForge Autodoc Function Header ===
def _load_policy_enabled_backends() -> List[str]:
    """Return backend IDs that are enabled in the current epoch policy."""
    e_dir = epoch.current_epoch_dir()
    candidates: List[str] = []
    paths = []
    if e_dir:
        paths.append(os.path.join(e_dir, "llm-backends-policy.yaml"))
    paths.append("/opt/noemaforge/configs/llm-backends-policy.yaml")

    try:
        import yaml

        for p in paths:
            if not os.path.exists(p):
                continue
            obj = yaml.safe_load(open(p, "r", encoding="utf-8")) or {}
            for b in (obj.get("backends") or []) or []:
                if not isinstance(b, dict):
                    continue
                bid = str(b.get("id") or "").strip()
                if bid and bool(b.get("enabled", False)):
                    candidates.append(bid)
            if candidates:
                break
    except Exception:
        pass

    # Always keep 'main' if present.
    if "main" not in candidates:
        candidates.append("main")

    # stable dedup
    seen = set()
    out: List[str] = []
    for x in candidates:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


# === NoemaForge Autodoc Function Header ===
# Function: _list_active_backend_ids(sock_dir: str = BACKENDS_SOCK_DIR)
# Purpose: Implement the routine ' list active backend ids'.
# Inputs:
#   - sock_dir: str = BACKENDS_SOCK_DIR
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - sort, listdir, isdir, endswith, append
# Returns / emits: List[str]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - bid, fn, out
# === End NoemaForge Autodoc Function Header ===
def _list_active_backend_ids(sock_dir: str = BACKENDS_SOCK_DIR) -> List[str]:
    out: List[str] = []
    try:
        if not os.path.isdir(sock_dir):
            return out
        for fn in os.listdir(sock_dir):
            if fn.endswith(".sock"):
                bid = fn[:-5]
                if bid:
                    out.append(bid)
    except Exception:
        return out
    out.sort()
    return out


# === NoemaForge Autodoc Function Header ===
# Function: _stop_backend(bid: str)
# Purpose: Stop backend service best-effort.
# Inputs:
#   - bid: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - run
# Returns / emits: bool
# Side effects:
#   - spawns subprocesses or workers
# Key locals:
#   - p, unit
# === End NoemaForge Autodoc Function Header ===
def _stop_backend(bid: str) -> bool:
    """Stop backend service best-effort."""
    # In real system we run under systemd. If not available, just return False.
    unit = f"noemaforge-llama@{bid}.service"
    try:
        p = subprocess.run(["/usr/bin/systemctl", "stop", unit], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return p.returncode == 0
    except Exception:
        return False


# === NoemaForge Autodoc Function Header ===
# Function: cleanup(max_work_age_sec: int = 3600, max_token_age_sec: int = 86400, stop_extra_backends: bool = False, keep_backends: Optional[List[str]] = None)
# Purpose: Cleanup transient resources and optionally unload extra model backends.
# Inputs:
#   - max_work_age_sec: int = 3600
#   - max_token_age_sec: int = 86400
#   - stop_extra_backends: bool = False
#   - keep_backends: Optional[List[str]] = None
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _cleanup_dir, int, list, _list_active_backend_ids, bool, _load_policy_enabled_backends, _stop_backend, append
# Returns / emits: Dict[str, Any]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - active, bid, keep, kept, rem_tok, rem_work, stopped
# === End NoemaForge Autodoc Function Header ===
def cleanup(
    *,
    max_work_age_sec: int = 3600,
    max_token_age_sec: int = 86400,
    stop_extra_backends: bool = False,
    keep_backends: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Cleanup transient resources and optionally unload extra model backends."""
    rem_work = _cleanup_dir(ROLE_WORKDIR, int(max_work_age_sec))
    rem_tok = _cleanup_dir(TOKENS_DIR, int(max_token_age_sec))

    stopped: List[str] = []
    kept: List[str] = []

    if stop_extra_backends:
        keep = keep_backends or _load_policy_enabled_backends()
        kept = list(keep)
        active = _list_active_backend_ids()
        for bid in active:
            if bid in keep:
                continue
            if _stop_backend(bid):
                stopped.append(bid)

    return {
        "ok": True,
        "removed_workdirs": int(rem_work),
        "removed_tokens": int(rem_tok),
        "stop_extra_backends": bool(stop_extra_backends),
        "kept_backends": kept,
        "stopped_backends": stopped,
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
#   - cleanup, print
# Returns / emits: int
# Key locals:
#   - rep
# === End NoemaForge Autodoc Function Header ===
def main() -> int:
    rep = cleanup()
    print(rep)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
