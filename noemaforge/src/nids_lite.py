#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/nids_lite.py
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
# File: src/nids_lite.py
# Purpose: Provide the module 'nids_lite'.
# Invoked by / imported from:
#   - src/localgateway.py
#   - src/scary_sweep.py
#   - src/toolproxy.py
# Public API / entry functions:
#   - load_nids_policy
#   - snapshot
#   - snapshot_and_analyze
# Inputs:
#   - Common path inputs: /var/lib/noemaforge/localgw/nids, noemaforge.nids/v1
#   - Imports: __future__, datetime, json, os, typing, toolvault, lan_identity, lan_discovery
# Output formats / side effects:
#   - JSON files
#   - YAML files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""nids_lite.py (v0.15.0)

NIDS-lite / LocalNet monitor for the 'scary' role.

Scope
-----
This is intentionally *not* a full IDS.
It is a best-effort observer that:
- snapshots neighbor table, routes, addresses, listening sockets
- detects new/unknown devices (by stable UID)
- writes SEL/WORM events
- opens incidents on suspicious changes

No active scanning by default.

Integration
-----------
- Called by scary_sweep (periodic background SECURITY task).
- Optionally called by LocalGateway preflight (arming protocol).

Policy file: nids-policy.yaml (epoch-scoped).

Security
--------
- Never returns raw packet content.
- Never exposes "how to attack"; it only reports observations and policy decisions.
"""


import datetime as dt
import json
import os
from typing import Any, Dict, List, Optional, Tuple

from toolvault import load_yaml

from lan_identity import compute_device_uid, norm_mac
from lan_discovery import parse_ip_neigh, ip_addr_show, ip_route_show, ss_listeners

try:
    from seclog import append_event
except Exception:  # pragma: no cover
    append_event = None  # type: ignore

try:
    from incidents import open_incident
except Exception:  # pragma: no cover
    open_incident = None  # type: ignore


DEFAULT_STATE_DIR = "/var/lib/noemaforge/localgw/nids"
DEFAULT_SNAP_DIR = os.path.join(DEFAULT_STATE_DIR, "snapshots")
DEFAULT_STATE_JSON = os.path.join(DEFAULT_STATE_DIR, "state.json")


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
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


# === NoemaForge Autodoc Function Header ===
# Function: _evt(phase: str, event_type: str, actor: Dict[str, Any], decision: str, trace_id: str, details: Dict[str, Any])
# Purpose: Implement the routine ' evt'.
# Inputs:
#   - phase: str
#   - event_type: str
#   - actor: Dict[str, Any]
#   - decision: str
#   - trace_id: str
#   - details: Dict[str, Any]
# Called by:
#   - src/bundles.py
#   - src/firstboot_eval.py
#   - src/llm_backends_manager.py
#   - src/localgateway.py
#   - src/toolproxy.py
#   - src/webgateway.py
# Calls:
#   - append_event
# Returns / emits: None
# Side effects:
#   - appends to logs or files
# === End NoemaForge Autodoc Function Header ===
def _evt(phase: str, event_type: str, actor: Dict[str, Any], decision: str, trace_id: str, details: Dict[str, Any]) -> None:
    if append_event is None:
        return
    try:
        append_event(
            phase=phase,
            event_type=event_type,
            actor=actor,
            decision=decision,
            trace_id=trace_id,
            details=details,
        )
    except Exception:
        return


# === NoemaForge Autodoc Function Header ===
# Function: load_nids_policy(epoch_dir: str)
# Purpose: Implement the routine 'load nids policy'.
# Inputs:
#   - epoch_dir: str
# Called by:
#   - src/localgateway.py
# Calls:
#   - join, exists, load_yaml
# Returns / emits: Dict[str, Any]
# Key locals:
#   - p
# === End NoemaForge Autodoc Function Header ===
def load_nids_policy(epoch_dir: str) -> Dict[str, Any]:
    p = os.path.join(epoch_dir, "nids-policy.yaml")
    if os.path.exists(p):
        try:
            return load_yaml(p)
        except Exception:
            pass
    return {
        "apiVersion": "noemaforge.nids/v1",
        "kind": "NIDSPolicy",
        "enabled": False,
        "snapshot": {"interval_sec": 300, "max_snapshots": 200},
        "identity": {
            "uid_prefix": "lan:",
            "uid_algorithm": "sha256",
            "prefer_fields": ["tls_pubkey_sha256", "device_cert_sha256", "serial", "dhcp_client_id", "mac"],
            "mac_normalization": "lower",
        },
        "devices": {"allowlist_uids": [], "allowlist_mode": "permissive", "on_unknown": "incident"},
        "capture": {"include_listeners": True, "include_routes": True, "include_addrs": True},
        "notes": ["NIDS-lite is observation-only; no packet payload capture."],
    }


# === NoemaForge Autodoc Function Header ===
# Function: _load_state()
# Purpose: Implement the routine ' load state'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - src/knowledge_maintainer.py
#   - src/localgateway.py
# Calls:
#   - exists, load, open
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads or writes files
# === End NoemaForge Autodoc Function Header ===
def _load_state() -> Dict[str, Any]:
    try:
        if os.path.exists(DEFAULT_STATE_JSON):
            return json.load(open(DEFAULT_STATE_JSON, "r", encoding="utf-8"))
    except Exception:
        pass
    return {"last_snapshot_at": "", "snapshots": 0}


# === NoemaForge Autodoc Function Header ===
# Function: _save_state(st: Dict[str, Any])
# Purpose: Implement the routine ' save state'.
# Inputs:
#   - st: Dict[str, Any]
# Called by:
#   - src/knowledge_maintainer.py
#   - src/localgateway.py
#   - src/maintenance.py
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
def _save_state(st: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(DEFAULT_STATE_JSON), exist_ok=True)
    with open(DEFAULT_STATE_JSON, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=2)


# === NoemaForge Autodoc Function Header ===
# Function: _maybe_prune(max_snapshots: int)
# Purpose: Implement the routine ' maybe prune'.
# Inputs:
#   - max_snapshots: int
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - sorted, isdir, len, max, remove, listdir, endswith, join
# Returns / emits: None
# Key locals:
#   - fn, fns
# === End NoemaForge Autodoc Function Header ===
def _maybe_prune(max_snapshots: int) -> None:
    try:
        if not os.path.isdir(DEFAULT_SNAP_DIR):
            return
        fns = sorted([fn for fn in os.listdir(DEFAULT_SNAP_DIR) if fn.endswith(".json")])
        if len(fns) <= max_snapshots:
            return
        for fn in fns[: max(0, len(fns) - max_snapshots)]:
            try:
                os.remove(os.path.join(DEFAULT_SNAP_DIR, fn))
            except Exception:
                pass
    except Exception:
        return


# === NoemaForge Autodoc Function Header ===
# Function: snapshot(policy: Dict[str, Any])
# Purpose: Implement the routine 'snapshot'.
# Inputs:
#   - policy: Dict[str, Any]
# Called by:
#   - src/brainui.py
# Calls:
#   - str, parse_ip_neigh, bool, get, norm_mac, compute_device_uid, append, _nowz, len, ip_addr_show, ip_route_show, ss_listeners
# Returns / emits: Dict[str, Any]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - cap, devices, fp, ident, mac, mac_norm, neigh, r, snap, uid
# === End NoemaForge Autodoc Function Header ===
def snapshot(policy: Dict[str, Any]) -> Dict[str, Any]:
    ident = policy.get("identity") or {}
    mac_norm = str(ident.get("mac_normalization") or "lower")

    neigh = parse_ip_neigh()
    devices: List[Dict[str, Any]] = []
    for r in neigh:
        mac = norm_mac(str(r.get("mac") or ""), mac_norm)
        fp: Dict[str, Any] = {}
        if mac:
            fp["mac"] = mac
        uid = compute_device_uid(ident, fp)
        devices.append({
            "device_uid": uid,
            "ip": str(r.get("ip") or ""),
            "mac": mac,
            "iface": str(r.get("iface") or ""),
            "state": str(r.get("state") or ""),
            "fingerprint": fp,
            "source": str(r.get("source") or "ip_neigh"),
        })

    cap = policy.get("capture") or {}
    snap: Dict[str, Any] = {
        "at": _nowz(),
        "devices": devices,
        "devices_count": len(devices),
        "ip_neigh": neigh,
    }
    if bool(cap.get("include_addrs", True)):
        snap["ip_addr"] = ip_addr_show()
    if bool(cap.get("include_routes", True)):
        snap["ip_route"] = ip_route_show()
    if bool(cap.get("include_listeners", True)):
        snap["listeners"] = ss_listeners()
    return snap


# === NoemaForge Autodoc Function Header ===
# Function: _load_last_snapshot()
# Purpose: Implement the routine ' load last snapshot'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - sorted, join, load, isdir, open, listdir, endswith
# Returns / emits: Optional[Dict[str, Any]]
# Side effects:
#   - reads or writes files
# Key locals:
#   - fns, p
# === End NoemaForge Autodoc Function Header ===
def _load_last_snapshot() -> Optional[Dict[str, Any]]:
    try:
        if not os.path.isdir(DEFAULT_SNAP_DIR):
            return None
        fns = sorted([fn for fn in os.listdir(DEFAULT_SNAP_DIR) if fn.endswith(".json")])
        if not fns:
            return None
        p = os.path.join(DEFAULT_SNAP_DIR, fns[-1])
        return json.load(open(p, "r", encoding="utf-8"))
    except Exception:
        return None


# === NoemaForge Autodoc Function Header ===
# Function: snapshot_and_analyze(epoch_dir: str, actor: Dict[str, Any], trace_id: str, force: bool = False)
# Purpose: Implement the routine 'snapshot and analyze'.
# Inputs:
#   - epoch_dir: str
#   - actor: Dict[str, Any]
#   - trace_id: str
#   - force: bool = False
# Called by:
#   - src/scary_sweep.py
# Calls:
#   - load_nids_policy, _load_state, int, snapshot, makedirs, join, _load_last_snapshot, set, strip, sorted, _evt, bool
# Returns / emits: Tuple[bool, Dict[str, Any], str]
# Side effects:
#   - creates directories
# Key locals:
#   - allow_cfg, allow_uids, decision, f, fn, incident_id, interval, last, last_dt, last_snap, last_uids, max_snaps
# === End NoemaForge Autodoc Function Header ===
def snapshot_and_analyze(*, epoch_dir: str, actor: Dict[str, Any], trace_id: str, force: bool = False) -> Tuple[bool, Dict[str, Any], str]:
    pol = load_nids_policy(epoch_dir)
    if not bool(pol.get("enabled", False)):
        return False, {"ok": False, "reason": "nids_disabled"}, "nids_disabled"

    st = _load_state()
    interval = int(((pol.get("snapshot") or {}).get("interval_sec") or 300))
    max_snaps = int(((pol.get("snapshot") or {}).get("max_snapshots") or 200))

    if not force:
        try:
            last = str(st.get("last_snapshot_at") or "")
            if last:
                last_dt = dt.datetime.fromisoformat(last.replace("Z", "+00:00"))
                if dt.datetime.now(dt.timezone.utc) < (last_dt + dt.timedelta(seconds=interval)):
                    return True, {"ok": True, "skipped": True, "reason": "interval"}, "ok"
        except Exception:
            pass

    snap = snapshot(pol)
    os.makedirs(DEFAULT_SNAP_DIR, exist_ok=True)
    fn = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".json"
    p = os.path.join(DEFAULT_SNAP_DIR, fn)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, indent=2)

    last_snap = _load_last_snapshot()
    last_uids = set([str(d.get("device_uid") or "") for d in ((last_snap or {}).get("devices") or []) if isinstance(d, dict)])
    now_uids = set([str(d.get("device_uid") or "") for d in (snap.get("devices") or []) if isinstance(d, dict)])
    new_uids = sorted(list(now_uids - last_uids)) if last_snap else []

    allow_cfg = pol.get("devices") or {}
    allow_uids = set([str(x) for x in (allow_cfg.get("allowlist_uids") or []) if str(x).strip()])
    mode = str(allow_cfg.get("allowlist_mode") or "permissive").lower().strip()
    on_unknown = str(allow_cfg.get("on_unknown") or "incident").lower().strip()

    unknown: List[str] = []
    for uid in sorted(list(now_uids)):
        if mode == "required":
            if uid not in allow_uids:
                unknown.append(uid)
        else:
            if allow_uids and uid not in allow_uids:
                unknown.append(uid)

    decision = "allow"
    reason = "ok"
    incident_id = ""
    if unknown and on_unknown in ("incident", "quarantine"):
        decision = "quarantine"
        reason = "unknown_devices"
        if open_incident is not None:
            try:
                incident_id = open_incident(
                    kind="lan_unknown_device",
                    severity="high",
                    summary=f"Unknown LAN devices detected ({len(unknown)})",
                    details={"unknown_uids": unknown[:50], "new_uids": new_uids[:50], "snapshot": p},
                    actor=actor,
                    trace_id=trace_id,
                    dedupe_key="lan_unknown_device",
                )
            except Exception:
                incident_id = ""

    try:
        st["last_snapshot_at"] = snap.get("at") or _nowz()
        st["snapshots"] = int(st.get("snapshots") or 0) + 1
        _save_state(st)
        _maybe_prune(max_snaps)
    except Exception:
        pass

    _evt(
        "S0",
        "NIDS_SNAPSHOT",
        actor,
        decision,
        trace_id,
        {
            "trace_id": trace_id,
            "snapshot_path": p,
            "devices": int(snap.get("devices_count") or 0),
            "new_uids": new_uids[:20],
            "unknown_uids": unknown[:20],
            "incident_id": incident_id,
        },
    )

    return True, {
        "ok": decision == "allow",
        "decision": decision,
        "reason": reason,
        "snapshot_path": p,
        "devices": (snap.get("devices") or [])[:50],
        "devices_count": snap.get("devices_count") or 0,
        "new_device_uids": new_uids,
        "unknown_device_uids": unknown,
        "incident_id": incident_id,
    }, reason
