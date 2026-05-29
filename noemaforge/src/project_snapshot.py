#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/project_snapshot.py
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
# File: src/project_snapshot.py
# Purpose: Provide the module 'project_snapshot'.
# Invoked by / imported from:
#   - src/noemaforge_core.py
#   - src/worktree_manager.py
# Public API / entry functions:
#   - class SnapshotSpec
#   - snapshots_dir
#   - list_snapshots
#   - latest_snapshot
#   - freeze_project
#   - thaw_project
# Inputs:
#   - Imports: __future__, hashlib, json, os, shutil, time, dataclasses, typing
# Output formats / side effects:
#   - JSON files
#   - YAML files
#   - copied filesystem artifacts
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""project_snapshot.py (v0.14.0)

Project freeze/thaw ("suspend/resume") for NoemaForge.

Why this exists:
- NoemaForge projects are long-lived, and teams (PM/architect/dev/qa/...) maintain state.
- When switching focus, we want a *repeatable* way to capture project control-state
  (backlog/wakes/semaphores/checkpoints) without duplicating large artifacts.
- Snapshots are used by Surgeon/SR/SSR and by the operator to resume work later.

Design:
- Artifacts are NOT duplicated by default (they live under the project root).
- Snapshot copies "control plane" only:
  project.yaml, backlog.yaml, roster.yaml, wakeq, semaphore, checkpoints, freeze summaries.
- Snapshot also records a manifest with hashes for WORM/audit correlation.

