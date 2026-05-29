#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/plugin_runner.py
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
# File: src/plugin_runner.py
# Purpose: Provide the module 'plugin_runner'.
# Invoked by / imported from:
#   - src/toolproxy.py
# Public API / entry functions:
#   - run_plugin
# Inputs:
#   - Common path inputs: noemaforge.toolplugin/v1, noemaforge.toolplugin/v1alpha, /workspace
#   - Imports: __future__, json, os, typing, sandbox, toolvault
# Output formats / side effects:
#   - JSON files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""plugin_runner.py (v0.11.0)

Runs *bundle-attested* ToolVault plugins inside SandboxPolicy.

Contract:
  - ToolProxy calls plugin runner only for tools with handler == "plugin".
  - Tool entry must include supply_chain.kind == bundle.
  - Bundle manifest must declare ToolPlugin metadata (entrypoint/runtime).
  - Plugin code is extracted to ToolVault installed dir **pre-start**.

Runtime posture:
  - deny if plugin is not prepared (unless policy explicitly allows runtime prepare)
  - no network
  - minimal env
  - stream allowlisted RO/RW roots only
"""


import json
import os
from typing import Any, Dict, Optional, Tuple

from sandbox import run as sandbox_run, roots_from_allowlist_patterns, quota_from_policy, microvm_available
from toolvault import (
    bundle_paths,
    installed_plugin_dir,
    load_yaml,
    prepare_plugin_bundle,
    verify_bundle_attestation,
)


# === NoemaForge Autodoc Function Header ===
# Function: _safe_int(x, default: int)
# Purpose: Implement the routine ' safe int'.
# Inputs:
#   - x
#   - default: int
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - int
# Returns / emits: int
# === End NoemaForge Autodoc Function Header ===
def _safe_int(x: Any, default: int) -> int:
    try:
        return int(x)
    except Exception:
        return int(default)


# === NoemaForge Autodoc Function Header ===
# Function: _load_plugin_manifest(policy: Dict[str, Any], bundle_id: str, manifest_path: str)
# Purpose: Implement the routine ' load plugin manifest'.
# Inputs:
#   - policy: Dict[str, Any]
#   - bundle_id: str
#   - manifest_path: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - load_yaml, strip, str, get
# Returns / emits: Tuple[bool, Optional[Dict[str, Any]], str]
# Key locals:
#   - mf
# === End NoemaForge Autodoc Function Header ===
def _load_plugin_manifest(policy: Dict[str, Any], bundle_id: str, manifest_path: str) -> Tuple[bool, Optional[Dict[str, Any]], str]:
    try:
        mf = load_yaml(manifest_path)
    except Exception as e:
        return False, None, f"manifest_load_failed:{e!r}"
    if str(mf.get("kind") or "").strip() != "ToolPlugin":
        return False, None, "manifest_kind_not_ToolPlugin"
    if str(mf.get("apiVersion") or "").strip() not in ("noemaforge.toolplugin/v1", "noemaforge.toolplugin/v1alpha"):
        return False, None, "manifest_apiVersion_bad"
    if not str(mf.get("plugin_id") or "").strip():
        return False, None, "manifest_plugin_id_missing"
    if not str(mf.get("entrypoint") or "").strip():
        return False, None, "manifest_entrypoint_missing"
    return True, mf, "ok"


# === NoemaForge Autodoc Function Header ===
# Function: run_plugin(toolproxy_cfg: Dict[str, Any], sandbox_policy: Dict[str, Any], supplychain_policy: Dict[str, Any], stream_cfg: Dict[str, Any], tool_entry: Dict[str, Any], args: Dict[str, Any])
# Purpose: Execute a plugin tool.
# Inputs:
#   - toolproxy_cfg: Dict[str, Any]
#   - sandbox_policy: Dict[str, Any]
#   - supplychain_policy: Dict[str, Any]
#   - stream_cfg: Dict[str, Any]
#   - tool_entry: Dict[str, Any]
#   - args: Dict[str, Any]
# Called by:
#   - src/toolproxy.py
# Calls:
#   - get, strip, bundle_paths, verify_bundle_attestation, _load_plugin_manifest, installed_plugin_dir, lower, join, encode, _safe_int, str, quota_from_policy
# Returns / emits: Tuple[bool, Any, str]
# Key locals:
#   - action_cfg, argv, artifact_sha, bmeta, bundle_id, entrypoint, env, ep, err, err_tr, exec_cfg, extra_ro
# === End NoemaForge Autodoc Function Header ===
def run_plugin(
    *,
    toolproxy_cfg: Dict[str, Any],
    sandbox_policy: Dict[str, Any],
    supplychain_policy: Dict[str, Any],
    stream_cfg: Dict[str, Any],
    tool_entry: Dict[str, Any],
    args: Dict[str, Any],
) -> Tuple[bool, Any, str]:
    """Execute a plugin tool.

    Returns: (ok, result, reason)
    """
    sc = tool_entry.get("supply_chain")
    if not isinstance(sc, dict):
        return False, None, "plugin:missing_attestation"
    if str(sc.get("kind") or "").strip().lower() != "bundle":
        return False, {"kind": sc.get("kind")}, "plugin:attestation_kind_not_bundle"

    plugin_cfg = tool_entry.get("plugin")
    if not isinstance(plugin_cfg, dict):
        return False, None, "plugin:missing_plugin_block"
    plugin_id = str(plugin_cfg.get("plugin_id") or "").strip()
    if not plugin_id:
        return False, None, "plugin:missing_plugin_id"

    bundle_id = str(sc.get("bundle_id") or f"plugin.{plugin_id}").strip() or f"plugin.{plugin_id}"
    manifest_sha = str(sc.get("manifest_sha256") or "").strip()
    artifact_sha = str(sc.get("artifact_sha256") or "").strip()

    manifest_path, artifact_path = bundle_paths(
        policy=supplychain_policy,
        bundle_id=bundle_id,
        manifest_path=str(sc.get("manifest_path") or ""),
        artifact_sha256=artifact_sha,
        artifact_path=str(sc.get("artifact_path") or ""),
    )

    ok_att, att_reason = verify_bundle_attestation(
        manifest_path=manifest_path,
        expected_manifest_sha256=manifest_sha,
        artifact_path=artifact_path,
        expected_artifact_sha256=artifact_sha,
    )
    if not ok_att:
        return False, {"reason": att_reason, "bundle_id": bundle_id}, "plugin:attestation_failed"

    ok_m, mf, m_reason = _load_plugin_manifest(supplychain_policy, bundle_id, manifest_path)
    if not ok_m or not mf:
        return False, {"reason": m_reason, "bundle_id": bundle_id}, "plugin:manifest_invalid"

    # Ensure plugin_id consistency
    mf_pid = str(mf.get("plugin_id") or "").strip()
    if mf_pid and mf_pid != plugin_id:
        return False, {"plugin_id": plugin_id, "manifest_plugin_id": mf_pid}, "plugin:id_mismatch"

    install_dir = installed_plugin_dir(supplychain_policy, plugin_id, artifact_sha)
    prepared = os.path.isdir(install_dir) and os.path.exists(os.path.join(install_dir, ".installed"))

    runtime_prepare = False
    try:
        runtime_prepare = bool((supplychain_policy.get("plugins") or {}).get("runtime_prepare", False))
    except Exception:
        runtime_prepare = False

    if not prepared:
        if not runtime_prepare:
            return False, {"plugin_id": plugin_id, "install_dir": install_dir}, "plugin:not_prepared_prestart"
        ok_p, p_reason, out_dir = prepare_plugin_bundle(
            policy=supplychain_policy,
            plugin_id=plugin_id,
            bundle_id=bundle_id,
            manifest_path=manifest_path,
            artifact_path=artifact_path,
            expected_manifest_sha256=manifest_sha,
            expected_artifact_sha256=artifact_sha,
        )
        if not ok_p:
            return False, {"plugin_id": plugin_id, "reason": p_reason}, "plugin:prepare_failed"
        install_dir = str(out_dir or install_dir)

    entrypoint = str(mf.get("entrypoint") or "").strip()
    runtime = str(mf.get("runtime") or "python3").strip().lower()
    ep = os.path.join(install_dir, entrypoint)
    if not os.path.exists(ep):
        return False, {"entrypoint": ep}, "plugin:entrypoint_missing"

    if runtime not in ("python3", "bash", "sh"):
        return False, {"runtime": runtime}, "plugin:runtime_not_allowed"

    # Build argv
    if runtime == "python3":
        argv = ["python3", ep]
    else:
        argv = ["bash" if runtime == "bash" else "sh", ep]

    # Input payload
    inp = args.get("input") if isinstance(args, dict) else None
    if inp is None:
        inp = {}
    if not isinstance(inp, dict):
        return False, None, "plugin:input_must_be_object"

    stdin_json = json.dumps(inp, ensure_ascii=False).encode("utf-8")

    # Output limits
    exec_cfg = toolproxy_cfg.get("exec") or {}
    max_out = _safe_int(exec_cfg.get("max_stdout_bytes"), 200_000)
    max_err = _safe_int(exec_cfg.get("max_stderr_bytes"), 200_000)

    # Quotas
    quota_profile = str(args.get("quota_profile") or "plugin_smoke")
    quota = quota_from_policy(sandbox_policy, quota_profile)

    env = {
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONNOUSERSITE": "1",
        "NOEMAFORGE_PLUGIN_ID": plugin_id,
    }

    # Mount stream allowlisted roots.
    ro_roots = roots_from_allowlist_patterns([str(x) for x in (stream_cfg.get("data_ro") or [])])
    rw_roots = roots_from_allowlist_patterns([str(x) for x in (stream_cfg.get("data_rw") or [])])

    # extra_ro_binds: plugin install dir itself.
    extra_ro = [install_dir]

    # Backend preference for plugin execution
    action_cfg = (sandbox_policy.get("actions") or {}).get("plugin.run") or {}
    prefer_backends = action_cfg.get("backend_preference") or ((sandbox_policy.get("backends") or {}).get("preference") or ["bwrap", "podman", "host"])
    if bool(action_cfg.get("require_microvm", False)):
        prefer_backends = ["microvm"]
        ok_vm, reason = microvm_available(sandbox_policy)
        if not ok_vm:
            return False, {
                "backend": {"backend": "microvm", "blocked": True, "blocked_reason": reason},
                "plugin_id": plugin_id,
            }, "plugin:microvm_unavailable"



    ok_cmd, res = sandbox_run(
        policy=sandbox_policy,
        prefer_backends=list(prefer_backends),
        argv=argv,
        cwd=str(mf.get("cwd") or "/workspace"),
        env=env,
        quota=quota,
        ro_binds=ro_roots,
        rw_binds=rw_roots,
        allow_network=False,
        extra_ro_binds=extra_ro,
        stdin_bytes=stdin_json,
    )

    bmeta = (res.get("backend") or {})
    if bool(bmeta.get("blocked")):
        return False, {"backend": bmeta, "stderr": res.get("stderr")}, "plugin:degraded_sandbox"

    out = (res.get("stdout") or "")
    err = (res.get("stderr") or "")

    # Truncate
    out_tr = len(out.encode("utf-8", "replace")) > max_out
    err_tr = len(err.encode("utf-8", "replace")) > max_err
    if out_tr:
        out = out.encode("utf-8", "replace")[:max_out].decode("utf-8", "replace")
    if err_tr:
        err = err.encode("utf-8", "replace")[:max_err].decode("utf-8", "replace")

    rc = int(res.get("exit_code") or 0)
    if rc != 0:
        return False, {
            "exit_code": rc,
            "stdout": out,
            "stderr": err,
            "truncated": {"stdout": out_tr, "stderr": err_tr},
            "backend": bmeta,
            "plugin_id": plugin_id,
        }, "plugin:exec_failed"

    # Parse JSON output if possible
    parsed: Any = None
    try:
        parsed = json.loads(out) if out.strip() else {}
    except Exception:
        parsed = {"text": out}

    return True, {
        "exit_code": rc,
        "result": parsed,
        "stderr": err,
        "truncated": {"stdout": out_tr, "stderr": err_tr},
        "backend": bmeta,
        "plugin_id": plugin_id,
        "bundle_id": bundle_id,
        "quota_profile": quota_profile,
    }, "ok"
