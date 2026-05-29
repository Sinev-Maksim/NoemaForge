#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/offline_apt.py
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
# File: src/offline_apt.py
# Purpose: Provide the module 'offline_apt'.
# Invoked by / imported from:
#   - src/brainctl.py
# Public API / entry functions:
#   - resolve_packages_from_installer
#   - build_offline_apt_plan
#   - build_offline_repo_from_plan
# Inputs:
#   - Common path inputs: /workspace/outbox/offline-apt, /var/lib/noemaforge/offline-apt/plans, /opt/noemaforge/bootstrap/noemaforge-bootstrap.sh, noemaforge.offline_apt.plan/v1, noemaforge.bundle/v1, noemaforge.prestart/v1
#   - Imports: __future__, datetime, hashlib, json, os, re, platform, shutil
# Output formats / side effects:
#   - JSON files
#   - YAML files
#   - copied filesystem artifacts
#   - Markdown files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""offline_apt.py (v0.11.0)

Offline APT builder + driver-vault helper.

Why this exists:
  - NoemaForge is offline-first (no network by default).
  - Yet we still need baseline + driver packages (firmware, GPU drivers, tools).
  - The safest pattern is: build an offline APT repo on a networked builder machine,
    bring it in as an attested offline artifact, and only then install.

This module supports two workflows:

1) PLAN (deterministic, can run on offline target)
   - Read installer-policy.yaml (bundle_catalog + apt_baseline)
   - Run hwscan + installer_plan to determine recommended bundles
   - Resolve bundle -> apt packages
   - Emit an "offline-apt plan" + a builder shell script template

2) BUILD (runs on a builder machine WITH network)
   - Given a plan JSON (or explicit package list), download .deb packages with deps
   - Generate Packages / Packages.gz
   - Create a tar.gz artifact compatible with BundlePolicy kind=AptRepoBundle
   - Emit a manifest template and checksums

Important:
  - This module does NOT enable network on NoemaForge.
  - It does NOT auto-install; it only prepares artifacts.
