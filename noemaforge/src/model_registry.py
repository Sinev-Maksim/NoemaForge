#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/model_registry.py
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
# File: src/model_registry.py
# Purpose: Provide the module 'model_registry'.
# Invoked by / imported from:
#   - src/brainctl.py
#   - src/firstboot_eval.py
#   - src/surgeon_auto.py
# Public API / entry functions:
#   - load_registry
#   - scan_modelstore
#   - update_registry
#   - main
# Inputs:
#   - --root
#   - --registry
#   - --write
#   - --no-sel
#   - Environment: NOEMAFORGE_MODELSTORE_ROOT, NOEMAFORGE_MODEL_REGISTRY
#   - Common path inputs: /var/lib/modelstore, noemaforge.modelregistry/v1, /run/noemaforge/llm/backends
#   - Imports: __future__, datetime, hashlib, json, os, re, typing, yaml
# Output formats / side effects:
#   - JSON files
#   - YAML files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""model_registry.py (v0.11.1)

ModelStore inventory builder for NoemaForge.

Why this exists
--------------
We want LLM/SLM fleets to be *portable* and *offline-first*. That means:

* models may be copied in/out of /var/lib/modelstore outside of NoemaForge runtime
* the OS must be able to discover what exists locally
* selection policies must be able to reference model IDs deterministically

This module scans the on-disk ModelStore and writes `model_registry.json`.
It also emits SEL events (append-only security log) for auditability.

Supported layouts
-----------------
1) Legacy (seed-kit MVP):

    /var/lib/modelstore/models/<model_id>/model.gguf

2) Manifest (future-proof):

    /var/lib/modelstore/models/<model_id>/manifest.yaml
    /var/lib/modelstore/models/<model_id>/artifacts/<sha>.gguf  (or arbitrary path)

