#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/worktree_manager.py
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
# File: src/worktree_manager.py
# Purpose: Provide the module 'worktree_manager'.
# Invoked by / imported from:
#   - src/toolproxy.py
# Public API / entry functions:
#   - enter
#   - status
#   - promote
#   - exit
#   - main
# Inputs:
#   - project_id
#   - repo_path
#   - --actor
#   - --base-ref
#   - --worktree-id
#   - worktree_id
#   - Common path inputs: /var/lib/noemaforge/projects
#   - Imports: __future__, argparse, datetime, json, os, shutil, subprocess, uuid
# Output formats / side effects:
#   - JSON files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===


import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import uuid
from typing import Any, Dict, List, Optional

try:
    from project_snapshot import freeze_project
except Exception:
    freeze_project = None  # type: ignore

BASE_DIR = "/var/lib/noemaforge/projects"


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
# Function: _slug()
# Purpose: Implement the routine ' slug'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - src/coordinator_fanout.py
#   - src/team_memory_sync.py
# Calls:
#   - strftime, uuid4, utcnow
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _slug() -> str:
    return dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]


# === NoemaForge Autodoc Function Header ===
# Function: _project_dir(project_id: str)
# Purpose: Implement the routine ' project dir'.
# Inputs:
#   - project_id: str
# Called by:
#   - src/plan_mode.py
# Calls:
#   - join, strip, str
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _project_dir(project_id: str) -> str:
    return os.path.join(BASE_DIR, str(project_id).strip())


# === NoemaForge Autodoc Function Header ===
# Function: _worktrees_root(project_id: str)
# Purpose: Implement the routine ' worktrees root'.
# Inputs:
#   - project_id: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - join, _project_dir
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _worktrees_root(project_id: str) -> str:
    return os.path.join(_project_dir(project_id), "worktrees")


# === NoemaForge Autodoc Function Header ===
# Function: _worktree_dir(project_id: str, worktree_id: str)
# Purpose: Implement the routine ' worktree dir'.
# Inputs:
#   - project_id: str
#   - worktree_id: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - join, _worktrees_root
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _worktree_dir(project_id: str, worktree_id: str) -> str:
    return os.path.join(_worktrees_root(project_id), worktree_id)


# === NoemaForge Autodoc Function Header ===
# Function: _meta_path(project_id: str, worktree_id: str)
# Purpose: Implement the routine ' meta path'.
# Inputs:
#   - project_id: str
#   - worktree_id: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - join, _worktree_dir
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _meta_path(project_id: str, worktree_id: str) -> str:
    return os.path.join(_worktree_dir(project_id, worktree_id), ".noemaforge-worktree.json")


# === NoemaForge Autodoc Function Header ===
# Function: _ensure(project_id: str, worktree_id: str = '')
# Purpose: Implement the routine ' ensure'.
# Inputs:
#   - project_id: str
#   - worktree_id: str = ''
# Called by:
#   - src/notifier.py
#   - src/plan_mode.py
# Calls:
#   - makedirs, _worktrees_root, _worktree_dir
# Returns / emits: str
# Side effects:
#   - creates directories
# Key locals:
#   - p
# === End NoemaForge Autodoc Function Header ===
def _ensure(project_id: str, worktree_id: str = "") -> str:
    p = _worktrees_root(project_id) if not worktree_id else _worktree_dir(project_id, worktree_id)
    os.makedirs(p, exist_ok=True)
    return p


# === NoemaForge Autodoc Function Header ===
# Function: _git()
# Purpose: Implement the routine ' git'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - which
# Returns / emits: Optional[str]
# === End NoemaForge Autodoc Function Header ===
def _git() -> Optional[str]:
    return shutil.which("git")


# === NoemaForge Autodoc Function Header ===
# Function: _is_git_repo(path: str)
# Purpose: Implement the routine ' is git repo'.
# Inputs:
#   - path: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - isdir, isfile, join
# Returns / emits: bool
# === End NoemaForge Autodoc Function Header ===
def _is_git_repo(path: str) -> bool:
    return os.path.isdir(os.path.join(path, ".git")) or os.path.isfile(os.path.join(path, ".git"))


