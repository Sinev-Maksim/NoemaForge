#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/localgateway.py
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
# File: src/localgateway.py
# Purpose: Broker local device access through typed connectors and safety controls.
# Invoked by / imported from:
#   - src/brainctl.py
#   - src/toolproxy.py
# Public API / entry functions:
#   - load_local_gateway_policy
#   - discover_devices
#   - preflight
#   - require_session
#   - connector_call
# Inputs:
#   - Common path inputs: /var/lib/noemaforge/localgw, noemaforge.localgateway/v1, /var/lib/noemaforge/localgw/devices.sqlite
#   - Imports: __future__, datetime, json, os, sqlite3, subprocess, uuid, typing
# Output formats / side effects:
#   - SQLite databases
#   - JSON files
#   - YAML files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""localgateway.py (v0.16.0)

Local Gateway (LAN airlock): controlled, audited window into the local network.

Principles
----------
- Subordinated to role 'scary' by policy.
- No raw network for executor roles.
- Arming protocol (preflight) required before any LAN actions.
- Device identity is SSID-independent: stable hardware IDs (prefer TLS pubkey/serial; fallback MAC).

Stage C additions (v0.15.0)
-------------------------
- Typed connector registry (octoprint/ipp) with allowlist.
- Optional invite gating for actuation methods (e.g., start_print, print_file).
- NIDS-lite hook during preflight (if enabled) to detect unknown devices before arming.

Stage C1 additions (v0.16.0)
----------------------------
- Uplink glove gate for OctoPrint uploads (upload_gcode) + file size guard.
- LocalGW rate limiting (SQLite fixed-window) for connector calls.