We keep backward compatibility with layout (1) to avoid breaking bootstraps.
"""


import datetime as dt
import hashlib
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import yaml

from platform_paths import DEFAULT_PATHS as _pp

try:
    from seclog import append as sel_append
except Exception:  # pragma: no cover
    sel_append = None  # type: ignore

try:
    import gguf_select
except Exception:  # pragma: no cover
    gguf_select = None  # type: ignore

try:
    import runtime_safety
except Exception:  # pragma: no cover
    runtime_safety = None  # type: ignore


DEFAULT_MODELSTORE_ROOT = os.environ.get("NOEMAFORGE_MODELSTORE_ROOT", str(_pp.data_root.parent / "modelstore"))
DEFAULT_MODELS_DIR = os.path.join(DEFAULT_MODELSTORE_ROOT, "models")
DEFAULT_REGISTRY_PATH = os.environ.get(
    "NOEMAFORGE_MODEL_REGISTRY", os.path.join(DEFAULT_MODELSTORE_ROOT, "model_registry.json")
)


_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")


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
    return dt.datetime.now(dt.UTC).replace(tzinfo=None).isoformat() + "Z"


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
#   - src/pipelines/finance_budget.py
#   - src/prestart.py
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
# Function: _load_json(path: str)
# Purpose: Implement the routine ' load json'.
# Inputs:
#   - path: str
# Called by:
#   - src/noemaforge_core.py
#   - src/fixture_bundle.py
#   - src/glove_agent.py
#   - src/model_installer_plan.py
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
# Function: _save_json(path: str, obj)
# Purpose: Implement the routine ' save json'.
# Inputs:
#   - path: str
#   - obj
# Called by:
#   - src/audit_remediation.py
#   - src/noemaforge_core.py
#   - src/fixture_bundle.py
#   - src/model_scorecards.py
#   - src/prestart.py
#   - src/roles/role_entry.py
#   - src/scary_sweep.py
#   - src/sr_cycle.py
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
# Function: _safe_model_id(s: str)
# Purpose: Implement the routine ' safe model id'.
# Inputs:
#   - s: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - strip, bool, match, str
# Returns / emits: bool
# Key locals:
#   - s
# === End NoemaForge Autodoc Function Header ===
def _safe_model_id(s: str) -> bool:
    s = str(s or "").strip()
    return bool(_SAFE_ID_RE.match(s))


# === NoemaForge Autodoc Function Header ===
# Function: load_registry(path: str = DEFAULT_REGISTRY_PATH)
# Purpose: Implement the routine 'load registry'.
# Inputs:
#   - path: str = DEFAULT_REGISTRY_PATH
# Called by:
#   - src/brainctl.py
#   - src/firstboot_eval.py
#   - src/skills_registry.py
#   - src/surgeon_auto.py
# Calls:
#   - exists, _load_json, isinstance
# Returns / emits: Dict[str, Any]
# Key locals:
#   - obj
# === End NoemaForge Autodoc Function Header ===
def load_registry(path: str = DEFAULT_REGISTRY_PATH) -> Dict[str, Any]:
    try:
        if os.path.exists(path):
            obj = _load_json(path)
            if isinstance(obj, dict):
                return obj
    except Exception:
        pass
    return {
        "apiVersion": "noemaforge.modelregistry/v1",
        "kind": "ModelRegistry",
        "updated_at": "",
        "models": [],
    }


# === NoemaForge Autodoc Function Header ===
# Function: _prev_cache_map(prev: Dict[str, Any])
# Purpose: Implement the routine ' prev cache map'.
# Inputs:
#   - prev: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - strip, dict, get, str
# Returns / emits: Dict[str, Dict[str, Any]]
# Key locals:
#   - m, mid, out
# === End NoemaForge Autodoc Function Header ===
def _prev_cache_map(prev: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for m in (prev.get("models") or []) or []:
        mid = str(m.get("model_id") or "").strip()
        if not mid:
            continue
        out[mid] = dict(m)
    return out


# === NoemaForge Autodoc Function Header ===
# Function: _trust_from_manifest(man: Dict[str, Any], artifact_sha: str)
# Purpose: Implement the routine ' trust from manifest'.
# Inputs:
#   - man: Dict[str, Any]
#   - artifact_sha: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - lower, join, strip, exists, str, get
# Returns / emits: str
# Key locals:
#   - marker, t
# === End NoemaForge Autodoc Function Header ===
def _trust_from_manifest(man: Dict[str, Any], artifact_sha: str) -> str:
    t = str(man.get("trust") or "").strip().lower()
    if t in ("verified", "unknown", "quarantine"):
        return t
    # Future hook: allow an explicit local trust marker file
    #   /var/lib/modelstore/.trusted/<sha256>
    try:
        marker = os.path.join(DEFAULT_MODELSTORE_ROOT, ".trusted", artifact_sha)
        if artifact_sha and os.path.exists(marker):
            return "verified"
    except Exception:
        pass
    return "unknown"


# === NoemaForge Autodoc Function Header ===
# Function: _model_record(model_id: str, artifact_path: str, prev: Optional[Dict[str, Any]] = None, manifest: Optional[Dict[str, Any]] = None)
# Purpose: Implement the routine ' model record'.
# Inputs:
#   - model_id: str
#   - artifact_path: str
#   - prev: Optional[Dict[str, Any]] = None
#   - manifest: Optional[Dict[str, Any]] = None
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - realpath, stat, int, str, _trust_from_manifest, join, _safe_model_id, exists, _sha256_file, endswith, get, bool
# Returns / emits: Optional[Dict[str, Any]]
# Key locals:
#   - ap, backend_sock, fmt, man, mtime, prev, prev_mtime, prev_path, prev_sha, prev_size, rec, sha
# === End NoemaForge Autodoc Function Header ===
def _model_record(
    model_id: str,
    artifact_path: str,
    prev: Optional[Dict[str, Any]] = None,
    manifest: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    if not _safe_model_id(model_id):
        return None
    if runtime_safety is not None and not runtime_safety.safe_backend_id(model_id):
        return None
    if runtime_safety is not None:
        ok_safe, _reason, _meta = runtime_safety.validate_artifact_path(artifact_path)
        if not ok_safe:
            return None
    ap = os.path.realpath(artifact_path)
    if not os.path.exists(ap):
        return None
    st = os.stat(ap)
    size = int(st.st_size)
    mtime = int(st.st_mtime)

    prev = prev or {}
    prev_path = str(prev.get("artifact_path") or "")
    prev_size = int(prev.get("size_bytes") or 0)
    prev_mtime = int(prev.get("mtime") or 0)
    prev_sha = str(prev.get("artifact_sha256") or "")

    sha = ""
    if prev_sha and os.path.realpath(prev_path) == ap and prev_size == size and prev_mtime == mtime:
        sha = prev_sha
    else:
        sha = _sha256_file(ap)

    fmt = "gguf" if ap.lower().endswith(".gguf") else (manifest or {}).get("format") or "unknown"
    man = manifest or {}

    sharding_meta: Dict[str, Any] = {}
    validation_reason = ""
    if fmt == "gguf" and gguf_select is not None:
        try:
            ok, validation_reason, sharding_meta = gguf_select.validate_artifact_path(ap, require_complete=True)
            if not ok:
                return None
        except Exception:
            # Keep the registry conservative if validation code itself is unavailable.
            return None

    trust = _trust_from_manifest(man, sha)
    backend_sock = os.path.join("/run/noemaforge/llm/backends", f"{model_id}.sock")

    rec: Dict[str, Any] = {
        "model_id": model_id,
        "format": fmt,
        "artifact_path": ap,
        "artifact_sha256": sha,
        "size_bytes": size,
        "mtime": mtime,
        "trust": trust,
        "backend": {
            "sock": backend_sock,
            "present": bool(os.path.exists(backend_sock)),
        },
        "meta": {
            "family": str(man.get("family") or ""),
            "variant": str(man.get("variant") or ""),
            "quant": str(man.get("quant") or ""),
            "notes": str(man.get("notes") or ""),
        },
    }
    if sharding_meta:
        rec["sharding"] = sharding_meta
    if validation_reason:
        rec["artifact_validation"] = validation_reason
    # Drop empty meta keys
    rec["meta"] = {k: v for k, v in rec["meta"].items() if str(v).strip()}
    return rec


# === NoemaForge Autodoc Function Header ===
# Function: scan_modelstore(modelstore_root: str = DEFAULT_MODELSTORE_ROOT, registry_path: str = DEFAULT_REGISTRY_PATH, emit_sel: bool = True)
# Purpose: Scan ModelStore and build a fresh registry.
# Inputs:
#   - modelstore_root: str = DEFAULT_MODELSTORE_ROOT
#   - registry_path: str = DEFAULT_REGISTRY_PATH
#   - emit_sel: bool = True
# Called by:
#   - src/brainctl.py
# Calls:
#   - load_registry, _prev_cache_map, join, makedirs, sorted, dict, pop, listdir, startswith, exists, _model_record, append
# Returns / emits: Tuple[Dict[str, Any], Dict[str, Any]]
# Side effects:
#   - creates directories
#   - appends to logs or files
# Key locals:
#   - ap, artifact, changed, discovered, legacy, manifest, manifest_path, mdir, mid, model_id, models, models_dir
# === End NoemaForge Autodoc Function Header ===
def scan_modelstore(
    modelstore_root: str = DEFAULT_MODELSTORE_ROOT,
    registry_path: str = DEFAULT_REGISTRY_PATH,
    emit_sel: bool = True,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Scan ModelStore and build a fresh registry.

    Returns (registry_obj, changes_summary)
    """
    prev = load_registry(registry_path)
    prev_map = _prev_cache_map(prev)

    models_dir = os.path.join(modelstore_root, "models")
    os.makedirs(models_dir, exist_ok=True)

    models: List[Dict[str, Any]] = []
    discovered: List[str] = []
    changed: List[str] = []

    for name in sorted(os.listdir(models_dir)):
        if name.startswith("."):
            continue
        model_id = name
        if not _safe_model_id(model_id):
            continue
        if runtime_safety is not None and not runtime_safety.safe_backend_id(model_id):
            continue
        mdir = os.path.join(models_dir, name)
        if not os.path.isdir(mdir):
            continue

        manifest_path = os.path.join(mdir, "manifest.yaml")
        manifest: Dict[str, Any] = {}
        artifact = ""

        if os.path.exists(manifest_path):
            try:
                manifest = _load_yaml(manifest_path)
            except Exception:
                manifest = {}
            # allow manifest override of artifact path
            ap = str(manifest.get("artifact_path") or "").strip()
            if ap:
                artifact = ap if ap.startswith("/") else os.path.join(mdir, ap)

        if not artifact:
            # Legacy fallback
            legacy = os.path.join(mdir, "model.gguf")
            if os.path.exists(legacy):
                artifact = legacy

        if not artifact:
            continue

        rec = _model_record(model_id=model_id, artifact_path=artifact, prev=prev_map.get(model_id), manifest=manifest)
        if not rec:
            continue
        models.append(rec)

        if model_id not in prev_map:
            discovered.append(model_id)
        else:
            # compare stable fields
            p = prev_map[model_id]
            if str(p.get("artifact_sha256") or "") != str(rec.get("artifact_sha256") or ""):
                changed.append(model_id)

    new = {
        "apiVersion": "noemaforge.modelregistry/v1",
        "kind": "ModelRegistry",
        "updated_at": _nowz(),
        "models": models,
    }

    # Compare without updated_at
    prev_cmp = dict(prev)
    prev_cmp.pop("updated_at", None)
    new_cmp = dict(new)
    new_cmp.pop("updated_at", None)
    registry_changed = json.dumps(prev_cmp, sort_keys=True, ensure_ascii=False) != json.dumps(new_cmp, sort_keys=True, ensure_ascii=False)

    summary = {
        "registry_changed": registry_changed,
        "discovered": discovered,
        "changed": changed,
        "models_count": len(models),
    }

    if emit_sel and sel_append is not None:
        if discovered:
            for mid in discovered:
                try:
                    sel_append({
                        "severity": "info",
                        "type": "model_discovered",
                        "model_id": mid,
                        "registry_path": registry_path,
                    })
                except Exception:
                    pass
        if changed:
            for mid in changed:
                try:
                    sel_append({
                        "severity": "high",
                        "type": "model_artifact_changed",
                        "model_id": mid,
                        "registry_path": registry_path,
                    })
                except Exception:
                    pass
        if registry_changed:
            try:
                sel_append({
                    "severity": "info",
                    "type": "model_registry_updated",
                    "registry_path": registry_path,
                    "models_count": len(models),
                })
            except Exception:
                pass

    return new, summary