"""


import datetime as dt
import hashlib
import json
import os
import re
import platform
import shutil
import subprocess
import tarfile
from typing import Any, Dict, List, Optional, Set, Tuple

import yaml

from hwscan import collect_inventory
from installer_plan import build_plan, load_policy as load_installer_policy
from toolvault import sha256_file


DEFAULT_OUTBOX_DIR = "/workspace/outbox/offline-apt"
DEFAULT_PLANS_DIR = "/var/lib/noemaforge/offline-apt/plans"


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
# Function: _read_os_release()
# Purpose: Implement the routine ' read os release'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - open, splitlines, strip, split, read
# Returns / emits: Dict[str, str]
# Side effects:
#   - reads or writes files
# Key locals:
#   - f, ln, out
# === End NoemaForge Autodoc Function Header ===
def _read_os_release() -> Dict[str, str]:
    out: Dict[str, str] = {}
    try:
        with open("/etc/os-release", "r", encoding="utf-8") as f:
            for ln in f.read().splitlines():
                ln = ln.strip()
                if not ln or "=" not in ln:
                    continue
                k, v = ln.split("=", 1)
                out[k.strip()] = v.strip().strip('"')
    except Exception:
        pass
    return out


# === NoemaForge Autodoc Function Header ===
# Function: _dedup_sorted(xs: List[str])
# Purpose: Implement the routine ' dedup sorted'.
# Inputs:
#   - xs: List[str]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - set, sorted, strip, str
# Returns / emits: List[str]
# Key locals:
#   - s
# === End NoemaForge Autodoc Function Header ===
def _dedup_sorted(xs: List[str]) -> List[str]:
    s = set([x.strip() for x in xs if str(x).strip()])
    return sorted(s)


BOOTSTRAP_CANDIDATE_PATHS = [
    "/opt/noemaforge/bootstrap/noemaforge-bootstrap.sh",
    # dev / seed-kit layout
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "bootstrap", "noemaforge-bootstrap.sh")),
]


# === NoemaForge Autodoc Function Header ===
# Function: _extract_bootstrap_base_pkgs()
# Purpose: Best-effort: parse BASE_PKGS=(...) from noemaforge-bootstrap.sh.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - read, search, group, split, _dedup_sorted, exists, strip, append, open, replace, startswith
# Returns / emits: List[str]
# Side effects:
#   - reads or writes files
#   - appends to logs or files
# Key locals:
#   - body, m, path, t, t2, toks, txt
# === End NoemaForge Autodoc Function Header ===
def _extract_bootstrap_base_pkgs() -> List[str]:
    """Best-effort: parse BASE_PKGS=(...) from noemaforge-bootstrap.sh.

    Why: offline-apt repo must include the same packages bootstrap tries to install,
    otherwise the target (no-network) will fail to bring the spine up.

    Returns: deduped sorted package list (may be empty if not detected).
    """
    for path in BOOTSTRAP_CANDIDATE_PATHS:
        try:
            if not os.path.exists(path):
                continue
            txt = open(path, "r", encoding="utf-8", errors="ignore").read()
            m = re.search(r"^BASE_PKGS=\(([^)]*)\)", txt, flags=re.MULTILINE)
            if not m:
                continue
            body = m.group(1)
            toks = []
            for t in (body or "").replace('\n', ' ').split():
                t2 = t.strip().strip('\"').strip("'")
                if not t2:
                    continue
                # Skip bash expansions (shouldn't appear here, but be conservative)
                if t2.startswith('$') or '@' in t2:
                    continue
                toks.append(t2)
            return _dedup_sorted(toks)
        except Exception:
            continue
    return []


# === NoemaForge Autodoc Function Header ===
# Function: resolve_packages_from_installer(installer_policy: Dict[str, Any], installer_plan: Dict[str, Any])
# Purpose: Resolve apt packages for the current hardware plan.
# Inputs:
#   - installer_policy: Dict[str, Any]
#   - installer_plan: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - set, _extract_bootstrap_base_pkgs, append, get, strip, sorted, add, isinstance, str, _dedup_sorted
# Returns / emits: Tuple[List[str], Dict[str, List[str]], List[str]]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - b, base_pkgs, bl, bundle_catalog, by_bundle, defaults, kind, p, pkgs, problems, r, recs
# === End NoemaForge Autodoc Function Header ===
def resolve_packages_from_installer(
    *,
    installer_policy: Dict[str, Any],
    installer_plan: Dict[str, Any],
) -> Tuple[List[str], Dict[str, List[str]], List[str]]:
    """Resolve apt packages for the current hardware plan.

    Returns: (packages, by_bundle, problems)
    """
    problems: List[str] = []
    pkgs: Set[str] = set()
    by_bundle: Dict[str, List[str]] = {}

    # Must include bootstrap spine packages for offline bring-up.
    base_pkgs = _extract_bootstrap_base_pkgs()
    if not base_pkgs:
        problems.append('bootstrap_base_pkgs_missing')
    for p in base_pkgs:
        if p:
            pkgs.add(str(p).strip())

    defaults = installer_policy.get("defaults") or {}
    for p in (defaults.get("apt_baseline") or []) or []:
        if p:
            pkgs.add(str(p).strip())

    recs = installer_plan.get("recommendations") or []
    bundle_catalog = installer_policy.get("bundle_catalog") or {}
    for r in recs:
        if not isinstance(r, dict):
            continue
        rtype = str(r.get("type") or "").strip()
        rid = str(r.get("id") or "").strip()
        if not rid:
            continue
        if rtype == "apt":
            pkgs.add(rid)
        elif rtype == "bundle":
            b = bundle_catalog.get(rid)
            if not isinstance(b, dict):
                problems.append(f"bundle_unknown:{rid}")
                continue
            kind = str(b.get("kind") or "").strip()
            if kind != "apt-packages":
                problems.append(f"bundle_kind_not_apt:{rid}:{kind}")
                continue
            bl = []
            for p in (b.get("packages") or []) or []:
                if p:
                    bl.append(str(p).strip())
                    pkgs.add(str(p).strip())
            by_bundle[rid] = _dedup_sorted(bl)

    return sorted(pkgs), by_bundle, problems


# === NoemaForge Autodoc Function Header ===
# Function: build_offline_apt_plan(outbox_dir: str = DEFAULT_OUTBOX_DIR)
# Purpose: Create an offline-apt plan artifact (deterministic).
# Inputs:
#   - outbox_dir: str = DEFAULT_OUTBOX_DIR
# Called by:
#   - src/brainctl.py
# Calls:
#   - makedirs, collect_inventory, load_installer_policy, build_plan, resolve_packages_from_installer, _read_os_release, encode, join, copy2, append, _nowz, _extract_bootstrap_base_pkgs
# Returns / emits: Dict[str, str]
# Side effects:
#   - creates directories
#   - copies filesystem artifacts
#   - appends to logs or files
# Key locals:
#   - base, bundle_id, f, inv, manifest, md, osr, p, p_json, p_manifest_tpl, p_md, p_out_json
# === End NoemaForge Autodoc Function Header ===
def build_offline_apt_plan(*, outbox_dir: str = DEFAULT_OUTBOX_DIR) -> Dict[str, str]:
    """Create an offline-apt plan artifact (deterministic)."""
    os.makedirs(outbox_dir, exist_ok=True)
    os.makedirs(DEFAULT_PLANS_DIR, exist_ok=True)

    inv = collect_inventory(level="summary")
    pol = load_installer_policy(epoch_dir=None)
    plan = build_plan(inv, pol)

    pkgs, by_bundle, problems = resolve_packages_from_installer(installer_policy=pol, installer_plan=plan)

    osr = _read_os_release()
    plan_obj: Dict[str, Any] = {
        "schema": "noemaforge.offline_apt.plan/v1",
        "created_at": _nowz(),
        "bootstrap_base_packages": _extract_bootstrap_base_pkgs(),
        "hardware_fingerprint": plan.get("hardware_fingerprint"),
        "device_uid": plan.get("device_uid"),
        "os_release": {"ID": osr.get("ID"), "VERSION_ID": osr.get("VERSION_ID"), "VERSION_CODENAME": osr.get("VERSION_CODENAME")},
        "packages": pkgs,
        "packages_by_bundle": by_bundle,
        "installer_plan_id": plan.get("plan_id"),
        "notes": [
            "Build the repo on a networked builder machine with the SAME distro family/version.",
            "This plan is deterministic; it does not execute network operations.",
        ],
        "problems": problems,
    }

    raw = json.dumps(plan_obj, sort_keys=True, ensure_ascii=False).encode("utf-8")
    pid = hashlib.sha256(raw).hexdigest()[:16]
    plan_obj["offline_apt_plan_id"] = pid

    base = f"offline-apt-plan-{pid}"
    p_json = os.path.join(DEFAULT_PLANS_DIR, f"{base}.json")
    p_out_json = os.path.join(outbox_dir, f"{base}.json")
    p_md = os.path.join(outbox_dir, f"{base}.md")
    p_sh = os.path.join(outbox_dir, f"{base}.builder.sh")
    p_manifest_tpl = os.path.join(outbox_dir, f"{base}.aptrepo-bundle.manifest.yaml")
    p_req = os.path.join(outbox_dir, f"{base}.prestart-request.yaml")

    with open(p_json, "w", encoding="utf-8") as f:
        json.dump(plan_obj, f, ensure_ascii=False, indent=2)
    shutil.copy2(p_json, p_out_json)

    md: List[str] = []
    md.append(f"# Offline APT Plan {pid}")
    md.append(f"- created_at: {plan_obj['created_at']}")
    md.append(f"- device_uid: {plan_obj.get('device_uid')}")
    md.append(f"- hardware_fingerprint: {plan_obj.get('hardware_fingerprint')}")
    md.append("")
    md.append("## Packages")
    for p in pkgs:
        md.append(f"- {p}")
    if by_bundle:
        md.append("")
        md.append("## Bundles → packages")
        for bid, lst in sorted(by_bundle.items()):
            md.append(f"- {bid}:")
            for p in lst:
                md.append(f"  - {p}")
    if problems:
        md.append("")
        md.append("## Problems")
        for pr in problems:
            md.append(f"- {pr}")
    with open(p_md, "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")

    pkgs_join = " ".join(pkgs)
    sh_lines: List[str] = []
    sh_lines.append("#!/usr/bin/env bash")
    sh_lines.append("set -euo pipefail")
    sh_lines.append("")
    sh_lines.append("# Builder script generated by NoemaForge (offline_apt.py)")
    sh_lines.append("# Run this on a NETWORKED builder machine.")
    sh_lines.append("# Requirements: apt-get, dpkg-scanpackages (dpkg-dev)")
    sh_lines.append("")
    sh_lines.append("OUT=${1:-noemaforge-offline-apt}")
    sh_lines.append("mkdir -p \"$OUT/aptrepo/debs\"")
    sh_lines.append("cd \"$OUT\"")
    sh_lines.append("sudo apt-get update")
    sh_lines.append("sudo apt-get install -y dpkg-dev")
    sh_lines.append("sudo apt-get -y -o Dir::Cache::archives=\"$PWD/aptrepo/debs\" --download-only install " + pkgs_join)
    sh_lines.append("cd aptrepo")
    sh_lines.append("dpkg-scanpackages debs /dev/null > Packages")
    sh_lines.append("gzip -kf Packages")
    sh_lines.append("echo \"OK: built aptrepo at $PWD\"")
    with open(p_sh, "w", encoding="utf-8") as f:
        f.write("\n".join(sh_lines) + "\n")
    try:
        os.chmod(p_sh, 0o755)
    except Exception:
        pass

    bundle_id = f"aptrepo-{plan_obj.get('device_uid','hw:unknown')}-{pid}"
    manifest = {
        "apiVersion": "noemaforge.bundle/v1",
        "kind": "AptRepoBundle",
        "bundle_id": bundle_id,
        "artifact_format": "tar.gz",
        "created_at": plan_obj["created_at"],
        "source_plan": {"offline_apt_plan_id": pid, "installer_plan_id": plan_obj.get("installer_plan_id")},
        "os_release": plan_obj.get("os_release"),
        "packages": pkgs,
        "layout": {"packages_file": "Packages", "debs_dir": "debs"},
        "notes": [
            "This manifest is a TEMPLATE. After building artifact.tar.gz, compute sha256 and pin it in PreStartChangeRequest.",
        ],
    }
    with open(p_manifest_tpl, "w", encoding="utf-8") as f:
        yaml.safe_dump(manifest, f, sort_keys=False, allow_unicode=True)

    req = {
        "apiVersion": "noemaforge.prestart/v1",
        "kind": "PreStartChangeRequest",
        "request_id": f"offline-apt-{pid}",
        "created_at": plan_obj["created_at"],
        "created_by": {"actor_type": "human", "channel": "offline_apt"},
        "status": "draft",
        "requested_changes": {
            "bundles_add": [
                {
                    "bundle_id": bundle_id,
                    "kind": "AptRepoBundle",
                    "manifest_sha256": "",
                    "artifact_sha256": "",
                    "manifest_path": "",
                    "artifact_path": "",
                    "note": "Fill sha256 locks + put manifest/artifact into ToolVault before applying",
                }
            ]
        },
        "user_comment": "AUTO-GENERATED skeleton. Review, fill sha256 locks, run FULL canary, then apply epoch.",
    }
    with open(p_req, "w", encoding="utf-8") as f:
        yaml.safe_dump(req, f, sort_keys=False, allow_unicode=True)

    return {
        "plan_json": p_out_json,
        "plan_md": p_md,
        "builder_script": p_sh,
        "manifest_template": p_manifest_tpl,
        "prestart_request_skeleton": p_req,
    }


# === NoemaForge Autodoc Function Header ===
# Function: _tar_add_deterministic(tf: tarfile.TarFile, src_dir: str)
# Purpose: Implement the routine ' tar add deterministic'.
# Inputs:
#   - tf: tarfile.TarFile
#   - src_dir: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - walk, sort, join, relpath, gettarinfo, open, addfile, listdir
# Returns / emits: None
# Side effects:
#   - reads or writes files
# Key locals:
#   - d, f, fn, p, pd, rel, rel_d, ti
# === End NoemaForge Autodoc Function Header ===
def _tar_add_deterministic(tf: tarfile.TarFile, src_dir: str) -> None:
    for root, dirs, files in os.walk(src_dir):
        dirs.sort()
        files.sort()
        for fn in files:
            p = os.path.join(root, fn)
            rel = os.path.relpath(p, src_dir)
            ti = tf.gettarinfo(p, arcname=rel)
            ti.mtime = 0
            with open(p, "rb") as f:
                tf.addfile(ti, fileobj=f)
        for d in dirs:
            pd = os.path.join(root, d)
            rel_d = os.path.relpath(pd, src_dir)
            if not os.listdir(pd):
                ti = tf.gettarinfo(pd, arcname=rel_d)
                ti.mtime = 0
                tf.addfile(ti)


# === NoemaForge Autodoc Function Header ===
# Function: build_offline_repo_from_plan(plan_json_path: str, repo_dir: str, artifact_out: str, bundle_manifest_path: Optional[str] = None, run_apt_update: bool = True)
# Purpose: Implement the routine 'build offline repo from plan'.
# Inputs:
#   - plan_json_path: str
#   - repo_dir: str
#   - artifact_out: str
#   - bundle_manifest_path: Optional[str] = None
#   - run_apt_update: bool = True
# Called by:
#   - src/brainctl.py
# Calls:
#   - load, join, makedirs, check_call, sha256_file, open, str, RuntimeError, _tar_add_deterministic, exists, isinstance, strip
# Returns / emits: Dict[str, str]
# Side effects:
#   - reads or writes files
#   - creates directories
# Key locals:
#   - artifact_sha, cmd, debs, f, mf, obj, pkg_path, pkgs, tf
# === End NoemaForge Autodoc Function Header ===
def build_offline_repo_from_plan(
    *,
    plan_json_path: str,
    repo_dir: str,
    artifact_out: str,
    bundle_manifest_path: Optional[str] = None,
    run_apt_update: bool = True,
) -> Dict[str, str]:
    obj = json.load(open(plan_json_path, "r", encoding="utf-8"))
    pkgs = [str(x) for x in (obj.get("packages") or []) if str(x).strip()]
    if not pkgs:
        raise RuntimeError("no_packages_in_plan")

    debs = os.path.join(repo_dir, "debs")
    os.makedirs(debs, exist_ok=True)

    if run_apt_update:
        subprocess.check_call(["sudo", "apt-get", "update"])
    subprocess.check_call(["sudo", "apt-get", "install", "-y", "dpkg-dev"])
    cmd = [
        "sudo",
        "apt-get",
        "-y",
        "-o",
        f"Dir::Cache::archives={debs}",
        "--download-only",
        "install",
    ] + pkgs
    subprocess.check_call(cmd)

    pkg_path = os.path.join(repo_dir, "Packages")
    with open(pkg_path, "w", encoding="utf-8") as f:
        subprocess.check_call(["dpkg-scanpackages", "debs", "/dev/null"], cwd=repo_dir, stdout=f)
    subprocess.check_call(["gzip", "-kf", "Packages"], cwd=repo_dir)

    os.makedirs(os.path.dirname(artifact_out) or ".", exist_ok=True)
    with tarfile.open(artifact_out, "w:gz") as tf:
        _tar_add_deterministic(tf, repo_dir)

    artifact_sha = sha256_file(artifact_out)

    if bundle_manifest_path and os.path.exists(bundle_manifest_path):
        mf = yaml.safe_load(open(bundle_manifest_path, "r", encoding="utf-8")) or {}
        if isinstance(mf, dict):
            mf["artifact_sha256"] = artifact_sha
            mf["built_at"] = _nowz()
            mf["builder"] = {"platform": platform.platform(), "python": platform.python_version()}
            with open(bundle_manifest_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(mf, f, sort_keys=False, allow_unicode=True)

    return {
        "repo_dir": repo_dir,
        "artifact_path": artifact_out,
        "artifact_sha256": artifact_sha,
    }