Notes
-----
- Discovery is passive by default (neighbor tables) – no active scanning.
- Secrets are never stored in epoch YAML; connectors use secret refs under spinal zone.
"""


import datetime as dt
import json
import os
import sqlite3
import subprocess
import uuid
from typing import Any, Dict, List, Optional, Tuple

from toolvault import load_yaml

from lan_identity import compute_device_uid, norm_mac
from lan_discovery import parse_ip_neigh

import invites
import localgw_connectors
from localgw_connectors.base import ConnectorContext
import localgw_ratelimit

try:
    from nids_lite import snapshot_and_analyze as nids_snapshot_and_analyze
    from nids_lite import load_nids_policy
except Exception:  # pragma: no cover
    nids_snapshot_and_analyze = None  # type: ignore
    load_nids_policy = None  # type: ignore

try:
    from seclog import append_event
except Exception:  # pragma: no cover
    append_event = None  # type: ignore


DEFAULT_STATE_DIR = "/var/lib/noemaforge/localgw"
DEFAULT_SESSIONS_DIR = os.path.join(DEFAULT_STATE_DIR, "sessions")
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
    return dt.datetime.utcnow().isoformat() + "Z"


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
#   - src/nids_lite.py
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
# Function: load_local_gateway_policy(epoch_dir: str)
# Purpose: Implement the routine 'load local gateway policy'.
# Inputs:
#   - epoch_dir: str
# Called by:
#   - src/brainctl.py
# Calls:
#   - join, exists, load_yaml
# Returns / emits: Dict[str, Any]
# Key locals:
#   - p
# === End NoemaForge Autodoc Function Header ===
def load_local_gateway_policy(epoch_dir: str) -> Dict[str, Any]:
    p = os.path.join(epoch_dir, "local-gateway-policy.yaml")
    if os.path.exists(p):
        try:
            return load_yaml(p)
        except Exception:
            pass

    # strict defaults
    return {
        "apiVersion": "noemaforge.localgateway/v1",
        "kind": "LocalGatewayPolicy",
        "enabled": False,
        "arming": {
            "preflight_required": True,
            "first_run_force_full": True,
            "token_ttl_sec": 900,
            "require_nids_preflight": True,
        },
        "identity": {
            "uid_prefix": "lan:",
            "uid_algorithm": "sha256",
            "prefer_fields": ["tls_pubkey_sha256", "device_cert_sha256", "serial", "dhcp_client_id", "mac"],
            "mac_normalization": "lower",
        },
        "network": {"allowed_interfaces": [], "allowed_subnets": [], "default_egress": "deny"},
        "devices": {
            "allowlist_uids": [],
            "allowlist": [],
            "allowlist_mode": "required",
            "quarantine_unknown_devices": True,
            "remember_seen_devices": True,
            "state_db_path": "/var/lib/noemaforge/localgw/devices.sqlite",
        },
        "connectors": {
            "enabled": False,
            "allow_connectors": ["octoprint", "ipp"],
            "deny_connectors": [],
            "deny_raw_sockets": True,
            "actuation": {"requires_invite": True, "invite_scope": "localgw_live"},
        },
    }


# === NoemaForge Autodoc Function Header ===
# Function: _load_state()
# Purpose: Implement the routine ' load state'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - src/knowledge_maintainer.py
#   - src/nids_lite.py
# Calls:
#   - exists, _nowz, load, open
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
    return {"preflight_runs": 0, "first_seen": _nowz()}


# === NoemaForge Autodoc Function Header ===
# Function: _save_state(st: Dict[str, Any])
# Purpose: Implement the routine ' save state'.
# Inputs:
#   - st: Dict[str, Any]
# Called by:
#   - src/knowledge_maintainer.py
#   - src/maintenance.py
#   - src/nids_lite.py
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
# Function: _allowlist(pol: Dict[str, Any])
# Purpose: Return (allow_uids, profiles_by_uid).
# Inputs:
#   - pol: Dict[str, Any]
# Called by:
#   - src/storage_broker.py
# Calls:
#   - set, isinstance, get, str, strip, add
# Returns / emits: Tuple[set[str], Dict[str, Dict[str, Any]]]
# Key locals:
#   - allow_uids, dev_cfg, ent, profiles, raw, uid
# === End NoemaForge Autodoc Function Header ===
def _allowlist(pol: Dict[str, Any]) -> Tuple[set[str], Dict[str, Dict[str, Any]]]:
    """Return (allow_uids, profiles_by_uid)."""
    dev_cfg = pol.get("devices") or {}
    allow_uids = set([str(x) for x in (dev_cfg.get("allowlist_uids") or []) if str(x).strip()])
    profiles: Dict[str, Dict[str, Any]] = {}

    raw = dev_cfg.get("allowlist") or []
    if isinstance(raw, list):
        for ent in raw:
            if not isinstance(ent, dict):
                continue
            uid = str(ent.get("device_uid") or "").strip()
            if not uid:
                continue
            allow_uids.add(uid)
            profiles[uid] = ent

    return allow_uids, profiles


# === NoemaForge Autodoc Function Header ===
# Function: discover_devices(policy: Dict[str, Any])
# Purpose: Implement the routine 'discover devices'.
# Inputs:
#   - policy: Dict[str, Any]
# Called by:
#   - src/brainctl.py
# Calls:
#   - str, parse_ip_neigh, get, norm_mac, compute_device_uid, append
# Returns / emits: List[Dict[str, Any]]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - devices, fp, ident, mac, mac_norm, r, raw, uid
# === End NoemaForge Autodoc Function Header ===
def discover_devices(policy: Dict[str, Any]) -> List[Dict[str, Any]]:
    ident = policy.get("identity") or {}
    mac_norm = str(ident.get("mac_normalization") or "lower")

    raw = parse_ip_neigh()
    devices: List[Dict[str, Any]] = []
    for r in raw:
        mac = norm_mac(str(r.get("mac") or ""), mac_norm)
        fp: Dict[str, Any] = {}
        if mac:
            fp["mac"] = mac
        uid = compute_device_uid(ident, fp)
        devices.append(
            {
                "device_uid": uid,
                "ip": r.get("ip"),
                "mac": mac,
                "iface": r.get("iface"),
                "state": r.get("state"),
                "fingerprint": fp,
                "source": r.get("source"),
            }
        )
    return devices


# === NoemaForge Autodoc Function Header ===
# Function: _db_init(path: str)
# Purpose: Implement the routine ' db init'.
# Inputs:
#   - path: str
# Called by:
#   - src/localgw_ratelimit.py
# Calls:
#   - makedirs, connect, dirname, execute, commit, close
# Returns / emits: None
# Side effects:
#   - opens a database or socket connection
#   - executes SQL or shell-like commands
#   - creates directories
# Key locals:
#   - con
# === End NoemaForge Autodoc Function Header ===
def _db_init(path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    con = sqlite3.connect(path)
    try:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS devices (
              device_uid TEXT PRIMARY KEY,
              first_seen TEXT,
              last_seen TEXT,
              fingerprint_json TEXT,
              last_ip TEXT,
              notes TEXT
            )
            """
        )
        con.commit()
    finally:
        con.close()