This module is deliberately filesystem-only (no DB dependency).
"""


import hashlib
import json
import os
import shutil
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


# === NoemaForge Autodoc Function Header ===
# Function: _ts()
# Purpose: Implement the routine ' ts'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - strftime, gmtime
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _ts() -> str:
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


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
#   - sha256, hexdigest, open, read, update
# Returns / emits: str
# Side effects:
#   - reads or writes files
# Key locals:
#   - b, f, h
# === End NoemaForge Autodoc Function Header ===
def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(1024 * 1024)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


# === NoemaForge Autodoc Function Header ===
# Function: _copy_file(src: str, dst: str)
# Purpose: Implement the routine ' copy file'.
# Inputs:
#   - src: str
#   - dst: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - makedirs, copy2, dirname
# Returns / emits: None
# Side effects:
#   - creates directories
#   - copies filesystem artifacts
# === End NoemaForge Autodoc Function Header ===
def _copy_file(src: str, dst: str) -> None:
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)


# === NoemaForge Autodoc Function Header ===
# Function: _copy_tree(src: str, dst: str, ignore: Optional[shutil.IgnorePattern] = None)
# Purpose: Implement the routine ' copy tree'.
# Inputs:
#   - src: str
#   - dst: str
#   - ignore: Optional[shutil.IgnorePattern] = None
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - makedirs, isdir, copytree, exists, dirname, rmtree
# Returns / emits: None
# Side effects:
#   - creates directories
# === End NoemaForge Autodoc Function Header ===
def _copy_tree(src: str, dst: str, *, ignore: Optional[shutil.IgnorePattern] = None) -> None:
    if not os.path.exists(src):
        return
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=ignore)


@dataclass
class SnapshotSpec:
    project_id: str
    snapshot_id: str
    snapshot_dir: str
    created_at: str
    actor: str
    reason: str
    include_artifacts: bool = False


CONTROL_PATHS = [
    "project.yaml",
    "backlog.yaml",
    os.path.join("team", "roster.yaml"),
    os.path.join("team", "semaphore.json"),
    os.path.join("team", "wakeq"),
    os.path.join("team", "batons"),
    os.path.join("team", "freeze"),
    "checkpoints",
    "team_eval",
]


# === NoemaForge Autodoc Function Header ===
# Function: snapshots_dir(project_dir: str)
# Purpose: Implement the routine 'snapshots dir'.
# Inputs:
#   - project_dir: str
# Called by:
#   - src/noemaforge_core.py
# Calls:
#   - join
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def snapshots_dir(project_dir: str) -> str:
    return os.path.join(project_dir, "snapshots")


# === NoemaForge Autodoc Function Header ===
# Function: list_snapshots(project_dir: str)
# Purpose: Implement the routine 'list snapshots'.
# Inputs:
#   - project_dir: str
# Called by:
#   - src/noemaforge_core.py
# Calls:
#   - snapshots_dir, listdir, sort, isdir, join, append
# Returns / emits: List[str]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - name, out, p, sd
# === End NoemaForge Autodoc Function Header ===
def list_snapshots(project_dir: str) -> List[str]:
    sd = snapshots_dir(project_dir)
    if not os.path.isdir(sd):
        return []
    out = []
    for name in os.listdir(sd):
        p = os.path.join(sd, name)
        if os.path.isdir(p):
            out.append(name)
    out.sort()
    return out


# === NoemaForge Autodoc Function Header ===
# Function: latest_snapshot(project_dir: str)
# Purpose: Implement the routine 'latest snapshot'.
# Inputs:
#   - project_dir: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - list_snapshots
# Returns / emits: Optional[str]
# Key locals:
#   - snaps
# === End NoemaForge Autodoc Function Header ===
def latest_snapshot(project_dir: str) -> Optional[str]:
    snaps = list_snapshots(project_dir)
    return snaps[-1] if snaps else None


# === NoemaForge Autodoc Function Header ===
# Function: freeze_project(project_dir: str, project_id: str, actor: str, reason: str, include_artifacts: bool = False)
# Purpose: Implement the routine 'freeze project'.
# Inputs:
#   - project_dir: str
#   - project_id: str
#   - actor: str
#   - reason: str
#   - include_artifacts: bool = False
# Called by:
#   - src/worktree_manager.py
# Calls:
#   - join, makedirs, snapshots_dir, _ts, bool, isdir, open, dump, exists, _copy_tree, walk, _copy_file
# Returns / emits: Tuple[bool, Dict[str, Any], str]
# Side effects:
#   - reads or writes files
#   - serializes structured data
#   - creates directories
# Key locals:
#   - art_dst, art_src, dst, f, fn, fp, manifest, mf_path, rel, relp, sd, sid
# === End NoemaForge Autodoc Function Header ===
def freeze_project(
    *,
    project_dir: str,
    project_id: str,
    actor: str,
    reason: str,
    include_artifacts: bool = False,
) -> Tuple[bool, Dict[str, Any], str]:
    sid = f"{_ts()}--{project_id}"
    sd = os.path.join(snapshots_dir(project_dir), sid)
    os.makedirs(sd, exist_ok=True)

    manifest: Dict[str, Any] = {
        "kind": "ProjectSnapshot",
        "project_id": project_id,
        "snapshot_id": sid,
        "created_at": _ts(),
        "actor": actor,
        "reason": reason,
        "include_artifacts": bool(include_artifacts),
        "files": [],
    }

    # Copy control plane
    for rel in CONTROL_PATHS:
        src = os.path.join(project_dir, rel)
        dst = os.path.join(sd, "state", rel)
        if not os.path.exists(src):
            continue
        if os.path.isdir(src):
            _copy_tree(src, dst)
            # enumerate hashes for contained files (shallow)
            for root, _, files in os.walk(dst):
                for fn in files:
                    fp = os.path.join(root, fn)
                    relp = os.path.relpath(fp, sd)
                    try:
                        manifest["files"].append({"path": relp, "sha256": _sha256_file(fp)})
                    except Exception:
                        manifest["files"].append({"path": relp, "sha256": None})
        else:
            _copy_file(src, dst)
            relp = os.path.relpath(dst, sd)
            try:
                manifest["files"].append({"path": relp, "sha256": _sha256_file(dst)})
            except Exception:
                manifest["files"].append({"path": relp, "sha256": None})

    # Optional artifact duplication (off by default)
    if include_artifacts:
        art_src = os.path.join(project_dir, "artifacts")
        art_dst = os.path.join(sd, "artifacts")
        if os.path.isdir(art_src):
            _copy_tree(art_src, art_dst)
            # do not hash every artifact (could be huge)
            manifest["artifacts" ] = {"path": "artifacts", "note": "copied"}
        else:
            manifest["artifacts" ] = {"path": None, "note": "no_artifacts"}
    else:
        manifest["artifacts" ] = {"path": os.path.join(project_dir, "artifacts"), "note": "referenced"}

    # Persist manifest
    mf_path = os.path.join(sd, "snapshot.json")
    with open(mf_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2, sort_keys=True)

    return True, manifest, "ok"


# === NoemaForge Autodoc Function Header ===
# Function: thaw_project(project_dir: str, project_id: str, snapshot_id: str, actor: str, restore_status: str = 'active', restore_artifacts: bool = False)
# Purpose: Implement the routine 'thaw project'.
# Inputs:
#   - project_dir: str
#   - project_id: str
#   - snapshot_id: str
#   - actor: str
#   - restore_status: str = 'active'
#   - restore_artifacts: bool = False
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - join, exists, snapshots_dir, isdir, _copy_tree, _copy_file, isinstance, open, _ts, safe_load, safe_dump
# Returns / emits: Tuple[bool, Dict[str, Any], str]
# Side effects:
#   - reads or writes files
#   - serializes structured data
# Key locals:
#   - art_dst, art_src, dst, f, obj, proj_yaml, rel, sd, src, state_dir
# === End NoemaForge Autodoc Function Header ===
def thaw_project(
    *,
    project_dir: str,
    project_id: str,
    snapshot_id: str,
    actor: str,
    restore_status: str = "active",
    restore_artifacts: bool = False,
) -> Tuple[bool, Dict[str, Any], str]:
    sd = os.path.join(snapshots_dir(project_dir), snapshot_id)
    if not os.path.isdir(sd):
        return False, {"snapshot_id": snapshot_id}, "snapshot_not_found"
    state_dir = os.path.join(sd, "state")
    if not os.path.isdir(state_dir):
        return False, {"snapshot_id": snapshot_id}, "snapshot_missing_state"

    # Restore control plane
    for rel in CONTROL_PATHS:
        src = os.path.join(state_dir, rel)
        dst = os.path.join(project_dir, rel)
        if not os.path.exists(src):
            continue
        if os.path.isdir(src):
            _copy_tree(src, dst)
        else:
            _copy_file(src, dst)

    # Optionally restore artifacts from snapshot copy
    if restore_artifacts:
        art_src = os.path.join(sd, "artifacts")
        art_dst = os.path.join(project_dir, "artifacts")
        if os.path.isdir(art_src):
            _copy_tree(art_src, art_dst)

    # Patch status if project.yaml exists
    proj_yaml = os.path.join(project_dir, "project.yaml")
    if os.path.exists(proj_yaml):
        try:
            import yaml
            with open(proj_yaml, "r", encoding="utf-8") as f:
                obj = yaml.safe_load(f) or {}
            if isinstance(obj, dict):
                obj["status"] = restore_status
                obj["thawed_from"] = snapshot_id
                obj["thawed_at"] = _ts()
                obj["thawed_by"] = actor
                with open(proj_yaml, "w", encoding="utf-8") as f:
                    yaml.safe_dump(obj, f, sort_keys=False, allow_unicode=True)
        except Exception:
            pass

    return True, {"project_id": project_id, "snapshot_id": snapshot_id, "restore_status": restore_status}, "ok"