# === NoemaForge Autodoc Function Header ===
# Function: update_registry(modelstore_root: str = DEFAULT_MODELSTORE_ROOT, registry_path: str = DEFAULT_REGISTRY_PATH, emit_sel: bool = True)
# Purpose: Scan and write registry if changed.
# Inputs:
#   - modelstore_root: str = DEFAULT_MODELSTORE_ROOT
#   - registry_path: str = DEFAULT_REGISTRY_PATH
#   - emit_sel: bool = True
# Called by:
#   - src/brainctl.py
#   - src/firstboot_eval.py
#   - src/surgeon_auto.py
# Calls:
#   - scan_modelstore, _save_json, bool, get
# Returns / emits: Tuple[bool, Dict[str, Any]]
# === End NoemaForge Autodoc Function Header ===
def update_registry(
    modelstore_root: str = DEFAULT_MODELSTORE_ROOT,
    registry_path: str = DEFAULT_REGISTRY_PATH,
    emit_sel: bool = True,
) -> Tuple[bool, Dict[str, Any]]:
    """Scan and write registry if changed.

    Returns (changed, summary)
    """
    new, summary = scan_modelstore(modelstore_root=modelstore_root, registry_path=registry_path, emit_sel=emit_sel)
    if not bool(summary.get("registry_changed")):
        return False, summary
    _save_json(registry_path, new)
    return True, summary


# === NoemaForge Autodoc Function Header ===
# Function: main(argv: List[str])
# Purpose: Implement the routine 'main'.
# Inputs:
#   - argv: List[str]
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
#   - ArgumentParser, add_argument, parse_args, scan_modelstore, print, update_registry, dumps
# Returns / emits: int
# Side effects:
#   - serializes structured data
# Key locals:
#   - ap, args
# === End NoemaForge Autodoc Function Header ===
def main(argv: List[str]) -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=DEFAULT_MODELSTORE_ROOT)
    ap.add_argument("--registry", default=DEFAULT_REGISTRY_PATH)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--no-sel", action="store_true")
    args = ap.parse_args(argv)

    if args.write:
        changed, summary = update_registry(modelstore_root=args.root, registry_path=args.registry, emit_sel=not args.no_sel)
        print(json.dumps({"ok": True, "changed": changed, "summary": summary}, ensure_ascii=False))
        return 0

    reg, summary = scan_modelstore(modelstore_root=args.root, registry_path=args.registry, emit_sel=False)
    print(json.dumps({"ok": True, "registry": reg, "summary": summary}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(os.sys.argv[1:]))