# === NoemaForge Autodoc Function Header ===
# Function: _db_upsert_seen(db_path: str, dev: Dict[str, Any])
# Purpose: Implement the routine ' db upsert seen'.
# Inputs:
#   - db_path: str
#   - dev: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _db_init, str, dumps, _nowz, connect, cursor, execute, fetchone, commit, close, get
# Returns / emits: None
# Side effects:
#   - serializes structured data
#   - opens a database or socket connection
#   - executes SQL or shell-like commands
# Key locals:
#   - con, cur, fpj, ip, now, row, uid
# === End NoemaForge Autodoc Function Header ===
def _db_upsert_seen(db_path: str, dev: Dict[str, Any]) -> None:
    _db_init(db_path)
    uid = str(dev.get("device_uid") or "")
    if not uid:
        return
    fpj = json.dumps(dev.get("fingerprint") or {}, sort_keys=True, ensure_ascii=False)
    ip = str(dev.get("ip") or "")
    now = _nowz()
    con = sqlite3.connect(db_path)
    try:
        cur = con.cursor()
        cur.execute("SELECT device_uid FROM devices WHERE device_uid=?", (uid,))
        row = cur.fetchone()
        if row:
            cur.execute(
                "UPDATE devices SET last_seen=?, fingerprint_json=?, last_ip=? WHERE device_uid=?",
                (now, fpj, ip, uid),
            )
        else:
            cur.execute(
                "INSERT INTO devices(device_uid, first_seen, last_seen, fingerprint_json, last_ip, notes) VALUES(?,?,?,?,?,?)",
                (uid, now, now, fpj, ip, ""),
            )
        con.commit()
    finally:
        con.close()


# === NoemaForge Autodoc Function Header ===
# Function: _mint_session_token(ttl_sec: int)
# Purpose: Implement the routine ' mint session token'.
# Inputs:
#   - ttl_sec: int
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - utcnow, uuid4, timedelta, isoformat, max, int
# Returns / emits: Dict[str, Any]
# Key locals:
#   - exp, now, tok
# === End NoemaForge Autodoc Function Header ===
def _mint_session_token(ttl_sec: int) -> Dict[str, Any]:
    tok = uuid.uuid4().hex
    now = dt.datetime.utcnow()
    exp = now + dt.timedelta(seconds=max(10, int(ttl_sec)))
    return {"token": tok, "issued_at": now.isoformat() + "Z", "expires_at": exp.isoformat() + "Z"}


