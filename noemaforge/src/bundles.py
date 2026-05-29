#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/bundles.py
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
# File: src/bundles.py
# Purpose: Provide the module 'bundles'.
# Invoked by / imported from:
#   - src/brainctl.py
# Public API / entry functions:
#   - load_bundle_policy
#   - class BundleLock
#   - prepare_bundles_for_epoch
# Inputs:
#   - Common path inputs: noemaforge.bundles/v1, /var/lib/noemaforge/toolvault, /var/lib/noemaforge/toolvault/manifests, /var/lib/noemaforge/toolvault/artifacts, /var/lib/noemaforge/toolvault/installed
#   - Imports: __future__, datetime, json, os, tarfile, dataclasses, typing, toolvault
# Output formats / side effects:
#   - JSON files
#   - YAML files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""bundles.py (v0.11.0)

Pre-start bundle preparation / installation.

Bundle goals:
- Keep base OS minimal.
- Allow optional tools/plugins to be staged offline in ToolVault.
- Enforce pinned supply-chain inputs (manifest sha256 + artifact sha256).
- Make all operations auditable (SEL/WORM).

Important constraints:
- This module is called only from *pre-start* (brainctl prestart apply-epoch).
- It must NOT auto-enable new tool surfaces. Enabling is done via contract patches.
- It must NOT delete artifacts/manifests (no clean-up of evidence). "Removal" is retirement.

