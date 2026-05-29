#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/localgw_uplink.py
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
# File: src/localgw_uplink.py
# Purpose: Provide the module 'localgw_uplink'.
# Invoked by / imported from:
#   - src/localgw_connectors/octoprint.py
# Public API / entry functions:
#   - run_octoprint_upload
# Inputs:
#   - Common path inputs: /opt/noemaforge/src/localgw_uplink_agent.py, /var/lib/noemaforge/localgw/uplink_out
#   - Imports: __future__, json, os, uuid, shutil, ipaddress, urllib.parse, typing
# Output formats / side effects:
#   - copied filesystem artifacts
#   - JSON files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""localgw_uplink.py (v0.17.0)

Uplink glove runner for LocalGateway.

This module executes deterministic "uplink agents" (NOT LLMs) inside
an isolated sandbox with network enabled (podman slirp or microVM when available).

Current use case:
- OctoPrint GCODE upload (multipart)

Policy sources
-------------
- sandbox-policy.yaml (Contract Epoch)
- local-gateway-policy.yaml (Contract Epoch)

Stage C1+ (v0.17.0)
-------------------
We still prefer a microVM when available, but for the MVP we can safely use
bwrap *with a kernel-level egress guard* (nftables) that only allows TCP
connections to the specific device IP:port.

This gives us:
- filesystem isolation (bwrap)
- network egress allowlist (nft meta skuid)