# === NoemaForge Autodoc Function Header ===
# Function: _run(cmd: List[str])
# Purpose: Implement the routine ' run'.
# Inputs:
#   - cmd: List[str]
# Called by:
#   - src/bootdoctor.py
#   - src/hwscan.py
#   - src/storage_broker.py
# Calls:
#   - run
# Returns / emits: subprocess.CompletedProcess
# Side effects:
#   - spawns subprocesses or workers
# === End NoemaForge Autodoc Function Header ===
def _run(cmd: List[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


# === NoemaForge Autodoc Function Header ===
# Function: _save_meta(project_id: str, worktree_id: str, meta: Dict[str, Any])
# Purpose: Implement the routine ' save meta'.
# Inputs:
#   - project_id: str
#   - worktree_id: str
#   - meta: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _ensure, replace, _meta_path, open, dump
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads or writes files
#   - serializes structured data
# Key locals:
#   - f, tmp
# === End NoemaForge Autodoc Function Header ===
def _save_meta(project_id: str, worktree_id: str, meta: Dict[str, Any]) -> Dict[str, Any]:
    _ensure(project_id, worktree_id)
    tmp = _meta_path(project_id, worktree_id) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _meta_path(project_id, worktree_id))
    return meta


# === NoemaForge Autodoc Function Header ===
# Function: _load_meta(project_id: str, worktree_id: str)
# Purpose: Implement the routine ' load meta'.
# Inputs:
#   - project_id: str
#   - worktree_id: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - open, load, isinstance, _meta_path
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads or writes files
# Key locals:
#   - f, obj
# === End NoemaForge Autodoc Function Header ===
def _load_meta(project_id: str, worktree_id: str) -> Dict[str, Any]:
    try:
        with open(_meta_path(project_id, worktree_id), "r", encoding="utf-8") as f:
            obj = json.load(f)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


# === NoemaForge Autodoc Function Header ===
# Function: enter(project_id: str, repo_path: str, actor: str = 'toolproxy', base_ref: str = 'HEAD')
# Purpose: Implement the routine 'enter'.
# Inputs:
#   - project_id: str
#   - repo_path: str
#   - actor: str = 'toolproxy'
#   - base_ref: str = 'HEAD'
# Called by:
#   - src/plan_mode.py
#   - src/toolproxy.py
# Calls:
#   - _slug, _worktree_dir, makedirs, abspath, _save_meta, strip, ValueError, dirname, isdir, _git, _is_git_repo, _run
# Returns / emits: Dict[str, Any]
# Side effects:
#   - creates directories
#   - spawns subprocesses or workers
# Key locals:
#   - base_branch, branch, meta, mode, p, repo_path, snapshot, worktree_id, wt_dir
# === End NoemaForge Autodoc Function Header ===
def enter(
    *,
    project_id: str,
    repo_path: str,
    actor: str = "toolproxy",
    base_ref: str = "HEAD",
) -> Dict[str, Any]:
    if not str(project_id).strip():
        raise ValueError("missing_project_id")
    if not str(repo_path).strip():
        raise ValueError("missing_repo_path")
    worktree_id = _slug()
    wt_dir = _worktree_dir(project_id, worktree_id)
    os.makedirs(os.path.dirname(wt_dir), exist_ok=True)
    repo_path = os.path.abspath(repo_path)
    snapshot = None
    if freeze_project is not None and os.path.isdir(_project_dir(project_id)):
        try:
            ok, snapshot, _ = freeze_project(project_dir=_project_dir(project_id), project_id=project_id, actor=actor, reason="worktree.enter", include_artifacts=False)
            if not ok:
                snapshot = None
        except Exception:
            snapshot = None

    mode = "copy"
    branch = ""
    base_branch = ""
    if _git() and _is_git_repo(repo_path):
        p = _run([_git(), "-C", repo_path, "rev-parse", "--abbrev-ref", "HEAD"])
        if p.returncode == 0:
            base_branch = (p.stdout or "").strip()
        branch = f"noemaforge26-{worktree_id[:8]}"
        p = _run([_git(), "-C", repo_path, "worktree", "add", "-b", branch, wt_dir, base_ref])
        if p.returncode != 0:
            raise RuntimeError(f"git_worktree_add_failed:{(p.stderr or p.stdout).strip()}")
        mode = "git"
    else:
        shutil.copytree(repo_path, wt_dir, ignore=shutil.ignore_patterns("__pycache__", ".git", ".pytest_cache"))
    meta = {
        "kind": "NoemaForgeWorktree",
        "version": "0.26.0",
        "project_id": project_id,
        "worktree_id": worktree_id,
        "created_at": _nowz(),
        "actor": actor,
        "repo_path": repo_path,
        "path": wt_dir,
        "mode": mode,
        "base_ref": base_ref,
        "base_branch": base_branch,
        "branch": branch,
        "status": "active",
        "snapshot": snapshot,
    }
    _save_meta(project_id, worktree_id, meta)
    return {"ok": True, "worktree": meta}


# === NoemaForge Autodoc Function Header ===
# Function: status(project_id: str, worktree_id: str = '')
# Purpose: Implement the routine 'status'.
# Inputs:
#   - project_id: str
#   - worktree_id: str = ''
# Called by:
#   - src/plan_mode.py
#   - src/toolproxy.py
# Calls:
#   - _worktrees_root, isdir, sorted, _load_meta, append, _git, _run, get, listdir, str, join, splitlines
# Returns / emits: Dict[str, Any]
# Side effects:
#   - spawns subprocesses or workers
#   - appends to logs or files
# Key locals:
#   - ids, meta, out, p, root, wid
# === End NoemaForge Autodoc Function Header ===
def status(*, project_id: str, worktree_id: str = "") -> Dict[str, Any]:
    root = _worktrees_root(project_id)
    if not os.path.isdir(root):
        return {"ok": True, "worktrees": []}
    ids = [worktree_id] if worktree_id else sorted([x for x in os.listdir(root) if os.path.isdir(os.path.join(root, x))])
    out = []
    for wid in ids:
        meta = _load_meta(project_id, wid)
        if not meta:
            continue
        if meta.get("mode") == "git" and _git():
            p = _run([_git(), "-C", str(meta.get("path")), "status", "--short"])
            meta["changes"] = [ln for ln in (p.stdout or "").splitlines() if ln.strip()] if p.returncode == 0 else []
        out.append(meta)
    return {"ok": True, "worktrees": out}


# === NoemaForge Autodoc Function Header ===
# Function: promote(project_id: str, worktree_id: str, actor: str = 'toolproxy')
# Purpose: Implement the routine 'promote'.
# Inputs:
#   - project_id: str
#   - worktree_id: str
#   - actor: str = 'toolproxy'
# Called by:
#   - src/toolproxy.py
# Calls:
#   - _load_meta, str, _run, _nowz, _save_meta, ValueError, RuntimeError, get, _git, strip
# Returns / emits: Dict[str, Any]
# Side effects:
#   - spawns subprocesses or workers
# Key locals:
#   - branch, meta, p, repo_path
# === End NoemaForge Autodoc Function Header ===
def promote(*, project_id: str, worktree_id: str, actor: str = "toolproxy") -> Dict[str, Any]:
    meta = _load_meta(project_id, worktree_id)
    if not meta:
        raise ValueError("unknown_worktree")
    if str(meta.get("status") or "") != "active":
        return {"ok": True, "worktree": meta}
    if meta.get("mode") != "git" or not _git():
        meta["status"] = "promotion_pending_manual_merge"
        meta["promoted_at"] = _nowz()
        meta["promoted_by"] = actor
        _save_meta(project_id, worktree_id, meta)
        return {"ok": True, "worktree": meta, "note": "manual_merge_required"}
    repo_path = str(meta.get("repo_path") or "")
    branch = str(meta.get("branch") or "")
    p = _run([_git(), "-C", repo_path, "merge", "--no-ff", "--no-edit", branch])
    if p.returncode != 0:
        raise RuntimeError(f"git_merge_failed:{(p.stderr or p.stdout).strip()}")
    meta["status"] = "promoted"
    meta["promoted_at"] = _nowz()
    meta["promoted_by"] = actor
    _save_meta(project_id, worktree_id, meta)
    return {"ok": True, "worktree": meta}


# === NoemaForge Autodoc Function Header ===
# Function: exit(project_id: str, worktree_id: str, actor: str = 'toolproxy', discard: bool = True)
# Purpose: Implement the routine 'exit'.
# Inputs:
#   - project_id: str
#   - worktree_id: str
#   - actor: str = 'toolproxy'
#   - discard: bool = True
# Called by:
#   - src/localgw_uplink_agent.py
#   - src/plan_mode.py
#   - src/toolproxy.py
#   - tools/sim/simulate_prestart.py
# Calls:
#   - _load_meta, str, isdir, _nowz, _save_meta, ValueError, get, _git, _run, rmtree, RuntimeError, strip
# Returns / emits: Dict[str, Any]
# Side effects:
#   - spawns subprocesses or workers
# Key locals:
#   - meta, mode, p, path
# === End NoemaForge Autodoc Function Header ===
def exit(*, project_id: str, worktree_id: str, actor: str = "toolproxy", discard: bool = True) -> Dict[str, Any]:
    meta = _load_meta(project_id, worktree_id)
    if not meta:
        raise ValueError("unknown_worktree")
    path = str(meta.get("path") or "")
    mode = str(meta.get("mode") or "copy")
    if os.path.isdir(path):
        if mode == "git" and _git():
            p = _run([_git(), "-C", str(meta.get("repo_path") or ""), "worktree", "remove", "--force", path])
            if p.returncode != 0:
                raise RuntimeError(f"git_worktree_remove_failed:{(p.stderr or p.stdout).strip()}")
        else:
            shutil.rmtree(path, ignore_errors=True)
    meta["status"] = "discarded" if discard else "closed"
    meta["closed_at"] = _nowz()
    meta["closed_by"] = actor
    _save_meta(project_id, worktree_id, meta)
    return {"ok": True, "worktree": meta}


# === NoemaForge Autodoc Function Header ===
# Function: main(argv: Optional[List[str]] = None)
# Purpose: Implement the routine 'main'.
# Inputs:
#   - argv: Optional[List[str]] = None
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
#   - ArgumentParser, add_subparsers, add_parser, add_argument, parse_args, print, enter, dumps, status, promote, exit
# Returns / emits: int
# Side effects:
#   - serializes structured data
# Key locals:
#   - ap, ns, out, p, sub
# === End NoemaForge Autodoc Function Header ===
def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("enter")
    p.add_argument("project_id")
    p.add_argument("repo_path")
    p.add_argument("--actor", default="cli")
    p.add_argument("--base-ref", default="HEAD")
    p = sub.add_parser("status")
    p.add_argument("project_id")
    p.add_argument("--worktree-id", default="")
    p = sub.add_parser("promote")
    p.add_argument("project_id")
    p.add_argument("worktree_id")
    p.add_argument("--actor", default="cli")
    p = sub.add_parser("exit")
    p.add_argument("project_id")
    p.add_argument("worktree_id")
    p.add_argument("--actor", default="cli")

    ns = ap.parse_args(argv)
    if ns.cmd == "enter":
        out = enter(project_id=ns.project_id, repo_path=ns.repo_path, actor=ns.actor, base_ref=ns.base_ref)
    elif ns.cmd == "status":
        out = status(project_id=ns.project_id, worktree_id=ns.worktree_id)
    elif ns.cmd == "promote":
        out = promote(project_id=ns.project_id, worktree_id=ns.worktree_id, actor=ns.actor)
    else:
        out = exit(project_id=ns.project_id, worktree_id=ns.worktree_id, actor=ns.actor)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