Supported manifest kinds (minimal):
- ToolPlugin     => extracted to ToolVault installed/plugins/<plugin_id>/<artifact_sha256>
- AptRepoBundle  => extracted to ToolVault aptrepo/<bundle_id>/<artifact_sha256> (system install optional)
"""


import datetime as dt
import json
import os
import tarfile
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Union

from toolvault import (
    bundle_paths,
    load_yaml,
    prepare_plugin_bundle,
    sha256_file,
    vault_paths,
    verify_bundle_attestation,
)

try:
    from seclog import append_event
except Exception:  # pragma: no cover
    append_event = None  # type: ignore


# === NoemaForge Autodoc Function Header ===
# Function: _nowz()
# Purpose: Implement the routine ' nowz'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - src/audit_remediation.py
#   - src/noemaforge_core.py
#   - src/caps.py
#   - src/casebase.py
#   - src/coordinator_fanout.py
#   - src/dream_cycle.py
#   - src/fixture_bundle.py
#   - src/glove_agent.py
# Calls:
#   - isoformat, utcnow
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _nowz() -> str:
    return dt.datetime.utcnow().isoformat() + "Z"


# === NoemaForge Autodoc Function Header ===
# Function: _evt(phase: str, event_type: str, actor: Dict[str, Any], decision: str, details: Dict[str, Any])
# Purpose: Implement the routine ' evt'.
# Inputs:
#   - phase: str
#   - event_type: str
#   - actor: Dict[str, Any]
#   - decision: str
#   - details: Dict[str, Any]
# Called by:
#   - src/firstboot_eval.py
#   - src/llm_backends_manager.py
#   - src/localgateway.py
#   - src/nids_lite.py
#   - src/toolproxy.py
#   - src/webgateway.py
# Calls:
#   - append_event, get
# Returns / emits: None
# Side effects:
#   - appends to logs or files
# === End NoemaForge Autodoc Function Header ===
def _evt(phase: str, event_type: str, actor: Dict[str, Any], decision: str, details: Dict[str, Any]) -> None:
    if append_event is None:
        return
    try:
        append_event(
            phase=phase,
            event_type=event_type,
            actor=actor,
            decision=decision,
            trace_id=details.get("trace_id") or "",
            details=details,
        )
    except Exception:
        return


# === NoemaForge Autodoc Function Header ===
# Function: _load_policy(epoch_dir: str, fname: str, fallback: Dict[str, Any])
# Purpose: Implement the routine ' load policy'.
# Inputs:
#   - epoch_dir: str
#   - fname: str
#   - fallback: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - join, exists, load_yaml
# Returns / emits: Dict[str, Any]
# Key locals:
#   - p
# === End NoemaForge Autodoc Function Header ===
def _load_policy(epoch_dir: str, fname: str, fallback: Dict[str, Any]) -> Dict[str, Any]:
    p = os.path.join(epoch_dir, fname)
    if os.path.exists(p):
        try:
            return load_yaml(p)
        except Exception:
            return fallback
    return fallback


# === NoemaForge Autodoc Function Header ===
# Function: load_bundle_policy(law_epoch_dir: str)
# Purpose: Implement the routine 'load bundle policy'.
# Inputs:
#   - law_epoch_dir: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _load_policy
# Returns / emits: Dict[str, Any]
# === End NoemaForge Autodoc Function Header ===
def load_bundle_policy(law_epoch_dir: str) -> Dict[str, Any]:
    return _load_policy(
        law_epoch_dir,
        "bundle-policy.yaml",
        {
            "apiVersion": "noemaforge.bundles/v1",
            "kind": "BundlePolicy",
            "enabled": True,
            "installer": {"prestart_only": True, "require_lock": True, "allowed_manifest_kinds": ["ToolPlugin", "AptRepoBundle"]},
            "tool_vault": {
                "root": "/var/lib/noemaforge/toolvault",
                "manifests_dir": "/var/lib/noemaforge/toolvault/manifests",
                "artifacts_dir": "/var/lib/noemaforge/toolvault/artifacts",
                "installed_dir": "/var/lib/noemaforge/toolvault/installed",
            },
        },
    )


@dataclass
class BundleLock:
    bundle_id: str
    manifest_sha256: str
    artifact_sha256: str
    manifest_path: str = ""
    artifact_path: str = ""
    kind_hint: str = ""
    version: str = ""


# === NoemaForge Autodoc Function Header ===
# Function: _parse_bundle_add_item(item)
# Purpose: Implement the routine ' parse bundle add item'.
# Inputs:
#   - item
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - isinstance, strip, BundleLock, str, get
# Returns / emits: Tuple[Optional[BundleLock], str]
# Key locals:
#   - ash, bid, msh
# === End NoemaForge Autodoc Function Header ===
def _parse_bundle_add_item(item: Any) -> Tuple[Optional[BundleLock], str]:
    if isinstance(item, str):
        return None, "bundle_lock_missing"  # strict mode by default
    if not isinstance(item, dict):
        return None, "bundle_lock_bad_type"
    bid = str(item.get("bundle_id") or "").strip()
    msh = str(item.get("manifest_sha256") or "").strip()
    ash = str(item.get("artifact_sha256") or "").strip()
    if not bid or not msh or not ash:
        return None, "bundle_lock_incomplete"
    return BundleLock(
        bundle_id=bid,
        manifest_sha256=msh,
        artifact_sha256=ash,
        manifest_path=str(item.get("manifest_path") or "").strip(),
        artifact_path=str(item.get("artifact_path") or "").strip(),
        kind_hint=str(item.get("kind") or "").strip(),
        version=str(item.get("version") or "").strip(),
    ), "ok"


# === NoemaForge Autodoc Function Header ===
# Function: _parse_bundle_remove_item(item)
# Purpose: Implement the routine ' parse bundle remove item'.
# Inputs:
#   - item
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - isinstance, strip, str, get
# Returns / emits: Tuple[Optional[Dict[str, str]], str]
# Key locals:
#   - bid, out
# === End NoemaForge Autodoc Function Header ===
def _parse_bundle_remove_item(item: Any) -> Tuple[Optional[Dict[str, str]], str]:
    if isinstance(item, str):
        bid = item.strip()
        return ({"bundle_id": bid} if bid else None), ("ok" if bid else "bundle_id_missing")
    if not isinstance(item, dict):
        return None, "bundle_remove_bad_type"
    bid = str(item.get("bundle_id") or "").strip()
    if not bid:
        return None, "bundle_id_missing"
    out = {"bundle_id": bid}
    if str(item.get("artifact_sha256") or "").strip():
        out["artifact_sha256"] = str(item.get("artifact_sha256") or "").strip()
    if str(item.get("version") or "").strip():
        out["version"] = str(item.get("version") or "").strip()
    return out, "ok"


# === NoemaForge Autodoc Function Header ===
# Function: _inventory_path(bundle_policy: Dict[str, Any])
# Purpose: Implement the routine ' inventory path'.
# Inputs:
#   - bundle_policy: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - strip, str, join, get
# Returns / emits: str
# Key locals:
#   - inv, root, tv
# === End NoemaForge Autodoc Function Header ===
def _inventory_path(bundle_policy: Dict[str, Any]) -> str:
    inv = str((((bundle_policy.get("installer") or {}).get("inventory_path")) or "")).strip()
    if inv:
        return inv
    tv = (bundle_policy.get("tool_vault") or {})
    root = str(tv.get("root") or "/var/lib/noemaforge/toolvault")
    return os.path.join(root, "installed", "_inventory.json")


# === NoemaForge Autodoc Function Header ===
# Function: _read_inventory(path: str)
# Purpose: Implement the routine ' read inventory'.
# Inputs:
#   - path: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - exists, load, open
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads or writes files
# === End NoemaForge Autodoc Function Header ===
def _read_inventory(path: str) -> Dict[str, Any]:
    try:
        if os.path.exists(path):
            return json.load(open(path, "r", encoding="utf-8"))
    except Exception:
        pass
    return {"schema_version": "v1", "installed": []}


# === NoemaForge Autodoc Function Header ===
# Function: _write_inventory(path: str, inv: Dict[str, Any])
# Purpose: Implement the routine ' write inventory'.
# Inputs:
#   - path: str
#   - inv: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
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
def _write_inventory(path: str, inv: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(inv, f, ensure_ascii=False, indent=2)


# === NoemaForge Autodoc Function Header ===
# Function: _inv_add(inv: Dict[str, Any], rec: Dict[str, Any])
# Purpose: Implement the routine ' inv add'.
# Inputs:
#   - inv: Dict[str, Any]
#   - rec: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - setdefault, append
# Returns / emits: None
# Side effects:
#   - appends to logs or files
# === End NoemaForge Autodoc Function Header ===
def _inv_add(inv: Dict[str, Any], rec: Dict[str, Any]) -> None:
    inv.setdefault("installed", [])
    inv["installed"].append(rec)


# === NoemaForge Autodoc Function Header ===
# Function: _inv_retire(inv: Dict[str, Any], bundle_id: str, artifact_sha256: str = '')
# Purpose: Implement the routine ' inv retire'.
# Inputs:
#   - inv: Dict[str, Any]
#   - bundle_id: str
#   - artifact_sha256: str = ''
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - get, _nowz, str
# Returns / emits: int
# Key locals:
#   - n, r
# === End NoemaForge Autodoc Function Header ===
def _inv_retire(inv: Dict[str, Any], bundle_id: str, artifact_sha256: str = "") -> int:
    n = 0
    for r in inv.get("installed") or []:
        if str(r.get("bundle_id") or "") != bundle_id:
            continue
        if artifact_sha256 and str(r.get("artifact_sha256") or "") != artifact_sha256:
            continue
        if str(r.get("status") or "active") == "retired":
            continue
        r["status"] = "retired"
        r["retired_at"] = _nowz()
        n += 1
    return n


# === NoemaForge Autodoc Function Header ===
# Function: _safe_extract_tar(artifact_path: str, out_dir: str)
# Purpose: Implement the routine ' safe extract tar'.
# Inputs:
#   - artifact_path: str
#   - out_dir: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - open, getmembers, extractall, startswith, split
# Returns / emits: Tuple[bool, str]
# Side effects:
#   - reads or writes files
# Key locals:
#   - m, name, tf
# === End NoemaForge Autodoc Function Header ===
def _safe_extract_tar(artifact_path: str, out_dir: str) -> Tuple[bool, str]:
    # Minimal path traversal defense.
    try:
        with tarfile.open(artifact_path, "r:gz") as tf:
            for m in tf.getmembers():
                name = m.name
                if name.startswith("/") or ".." in name.split("/"):
                    return False, "tar_unsafe_path"
            tf.extractall(out_dir)
        return True, "ok"
    except Exception as e:
        return False, f"tar_extract_failed:{e!r}"


# === NoemaForge Autodoc Function Header ===
# Function: _prepare_toolplugin(bundle_policy: Dict[str, Any], lock: BundleLock, actor: Dict[str, Any])
# Purpose: Implement the routine ' prepare toolplugin'.
# Inputs:
#   - bundle_policy: Dict[str, Any]
#   - lock: BundleLock
#   - actor: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - strip, prepare_plugin_bundle, load_yaml, _evt, str, get
# Returns / emits: Tuple[bool, str, Optional[str]]
# Key locals:
#   - mf, plugin_id
# === End NoemaForge Autodoc Function Header ===
def _prepare_toolplugin(
    *,
    bundle_policy: Dict[str, Any],
    lock: BundleLock,
    actor: Dict[str, Any],
) -> Tuple[bool, str, Optional[str]]:
    # Load manifest to find plugin_id
    try:
        mf = load_yaml(lock.manifest_path)
    except Exception as e:
        return False, f"manifest_load_failed:{e!r}", None

    plugin_id = str(mf.get("plugin_id") or "").strip()
    if not plugin_id:
        return False, "manifest_plugin_id_missing", None

    ok, reason, out_dir = prepare_plugin_bundle(
        policy=bundle_policy,
        plugin_id=plugin_id,
        bundle_id=lock.bundle_id,
        manifest_path=lock.manifest_path,
        artifact_path=lock.artifact_path,
        expected_manifest_sha256=lock.manifest_sha256,
        expected_artifact_sha256=lock.artifact_sha256,
    )
    if ok:
        _evt("S0", "BUNDLE_PREPARE", actor, "allow", {
            "bundle_id": lock.bundle_id,
            "kind": "ToolPlugin",
            "plugin_id": plugin_id,
            "manifest_sha256": lock.manifest_sha256,
            "artifact_sha256": lock.artifact_sha256,
        })
    return ok, reason, out_dir


# === NoemaForge Autodoc Function Header ===
# Function: _prepare_aptrepo_bundle(bundle_policy: Dict[str, Any], lock: BundleLock, actor: Dict[str, Any])
# Purpose: Implement the routine ' prepare aptrepo bundle'.
# Inputs:
#   - bundle_policy: Dict[str, Any]
#   - lock: BundleLock
#   - actor: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - str, join, makedirs, _safe_extract_tar, _evt, get, isdir, exists, open, write, symlink, dirname
# Returns / emits: Tuple[bool, str, Optional[str]]
# Side effects:
#   - reads or writes files
#   - creates directories
# Key locals:
#   - active_link, f, out_dir, root, stamp, tv
# === End NoemaForge Autodoc Function Header ===
def _prepare_aptrepo_bundle(
    *,
    bundle_policy: Dict[str, Any],
    lock: BundleLock,
    actor: Dict[str, Any],
) -> Tuple[bool, str, Optional[str]]:
    tv = (bundle_policy.get("tool_vault") or {})
    root = str(tv.get("root") or "/var/lib/noemaforge/toolvault")
    out_dir = os.path.join(root, "aptrepo", lock.bundle_id, lock.artifact_sha256)
    active_link = os.path.join(root, "aptrepo", "_active")
    stamp = os.path.join(out_dir, ".prepared")
    if os.path.isdir(out_dir) and os.path.exists(stamp):
        return True, "already_prepared", out_dir

    os.makedirs(out_dir, exist_ok=True)
    ok, r = _safe_extract_tar(lock.artifact_path, out_dir)
    if not ok:
        return False, r, None

    with open(stamp, "w", encoding="utf-8") as f:
        f.write(f"bundle_id={lock.bundle_id}\n")
        f.write(f"artifact_sha256={lock.artifact_sha256}\n")
        f.write(f"manifest_sha256={lock.manifest_sha256}\n")

    # Best-effort: point toolvault/aptrepo/_active to the latest prepared repo.
    # This keeps the bootstrap path stable while preserving evidence (versioned dirs).
    try:
        os.makedirs(os.path.dirname(active_link), exist_ok=True)
        if os.path.islink(active_link) or os.path.exists(active_link):
            try:
                os.remove(active_link)
            except Exception:
                pass
        os.symlink(out_dir, active_link)
    except Exception:
        pass

    _evt("S0", "BUNDLE_PREPARE", actor, "allow", {
        "bundle_id": lock.bundle_id,
        "kind": "AptRepoBundle",
        "manifest_sha256": lock.manifest_sha256,
        "artifact_sha256": lock.artifact_sha256,
        "out_dir": out_dir,
    })

    return True, "prepared", out_dir


# === NoemaForge Autodoc Function Header ===
# Function: prepare_bundles_for_epoch(epoch_dir: str, law_epoch_dir: str, request_objs: List[Dict[str, Any]], only_request_ids: Optional[List[str]] = None)
# Purpose: Prepare bundles for a candidate epoch.
# Inputs:
#   - epoch_dir: str
#   - law_epoch_dir: str
#   - request_objs: List[Dict[str, Any]]
#   - only_request_ids: Optional[List[str]] = None
# Called by:
#   - src/brainctl.py
# Calls:
#   - load_bundle_policy, bool, set, _inventory_path, _read_inventory, get, strip, _write_inventory, str, isinstance, _parse_bundle_remove_item, _inv_retire
# Returns / emits: Tuple[bool, List[str]]
# Key locals:
#   - actor, adds, allowed_ids, allowed_kinds, ash, bid, bundle_policy, ch, installer, inv, inv_path, it
# === End NoemaForge Autodoc Function Header ===
def prepare_bundles_for_epoch(
    *,
    epoch_dir: str,
    law_epoch_dir: str,
    request_objs: List[Dict[str, Any]],
    only_request_ids: Optional[List[str]] = None,
) -> Tuple[bool, List[str]]:
    """Prepare bundles for a candidate epoch.

    This is called from brainctl prestart apply-epoch.

    Returns (ok, problems).
    """

    problems: List[str] = []

    bundle_policy = load_bundle_policy(law_epoch_dir)
    if not bool(bundle_policy.get("enabled", True)):
        return True, []

    installer = bundle_policy.get("installer") or {}
    require_lock = bool(installer.get("require_lock", True))
    allowed_kinds = set([str(x) for x in (installer.get("allowed_manifest_kinds") or []) if isinstance(x, str)])
    if not allowed_kinds:
        allowed_kinds = {"ToolPlugin", "AptRepoBundle"}

    inv_path = _inventory_path(bundle_policy)
    inv = _read_inventory(inv_path)

    allowed_ids = set(only_request_ids or [])

    for robj in request_objs:
        rid = str(robj.get("request_id") or "").strip()
        if allowed_ids and rid not in allowed_ids:
            continue
        ch = (robj.get("requested_changes") or {})
        adds = ch.get("bundles_add") or []
        rems = ch.get("bundles_remove") or []

        # Retirement is just inventory mark (no deletes).
        for it in rems if isinstance(rems, list) else []:
            rm, rr = _parse_bundle_remove_item(it)
            if not rm:
                problems.append(f"{rid}:bundle_remove:{rr}")
                continue
            bid = rm.get("bundle_id") or ""
            ash = rm.get("artifact_sha256") or ""
            n = _inv_retire(inv, bid, ash)
            _evt("S0", "BUNDLE_RETIRE", robj.get("created_by") or {"actor_type": "system"}, "allow", {
                "request_id": rid,
                "bundle_id": bid,
                "artifact_sha256": ash,
                "retired_count": n,
            })

        for it in adds if isinstance(adds, list) else []:
            lock, rr = _parse_bundle_add_item(it)
            if not lock:
                if require_lock:
                    problems.append(f"{rid}:bundle_add:{rr}")
                    continue
                # If lock is not required, accept string bundle_id (not implemented in strict kit).
                continue

            # Resolve paths via ToolVault layout.
            mp, ap = bundle_paths(
                policy=bundle_policy,
                bundle_id=lock.bundle_id,
                manifest_path=lock.manifest_path,
                artifact_sha256=lock.artifact_sha256,
                artifact_path=lock.artifact_path,
            )
            lock.manifest_path = mp
            lock.artifact_path = ap

            ok_att, att_reason = verify_bundle_attestation(
                manifest_path=lock.manifest_path,
                expected_manifest_sha256=lock.manifest_sha256,
                artifact_path=lock.artifact_path,
                expected_artifact_sha256=lock.artifact_sha256,
            )
            if not ok_att:
                problems.append(f"{rid}:bundle_attestation:{lock.bundle_id}:{att_reason}")
                _evt("S0", "BUNDLE_ATTESTATION", robj.get("created_by") or {"actor_type": "system"}, "deny", {
                    "request_id": rid,
                    "bundle_id": lock.bundle_id,
                    "reason": att_reason,
                })
                continue

            # Load manifest kind
            try:
                mf = load_yaml(lock.manifest_path)
            except Exception as e:
                problems.append(f"{rid}:bundle_manifest_load:{lock.bundle_id}:{e!r}")
                continue

            kind = str(mf.get("kind") or "").strip()
            if lock.kind_hint and kind and lock.kind_hint != kind:
                # Kind mismatch is suspicious, but don't auto-fail; log.
                problems.append(f"{rid}:bundle_kind_mismatch_hint:{lock.bundle_id}:{lock.kind_hint}!={kind}")

            if kind not in allowed_kinds:
                problems.append(f"{rid}:bundle_kind_not_allowed:{lock.bundle_id}:{kind}")
                continue

            actor = robj.get("created_by") or {"actor_type": "system"}

            if kind == "ToolPlugin":
                ok_p, p_reason, out_dir = _prepare_toolplugin(bundle_policy=bundle_policy, lock=lock, actor=actor)
                if not ok_p:
                    problems.append(f"{rid}:bundle_prepare:{lock.bundle_id}:{p_reason}")
                    continue
                _inv_add(inv, {
                    "bundle_id": lock.bundle_id,
                    "kind": kind,
                    "manifest_sha256": lock.manifest_sha256,
                    "artifact_sha256": lock.artifact_sha256,
                    "installed_at": _nowz(),
                    "status": "active",
                    "installed_dir": out_dir,
                    "installed_by": {"request_id": rid, "actor": actor},
                })

            elif kind == "AptRepoBundle":
                ok_p, p_reason, out_dir = _prepare_aptrepo_bundle(bundle_policy=bundle_policy, lock=lock, actor=actor)
                if not ok_p:
                    problems.append(f"{rid}:aptrepo_prepare:{lock.bundle_id}:{p_reason}")
                    continue
                _inv_add(inv, {
                    "bundle_id": lock.bundle_id,
                    "kind": kind,
                    "manifest_sha256": lock.manifest_sha256,
                    "artifact_sha256": lock.artifact_sha256,
                    "installed_at": _nowz(),
                    "status": "active",
                    "installed_dir": out_dir,
                    "installed_by": {"request_id": rid, "actor": actor},
                })

            else:
                # Should not happen due to allowed_kinds check.
                problems.append(f"{rid}:bundle_kind_unhandled:{lock.bundle_id}:{kind}")
                continue

    # Persist inventory
    try:
        _write_inventory(inv_path, inv)
    except Exception as e:
        problems.append(f"inventory_write_failed:{e!r}")

    ok = not any(p.startswith("inventory_write_failed") for p in problems) and not any(
        ":bundle_prepare:" in p or ":aptrepo_prepare:" in p or ":bundle_attestation:" in p or ":bundle_kind_not_allowed:" in p
        for p in problems
    )
    return ok, problems