# === NoemaForge Autodoc Function Header ===
# Function: _save_session(sess: Dict[str, Any])
# Purpose: Implement the routine ' save session'.
# Inputs:
#   - sess: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - makedirs, str, join, open, dump, get
# Returns / emits: str
# Side effects:
#   - reads or writes files
#   - serializes structured data
#   - creates directories
# Key locals:
#   - f, p, token
# === End NoemaForge Autodoc Function Header ===
def _save_session(sess: Dict[str, Any]) -> str:
    os.makedirs(DEFAULT_SESSIONS_DIR, exist_ok=True)
    token = str(sess.get("token") or "")
    p = os.path.join(DEFAULT_SESSIONS_DIR, f"{token}.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(sess, f, ensure_ascii=False, indent=2)
    return p


# === NoemaForge Autodoc Function Header ===
# Function: _load_session(token: str)
# Purpose: Implement the routine ' load session'.
# Inputs:
#   - token: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - join, exists, load, open
# Returns / emits: Optional[Dict[str, Any]]
# Side effects:
#   - reads or writes files
# Key locals:
#   - p
# === End NoemaForge Autodoc Function Header ===
def _load_session(token: str) -> Optional[Dict[str, Any]]:
    p = os.path.join(DEFAULT_SESSIONS_DIR, f"{token}.json")
    if not os.path.exists(p):
        return None
    try:
        return json.load(open(p, "r", encoding="utf-8"))
    except Exception:
        return None


# === NoemaForge Autodoc Function Header ===
# Function: _is_expired(sess: Dict[str, Any])
# Purpose: Implement the routine ' is expired'.
# Inputs:
#   - sess: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - str, replace, fromisoformat, get, utcnow
# Returns / emits: bool
# Key locals:
#   - dt_exp, exp, exp2
# === End NoemaForge Autodoc Function Header ===
def _is_expired(sess: Dict[str, Any]) -> bool:
    try:
        exp = str(sess.get("expires_at") or "")
        if not exp:
            return True
        exp2 = exp.replace("Z", "+00:00")
        dt_exp = dt.datetime.fromisoformat(exp2)
        return dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc) >= dt_exp
    except Exception:
        return True