If netguard cannot be enforced and policy requires it, we fail closed.
"""


import json
import os
import uuid
import shutil
import ipaddress
import urllib.parse
from typing import Any, Dict, Tuple

import yaml

from sandbox import run as sandbox_run, quota_from_policy


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
# Function: _resolve_agent_path()
# Purpose: Implement the routine ' resolve agent path'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - exists, dirname, join, abspath
# Returns / emits: str
# Key locals:
#   - here, p1
# === End NoemaForge Autodoc Function Header ===
def _resolve_agent_path() -> str:
    p1 = "/opt/noemaforge/src/localgw_uplink_agent.py"
    if os.path.exists(p1):
        return p1
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, "localgw_uplink_agent.py")


# === NoemaForge Autodoc Function Header ===
# Function: _action_cfg(sandbox_policy: Dict[str, Any], action: str)
# Purpose: Implement the routine ' action cfg'.
# Inputs:
#   - sandbox_policy: Dict[str, Any]
#   - action: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - get, isinstance
# Returns / emits: Dict[str, Any]
# Key locals:
#   - acts, cfg
# === End NoemaForge Autodoc Function Header ===
def _action_cfg(sandbox_policy: Dict[str, Any], action: str) -> Dict[str, Any]:
    acts = (sandbox_policy.get("actions") or {}) if isinstance(sandbox_policy, dict) else {}
    cfg = acts.get(action)
    return cfg if isinstance(cfg, dict) else {}


# === NoemaForge Autodoc Function Header ===
# Function: _uplink_allow_podman(policy: Dict[str, Any])
# Purpose: Implement the routine ' uplink allow podman'.
# Inputs:
#   - policy: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - bool, isinstance, get
# Returns / emits: bool
# Key locals:
#   - upl
# === End NoemaForge Autodoc Function Header ===
def _uplink_allow_podman(policy: Dict[str, Any]) -> bool:
    upl = (policy.get("uplink") or {}) if isinstance(policy, dict) else {}
    # default allow podman fallback; can be set false for stricter deployments.
    return bool(upl.get("allow_podman_fallback", True))


# === NoemaForge Autodoc Function Header ===
# Function: _uplink_cfg(policy: Dict[str, Any])
# Purpose: Implement the routine ' uplink cfg'.
# Inputs:
#   - policy: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - isinstance, get
# Returns / emits: Dict[str, Any]
# Key locals:
#   - upl
# === End NoemaForge Autodoc Function Header ===
def _uplink_cfg(policy: Dict[str, Any]) -> Dict[str, Any]:
    upl = (policy.get("uplink") or {}) if isinstance(policy, dict) else {}
    return upl if isinstance(upl, dict) else {}


# === NoemaForge Autodoc Function Header ===
# Function: _parse_target(base_url: str)
# Purpose: Return (host, port, scheme) from base_url.
# Inputs:
#   - base_url: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - urlparse, lower, strip, int, ValueError, str
# Returns / emits: Tuple[str, int, str]
# Key locals:
#   - host, port, scheme, u
# === End NoemaForge Autodoc Function Header ===
def _parse_target(base_url: str) -> Tuple[str, int, str]:
    """Return (host, port, scheme) from base_url."""
    u = urllib.parse.urlparse(str(base_url).strip())
    scheme = (u.scheme or "").lower()
    if scheme not in ("http", "https"):
        raise ValueError("invalid_scheme")
    host = (u.hostname or "").strip()
    if not host:
        raise ValueError("missing_host")
    port = int(u.port or (443 if scheme == "https" else 80))
    if port <= 0 or port > 65535:
        raise ValueError("invalid_port")
    return host, port, scheme


# === NoemaForge Autodoc Function Header ===
# Function: _is_ip_literal(host: str)
# Purpose: Implement the routine ' is ip literal'.
# Inputs:
#   - host: str
# Called by:
#   - src/webgateway.py
# Calls:
#   - ip_address, str
# Returns / emits: bool
# === End NoemaForge Autodoc Function Header ===
def _is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(str(host))
        return True
    except Exception:
        return False


# === NoemaForge Autodoc Function Header ===
# Function: _within_allowed_subnets(host: str, allowed_subnets)
# Purpose: Implement the routine ' within allowed subnets'.
# Inputs:
#   - host: str
#   - allowed_subnets
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _is_ip_literal, ip_address, isinstance, bool, ip_network, str
# Returns / emits: bool
# Key locals:
#   - ip, net, s, subs
# === End NoemaForge Autodoc Function Header ===
def _within_allowed_subnets(host: str, allowed_subnets: Any) -> bool:
    if not _is_ip_literal(host):
        return False
    try:
        ip = ipaddress.ip_address(host)
    except Exception:
        return False
    subs = allowed_subnets if isinstance(allowed_subnets, list) else []
    if not subs:
        # If not specified, default to private ranges only.
        return bool(ip.is_private)
    for s in subs:
        try:
            net = ipaddress.ip_network(str(s), strict=False)
            if ip in net:
                return True
        except Exception:
            continue
    return False


# === NoemaForge Autodoc Function Header ===
# Function: _mk_netguard(local_gateway_policy: Dict[str, Any], host: str, port: int)
# Purpose: Implement the routine ' mk netguard'.
# Inputs:
#   - local_gateway_policy: Dict[str, Any]
#   - host: str
#   - port: int
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _uplink_cfg, bool, int, isinstance, get
# Returns / emits: Dict[str, Any]
# Key locals:
#   - allow_loopback, enabled, ng, require, uid, upl
# === End NoemaForge Autodoc Function Header ===
def _mk_netguard(local_gateway_policy: Dict[str, Any], *, host: str, port: int) -> Dict[str, Any]:
    upl = _uplink_cfg(local_gateway_policy)
    ng = (upl.get("netguard") or {}) if isinstance(upl.get("netguard"), dict) else {}

    enabled = bool(ng.get("enabled", True))
    require = bool(ng.get("require", True))
    uid = int(ng.get("uid") or 29999)
    allow_loopback = bool(ng.get("allow_loopback", False))

    return {
        "enabled": enabled,
        "require": require,
        "uid": uid,
        "allow_loopback": allow_loopback,
        "targets": [{"ip": host, "port": int(port), "proto": "tcp"}],
    }


# === NoemaForge Autodoc Function Header ===
# Function: run_octoprint_upload(epoch_dir: str, sandbox_policy: Dict[str, Any], local_gateway_policy: Dict[str, Any], base_url: str, api_key_file: str, local_path: str, dest_name: str, select: bool = False, do_print: bool = False)
# Purpose: Run OctoPrint upload in an uplink glove.
# Inputs:
#   - epoch_dir: str
#   - sandbox_policy: Dict[str, Any]
#   - local_gateway_policy: Dict[str, Any]
#   - base_url: str
#   - api_key_file: str
#   - local_path: str
#   - dest_name: str
#   - select: bool = False
#   - do_print: bool = False
# Called by:
#   - src/localgw_connectors/octoprint.py
#   - src/localgw_uplink_agent.py
# Calls:
#   - _resolve_agent_path, join, makedirs, _uplink_cfg, bool, _parse_target, _action_cfg, quota_from_policy, _mk_netguard, int, list, enumerate
# Returns / emits: Tuple[bool, Dict[str, Any], str]
# Side effects:
#   - creates directories
# Key locals:
#   - act, agent, allowed_subnets, argv, argv2, env, extra_ro, in_dir, max_mib, ng, out_dir, out_path
# === End NoemaForge Autodoc Function Header ===
def run_octoprint_upload(
    *,
    epoch_dir: str,
    sandbox_policy: Dict[str, Any],
    local_gateway_policy: Dict[str, Any],
    base_url: str,
    api_key_file: str,
    local_path: str,
    dest_name: str,
    select: bool = False,
    do_print: bool = False,
) -> Tuple[bool, Dict[str, Any], str]:
    """Run OctoPrint upload in an uplink glove."""

    if not os.path.exists(local_path):
        return False, {"ok": False, "reason": "file_not_found"}, "file_not_found"

    agent = _resolve_agent_path()
    out_dir = os.path.join("/var/lib/noemaforge/localgw/uplink_out", uuid.uuid4().hex[:10])
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "uplink_result.json")

    # Enforce basic safety on the target.
    upl = _uplink_cfg(local_gateway_policy)
    require_ip = bool(upl.get("require_ip_literal", True))
    host, port, scheme = _parse_target(base_url)
    if require_ip and not _is_ip_literal(host):
        return False, {"ok": False, "reason": "target_must_be_ip", "host": host}, "target_must_be_ip"

    # Subnet allowlist (defaults to private ranges).
    allowed_subnets = (((local_gateway_policy.get("network") or {}) if isinstance(local_gateway_policy, dict) else {}).get("allowed_subnets") or [])
    if not _within_allowed_subnets(host, allowed_subnets):
        return False, {"ok": False, "reason": "target_outside_allowed_subnets", "host": host}, "target_outside_allowed_subnets"

    # Upload size guard.
    try:
        max_mib = int(upl.get("max_file_mib") or 200)
        sz = int(os.path.getsize(local_path) or 0)
        if sz > max_mib * 1024 * 1024:
            return False, {"ok": False, "reason": "file_too_large", "size": sz, "max_mib": max_mib}, "file_too_large"
    except Exception:
        pass

    # Prefer network-safe backends.
    act = _action_cfg(sandbox_policy, "glove.uplink")
    prefer = act.get("backend_preference") or ["microvm", "bwrap", "podman"]
    prefer = [str(x) for x in prefer if str(x).strip()]

    # Host backend is still too permissive for uplinks.
    prefer = [b for b in prefer if b != "host"]

    # If podman fallback is disabled, remove it.
    if not _uplink_allow_podman(local_gateway_policy):
        prefer = [b for b in prefer if b != "podman"]

    if not prefer:
        return False, {"ok": False, "reason": "no_safe_backend"}, "no_safe_backend"

    quota = quota_from_policy(sandbox_policy, "uplink")

    env = {
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONNOUSERSITE": "1",
    }

    argv = [
        "python3",
        agent,
        "--kind",
        "octoprint.upload_gcode",
        "--base-url",
        str(base_url),
        "--api-key-file",
        str(api_key_file),
        "--file",
        str(local_path),
        "--dest",
        str(dest_name or ""),
        "--out",
        out_path,
    ]

    if select:
        argv.append("--select")
    if do_print:
        argv.append("--print")

    # Prepare safe, short-lived copies readable by the guarded uid.
    # This avoids giving the glove read access to arbitrary host paths.
    # NOTE: keep input dir separate from out_dir to avoid RW bind overriding RO binds.
    in_dir = out_dir + "_in"
    os.makedirs(in_dir, exist_ok=True)

    safe_file = os.path.join(in_dir, os.path.basename(local_path) or "upload.bin")
    safe_key = os.path.join(in_dir, "api_key.txt")
    try:
        shutil.copy2(local_path, safe_file)
    except Exception:
        # As a fallback, use original path (may fail on perms in guarded uid).
        safe_file = os.path.abspath(local_path)
    try:
        shutil.copy2(api_key_file, safe_key)
    except Exception:
        safe_key = os.path.abspath(api_key_file)

    ng = _mk_netguard(local_gateway_policy, host=host, port=port)
    uid = int(ng.get("uid") or 29999)

    for p in (safe_file, safe_key):
        try:
            os.chmod(p, 0o440)
            os.chown(p, uid, uid)
        except Exception:
            # If we cannot chown, the glove may not be able to read; bwrap backend
            # will fail and sandbox runner will try other backends.
            pass

    # Note: use the safe copies inside the glove.
    argv2 = list(argv)
    # Replace file args
    for i, a in enumerate(argv2):
        if a == "--api-key-file" and i + 1 < len(argv2):
            argv2[i + 1] = safe_key
        if a == "--file" and i + 1 < len(argv2):
            argv2[i + 1] = safe_file

    ro_binds = [os.path.abspath(safe_file), os.path.abspath(safe_key)]
    extra_ro = [os.path.abspath(agent)]
    rw_binds = [out_dir]

    ok, res = sandbox_run(
        policy=sandbox_policy,
        argv=argv2,
        cwd=out_dir,
        env=env,
        quota=quota,
        ro_binds=ro_binds,
        rw_binds=rw_binds,
        allow_network=True,
        extra_ro_binds=extra_ro,
        prefer_backends=prefer,
        network_guard=ng,
    )

    # Parse result
    if not os.path.exists(out_path):
        return False, {"ok": False, "reason": "uplink_report_missing", "sandbox": res}, "uplink_report_missing"

    try:
        rep = json.load(open(out_path, "r", encoding="utf-8"))
    except Exception:
        rep = {"ok": False, "reason": "uplink_report_unreadable"}

    if not bool(ok) or not bool(rep.get("ok")):
        return False, {"ok": False, "report": rep, "sandbox": res}, str(rep.get("reason") or "uplink_failed")

    return True, {"ok": True, "report": rep, "sandbox": res}, "ok"
