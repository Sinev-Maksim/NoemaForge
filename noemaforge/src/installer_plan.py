#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/installer_plan.py
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
# File: src/installer_plan.py
# Purpose: Provide the module 'installer_plan'.
# Invoked by / imported from:
#   - src/bootdoctor.py
#   - src/brainctl.py
#   - src/offline_apt.py
# Public API / entry functions:
#   - load_policy
#   - build_plan
#   - write_plan
# Inputs:
#   - Common path inputs: /opt/noemaforge/configs, noemaforge.installer.plan/v1, /var/lib/noemaforge/installer/plans, /workspace/outbox/installer-plan, noemaforge.prestart/v1
#   - Imports: __future__, datetime, hashlib, json, os, typing, yaml, hwscan
# Output formats / side effects:
#   - JSON files
#   - YAML files
#   - Markdown files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""installer_plan.py (v0.11.0)

Deterministic installer planning (no installs).

Inputs:
- hardware inventory (hwscan.collect_inventory)
- installer-policy.yaml (epoch policy)

Outputs:
- JSON plan + human-readable markdown
- optional skeleton PreStartChangeRequest (NOT auto-applied)

This is part of the "spine": no LLM, no network.
"""


import datetime as dt
import hashlib
import json
import os
from typing import Any, Dict, List, Optional, Tuple

import yaml

from hwscan import fingerprint_inventory
from platform_paths import DEFAULT_PATHS as _pp


CONFIG_DIR = str(_pp.root / "configs")


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
# Function: load_policy(epoch_dir: Optional[str] = None)
# Purpose: Implement the routine 'load policy'.
# Inputs:
#   - epoch_dir: Optional[str] = None
# Called by:
#   - src/audit_remediation.py
#   - src/bootdoctor.py
#   - src/brainctl.py
#   - src/daily_scheduler.py
#   - src/lsm.py
#   - src/maintenance.py
#   - src/resource_policy.py
#   - src/role_runner.py
# Calls:
#   - append, join, exists, isinstance, open, safe_load
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads or writes files
#   - appends to logs or files
# Key locals:
#   - candidates, f, p, y
# === End NoemaForge Autodoc Function Header ===
def load_policy(epoch_dir: Optional[str] = None) -> Dict[str, Any]:
    # Prefer epoch policy if provided, else /opt/noemaforge/configs.
    candidates: List[str] = []
    if epoch_dir:
        candidates.append(os.path.join(epoch_dir, "installer-policy.yaml"))
    candidates.append(os.path.join(CONFIG_DIR, "installer-policy.yaml"))
    for p in candidates:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    y = yaml.safe_load(f) or {}
                if isinstance(y, dict):
                    return y
            except Exception:
                continue
    return {}


# === NoemaForge Autodoc Function Header ===
# Function: _match_prefix(value: str, prefix: str)
# Purpose: Implement the routine ' match prefix'.
# Inputs:
#   - value: str
#   - prefix: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - strip, bool, startswith, lower
# Returns / emits: bool
# Key locals:
#   - p, v
# === End NoemaForge Autodoc Function Header ===
def _match_prefix(value: str, prefix: str) -> bool:
    v = (value or "").lower().strip()
    p = (prefix or "").lower().strip()
    return bool(v) and bool(p) and v.startswith(p)


# === NoemaForge Autodoc Function Header ===
# Function: _recommend_from_pci(inv: Dict[str, Any], policy: Dict[str, Any])
# Purpose: Implement the routine ' recommend from pci'.
# Inputs:
#   - inv: Dict[str, Any]
#   - policy: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - get, strip, isinstance, lower, startswith, append, _match_prefix, str
# Returns / emits: Tuple[List[Dict[str, Any]], List[str]]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - b, bid, cls, cls_prefix, dev, m, mcls, mvendor, n, notes, pci, r
# === End NoemaForge Autodoc Function Header ===
def _recommend_from_pci(inv: Dict[str, Any], policy: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[str]]:
    recs: List[Dict[str, Any]] = []
    notes: List[str] = []

    rules = ((policy.get("hardware_rules") or {}).get("pci") or [])
    pci = inv.get("pci") or []

    for r in rules:
        if not isinstance(r, dict):
            continue
        m = r.get("match") or {}
        mvendor = str(m.get("vendor") or "").lower().strip()
        mcls = str(m.get("class_prefix") or "").lower().strip()
        for dev in pci:
            if not isinstance(dev, dict):
                continue
            vendor = str(dev.get("vendor") or "").lower().strip()
            cls = str(dev.get("class") or "").lower().strip()

            # lspci-based inventory may not have class; try raw heuristic.
            if not cls and dev.get("raw"):
                raw = str(dev.get("raw") or "").lower()
                if "vga" in raw or "3d controller" in raw:
                    cls = "0x03"
            cls_prefix = cls[:4] if cls.startswith("0x") else cls

            if mvendor and vendor and mvendor != vendor:
                continue
            if mcls and cls_prefix and not _match_prefix(cls_prefix, mcls):
                continue

            for b in (r.get("recommend_bundles") or []) or []:
                if not isinstance(b, dict):
                    continue
                bid = str(b.get("id") or "").strip()
                if not bid:
                    continue
                recs.append({
                    "type": "bundle",
                    "id": bid,
                    "confidence": str(b.get("confidence") or "").strip() or "unknown",
                    "reason": str(b.get("reason") or "").strip() or "matched hardware rule",
                    "evidence": {
                        "pci_vendor": vendor,
                        "pci_class": cls,
                        "pci_device": str(dev.get("device") or ""),
                        "pci_slot": str(dev.get("slot") or ""),
                    },
                })

            for n in (r.get("notes") or []) or []:
                try:
                    notes.append(str(n))
                except Exception:
                    pass

    return recs, notes


# === NoemaForge Autodoc Function Header ===
# Function: build_plan(inv: Dict[str, Any], policy: Dict[str, Any])
# Purpose: Implement the routine 'build plan'.
# Inputs:
#   - inv: Dict[str, Any]
#   - policy: Dict[str, Any]
# Called by:
#   - src/bootdoctor.py
#   - src/brainctl.py
#   - src/offline_apt.py
# Calls:
#   - fingerprint_inventory, _recommend_from_pci, extend, set, encode, strip, append, add, _nowz, get, hexdigest, isinstance
# Returns / emits: Dict[str, Any]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - b, bid, fp, k, notes, p, plan, plan_id, r, raw, recs, seen
# === End NoemaForge Autodoc Function Header ===
def build_plan(inv: Dict[str, Any], policy: Dict[str, Any]) -> Dict[str, Any]:
    fp = fingerprint_inventory(inv)

    recs: List[Dict[str, Any]] = []
    notes: List[str] = []

    # defaults
    for b in ((policy.get("defaults") or {}).get("bundles") or []) or []:
        if not isinstance(b, dict):
            continue
        bid = str(b.get("id") or "").strip()
        if not bid:
            continue
        recs.append({
            "type": "bundle",
            "id": bid,
            "confidence": str(b.get("confidence") or "").strip() or "unknown",
            "reason": str(b.get("reason") or "").strip() or "default",
            "evidence": {"source": "defaults"},
        })

    for p in ((policy.get("defaults") or {}).get("apt_baseline") or []) or []:
        if not p:
            continue
        recs.append({
            "type": "apt",
            "id": str(p),
            "confidence": "high",
            "reason": "baseline spine dependency",
            "evidence": {"source": "defaults"},
        })

    # hardware rules
    r2, n2 = _recommend_from_pci(inv, policy)
    recs.extend(r2)
    notes.extend(n2)

    # de-dup by (type,id)
    seen = set()
    uniq: List[Dict[str, Any]] = []
    for r in recs:
        k = (str(r.get("type") or ""), str(r.get("id") or ""))
        if k in seen:
            continue
        seen.add(k)
        uniq.append(r)

    plan = {
        "schema": "noemaforge.installer.plan/v1",
        "created_at": _nowz(),
        "hardware_fingerprint": fp,
        "device_uid": "hw:" + fp[:32],
        "inventory_summary": {
            "cpu": (inv.get("cpu") or {}).get("model"),
            "mem_total_kb": inv.get("mem_total_kb"),
            "pci_count": len(inv.get("pci") or []),
            "net_ifaces": [x.get("name") for x in (inv.get("net") or []) if isinstance(x, dict)],
        },
        "recommendations": uniq,
        "notes": notes,
        "policy_version": policy.get("version"),
    }

    raw = json.dumps(plan, sort_keys=True, ensure_ascii=False).encode("utf-8")
    plan_id = hashlib.sha256(raw).hexdigest()[:16]
    plan["plan_id"] = plan_id
    return plan


# === NoemaForge Autodoc Function Header ===
# Function: write_plan(plan: Dict[str, Any], policy: Dict[str, Any])
# Purpose: Implement the routine 'write plan'.
# Inputs:
#   - plan: Dict[str, Any]
#   - policy: Dict[str, Any]
# Called by:
#   - src/bootdoctor.py
#   - src/brainctl.py
# Calls:
#   - str, makedirs, join, append, items, get, int, open, dump, write, safe_dump, sort
# Returns / emits: Dict[str, str]
# Side effects:
#   - reads or writes files
#   - serializes structured data
#   - creates directories
#   - appends to logs or files
# Key locals:
#   - base, bundles_add, f, files, keep, md, n, out, outbox_dir, p, p_json, p_md
# === End NoemaForge Autodoc Function Header ===
def write_plan(plan: Dict[str, Any], policy: Dict[str, Any]) -> Dict[str, str]:
    out = policy.get("output") or {}
    plans_dir = str(out.get("plans_dir") or "/var/lib/noemaforge/installer/plans")
    outbox_dir = str(out.get("outbox_dir") or "/workspace/outbox/installer-plan")

    os.makedirs(plans_dir, exist_ok=True)
    os.makedirs(outbox_dir, exist_ok=True)

    base = f"installer-plan-{plan.get('created_at','').replace(':','').replace('-','')}-{plan.get('plan_id','')}"
    p_json = os.path.join(plans_dir, f"{base}.json")
    p_md = os.path.join(outbox_dir, f"{base}.md")
    p_skel = os.path.join(outbox_dir, f"{base}.prestart-request.yaml")

    with open(p_json, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)

    md: List[str] = []
    md.append(f"# Installer Plan {plan.get('plan_id')}")
    md.append(f"- created_at: {plan.get('created_at')}")
    md.append(f"- hardware_fingerprint: {plan.get('hardware_fingerprint')}")
    md.append(f"- device_uid: {plan.get('device_uid')}")
    md.append("")
    md.append("## Inventory summary")
    summ = plan.get("inventory_summary") or {}
    for k, v in summ.items():
        md.append(f"- {k}: {v}")
    md.append("")
    md.append("## Recommendations")
    recs = plan.get("recommendations") or []
    for r in recs:
        md.append(f"- [{r.get('type')}] {r.get('id')}  ({r.get('confidence')}) — {r.get('reason')}")
    if plan.get("notes"):
        md.append("")
        md.append("## Notes")
        for n in plan.get("notes") or []:
            md.append(f"- {n}")

    with open(p_md, "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")

    # skeleton PreStartChangeRequest (ONLY suggestions, not auto-applied)
    bundles_add = [r for r in recs if r.get("type") == "bundle"]
    req = {
        "apiVersion": "noemaforge.prestart/v1",
        "kind": "PreStartChangeRequest",
        "request_id": f"installer-plan-{plan.get('plan_id')}",
        "created_at": plan.get("created_at"),
        "created_by": {"actor_type": "human", "channel": "installer_plan"},
        "status": "draft",
        "requested_changes": {
            "bundles_add": [{"bundle_id": b.get("id"), "note": b.get("reason")} for b in bundles_add],
        },
        "user_comment": "AUTO-GENERATED SKELETON. Review + add locks (sha256) before approving.",
    }
    with open(p_skel, "w", encoding="utf-8") as f:
        yaml.safe_dump(req, f, sort_keys=False, allow_unicode=True)

    keep = int(out.get("keep_plans") or 50)
    try:
        files = [os.path.join(plans_dir, fn) for fn in os.listdir(plans_dir) if fn.endswith(".json")]
        files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        for p in files[keep:]:
            try:
                os.remove(p)
            except Exception:
                pass
    except Exception:
        pass

    return {"plan_json": p_json, "plan_md": p_md, "prestart_skeleton": p_skel}