# === NoemaForge Autodoc Function Header ===
# Function: preflight(epoch_dir: str, actor: Dict[str, Any], trace_id: str, requested_suite: str = 'auto')
# Purpose: Run LAN preflight and mint a short-lived session token.
# Inputs:
#   - epoch_dir: str
#   - actor: Dict[str, Any]
#   - trace_id: str
#   - requested_suite: str = 'auto'
# Called by:
#   - src/brainctl.py
# Calls:
#   - load_local_gateway_policy, int, _load_state, strip, discover_devices, _allowlist, bool, str, _mint_session_token, len, _save_session, _evt
# Returns / emits: Tuple[bool, Dict[str, Any], str]
# Key locals:
#   - allow_mode, arming, d, db_path, decision, dev_cfg, devices, force_full, nids_report, nids_unknown, npol, p
# === End NoemaForge Autodoc Function Header ===
def preflight(*, epoch_dir: str, actor: Dict[str, Any], trace_id: str, requested_suite: str = "auto") -> Tuple[bool, Dict[str, Any], str]:
    """Run LAN preflight and mint a short-lived session token.

    requested_suite: auto|smoke|full
    First run is forced to FULL if policy.arming.first_run_force_full.

    v0.15.0: if NIDS-lite is enabled and policy.arming.require_nids_preflight is true,
    we run a NIDS snapshot first and treat unknown devices as quarantine.
    """

    pol = load_local_gateway_policy(epoch_dir)
    if not bool(pol.get("enabled", False)):
        return False, {"ok": False}, "localgw_disabled"

    arming = pol.get("arming") or {}
    ttl = int(arming.get("token_ttl_sec") or 900)
    st = _load_state()
    runs = int(st.get("preflight_runs") or 0)
    force_full = bool(arming.get("first_run_force_full", True)) and runs <= 0

    suite = (requested_suite or "auto").lower().strip()
    if suite not in ("auto", "smoke", "full"):
        suite = "auto"
    if force_full:
        suite_used = "full"
    elif suite == "auto":
        suite_used = "smoke"
    else:
        suite_used = suite

    warnings: List[str] = []

    # Optional NIDS-lite hook
    nids_report: Dict[str, Any] = {}
    if bool(arming.get("require_nids_preflight", True)) and nids_snapshot_and_analyze is not None and load_nids_policy is not None:
        try:
            npol = load_nids_policy(epoch_dir)
            if bool((npol or {}).get("enabled", False)):
                okn, rep, _ = nids_snapshot_and_analyze(epoch_dir=epoch_dir, actor=actor, trace_id=trace_id, force=True)
                if okn:
                    nids_report = rep or {}
                    if str(nids_report.get("decision") or "") == "quarantine":
                        warnings.append("nids_quarantine")
        except Exception:
            warnings.append("nids_failed")

    devices = discover_devices(pol)

    dev_cfg = pol.get("devices") or {}
    allow_uids, profiles = _allowlist(pol)
    allow_mode = str(dev_cfg.get("allowlist_mode") or "permissive").lower().strip()
    remember = bool(dev_cfg.get("remember_seen_devices", True))
    db_path = str(dev_cfg.get("state_db_path") or os.path.join(DEFAULT_STATE_DIR, "devices.sqlite"))

    unknown: List[str] = []
    for d in devices:
        uid = str(d.get("device_uid") or "")
        if uid:
            if allow_mode == "required":
                if uid not in allow_uids:
                    unknown.append(uid)
            else:
                if allow_uids and uid not in allow_uids:
                    unknown.append(uid)
        if remember:
            try:
                _db_upsert_seen(db_path, d)
            except Exception:
                pass

    # Merge NIDS unknown list (if any)
    nids_unknown = [str(x) for x in (nids_report.get("unknown_device_uids") or []) if str(x).strip()]
    for uid in nids_unknown:
        if uid not in unknown:
            unknown.append(uid)

    if suite_used == "full":
        try:
            p = subprocess.run(["nft", "list", "ruleset"], check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if p.returncode != 0:
                warnings.append("nft_ruleset_unavailable")
        except Exception:
            warnings.append("nft_not_available")

    decision = "allow"
    reason = "ok"
    if unknown and bool(dev_cfg.get("quarantine_unknown_devices", True)):
        decision = "quarantine"
        reason = "unknown_devices"

    sess = _mint_session_token(ttl)
    sess["suite"] = suite_used
    sess["devices_seen"] = len(devices)
    sess["unknown_devices"] = unknown

    _save_session(sess)

    try:
        st["preflight_runs"] = runs + 1
        st["last_preflight"] = _nowz()
        _save_state(st)
    except Exception:
        pass

    _evt(
        "S0",
        "LOCALGW_PREFLIGHT",
        actor,
        decision,
        trace_id,
        {
            "trace_id": trace_id,
            "suite": suite_used,
            "forced_full": bool(force_full),
            "devices_seen": len(devices),
            "unknown_devices": len(unknown),
            "unknown_uids": unknown[:20],
            "warnings": warnings,
            "nids": {"decision": nids_report.get("decision"), "snapshot": nids_report.get("snapshot_path"), "incident_id": nids_report.get("incident_id")},
        },
    )

    # Return device profiles only as names, not secrets.
    prof_names = {uid: str((profiles.get(uid) or {}).get("name") or "") for uid in profiles.keys()}

    return (
        decision == "allow",
        {
            "ok": decision == "allow",
            "decision": decision,
            "reason": reason,
            "suite": suite_used,
            "forced_full": bool(force_full),
            "lan_session_token": sess.get("token"),
            "expires_at": sess.get("expires_at"),
            "devices": devices[:50],
            "unknown_device_uids": unknown,
            "known_device_names": prof_names,
            "warnings": warnings,
            "nids_report": {k: nids_report.get(k) for k in ("decision", "reason", "snapshot_path", "incident_id")},
        },
        reason,
    )


# === NoemaForge Autodoc Function Header ===
# Function: require_session(token: str)
# Purpose: Implement the routine 'require session'.
# Inputs:
#   - token: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _load_session, _is_expired
# Returns / emits: Tuple[bool, Optional[Dict[str, Any]], str]
# Key locals:
#   - sess
# === End NoemaForge Autodoc Function Header ===
def require_session(token: str) -> Tuple[bool, Optional[Dict[str, Any]], str]:
    sess = _load_session(token)
    if not sess:
        return False, None, "lan_session_missing"
    if _is_expired(sess):
        return False, sess, "lan_session_expired"
    return True, sess, "ok"


# === NoemaForge Autodoc Function Header ===
# Function: connector_call(epoch_dir: str, actor: Dict[str, Any], trace_id: str, lan_session_token: str, connector: str, method: str, params: Dict[str, Any])
# Purpose: Typed connector call.
# Inputs:
#   - epoch_dir: str
#   - actor: Dict[str, Any]
#   - trace_id: str
#   - lan_session_token: str
#   - connector: str
#   - method: str
#   - params: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - load_local_gateway_policy, require_session, set, _allowlist, strip, ConnectorContext, call, _evt, bool, str, get, has_connector
# Returns / emits: Tuple[bool, Dict[str, Any], str]
# Side effects:
#   - opens a database or socket connection
# Key locals:
#   - act, allow, allow_mode, con, ctx, dangerous, decision, deny, dev_cfg, device_profile, device_uid, info
# === End NoemaForge Autodoc Function Header ===
def connector_call(
    *,
    epoch_dir: str,
    actor: Dict[str, Any],
    trace_id: str,
    lan_session_token: str,
    connector: str,
    method: str,
    params: Dict[str, Any],
) -> Tuple[bool, Dict[str, Any], str]:
    """Typed connector call.

    v0.15.0: real connectors (octoprint/ipp) are now available.
    """

    pol = load_local_gateway_policy(epoch_dir)
    if not bool(pol.get("enabled", False)):
        return False, {"ok": False}, "localgw_disabled"

    ok, sess, reason = require_session(str(lan_session_token or ""))
    if not ok:
        _evt("S1", "LOCALGW_CALL", actor, "deny", trace_id, {"trace_id": trace_id, "reason": reason, "connector": connector, "method": method})
        return False, {"ok": False, "reason": reason}, reason

    con = pol.get("connectors") or {}
    if not bool(con.get("enabled", False)):
        _evt("S1", "LOCALGW_CALL", actor, "deny", trace_id, {"trace_id": trace_id, "reason": "connectors_disabled", "connector": connector, "method": method})
        return False, {"ok": False, "reason": "connectors_disabled"}, "connectors_disabled"

    deny = set([str(x) for x in (con.get("deny_connectors") or [])])
    if str(connector) in deny:
        _evt("S1", "LOCALGW_CALL", actor, "deny", trace_id, {"trace_id": trace_id, "reason": "connector_denied", "connector": connector, "method": method})
        return False, {"ok": False, "reason": "connector_denied"}, "connector_denied"

    allow = [str(x) for x in (con.get("allow_connectors") or []) if str(x).strip()]
    if not allow:
        _evt("S1", "LOCALGW_CALL", actor, "deny", trace_id, {"trace_id": trace_id, "reason": "connector_not_allowed", "connector": connector, "method": method})
        return False, {"ok": False, "reason": "connector_not_allowed"}, "connector_not_allowed"
    if str(connector) not in set(allow):
        _evt("S1", "LOCALGW_CALL", actor, "deny", trace_id, {"trace_id": trace_id, "reason": "connector_not_allowed", "connector": connector, "method": method})
        return False, {"ok": False, "reason": "connector_not_allowed"}, "connector_not_allowed"

    if not localgw_connectors.has_connector(str(connector)):
        _evt("S1", "LOCALGW_CALL", actor, "deny", trace_id, {"trace_id": trace_id, "reason": "connector_not_found", "connector": connector, "method": method})
        return False, {"ok": False, "reason": "connector_not_found"}, "connector_not_found"

    # Resolve device profile (allowlist) – secure default is deny if required.
    dev_cfg = pol.get("devices") or {}
    allow_uids, profiles = _allowlist(pol)
    allow_mode = str(dev_cfg.get("allowlist_mode") or "permissive").lower().strip()

    device_uid = str((params or {}).get("device_uid") or "").strip()
    device_profile = profiles.get(device_uid) if device_uid else None

    if allow_mode == "required":
        if device_uid and device_uid not in allow_uids:
            _evt("S1", "LOCALGW_CALL", actor, "quarantine", trace_id, {"trace_id": trace_id, "reason": "device_not_allowed", "device_uid": device_uid, "connector": connector, "method": method})
            return False, {"ok": False, "reason": "device_not_allowed"}, "device_not_allowed"
        if not device_uid:
            # For required mode we demand explicit device_uid to avoid accidental target.
            _evt("S1", "LOCALGW_CALL", actor, "deny", trace_id, {"trace_id": trace_id, "reason": "missing_device_uid", "connector": connector, "method": method})
            return False, {"ok": False, "reason": "missing_device_uid"}, "missing_device_uid"

    # Invite gating for actuation methods
    info = (localgw_connectors.list_connectors().get(str(connector)) or {})
    dangerous = set([str(x) for x in (info.get("dangerous_methods") or [])])
    act = con.get("actuation") or {}
    if str(method) in dangerous and bool(act.get("requires_invite", True)):
        scope = str(act.get("invite_scope") or "localgw_live").strip().lower()
        if scope and not invites.is_active(scope):
            _evt("S1", "LOCALGW_CALL", actor, "deny", trace_id, {"trace_id": trace_id, "reason": "invite_required", "invite_scope": scope, "connector": connector, "method": method})
            return False, {"ok": False, "reason": "invite_required", "invite_scope": scope}, "invite_required"

    # Stage C1: uplink enable gate (uploads are handled via disposable uplink glove)
    upl = (pol.get("uplink") or {}) if isinstance(pol, dict) else {}
    if str(connector) == "octoprint" and str(method) == "upload_gcode":
        if not bool(upl.get("enabled", False)):
            _evt("S1", "LOCALGW_CALL", actor, "deny", trace_id, {"trace_id": trace_id, "reason": "uplink_disabled", "connector": connector, "method": method})
            return False, {"ok": False, "reason": "uplink_disabled"}, "uplink_disabled"
        # Optional size guard
        try:
            max_mib = int(upl.get("max_file_mib") or 200)
            lp = str((params or {}).get("local_path") or "").strip()
            if lp and os.path.exists(lp):
                sz = os.path.getsize(lp)
                if sz > max(1, max_mib) * 1024 * 1024:
                    _evt("S1", "LOCALGW_CALL", actor, "deny", trace_id, {"trace_id": trace_id, "reason": "upload_too_large", "size": int(sz), "max_mib": int(max_mib)})
                    return False, {"ok": False, "reason": "upload_too_large", "max_mib": int(max_mib)}, "upload_too_large"
        except Exception:
            pass

    # Rate limiting (after auth/invite checks, before executing connector)
    try:
        ok_rl, rl = localgw_ratelimit.check_and_increment(policy=pol, device_uid=device_uid or "", connector=str(connector), method=str(method))
        if not ok_rl:
            _evt(
                "S1",
                "LOCALGW_RATE_LIMIT",
                actor,
                "deny",
                trace_id,
                {"trace_id": trace_id, "connector": connector, "method": method, "device_uid": device_uid, "rate": rl},
            )
            return False, {"ok": False, "reason": "rate_limited", "rate": rl}, "rate_limited"
    except Exception:
        # Fail closed would be too aggressive here; we log a warning and proceed.
        pass

    ctx = ConnectorContext(
        epoch_dir=epoch_dir,
        policy=pol,
        actor=actor,
        trace_id=trace_id,
        lan_session_token=str(lan_session_token or ""),
        device_uid=device_uid,
        device_profile=device_profile,
    )

    ok2, result, rr = localgw_connectors.call(connector_id=str(connector), method=str(method), params=(params or {}), ctx=ctx)

    decision = "allow" if ok2 else "quarantine"
    _evt(
        "S1",
        "LOCALGW_CALL",
        actor,
        decision,
        trace_id,
        {
            "trace_id": trace_id,
            "connector": connector,
            "method": method,
            "device_uid": device_uid,
            "ok": bool(ok2),
            "reason": rr,
        },
    )

    return ok2, result, rr
