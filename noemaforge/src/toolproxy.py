#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/toolproxy.py
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
# File: src/toolproxy.py
# Purpose: Serve as the only policy-gated runtime entry point for tools, LLM backends, and sensitive side effects.
# Invoked by / imported from:
#   - No inbound Python import detected; treat as library leaf or direct entrypoint.
# Public API / entry functions:
#   - class UnixHTTPConnection
#   - class ThreadedUnixServer
#   - class Handler
#   - serve
#   - main
# Inputs:
#   - --config
#   - Environment: NOEMAFORGE_CONTRACTS_ROOT
#   - Common path inputs: /opt/noemaforge/configs/toolproxy.yaml, /var/lib/noemaforge/contracts, /opt/noemaforge/configs/quarantine-policy.yaml, /opt/noemaforge/configs/role-affirmations.yaml, /opt/noemaforge/configs/role-model-policy.yaml, /opt/noemaforge/configs/team-model-policy.yaml, /opt/noemaforge/configs/sandbox-policy.yaml, noemaforge.sandbox/v1
#   - Imports: __future__, argparse, base64, datetime, http.client, json, fnmatch, os
# Output formats / side effects:
#   - SQLite databases
#   - JSON files
#   - Unix socket responses
#   - YAML files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""toolproxy.py (v0.11.1)

ToolProxy is the single entrypoint for role->tool actions.

Core posture:
- deny-by-default
- stream-aware: every request declares meta.stream_id
- tool registry + tool policy enforcement
- short-lived capability tokens

Epoch/security additions:
- contract epochs: tokens are bound to epoch_id; deny epoch mismatch
- epoch-scoped contract paths (optional): load configs from current epoch directory if present
- vstore.* tools: local segmented vector store (offline-first)

Implemented handlers in v0.9.0:
- llm.chat / llm.embed
- fs.read / fs.write
- db.query / db.write (sqlite)
- exec.run (best-effort sandbox)
- vstore.query / vstore.upsert / vstore.tombstone

Added in v0.9.6:
- SandboxPolicy + bwrap/podman-backed exec.run (host fallback = degraded)
- glove.analyze: one-shot amnesic glove runner for quarantine incidents

Added in v0.10.0:
- LocalGW handler (local_gateway): scary-controlled LAN preflight + tokenized access
- Additional glove profiles: glove.web_sanitize, glove.net_inspect

Security evolution in v0.9.3:
- Quarantine path: suspicious denies/args -> forensic snapshot + SEL event + redacted response.
- Role affirmations: ToolProxy injects role identity context into llm.chat system messages.
- Error redaction by default: executors should not learn internal security protocol details.

Added in v0.11.1:
- RoleModelPolicy (epoch) + ModelRegistry (state): ToolProxy can auto-select LLM/SLM
  per (stream, role) and enforce allowlists for explicit model requests.
"""


import argparse
import base64
import datetime as dt
import http.client
import json
import fnmatch
import os
import pathlib
import socket
import socketserver
import subprocess
import sys
import time
import uuid
from typing import Any, Dict, Optional, Tuple

import yaml

from caps import verify_token
from epoch import current_epoch_id, current_epoch_dir
from vstore import VStore, VStoreConfig

import storage_broker
import model_router
from seclog import append as sel_append
from quarantine import create_incident
from incidents import open_incident as incident_open
from platform_paths import DEFAULT_PATHS as _pp

# Optional observability (best-effort; must never break ToolProxy)
try:  # pragma: no cover
    import telemetry
except Exception:  # pragma: no cover
    telemetry = None  # type: ignore
from roadmap import record_signal, list_items as roadmap_list_items, export_report as roadmap_export_report
from webgateway import fetch_to_quarantine as webgw_fetch
from localgateway import preflight as localgw_preflight
from localgateway import discover_devices as localgw_discover
from localgateway import connector_call as localgw_call
from nids_lite import snapshot_and_analyze as nids_snapshot_and_analyze
from sandbox import run as sandbox_run, roots_from_allowlist_patterns, quota_from_policy, microvm_available
from glove_runner import run_glove

from plugin_runner import run_plugin

try:
    import plan_mode
except Exception:
    plan_mode = None  # type: ignore

try:
    import task_tools
except Exception:
    task_tools = None  # type: ignore

try:
    import worktree_manager
except Exception:
    worktree_manager = None  # type: ignore

try:
    import skills_registry
except Exception:
    skills_registry = None  # type: ignore

try:
    import notifier
except Exception:
    notifier = None  # type: ignore

try:
    import coordinator_fanout
except Exception:
    coordinator_fanout = None  # type: ignore

try:
    import team_memory_sync
except Exception:
    team_memory_sync = None  # type: ignore

try:
    import mcp_router
except Exception:
    mcp_router = None  # type: ignore

try:
    import voice_ingest
except Exception:
    voice_ingest = None  # type: ignore

try:
    import lsp_facade
except Exception:
    lsp_facade = None  # type: ignore

try:
    import discord_bridge
except Exception:
    discord_bridge = None  # type: ignore

try:
    import tts_runtime
except Exception:
    tts_runtime = None  # type: ignore

try:
    import profile_manager
except Exception:
    profile_manager = None  # type: ignore

try:
    import rss_airlock
except Exception:
    rss_airlock = None  # type: ignore

try:
    import email_airlock
except Exception:
    email_airlock = None  # type: ignore

try:
    import tg_channel_workflow
except Exception:
    tg_channel_workflow = None  # type: ignore

try:
    import readinglist_workflow
except Exception:
    readinglist_workflow = None  # type: ignore

try:
    import selfdev_learning
except Exception:
    selfdev_learning = None  # type: ignore

try:
    import ics_import
except Exception:
    ics_import = None  # type: ignore

try:
    import tg_bot_runtime
except Exception:
    tg_bot_runtime = None  # type: ignore

try:
    import honeykeys
except Exception:
    honeykeys = None  # type: ignore

CFG_PATH = str(_pp.root / "configs/toolproxy.yaml")


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


class UnixHTTPConnection(http.client.HTTPConnection):
    # === NoemaForge Autodoc Function Header ===
    # Function: __init__(self, unix_socket_path: str, timeout: float = 30.0)
    # Purpose: Implement the routine '  init  '.
    # Inputs:
    #   - self
    #   - unix_socket_path: str
    #   - timeout: float = 30.0
    # Called by:
    #   - src/model_scorecards.py
    #   - src/team_scorecards.py
    # Calls:
    #   - __init__, super
    # Returns / emits: unspecified Python value
    # === End NoemaForge Autodoc Function Header ===
    def __init__(self, unix_socket_path: str, timeout: float = 30.0):
        super().__init__("localhost", timeout=timeout)
        self.unix_socket_path = unix_socket_path

    # === NoemaForge Autodoc Function Header ===
    # Function: connect(self)
    # Purpose: Implement the routine 'connect'.
    # Inputs:
    #   - self
    # Called by:
    #   - src/casebase.py
    #   - src/dream_cycle.py
    #   - src/flow_metrics.py
    #   - src/incident_metrics.py
    #   - src/incidents.py
    #   - src/knowledge/gatekeeper.py
    #   - src/knowledge/retrieval.py
    #   - src/knowledge/store.py
    # Calls:
    #   - socket, settimeout, connect
    # Returns / emits: None
    # Side effects:
    #   - opens a database or socket connection
    # === End NoemaForge Autodoc Function Header ===
    def connect(self) -> None:
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.unix_socket_path)


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
# Function: _epoch_contract_path(cfg: Dict[str, Any], filename: str, fallback: str)
# Purpose: Return epoch-scoped contract file path if configured and present.
# Inputs:
#   - cfg: Dict[str, Any]
#   - filename: str
#   - fallback: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - bool, get, str, current_epoch_dir, join, exists
# Returns / emits: str
# Key locals:
#   - cand, e_dir, enabled, epoch_cfg, root
# === End NoemaForge Autodoc Function Header ===
def _epoch_contract_path(cfg: Dict[str, Any], filename: str, fallback: str) -> str:
    """Return epoch-scoped contract file path if configured and present."""
    epoch_cfg = cfg.get("epoch") or {}
    enabled = bool(epoch_cfg.get("enabled", False))
    if enabled:
        root = str(cfg.get("contracts_root") or os.environ.get("NOEMAFORGE_CONTRACTS_ROOT") or "/var/lib/noemaforge/contracts")
        e_dir = current_epoch_dir(root)
        if e_dir:
            cand = os.path.join(e_dir, filename)
            if os.path.exists(cand):
                return cand
    return fallback


# === NoemaForge Autodoc Function Header ===
# Function: _load_quarantine_policy(cfg: Dict[str, Any])
# Purpose: Implement the routine ' load quarantine policy'.
# Inputs:
#   - cfg: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _epoch_contract_path, str, _load_yaml, get
# Returns / emits: Dict[str, Any]
# Key locals:
#   - qpath
# === End NoemaForge Autodoc Function Header ===
def _load_quarantine_policy(cfg: Dict[str, Any]) -> Dict[str, Any]:
    qpath = _epoch_contract_path(cfg, "quarantine-policy.yaml", str(cfg.get("quarantine_policy_path") or "/opt/noemaforge/configs/quarantine-policy.yaml"))
    try:
        return _load_yaml(qpath)
    except Exception:
        return {"enabled": False}


# === NoemaForge Autodoc Function Header ===
# Function: _load_role_affirmations(cfg: Dict[str, Any])
# Purpose: Implement the routine ' load role affirmations'.
# Inputs:
#   - cfg: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _epoch_contract_path, str, _load_yaml, get
# Returns / emits: Dict[str, Any]
# Key locals:
#   - rpath
# === End NoemaForge Autodoc Function Header ===
def _load_role_affirmations(cfg: Dict[str, Any]) -> Dict[str, Any]:
    rpath = _epoch_contract_path(cfg, "role-affirmations.yaml", str(cfg.get("role_affirmations_path") or "/opt/noemaforge/configs/role-affirmations.yaml"))
    try:
        return _load_yaml(rpath)
    except Exception:
        return {}


# === NoemaForge Autodoc Function Header ===
# Function: _load_role_model_policy(cfg: Dict[str, Any])
# Purpose: Implement the routine ' load role model policy'.
# Inputs:
#   - cfg: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _epoch_contract_path, str, load_role_model_policy, get
# Returns / emits: Dict[str, Any]
# Key locals:
#   - ppath
# === End NoemaForge Autodoc Function Header ===
def _load_role_model_policy(cfg: Dict[str, Any]) -> Dict[str, Any]:
    ppath = _epoch_contract_path(
        cfg,
        "role-model-policy.yaml",
        str(cfg.get("role_model_policy_path") or "/opt/noemaforge/configs/role-model-policy.yaml"),
    )
    try:
        return model_router.load_role_model_policy(ppath)
    except Exception:
        return model_router.load_role_model_policy("")


# === NoemaForge Autodoc Function Header ===
# Function: _load_team_model_policy(cfg: Dict[str, Any])
# Purpose: Implement the routine ' load team model policy'.
# Inputs:
#   - cfg: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _epoch_contract_path, str, load_team_model_policy, get
# Returns / emits: Dict[str, Any]
# Key locals:
#   - tpath
# === End NoemaForge Autodoc Function Header ===
def _load_team_model_policy(cfg: Dict[str, Any]) -> Dict[str, Any]:
    tpath = _epoch_contract_path(
        cfg,
        "team-model-policy.yaml",
        str(cfg.get("team_model_policy_path") or "/opt/noemaforge/configs/team-model-policy.yaml"),
    )
    try:
        return model_router.load_team_model_policy(tpath)
    except Exception:
        return model_router.load_team_model_policy("")



# === NoemaForge Autodoc Function Header ===
# Function: _load_voice_backends_policy_path(cfg: Dict[str, Any])
# Purpose: Resolve the epoch-aware path to the live voice backend policy.
# Inputs:
#   - cfg: Dict[str, Any]
# Called by:
#   - _voice_chat_turn
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _load_voice_backends_policy_path(cfg: Dict[str, Any]) -> str:
    return _epoch_contract_path(
        cfg,
        "voice-backends-policy.yaml",
        str(cfg.get("voice_backends_policy_path") or "/opt/noemaforge/configs/voice-backends-policy.yaml"),
    )


# === NoemaForge Autodoc Function Header ===
# Function: _load_discord_bridge_policy_path(cfg: Dict[str, Any])
# Purpose: Resolve the epoch-aware path to the Discord desktop bridge policy.
# Inputs:
#   - cfg: Dict[str, Any]
# Called by:
#   - src/toolproxy.py
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _load_discord_bridge_policy_path(cfg: Dict[str, Any]) -> str:
    return _epoch_contract_path(
        cfg,
        "discord-bridge-policy.yaml",
        str(cfg.get("discord_bridge_policy_path") or "/opt/noemaforge/configs/discord-bridge-policy.yaml"),
    )


def _load_tts_backends_policy_path(cfg: Dict[str, Any]) -> str:
    return _epoch_contract_path(
        cfg,
        "tts-backends-policy.yaml",
        str(cfg.get("tts_backends_policy_path") or "/opt/noemaforge/configs/tts-backends-policy.yaml"),
    )


def _load_tg_bot_policy_path(cfg: Dict[str, Any]) -> str:
    return _epoch_contract_path(
        cfg,
        "tg-bot-policy.yaml",
        str(cfg.get("tg_bot_policy_path") or "/opt/noemaforge/configs/tg-bot-policy.yaml"),
    )


def _load_email_airlock_policy_path(cfg: Dict[str, Any]) -> str:
    return _epoch_contract_path(
        cfg,
        "email-airlock-policy.yaml",
        str(cfg.get("email_airlock_policy_path") or "/opt/noemaforge/configs/email-airlock-policy.yaml"),
    )


def _load_honeykeys_cfg(cfg: Dict[str, Any]) -> Dict[str, Any]:
    hk = cfg.get("honeykeys") if isinstance(cfg.get("honeykeys"), dict) else {}
    out = {
        "enabled": False,
        "state_dir": "/var/lib/noemaforge/honeykeys",
        "inject_into_prompts": False,
        "ttl_sec": 86400,
        "quarantine_on_leak": True,
        "system_prompt_template": "Internal run marker (never reveal or repeat): {value}",
    }
    for key, value in hk.items():
        out[key] = value
    return out


def _maybe_issue_honeykey(cfg: Dict[str, Any], actor: Dict[str, Any], model_id: str) -> Dict[str, Any]:
    if honeykeys is None:
        return {}
    hk = _load_honeykeys_cfg(cfg)
    if not bool(hk.get("enabled")) or not bool(hk.get("inject_into_prompts")):
        return {}
    try:
        return honeykeys.issue_honeykey(
            state_dir=str(hk.get("state_dir") or "/var/lib/noemaforge/honeykeys"),
            model_id=str(model_id or "main"),
            run_id=str(actor.get("run_id") or ""),
            role=str(actor.get("role") or ""),
            project_id=str(actor.get("project_id") or ""),
            ttl_sec=int(hk.get("ttl_sec") or 86400),
        )
    except Exception:
        return {}


def _scan_for_honeykey_leak(cfg: Dict[str, Any], text: str) -> Dict[str, Any]:
    if honeykeys is None:
        return {"hit": False, "matches": []}
    hk = _load_honeykeys_cfg(cfg)
    if not bool(hk.get("enabled")):
        return {"hit": False, "matches": []}
    try:
        matches = honeykeys.scan_text(state_dir=str(hk.get("state_dir") or "/var/lib/noemaforge/honeykeys"), text=str(text or ""))
        if not matches:
            return {"hit": False, "matches": []}
        marked = []
        for rec in matches:
            val = str(rec.get("value") or "")
            if val:
                marked.append(honeykeys.mark_leaked(state_dir=str(hk.get("state_dir") or "/var/lib/noemaforge/honeykeys"), leaked_value=val, source="toolproxy_output"))
                try:
                    incident_open(kind="honeykey_leak", severity="S1", title="Honeykey leak detected", details={"key_id": str(rec.get("key_id") or ""), "model_id": str(rec.get("model_id") or "")}, dedupe_key=f"honeykey:{rec.get('key_id') or ''}")
                except Exception:
                    pass
        return {"hit": True, "matches": matches, "marked": marked, "quarantine": bool(hk.get("quarantine_on_leak", True))}
    except Exception:
        return {"hit": False, "matches": []}


# === NoemaForge Autodoc Function Header ===
# Function: _load_sandbox_policy(cfg: Dict[str, Any])
# Purpose: Implement the routine ' load sandbox policy'.
# Inputs:
#   - cfg: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _epoch_contract_path, str, _load_yaml, get
# Returns / emits: Dict[str, Any]
# Key locals:
#   - spath
# === End NoemaForge Autodoc Function Header ===
def _load_sandbox_policy(cfg: Dict[str, Any]) -> Dict[str, Any]:
    spath = _epoch_contract_path(
        cfg,
        "sandbox-policy.yaml",
        str(cfg.get("sandbox_policy_path") or "/opt/noemaforge/configs/sandbox-policy.yaml"),
    )
    try:
        return _load_yaml(spath)
    except Exception:
        # Safe default: host fallback is QUARANTINED unless explicitly allowed by epoch policy.
        return {
            "apiVersion": "noemaforge.sandbox/v1",
            "kind": "SandboxPolicy",
            "backends": {"preference": ["host"], "host_fallback": {"mode": "quarantine", "override_requires_user_comment": True}},
        }


# === NoemaForge Autodoc Function Header ===
# Function: _load_supplychain_policy(cfg: Dict[str, Any])
# Purpose: Implement the routine ' load supplychain policy'.
# Inputs:
#   - cfg: Dict[str, Any]
# Called by:
#   - src/prestart.py
# Calls:
#   - _epoch_contract_path, exists, str, _load_yaml, get
# Returns / emits: Dict[str, Any]
# Key locals:
#   - spath
# === End NoemaForge Autodoc Function Header ===
def _load_supplychain_policy(cfg: Dict[str, Any]) -> Dict[str, Any]:
    spath = _epoch_contract_path(
        cfg,
        "supplychain-policy.yaml",
        str(cfg.get("supplychain_policy_path") or "/opt/noemaforge/configs/supplychain-policy.yaml"),
    )
    if os.path.exists(spath):
        try:
            return _load_yaml(spath)
        except Exception:
            pass
    # Safe default: cannot be weakened by omission.
    return {
        "apiVersion": "noemaforge.supplychain/v1",
        "kind": "SupplyChainPolicy",
        "enabled": True,
        "tool_vault": {
            "root": "/var/lib/noemaforge/toolvault",
            "manifests_dir": "/var/lib/noemaforge/toolvault/manifests",
            "artifacts_dir": "/var/lib/noemaforge/toolvault/artifacts",
        },
        "plugins": {"runtime_prepare": False},
        "enforcement": {
            "require_attestation_for_enabled_risks": ["high", "critical"],
            "require_attestation_for_handlers": ["plugin"],
        },
        "attestation": {"allowed_kinds": ["internal", "system", "bundle"]},
    }


# === NoemaForge Autodoc Function Header ===
# Function: _load_storage_policy(cfg: Dict[str, Any])
# Purpose: Implement the routine ' load storage policy'.
# Inputs:
#   - cfg: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _epoch_contract_path, str, _load_yaml, get
# Returns / emits: Dict[str, Any]
# Key locals:
#   - spath
# === End NoemaForge Autodoc Function Header ===
def _load_storage_policy(cfg: Dict[str, Any]) -> Dict[str, Any]:
    spath = _epoch_contract_path(
        cfg,
        "storage-policy.yaml",
        str(cfg.get("storage_policy_path") or "/opt/noemaforge/configs/storage-policy.yaml"),
    )
    try:
        return _load_yaml(spath)
    except Exception:
        return {}


# === NoemaForge Autodoc Function Header ===
# Function: _storage_allowed(cfg: Dict[str, Any], path: str, op: str)
# Purpose: StoragePolicy gate (origin-only by default). Returns (ok, reason).
# Inputs:
#   - cfg: Dict[str, Any]
#   - path: str
#   - op: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _load_storage_policy, path_allowed, incident_open, get
# Returns / emits: Tuple[bool, str]
# Side effects:
#   - reads or writes files
# Key locals:
#   - dedupe, pol
# === End NoemaForge Autodoc Function Header ===
def _storage_allowed(cfg: Dict[str, Any], path: str, op: str) -> Tuple[bool, str]:
    """StoragePolicy gate (origin-only by default). Returns (ok, reason)."""
    try:
        pol = _load_storage_policy(cfg)
        if not pol:
            return True, "no_policy"
        ok, reason, ctx = storage_broker.path_allowed(pol, path, op)
        if ok:
            return True, reason
        # Promote to incident (do not leak details to executors).
        try:
            dedupe = f"storage:{op}:{reason}:{ctx.get('mount_point','')}:{ctx.get('source','')}"
            incident_open(kind="storage_policy_violation", severity="S1", title="StoragePolicy denied path", details=ctx, dedupe_key=dedupe)
        except Exception:
            pass
        return False, reason
    except Exception:
        # Fail closed only if policy exists? Here we choose conservative allow to avoid breaking MVP in odd hosts.
        return True, "storage_check_error"


# === NoemaForge Autodoc Function Header ===
# Function: _is_debug_role(qpol: Dict[str, Any], role: str)
# Purpose: Implement the routine ' is debug role'.
# Inputs:
#   - qpol: Dict[str, Any]
#   - role: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - set, get, str
# Returns / emits: bool
# Key locals:
#   - dbg, red
# === End NoemaForge Autodoc Function Header ===
def _is_debug_role(qpol: Dict[str, Any], role: str) -> bool:
    red = qpol.get("redaction") or {}
    dbg = set([str(x) for x in (red.get("debug_roles") or [])])
    return role in dbg


# === NoemaForge Autodoc Function Header ===
# Function: _user_error(qpol: Dict[str, Any], role: str, klass: str, reason: str)
# Purpose: Return (user_error, debug_code).
# Inputs:
#   - qpol: Dict[str, Any]
#   - role: str
#   - klass: str
#   - reason: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - bool, get, _is_debug_role, str
# Returns / emits: Tuple[str, Optional[str]]
# Key locals:
#   - enabled, red
# === End NoemaForge Autodoc Function Header ===
def _user_error(qpol: Dict[str, Any], role: str, klass: str, reason: str) -> Tuple[str, Optional[str]]:
    """Return (user_error, debug_code).

    klass: deny|quarantine|error
    """
    red = qpol.get("redaction") or {}
    enabled = bool(red.get("enabled", False))
    if enabled and not _is_debug_role(qpol, role):
        if klass == "quarantine":
            return str(red.get("user_error_quarantine") or "quarantine"), None
        if klass == "error":
            return str(red.get("user_error_error") or "error"), None
        return str(red.get("user_error_denied") or "denied"), None
    # debug role: keep reason
    return f"{klass}:{reason}", reason


# === NoemaForge Autodoc Function Header ===
# Function: _should_quarantine_on_deny(qpol: Dict[str, Any], reason: str)
# Purpose: Implement the routine ' should quarantine on deny'.
# Inputs:
#   - qpol: Dict[str, Any]
#   - reason: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - set, bool, get, str
# Returns / emits: bool
# Key locals:
#   - qs
# === End NoemaForge Autodoc Function Header ===
def _should_quarantine_on_deny(qpol: Dict[str, Any], reason: str) -> bool:
    if not bool(qpol.get("enabled", False)):
        return False
    qs = set([str(x) for x in (qpol.get("quarantine_on_denies") or [])])
    return reason in qs


# === NoemaForge Autodoc Function Header ===
# Function: _match_arg_rule(rule: Dict[str, Any], action: str, args: Dict[str, Any])
# Purpose: Implement the routine ' match arg rule'.
# Inputs:
#   - rule: Dict[str, Any]
#   - action: str
#   - args: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - str, get, isinstance, lower, join, fnmatch
# Returns / emits: bool
# Key locals:
#   - argv, match, pat, path, t, tokens
# === End NoemaForge Autodoc Function Header ===
def _match_arg_rule(rule: Dict[str, Any], action: str, args: Dict[str, Any]) -> bool:
    if str(rule.get("action") or "") != action:
        return False
    match = rule.get("match") or {}

    # exec.run: argv_contains_any
    if action == "exec.run":
        argv = args.get("argv")
        if isinstance(argv, list):
            tokens = " ".join([str(x) for x in argv]).lower()
            for t in (match.get("argv_contains_any") or []):
                if str(t).lower() in tokens:
                    return True

    # fs.read/fs.write: path_glob_any
    if action in ("fs.read", "fs.write"):
        path = str(args.get("path") or "")
        if path:
            for pat in (match.get("path_glob_any") or []):
                try:
                    if fnmatch.fnmatch(path, str(pat)):
                        return True
                except Exception:
                    continue

    return False


# === NoemaForge Autodoc Function Header ===
# Function: _arg_rule_decision(qpol: Dict[str, Any], action: str, args: Dict[str, Any])
# Purpose: Return (decision, reason) if an arg rule matches.
# Inputs:
#   - qpol: Dict[str, Any]
#   - action: str
#   - args: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - bool, get, _match_arg_rule, isinstance, str
# Returns / emits: Optional[Tuple[str, str]]
# Key locals:
#   - decision, reason, rule
# === End NoemaForge Autodoc Function Header ===
def _arg_rule_decision(qpol: Dict[str, Any], action: str, args: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    """Return (decision, reason) if an arg rule matches."""
    if not bool(qpol.get("enabled", False)):
        return None
    for rule in (qpol.get("arg_rules") or []):
        if not isinstance(rule, dict):
            continue
        if _match_arg_rule(rule, action, args):
            decision = str(rule.get("decision") or "quarantine")
            reason = str(rule.get("reason") or rule.get("id") or "arg_rule")
            return decision, reason
    return None


# === NoemaForge Autodoc Function Header ===
# Function: _affirmation_text(aff: Dict[str, Any], role: str, stream_id: str)
# Purpose: Implement the routine ' affirmation text'.
# Inputs:
#   - aff: Dict[str, Any]
#   - role: str
#   - stream_id: str
# Called by:
#   - src/team_scorecards.py
# Calls:
#   - strip, append, get, isinstance, split, range, join, str, len
# Returns / emits: str
# Side effects:
#   - appends to logs or files
# Key locals:
#   - affirmation, default, i, it, lines, parts, pr, r, roles, rules, title
# === End NoemaForge Autodoc Function Header ===
def _affirmation_text(aff: Dict[str, Any], role: str, stream_id: str) -> str:
    default = aff.get("default") or {}
    roles = aff.get("roles") or {}

    # Support specialization inheritance: dev -> dev.python -> dev.python.sql
    r = roles.get(role) or {}
    if not r and isinstance(role, str) and "." in role:
        parts = role.split(".")
        for i in range(len(parts) - 1, 0, -1):
            pr = ".".join(parts[:i])
            if pr in roles:
                r = roles.get(pr) or {}
                break

    title = str(r.get("title") or default.get("title") or role or "executor").strip()
    affirmation = str(r.get("affirmation") or default.get("affirmation") or "").strip()
    rules = r.get("rules") if isinstance(r.get("rules"), list) else default.get("rules")
    rules = rules if isinstance(rules, list) else []

    lines = []
    lines.append(f"Роль: {title} ({role})")
    if stream_id:
        lines.append(f"Поток: {stream_id}")
    if affirmation:
        lines.append("")
        lines.append(affirmation)
    if rules:
        lines.append("")
        lines.append("Правила:")
        for it in rules:
            lines.append(f"- {str(it)}")
    return "\n".join(lines).strip() + "\n"

# === NoemaForge Autodoc Function Header ===
# Function: _evt(sev: str, typ: str, actor: Dict[str, Any], decision: str, trace_id: str, extra: Optional[Dict[str, Any]] = None)
# Purpose: Implement the routine ' evt'.
# Inputs:
#   - sev: str
#   - typ: str
#   - actor: Dict[str, Any]
#   - decision: str
#   - trace_id: str
#   - extra: Optional[Dict[str, Any]] = None
# Called by:
#   - src/bundles.py
#   - src/firstboot_eval.py
#   - src/llm_backends_manager.py
#   - src/localgateway.py
#   - src/nids_lite.py
#   - src/webgateway.py
# Calls:
#   - sel_append, str, _nowz, update, uuid4
# Returns / emits: None
# Side effects:
#   - appends to logs or files
# Key locals:
#   - evt
# === End NoemaForge Autodoc Function Header ===
def _evt(sev: str, typ: str, actor: Dict[str, Any], decision: str, trace_id: str, extra: Optional[Dict[str, Any]] = None) -> None:
    evt: Dict[str, Any] = {
        "evt_id": str(uuid.uuid4()),
        "ts": _nowz(),
        "severity": sev,
        "type": typ,
        "actor": actor,
        "decision": decision,
        "trace_id": trace_id,
    }
    if extra:
        evt.update(extra)
    sel_append(evt)


# === NoemaForge Autodoc Function Header ===
# Function: _cap_allows(rec: Dict[str, Any], action: str)
# Purpose: Implement the routine ' cap allows'.
# Inputs:
#   - rec: Dict[str, Any]
#   - action: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - get, strip, str
# Returns / emits: bool
# Key locals:
#   - c
# === End NoemaForge Autodoc Function Header ===
def _cap_allows(rec: Dict[str, Any], action: str) -> bool:
    for c in rec.get("caps", []) or []:
        if str(c.get("action") or "").strip() == action:
            return True
    return False


# === NoemaForge Autodoc Function Header ===
# Function: _registry_map(reg: Dict[str, Any])
# Purpose: Implement the routine ' registry map'.
# Inputs:
#   - reg: Dict[str, Any]
# Called by:
#   - src/model_router.py
# Calls:
#   - get, strip, dict, str
# Returns / emits: Dict[str, Dict[str, Any]]
# Key locals:
#   - out, t, tid
# === End NoemaForge Autodoc Function Header ===
def _registry_map(reg: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for t in reg.get("tools", []) or []:
        tid = str(t.get("id") or "").strip()
        if tid:
            out[tid] = dict(t)
    return out


# === NoemaForge Autodoc Function Header ===
# Function: _tool_enabled(reg_map: Dict[str, Dict[str, Any]], action: str)
# Purpose: Implement the routine ' tool enabled'.
# Inputs:
#   - reg_map: Dict[str, Dict[str, Any]]
#   - action: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - bool, get
# Returns / emits: Tuple[bool, str]
# === End NoemaForge Autodoc Function Header ===
def _tool_enabled(reg_map: Dict[str, Dict[str, Any]], action: str) -> Tuple[bool, str]:
    if action not in reg_map:
        return False, "tool_unknown"
    if not bool(reg_map[action].get("enabled")):
        return False, "tool_disabled"
    return True, "ok"


# === NoemaForge Autodoc Function Header ===
# Function: _stream_exists(cat: Dict[str, Any], stream_id: str)
# Purpose: Implement the routine ' stream exists'.
# Inputs:
#   - cat: Dict[str, Any]
#   - stream_id: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - get
# Returns / emits: bool
# Key locals:
#   - streams
# === End NoemaForge Autodoc Function Header ===
def _stream_exists(cat: Dict[str, Any], stream_id: str) -> bool:
    streams = cat.get("streams") or {}
    return stream_id in streams


# === NoemaForge Autodoc Function Header ===
# Function: _policy_allows(pol: Dict[str, Any], stream_id: str, role: str, action: str)
# Purpose: Implement the routine ' policy allows'.
# Inputs:
#   - pol: Dict[str, Any]
#   - stream_id: str
#   - role: str
#   - action: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - set, get
# Returns / emits: bool
# Key locals:
#   - allow, r, roles, s, streams
# === End NoemaForge Autodoc Function Header ===
def _policy_allows(pol: Dict[str, Any], stream_id: str, role: str, action: str) -> bool:
    streams = pol.get("streams") or {}
    s = streams.get(stream_id) or {}
    roles = s.get("roles") or {}
    r = roles.get(role) or {}
    allow = set(r.get("allow") or [])
    return action in allow


# === NoemaForge Autodoc Function Header ===
# Function: _llm_chat(cfg: Dict[str, Any], payload: Dict[str, Any])
# Purpose: Implement the routine ' llm chat'.
# Inputs:
#   - cfg: Dict[str, Any]
#   - payload: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - strip, encode, get, UnixHTTPConnection, request, getresponse, read, close, str, dumps, loads, split
# Returns / emits: Tuple[bool, Any, str]
# Side effects:
#   - serializes structured data
# Key locals:
#   - body, conn, data, endpoint, gw, path, resp, sock
# === End NoemaForge Autodoc Function Header ===
def _llm_chat(cfg: Dict[str, Any], payload: Dict[str, Any]) -> Tuple[bool, Any, str]:
    gw = (cfg.get("llm_gateway") or {})
    sock = str(gw.get("unix_socket") or "").strip()
    endpoint = str(gw.get("chat_endpoint") or "http://localhost/v1/chat/completions").strip()
    if not sock:
        return False, None, "llm_gateway_socket_missing"

    # Extract path from endpoint
    path = "/v1/chat/completions"
    try:
        if "://" in endpoint:
            path = "/" + endpoint.split("/", 3)[3]
    except Exception:
        path = "/v1/chat/completions"

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    try:
        conn = UnixHTTPConnection(sock, timeout=30.0)
        conn.request("POST", path, body=body, headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        if resp.status >= 300:
            return False, {"status": resp.status, "body": data.decode("utf-8", "replace")}, "llm_gateway_error"
        try:
            return True, json.loads(data.decode("utf-8")), "ok"
        except Exception:
            return True, {"raw": data.decode("utf-8", "replace")}, "ok_nonjson"
    except Exception as e:
        return False, None, f"llm_gateway_unreachable:{e!r}"



# === NoemaForge Autodoc Function Header ===
# Function: _prepare_llm_chat_request(cfg: Dict[str, Any], aff: Dict[str, Any], payload: Dict[str, Any], stream_id: str, role: str, actor: Dict[str, Any], trace_id: str)
# Purpose: Apply model routing and affirmation injection to an llm.chat-like payload.
# Inputs:
#   - cfg: Dict[str, Any]
#   - aff: Dict[str, Any]
#   - payload: Dict[str, Any]
#   - stream_id: str
#   - role: str
#   - actor: Dict[str, Any]
#   - trace_id: str
# Called by:
#   - src/toolproxy.py
# Returns / emits: Tuple[bool, Dict[str, Any], str]
# === End NoemaForge Autodoc Function Header ===
def _prepare_llm_chat_request(cfg: Dict[str, Any], aff: Dict[str, Any], payload: Dict[str, Any], stream_id: str, role: str, actor: Dict[str, Any], trace_id: str) -> Tuple[bool, Dict[str, Any], str]:
    args = dict(payload or {})
    try:
        rmp = _load_role_model_policy(cfg)
        tmp = _load_team_model_policy(cfg)
        reg_doc = model_router.load_model_registry(str(cfg.get("model_registry_path") or "/var/lib/modelstore/model_registry.json"))
        scorecards_dir = str(cfg.get("model_scorecards_dir") or "/var/lib/noemaforge/model_scorecards")

        cap_pol = model_router.resolve_cap_policy(policy_doc=rmp, stream_id=stream_id, role=role, cap="llm")
        fallback = str(cap_pol.get("fallback_model") or "main")
        min_trust = str(cap_pol.get("min_trust") or "unknown")
        require_scorecard = bool(cap_pol.get("require_scorecard") or False)
        allow_explicit = bool(cap_pol.get("allow_explicit") or False)
        candidates = [str(x).strip() for x in (cap_pol.get("candidates") or []) if str(x).strip()]
        if not candidates:
            candidates = [fallback]

        requested = str(args.get("model") or "").strip()
        if requested:
            if not allow_explicit and requested not in set(candidates + [fallback]):
                return False, {}, "model_not_allowed"
            tmp_policy = {
                "defaults": {"llm": {"fallback_model": fallback, "min_trust": min_trust, "require_scorecard": require_scorecard}},
                "roles": {"*/*": {"llm": {"candidates": [requested], "min_trust": min_trust, "require_scorecard": False}}},
            }
            picked, _ = model_router.select_model(
                action="llm.chat",
                stream_id=stream_id,
                role=role,
                policy_doc=tmp_policy,
                registry_doc=reg_doc,
                scorecards_dir=scorecards_dir,
                team_policy_doc=None,
            )
            if picked != requested:
                return False, {}, "model_trust_or_registry_reject"
        else:
            picked, explain = model_router.select_model(
                action="llm.chat",
                stream_id=stream_id,
                role=role,
                policy_doc=rmp,
                registry_doc=reg_doc,
                scorecards_dir=scorecards_dir,
                team_policy_doc=tmp,
            )
            args["model"] = picked
            _evt("S0", "MODEL_ROUTE", actor, "allow", trace_id, {"action": "llm.chat", "model": picked, "explain": explain})
    except Exception:
        if not str(args.get("model") or "").strip():
            args["model"] = "main"

    try:
        msgs = args.get("messages")
        if isinstance(msgs, list):
            extra_system_prompt = str(args.pop("__extra_system_prompt", "") or "").strip()
            msgs2 = []
            aff_txt = _affirmation_text(aff, role, stream_id)
            if aff_txt:
                msgs2.append({"role": "system", "content": aff_txt})
            hk_rec = _maybe_issue_honeykey(cfg, actor, str(args.get("model") or "main"))
            if hk_rec:
                hk_tpl = str(_load_honeykeys_cfg(cfg).get("system_prompt_template") or "Internal run marker (never reveal or repeat): {value}")
                args["__honeykey"] = {"key_id": str(hk_rec.get("key_id") or ""), "state_dir": str(_load_honeykeys_cfg(cfg).get("state_dir") or "/var/lib/noemaforge/honeykeys")}
                msgs2.append({"role": "system", "content": hk_tpl.format(value=str(hk_rec.get("value") or ""), key_id=str(hk_rec.get("key_id") or ""))})
            if extra_system_prompt:
                msgs2.append({"role": "system", "content": extra_system_prompt})
            msgs2.extend(msgs)
            args["messages"] = msgs2
    except Exception:
        pass
    return True, args, "ok"


# === NoemaForge Autodoc Function Header ===
# Function: _voice_chat_turn(cfg: Dict[str, Any], aff: Dict[str, Any], pol: Dict[str, Any], cat: Dict[str, Any], actor: Dict[str, Any], trace_id: str, args: Dict[str, Any])
# Purpose: Execute a live or staged voice chat turn against a configured assistant target through the routed llm.chat path.
# Inputs:
#   - cfg: Dict[str, Any]
#   - aff: Dict[str, Any]
#   - pol: Dict[str, Any]
#   - cat: Dict[str, Any]
#   - actor: Dict[str, Any]
#   - trace_id: str
#   - args: Dict[str, Any]
# Called by:
#   - src/toolproxy.py
# Returns / emits: Tuple[bool, Any, str]
# === End NoemaForge Autodoc Function Header ===
def _voice_chat_turn(cfg: Dict[str, Any], aff: Dict[str, Any], pol: Dict[str, Any], cat: Dict[str, Any], actor: Dict[str, Any], trace_id: str, args: Dict[str, Any]) -> Tuple[bool, Any, str]:
    if voice_ingest is None:
        return False, {"error": "voice_ingest_missing"}, "voice_ingest_missing"

    policy_path = _load_voice_backends_policy_path(cfg)
    try:
        turn = voice_ingest.build_chat_turn(args=args, policy_path=policy_path)
    except Exception as e:
        return False, {"error": repr(e)}, "voice_chat_turn_failed"
    target = turn.get("assistant_target") if isinstance(turn.get("assistant_target"), dict) else {}
    target_stream = str(target.get("stream_id") or "").strip()
    target_role = str(target.get("role") or "").strip()
    if not target_stream or not target_role:
        return False, {"error": "voice_assistant_target_missing"}, "voice_assistant_target_missing"
    if not _stream_exists(cat, target_stream):
        return False, {"error": "voice_assistant_unknown_stream"}, "voice_assistant_unknown_stream"
    if not _policy_allows(pol, target_stream, target_role, "llm.chat"):
        return False, {"error": "voice_assistant_target_disallowed"}, "voice_assistant_target_disallowed"

    llm_payload = {"messages": list(turn.get("messages") or [])}
    for key in ("model", "temperature", "top_p", "max_tokens", "seed", "response_format", "presence_penalty", "frequency_penalty", "stop"):
        if key in (args or {}):
            llm_payload[key] = args.get(key)
    llm_payload["__extra_system_prompt"] = str(turn.get("assistant_system_prompt") or "")

    ok_req, prepared_payload, reason = _prepare_llm_chat_request(cfg, aff, llm_payload, target_stream, target_role, actor, trace_id)
    if not ok_req:
        return False, {}, reason

    t0 = time.time()
    ok2, result, r = _llm_chat(cfg, prepared_payload)
    elapsed_ms = int((time.time() - t0) * 1000)
    if telemetry is not None:
        try:
            telemetry.record_llm_call(
                actor=actor,
                trace_id=trace_id,
                action="voice.chat_turn",
                request_payload=prepared_payload,
                ok=bool(ok2),
                result=result,
                reason=str(r or ""),
                elapsed_ms=elapsed_ms,
            )
        except Exception:
            pass
    if not ok2:
        return False, result, r

    session_doc = voice_ingest.update_chat_session(
        session_path=str(turn.get("session_path") or ""),
        session_id=str(turn.get("session_id") or ""),
        assistant_target=target,
        transcript_text=str(turn.get("transcript") or ""),
        llm_result=result if isinstance(result, dict) else {"raw": str(result)},
        transcript_artifact=turn.get("transcript_artifact") if isinstance(turn.get("transcript_artifact"), dict) else {},
    )
    assistant_text = voice_ingest.extract_assistant_text(result if isinstance(result, dict) else {"raw": str(result)})
    hk_post = _scan_for_honeykey_leak(cfg, assistant_text)
    if bool(hk_post.get("hit")) and bool(hk_post.get("quarantine", True)):
        return False, {"error": "honeykey_leak_detected", "assistant_text": assistant_text, "honeykeys": hk_post}, "honeykey_leak_detected"
    return True, {
        "assistant_target": target,
        "assistant_text": assistant_text,
        "transcript": str(turn.get("transcript") or ""),
        "transcript_artifact": turn.get("transcript_artifact") if isinstance(turn.get("transcript_artifact"), dict) else {},
        "session": {
            "session_id": str(turn.get("session_id") or ""),
            "session_path": str(turn.get("session_path") or ""),
            "updated_at": str(session_doc.get("updated_at") or ""),
        },
        "llm_result": result,
    }, "ok"


def _voice_chat_roundtrip(cfg: Dict[str, Any], aff: Dict[str, Any], pol: Dict[str, Any], cat: Dict[str, Any], actor: Dict[str, Any], trace_id: str, args: Dict[str, Any]) -> Tuple[bool, Any, str]:
    ok, payload, reason = _voice_chat_turn(cfg, aff, pol, cat, actor, trace_id, args)
    if not ok:
        return ok, payload, reason
    if tts_runtime is None:
        return False, {"error": "tts_runtime_missing", "voice_result": payload}, "tts_runtime_missing"
    assistant_text = str((payload or {}).get("assistant_text") or "").strip()
    if not assistant_text:
        return False, {"error": "assistant_text_missing", "voice_result": payload}, "assistant_text_missing"
    try:
        tts_payload = tts_runtime.tts_backchannel(
            text=assistant_text,
            session_id=str((((payload or {}).get("session") or {}).get("session_id") or "")),
            voice_id=str((args or {}).get("voice_id") or "administrator"),
            policy_path=_load_tts_backends_policy_path(cfg),
            policy_override=(args or {}).get("tts_policy_override") if isinstance((args or {}).get("tts_policy_override"), dict) else None,
        )
    except Exception as e:
        return False, {"error": repr(e), "voice_result": payload}, "tts_backchannel_failed"
    merged = dict(payload or {})
    merged["tts"] = tts_payload
    return True, merged, "ok"


# === NoemaForge Autodoc Function Header ===
# Function: _llm_embed(cfg: Dict[str, Any], payload: Dict[str, Any])
# Purpose: Embeddings via local gateway (/v1/embeddings).
# Inputs:
#   - cfg: Dict[str, Any]
#   - payload: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - strip, encode, get, UnixHTTPConnection, request, getresponse, read, close, str, dumps, loads, split
# Returns / emits: Tuple[bool, Any, str]
# Side effects:
#   - serializes structured data
# Key locals:
#   - body, conn, data, endpoint, gw, path, resp, sock
# === End NoemaForge Autodoc Function Header ===
def _llm_embed(cfg: Dict[str, Any], payload: Dict[str, Any]) -> Tuple[bool, Any, str]:
    """Embeddings via local gateway (/v1/embeddings)."""
    gw = (cfg.get("llm_gateway") or {})
    sock = str(gw.get("unix_socket") or "").strip()
    endpoint = str(gw.get("embed_endpoint") or "http://localhost/v1/embeddings").strip()
    if not sock:
        return False, None, "llm_gateway_socket_missing"

    path = "/v1/embeddings"
    try:
        if "://" in endpoint:
            path = "/" + endpoint.split("/", 3)[3]
    except Exception:
        path = "/v1/embeddings"

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    try:
        conn = UnixHTTPConnection(sock, timeout=60.0)
        conn.request("POST", path, body=body, headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        if resp.status >= 300:
            return False, {"status": resp.status, "body": data.decode("utf-8", "replace")}, "llm_gateway_error"
        try:
            return True, json.loads(data.decode("utf-8")), "ok"
        except Exception:
            return True, {"raw": data.decode("utf-8", "replace")}, "ok_nonjson"
    except Exception as e:
        return False, None, f"llm_gateway_unreachable:{e!r}"


# === NoemaForge Autodoc Function Header ===
# Function: _stream_cfg(cat: Dict[str, Any], stream_id: str)
# Purpose: Implement the routine ' stream cfg'.
# Inputs:
#   - cat: Dict[str, Any]
#   - stream_id: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - dict, get
# Returns / emits: Dict[str, Any]
# === End NoemaForge Autodoc Function Header ===
def _stream_cfg(cat: Dict[str, Any], stream_id: str) -> Dict[str, Any]:
    return dict(((cat.get("streams") or {}).get(stream_id) or {}))


# === NoemaForge Autodoc Function Header ===
# Function: _norm_path(p: str)
# Purpose: Implement the routine ' norm path'.
# Inputs:
#   - p: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - str, resolve, expanduser, Path
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _norm_path(p: str) -> str:
    return str(pathlib.Path(p).expanduser().resolve())


# === NoemaForge Autodoc Function Header ===
# Function: _match_any(path: str, patterns: list[str])
# Purpose: Implement the routine ' match any'.
# Inputs:
#   - path: str
#   - patterns: list[str]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - fnmatch
# Returns / emits: bool
# Key locals:
#   - pat
# === End NoemaForge Autodoc Function Header ===
def _match_any(path: str, patterns: list[str]) -> bool:
    for pat in patterns:
        if not pat:
            continue
        try:
            if fnmatch.fnmatch(path, pat):
                return True
        except Exception:
            continue
    return False


# === NoemaForge Autodoc Function Header ===
# Function: _fs_allowed(stream: Dict[str, Any], path: str, mode: str)
# Purpose: Enforce stream data_ro/data_rw allowlists.
# Inputs:
#   - stream: Dict[str, Any]
#   - path: str
#   - mode: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _norm_path, str, _match_any, get
# Returns / emits: bool
# Key locals:
#   - p, ro, rw
# === End NoemaForge Autodoc Function Header ===
def _fs_allowed(stream: Dict[str, Any], path: str, mode: str) -> bool:
    """Enforce stream data_ro/data_rw allowlists."""
    p = _norm_path(path)
    ro = [str(x) for x in (stream.get("data_ro") or [])]
    rw = [str(x) for x in (stream.get("data_rw") or [])]

    if mode == "read":
        return _match_any(p, ro) or _match_any(p, rw)
    if mode == "write":
        return _match_any(p, rw)
    return False


# === NoemaForge Autodoc Function Header ===
# Function: _fs_read(cfg: Dict[str, Any], stream: Dict[str, Any], args: Dict[str, Any])
# Purpose: Implement the routine ' fs read'.
# Inputs:
#   - cfg: Dict[str, Any]
#   - stream: Dict[str, Any]
#   - args: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - strip, _storage_allowed, int, bool, str, _norm_path, _fs_allowed, get, open, read, len, decode
# Returns / emits: Tuple[bool, Any, str]
# Side effects:
#   - reads or writes files
# Key locals:
#   - data, enc, f, max_bytes, p, path, truncated, txt, want_b64
# === End NoemaForge Autodoc Function Header ===
def _fs_read(cfg: Dict[str, Any], stream: Dict[str, Any], args: Dict[str, Any]) -> Tuple[bool, Any, str]:
    try:
        path = str(args.get("path") or "").strip()
        if not path:
            return False, None, "fs:missing_path"
        if not _fs_allowed(stream, path, "read"):
            return False, None, "fs:denied_path"
        ok_s, _s_reason = _storage_allowed(cfg, path, "read")
        if not ok_s:
            return False, None, "fs:denied_path"

        max_bytes = int(((cfg.get("fs") or {}).get("max_read_bytes")) or 2_000_000)
        want_b64 = bool(args.get("base64"))
        enc = str(args.get("encoding") or "utf-8")

        p = _norm_path(path)
        with open(p, "rb") as f:
            data = f.read(max_bytes + 1)
        truncated = len(data) > max_bytes
        if truncated:
            data = data[:max_bytes]

        if want_b64:
            return True, {"path": p, "base64": base64.b64encode(data).decode("ascii"), "truncated": truncated}, "ok"
        try:
            txt = data.decode(enc, "replace")
            return True, {"path": p, "text": txt, "truncated": truncated, "encoding": enc}, "ok"
        except Exception:
            return True, {"path": p, "base64": base64.b64encode(data).decode("ascii"), "truncated": truncated}, "ok_binary"
    except Exception as e:
        return False, {"error": str(e)}, "fs:read_error"


# === NoemaForge Autodoc Function Header ===
# Function: _fs_write(cfg: Dict[str, Any], stream: Dict[str, Any], args: Dict[str, Any])
# Purpose: Implement the routine ' fs write'.
# Inputs:
#   - cfg: Dict[str, Any]
#   - stream: Dict[str, Any]
#   - args: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - strip, _storage_allowed, int, str, bool, get, _norm_path, makedirs, _fs_allowed, dirname, b64decode, encode
# Returns / emits: Tuple[bool, Any, str]
# Side effects:
#   - creates directories
# Key locals:
#   - content, enc, f, fmode, max_bytes, mode, p, path, raw, want_b64
# === End NoemaForge Autodoc Function Header ===
def _fs_write(cfg: Dict[str, Any], stream: Dict[str, Any], args: Dict[str, Any]) -> Tuple[bool, Any, str]:
    try:
        path = str(args.get("path") or "").strip()
        if not path:
            return False, None, "fs:missing_path"
        if not _fs_allowed(stream, path, "write"):
            return False, None, "fs:denied_path"
        ok_s, _s_reason = _storage_allowed(cfg, path, "write")
        if not ok_s:
            return False, None, "fs:denied_path"

        max_bytes = int(((cfg.get("fs") or {}).get("max_write_bytes")) or 5_000_000)
        mode = str(args.get("mode") or "overwrite")
        enc = str(args.get("encoding") or "utf-8")
        want_b64 = bool(args.get("base64"))
        content = args.get("content")
        if content is None:
            return False, None, "fs:missing_content"

        p = _norm_path(path)
        os.makedirs(os.path.dirname(p), exist_ok=True)

        if want_b64:
            raw = base64.b64decode(str(content).encode("ascii"))
        else:
            raw = str(content).encode(enc)

        if len(raw) > max_bytes:
            return False, None, "fs:content_too_large"

        fmode = "ab" if mode == "append" else "wb"
        with open(p, fmode) as f:
            f.write(raw)
        return True, {"path": p, "bytes": len(raw), "mode": mode}, "ok"
    except Exception as e:
        return False, {"error": str(e)}, "fs:write_error"


# === NoemaForge Autodoc Function Header ===
# Function: _db_query(cfg: Dict[str, Any], stream: Dict[str, Any], args: Dict[str, Any])
# Purpose: Implement the routine ' db query'.
# Inputs:
#   - cfg: Dict[str, Any]
#   - stream: Dict[str, Any]
#   - args: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - strip, _storage_allowed, upper, connect, cursor, execute, fetchmany, close, get, _fs_allowed, rstrip, _norm_path
# Returns / emits: Tuple[bool, Any, str]
# Side effects:
#   - opens a database or socket connection
#   - executes SQL or shell-like commands
# Key locals:
#   - con, cur, db_path, out, params, rows, sql, up
# === End NoemaForge Autodoc Function Header ===
def _db_query(cfg: Dict[str, Any], stream: Dict[str, Any], args: Dict[str, Any]) -> Tuple[bool, Any, str]:
    import sqlite3

    try:
        db_path = str(args.get("db_path") or "").strip()
        sql = str(args.get("sql") or "").strip()
        params = args.get("params") or []
        if not db_path or not sql:
            return False, None, "db:missing_db_or_sql"
        if not _fs_allowed(stream, db_path, "read"):
            return False, None, "db:denied_db_path"
        ok_s, _s_reason = _storage_allowed(cfg, db_path, "read")
        if not ok_s:
            return False, None, "db:denied_db_path"

        # crude injection prevention: no multi-statement
        if ";" in sql.strip().rstrip(";"):
            return False, None, "db:multi_statement_denied"
        up = sql.lstrip().upper()
        if not (up.startswith("SELECT") or up.startswith("WITH") or up.startswith("PRAGMA")):
            return False, None, "db:query_only"

        con = sqlite3.connect(_norm_path(db_path))
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        cur.execute(sql, params)
        rows = cur.fetchmany(int(args.get("max_rows") or 200))
        out = [dict(r) for r in rows]
        con.close()
        return True, {"rows": out, "count": len(out)}, "ok"
    except Exception as e:
        return False, {"error": str(e)}, "db:query_error"


# === NoemaForge Autodoc Function Header ===
# Function: _db_write(cfg: Dict[str, Any], stream: Dict[str, Any], args: Dict[str, Any])
# Purpose: Implement the routine ' db write'.
# Inputs:
#   - cfg: Dict[str, Any]
#   - stream: Dict[str, Any]
#   - args: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - strip, _storage_allowed, connect, cursor, execute, commit, close, get, _fs_allowed, rstrip, _norm_path, str
# Returns / emits: Tuple[bool, Any, str]
# Side effects:
#   - opens a database or socket connection
#   - executes SQL or shell-like commands
# Key locals:
#   - con, cur, db_path, n, params, sql
# === End NoemaForge Autodoc Function Header ===
def _db_write(cfg: Dict[str, Any], stream: Dict[str, Any], args: Dict[str, Any]) -> Tuple[bool, Any, str]:
    import sqlite3

    try:
        db_path = str(args.get("db_path") or "").strip()
        sql = str(args.get("sql") or "").strip()
        params = args.get("params") or []
        if not db_path or not sql:
            return False, None, "db:missing_db_or_sql"
        if not _fs_allowed(stream, db_path, "write"):
            return False, None, "db:denied_db_path"
        ok_s, _s_reason = _storage_allowed(cfg, db_path, "write")
        if not ok_s:
            return False, None, "db:denied_db_path"

        if ";" in sql.strip().rstrip(";"):
            return False, None, "db:multi_statement_denied"

        con = sqlite3.connect(_norm_path(db_path))
        cur = con.cursor()
        cur.execute(sql, params)
        con.commit()
        n = cur.rowcount
        con.close()
        return True, {"rows_affected": n}, "ok"
    except Exception as e:
        return False, {"error": str(e)}, "db:write_error"


# === NoemaForge Autodoc Function Header ===
# Function: _exec_run(cfg: Dict[str, Any], sandbox_policy: Dict[str, Any], stream: Dict[str, Any], args: Dict[str, Any])
# Purpose: Sandboxed exec.run.
# Inputs:
#   - cfg: Dict[str, Any]
#   - sandbox_policy: Dict[str, Any]
#   - stream: Dict[str, Any]
#   - args: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - get, set, basename, strip, int, str, quota_from_policy, bool, isinstance, roots_from_allowlist_patterns, sandbox_run, microvm_available
# Returns / emits: Tuple[bool, Any, str]
# Side effects:
#   - spawns subprocesses or workers
# Key locals:
#   - action, allow_bins, allow_network, argv, bin0, bmeta, cwd, env, err, err_tr, exec_cfg, extra_env
# === End NoemaForge Autodoc Function Header ===
def _exec_run(cfg: Dict[str, Any], sandbox_policy: Dict[str, Any], stream: Dict[str, Any], args: Dict[str, Any]) -> Tuple[bool, Any, str]:
    """Sandboxed exec.run.

    v0.9.6: uses SandboxPolicy backends (bwrap/podman/host).
    """
    try:
        argv = args.get("argv")
        if not isinstance(argv, list) or not argv:
            return False, None, "exec:missing_argv"
        argv = [str(x) for x in argv]

        exec_cfg = cfg.get("exec") or {}
        allow_bins = set(exec_cfg.get("allow_bins") or ["python3", "bash", "ffmpeg", "git"])
        bin0 = os.path.basename(argv[0])
        if bin0 not in allow_bins:
            return False, {"bin": bin0}, "exec:bin_not_allowed"

        cwd = str(args.get("cwd") or "/workspace").strip()
        if not _fs_allowed(stream, cwd, "read") and not _fs_allowed(stream, cwd, "write"):
            return False, None, "exec:cwd_denied"

        # Output limits
        max_out = int(exec_cfg.get("max_stdout_bytes") or 200_000)
        max_err = int(exec_cfg.get("max_stderr_bytes") or 200_000)

        # Sandbox quotas
        quota_profile = str(args.get("quota_profile") or "exec_smoke")
        quota = quota_from_policy(sandbox_policy, quota_profile)

        # Action-level sandbox controls (Contract Epoch)
        action = (sandbox_policy.get("actions") or {}).get("exec.run") or {}
        allow_network = bool(action.get("allow_network", False))
        prefer_backends = action.get("backend_preference") or ((sandbox_policy.get("backends") or {}).get("preference") or ["bwrap", "podman", "host"])
        if bool(action.get("require_microvm", False)):
            ok_vm, reason = microvm_available(sandbox_policy)
            if not ok_vm:
                return False, {"backend": "microvm", "reason": reason}, "exec:microvm_unavailable"
            prefer_backends = ["microvm"]


        # Environment: minimal + explicit overrides
        env = {
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PYTHONNOUSERSITE": "1",
        }
        extra_env = args.get("env") or {}
        if isinstance(extra_env, dict):
            for k, v in extra_env.items():
                if not isinstance(k, str):
                    continue
                # Do not allow proxy env injection.
                if k.upper().startswith("HTTP_") or k.upper().startswith("HTTPS_") or k.upper() in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
                    continue
                env[k] = str(v)

        # Mount only stream allowlisted roots.
        ro_roots = roots_from_allowlist_patterns([str(x) for x in (stream.get("data_ro") or [])])
        rw_roots = roots_from_allowlist_patterns([str(x) for x in (stream.get("data_rw") or [])])
        # StoragePolicy (origin-only by default): do not mount foreign roots even if allowlisted by stream.
        try:
            pol_sp = _load_storage_policy(cfg)
            if pol_sp:
                ro_roots = [r for r in ro_roots if storage_broker.path_allowed(pol_sp, r, "read")[0]]
                rw_roots = [r for r in rw_roots if storage_broker.path_allowed(pol_sp, r, "write")[0]]
        except Exception:
            pass

        cmd_ok, res = sandbox_run(
            policy=sandbox_policy,
            argv=argv,
            cwd=_norm_path(cwd),
            env=env,
            quota=quota,
            ro_binds=ro_roots,
            rw_binds=rw_roots,
            allow_network=allow_network,
        )

        bmeta = (res.get("backend") or {})
        iso = str(bmeta.get("isolation") or "")
        if bool(bmeta.get("blocked")):
            # Host fallback blocked by SandboxPolicy -> treat as quarantine-worthy.
            return False, {"backend": bmeta, "stderr": res.get("stderr")}, "exec:degraded_sandbox"
        if iso in ("missing", "error"):
            return False, {"backend": bmeta, "stderr": res.get("stderr")}, "exec:error"

        # Truncate outputs
        out = (res.get("stdout") or "")
        err = (res.get("stderr") or "")
        out_tr = len(out.encode("utf-8", "replace")) > max_out
        err_tr = len(err.encode("utf-8", "replace")) > max_err
        if out_tr:
            out = out.encode("utf-8", "replace")[:max_out].decode("utf-8", "replace")
        if err_tr:
            err = err.encode("utf-8", "replace")[:max_err].decode("utf-8", "replace")

        return True, {
            "exit_code": int(res.get("exit_code") or 0),
            "command_ok": bool(cmd_ok),
            "stdout": out,
            "stderr": err,
            "truncated": {"stdout": out_tr, "stderr": err_tr},
            "backend": bmeta,
            "quota_profile": quota_profile,
        }, "ok"
    except Exception as e:
        return False, {"error": str(e)}, "exec:error"


# === NoemaForge Autodoc Function Header ===
# Function: _plugin_facade_or_args(cfg: Dict[str, Any], action: str, args: Dict[str, Any])
# Purpose: Provide local safe facades for selected bundle-backed actions and normalize plugin input where needed.
# Inputs:
#   - cfg: Dict[str, Any]
#   - action: str
#   - args: Dict[str, Any]
# Called by:
#   - src/toolproxy.py
# Returns / emits: Tuple[str, Dict[str, Any], str]
# === End NoemaForge Autodoc Function Header ===
def _plugin_facade_or_args(cfg: Dict[str, Any], action: str, args: Dict[str, Any]) -> Tuple[str, Dict[str, Any], str]:
    """Provide local facades and normalized plugin input where needed.

    Returns a tuple: (mode, payload, reason)
      - mode='local_result' -> payload is the final tool result to return directly
      - mode='plugin_args'  -> payload is the normalized args dict for plugin runner
      - mode='error'        -> payload contains details and reason explains the deny/error
      - mode='skip'         -> no special handling
    """
    action = str(action or "").strip()
    args = args if isinstance(args, dict) else {}

    if action.startswith("mcp.") and mcp_router is not None:
        cat_path = _epoch_contract_path(cfg, "mcp-adapters.yaml", str(cfg.get("mcp_adapters_path") or "/opt/noemaforge/configs/mcp-adapters.yaml"))
        return mcp_router.runtime_action(action, args, config_path=cat_path)

    if action in ("voice.capture", "voice.transcribe", "voice.capture_live", "voice.transcribe_live") and voice_ingest is not None:
        ok, payload, reason = voice_ingest.prepare_tool_action(action, args, policy_path=_load_voice_backends_policy_path(cfg))
        return ("local_result" if ok else "error"), payload, reason

    if action.startswith("lsp.") and lsp_facade is not None:
        ok, payload, reason = lsp_facade.prepare_tool_action(action, args)
        return ("local_result" if ok else "error"), payload, reason

    if action.startswith("discord.") and discord_bridge is not None:
        ok, payload, reason = discord_bridge.prepare_tool_action(action, args, policy_path=_load_discord_bridge_policy_path(cfg))
        return ("local_result" if ok else "error"), payload, reason

    if action == "voice.tts_backchannel" and tts_runtime is not None:
        ok, payload, reason = tts_runtime.prepare_tool_action(action, args, policy_path=_load_tts_backends_policy_path(cfg))
        return ("local_result" if ok else "error"), payload, reason

    if action in ("profiles.list", "profiles.set_enabled", "operator.status") and profile_manager is not None:
        base_dir = str(cfg.get("profiles_root") or "/opt/noemaforge/configs")
        try:
            if action == "profiles.list":
                return "local_result", profile_manager.list_profiles(base_dir), "ok"
            if action == "profiles.set_enabled":
                return "local_result", profile_manager.set_profile_enabled(base_dir, str(args.get("profile_id") or ""), bool(args.get("enabled", True))), "ok"
            return "local_result", profile_manager.operator_status_snapshot(base_dir), "ok"
        except Exception as e:
            return "error", {"error": repr(e)}, "profile_runtime_error"

    if action == "rss.intake" and rss_airlock is not None:
        try:
            payload = rss_airlock.intake_feed(
                url=str(args.get("url") or ""),
                epoch_dir=current_epoch_dir(str(cfg.get("contracts_root") or os.environ.get("NOEMAFORGE_CONTRACTS_ROOT") or "/var/lib/noemaforge/contracts")),
                actor={
                    "role": str(args.get("role") or "scary"),
                    "project_id": str(args.get("project_id") or ""),
                    "run_id": str(args.get("run_id") or ""),
                },
                trace_id=str(args.get("trace_id") or _nowz()),
                channel=str(args.get("channel") or "rss"),
            )
            return "local_result", payload, "ok"
        except Exception as e:
            return "error", {"error": repr(e)}, "rss_intake_failed"

    if action == "mail.intake" and email_airlock is not None:
        try:
            epol = _load_yaml(_load_email_airlock_policy_path(cfg)) if os.path.exists(_load_email_airlock_policy_path(cfg)) else {}
            if not bool(epol.get("enabled", False)) and not isinstance(args.get("policy_override"), dict):
                return "error", {"error": "email_airlock_disabled"}, "email_airlock_disabled"
            if str(args.get("path") or "").strip():
                payload = email_airlock.build_safe_summary(str(args.get("path") or ""), quarantine_root=str(epol.get("quarantine_root") or "/var/lib/noemaforge/quarantine/email"), summary_root=str(epol.get("summary_root") or "/workspace/outbox/email_safe"))
            else:
                payload = email_airlock.intake_maildir(str(args.get("maildir_root") or ""), quarantine_root=str(epol.get("quarantine_root") or "/var/lib/noemaforge/quarantine/email"), summary_root=str(epol.get("summary_root") or "/workspace/outbox/email_safe"))
            return "local_result", payload, "ok"
        except Exception as e:
            return "error", {"error": repr(e)}, "email_intake_failed"

    if action == "tg.bot.fetch" and tg_bot_runtime is not None:
        try:
            payload = tg_bot_runtime.fetch_updates(offset=int(args.get("offset") or 0), policy_path=_load_tg_bot_policy_path(cfg), policy_override=args.get("policy_override") if isinstance(args.get("policy_override"), dict) else None)
            out_dir = str((((args or {}).get("policy_override") or {}).get("outbox_dir") or "/workspace/outbox/tg_bot")) if isinstance((args or {}).get("policy_override"), dict) else ''
            if not out_dir:
                pol = tg_bot_runtime._load_policy(policy_path=_load_tg_bot_policy_path(cfg))
                out_dir = str(pol.get("outbox_dir") or "/workspace/outbox/tg_bot")
            normalized = tg_bot_runtime.ingest_updates(list(payload.get("result") or []), out_dir)
            return "local_result", {"fetch": payload, "normalized": normalized}, "ok"
        except Exception as e:
            return "error", {"error": repr(e)}, "tg_bot_fetch_failed"

    if action == "tg.channel.curate" and tg_channel_workflow is not None:
        try:
            payload = tg_channel_workflow.curate_channel(
                index_db=str(args.get("index_db") or ""),
                out_dir=str(args.get("out_dir") or "/workspace/outbox/tg_channel"),
                limit=int(args.get("limit") or 100),
            )
            return "local_result", payload, "ok"
        except Exception as e:
            return "error", {"error": repr(e)}, "tg_channel_curate_failed"

    if action == "readinglist.curate" and readinglist_workflow is not None:
        try:
            payload = readinglist_workflow.build_reading_queue(
                index_db=str(args.get("index_db") or ""),
                out_dir=str(args.get("out_dir") or "/workspace/outbox/readinglist"),
                limit=int(args.get("limit") or 100),
            )
            return "local_result", payload, "ok"
        except Exception as e:
            return "error", {"error": repr(e)}, "readinglist_curate_failed"

    if action == "selfdev.ics.import" and ics_import is not None:
        try:
            payload = ics_import.import_ics_file(
                path=str(args.get("path") or ""),
                out_dir=str(args.get("out_dir") or "/workspace/outbox/selfdev"),
            )
            return "local_result", payload, "ok"
        except Exception as e:
            return "error", {"error": repr(e)}, "selfdev_ics_import_failed"

    if action in ("selfdev.learning.ingest", "selfdev.learning.review") and selfdev_learning is not None:
        try:
            state_path = str(args.get("state_path") or "/workspace/outbox/selfdev/learning_state.json")
            payload = {}
            if action == "selfdev.learning.ingest":
                payload = selfdev_learning.ingest_learning_items(in_dir=str(args.get("in_dir") or ""), state_path=state_path)
                if str(args.get("ics_path") or "").strip() and ics_import is not None:
                    imported = ics_import.import_ics_file(path=str(args.get("ics_path") or ""), out_dir=str(args.get("out_dir") or "/workspace/outbox/selfdev"))
                    payload["calendar_merge"] = selfdev_learning.merge_calendar_events(state_path=state_path, events=list(imported.get("events") or []))
                return "local_result", payload, "ok"
            payload = selfdev_learning.build_review_queue(state_path=state_path, out_dir=str(args.get("out_dir") or "/workspace/outbox/selfdev"))
            return "local_result", payload, "ok"
        except Exception as e:
            return "error", {"error": repr(e)}, "selfdev_learning_failed"

    return "skip", args, "ok"


# === NoemaForge Autodoc Function Header ===
# Function: _plugin_run(cfg: Dict[str, Any], sandbox_policy: Dict[str, Any], stream: Dict[str, Any], tool_entry: Dict[str, Any], args: Dict[str, Any])
# Purpose: Run a ToolVault plugin (bundle-attested) under SandboxPolicy.
# Inputs:
#   - cfg: Dict[str, Any]
#   - sandbox_policy: Dict[str, Any]
#   - stream: Dict[str, Any]
#   - tool_entry: Dict[str, Any]
#   - args: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _load_supplychain_policy, run_plugin, str
# Returns / emits: Tuple[bool, Any, str]
# Side effects:
#   - spawns subprocesses or workers
# Key locals:
#   - sc_pol
# === End NoemaForge Autodoc Function Header ===
def _plugin_run(cfg: Dict[str, Any], sandbox_policy: Dict[str, Any], stream: Dict[str, Any], tool_entry: Dict[str, Any], args: Dict[str, Any]) -> Tuple[bool, Any, str]:
    """Run a ToolVault plugin (bundle-attested) under SandboxPolicy."""
    try:
        sc_pol = _load_supplychain_policy(cfg)
        return run_plugin(
            toolproxy_cfg=cfg,
            sandbox_policy=sandbox_policy,
            supplychain_policy=sc_pol,
            stream_cfg=stream,
            tool_entry=tool_entry,
            args=args,
        )
    except Exception as e:
        return False, {"error": str(e)}, "plugin:error"


# === NoemaForge Autodoc Function Header ===
# Function: _glove_analyze(cfg: Dict[str, Any], sandbox_policy: Dict[str, Any], qpol: Dict[str, Any], actor: Dict[str, Any], args: Dict[str, Any])
# Purpose: Run one-shot glove analysis for a quarantine incident.
# Inputs:
#   - cfg: Dict[str, Any]
#   - sandbox_policy: Dict[str, Any]
#   - qpol: Dict[str, Any]
#   - actor: Dict[str, Any]
#   - args: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - strip, str, _norm_path, run_glove, join, isdir, bool, get, commonpath
# Returns / emits: Tuple[bool, Any, str]
# Side effects:
#   - spawns subprocesses or workers
# Key locals:
#   - idir, incident_id, langs, profile, qroot
# === End NoemaForge Autodoc Function Header ===
def _glove_analyze(cfg: Dict[str, Any], sandbox_policy: Dict[str, Any], qpol: Dict[str, Any], actor: Dict[str, Any], args: Dict[str, Any]) -> Tuple[bool, Any, str]:
    """Run one-shot glove analysis for a quarantine incident.

    Only privileged roles should be allowed this tool via ToolPolicy.
    """
    try:
        incident_id = str(args.get("incident_id") or "").strip()
        if not incident_id:
            return False, None, "glove:missing_incident_id"

        qroot = str(((qpol.get("paths") or {}).get("quarantine_root")) or "/var/lib/noemaforge/quarantine/incidents")
        idir = _norm_path(os.path.join(qroot, incident_id))

        # Path safety: ensure idir is inside qroot
        try:
            if os.path.commonpath([idir, _norm_path(qroot)]) != _norm_path(qroot):
                return False, {"incident_dir": idir}, "glove:bad_path"
        except Exception:
            return False, {"incident_dir": idir}, "glove:bad_path"

        if not os.path.isdir(idir):
            return False, {"incident_dir": idir}, "glove:incident_not_found"

        if not bool((qpol.get("gloves") or {}).get("enabled", True)):
            return False, None, "glove:disabled_by_policy"

        # Default languages from quarantine policy (preferred), then sandbox policy.
        langs = str(args.get("languages") or "").strip()
        if not langs:
            langs = "ru,en,de,zh"
            try:
                langs = str((((qpol.get("gloves") or {}).get("default_languages")) or langs))
            except Exception:
                pass
            try:
                langs = str((((sandbox_policy.get("actions") or {}).get("glove.analyze") or {}).get("languages")) or langs)
            except Exception:
                pass

        profile = str(args.get("profile") or "generic").strip() or "generic"
        ok2, res = run_glove(sandbox_policy=sandbox_policy, incident_dir=idir, profile=profile, languages=langs)
        return bool(ok2), res, "ok" if ok2 else "glove:error"
    except Exception as e:
        return False, {"error": str(e)}, "glove:error"



# === NoemaForge Autodoc Function Header ===
# Function: _vstore_config(cfg: Dict[str, Any])
# Purpose: Implement the routine ' vstore config'.
# Inputs:
#   - cfg: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - VStoreConfig, get, str, int
# Returns / emits: VStoreConfig
# Key locals:
#   - vcfg
# === End NoemaForge Autodoc Function Header ===
def _vstore_config(cfg: Dict[str, Any]) -> VStoreConfig:
    vcfg = cfg.get("vstore") or {}
    return VStoreConfig(
        backend=str(vcfg.get("backend") or "flat"),
        metric=str(vcfg.get("metric") or "cosine"),
        max_items_per_segment=int(vcfg.get("max_items_per_segment") or 50000),
        base_dir=str(vcfg.get("base_dir") or "/var/lib/noemaforge/vstore"),
    )


# === NoemaForge Autodoc Function Header ===
# Function: _vstore_upsert(cfg: Dict[str, Any], args: Dict[str, Any])
# Purpose: Implement the routine ' vstore upsert'.
# Inputs:
#   - cfg: Dict[str, Any]
#   - args: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - strip, VStore, upsert_many, get, isinstance, _vstore_config, str
# Returns / emits: Tuple[bool, Any, str]
# Key locals:
#   - items, layer, res, store
# === End NoemaForge Autodoc Function Header ===
def _vstore_upsert(cfg: Dict[str, Any], args: Dict[str, Any]) -> Tuple[bool, Any, str]:
    try:
        layer = str(args.get("layer") or "").strip()
        items = args.get("items") or []
        if not layer:
            return False, None, "vstore:missing_layer"
        if not isinstance(items, list):
            return False, None, "vstore:items_not_list"
        store = VStore(layer, _vstore_config(cfg))
        res = store.upsert_many(items)
        return True, res, "ok"
    except Exception as e:
        return False, {"error": str(e)}, "vstore:upsert_error"


# === NoemaForge Autodoc Function Header ===
# Function: _vstore_query(cfg: Dict[str, Any], args: Dict[str, Any])
# Purpose: Implement the routine ' vstore query'.
# Inputs:
#   - cfg: Dict[str, Any]
#   - args: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - strip, get, int, VStore, query, len, _vstore_config, str, isinstance
# Returns / emits: Tuple[bool, Any, str]
# Key locals:
#   - dims, filters, layer, model_id, res, store, top_k, vector
# === End NoemaForge Autodoc Function Header ===
def _vstore_query(cfg: Dict[str, Any], args: Dict[str, Any]) -> Tuple[bool, Any, str]:
    try:
        layer = str(args.get("layer") or "").strip()
        vector = args.get("vector")
        dims = int(args.get("dims") or 0)
        model_id = str(args.get("model_id") or "").strip()
        top_k = int(args.get("top_k") or 10)
        filters = args.get("filters") or {}
        if not layer:
            return False, None, "vstore:missing_layer"
        if not isinstance(vector, list) or not vector:
            return False, None, "vstore:missing_vector"
        if dims <= 0:
            dims = len(vector)
        if not model_id:
            return False, None, "vstore:missing_model_id"
        store = VStore(layer, _vstore_config(cfg))
        res = store.query(vector=vector, dims=dims, model_id=model_id, top_k=top_k, filters=filters)
        return True, res, "ok"
    except Exception as e:
        return False, {"error": str(e)}, "vstore:query_error"


# === NoemaForge Autodoc Function Header ===
# Function: _vstore_tombstone(cfg: Dict[str, Any], args: Dict[str, Any])
# Purpose: Implement the routine ' vstore tombstone'.
# Inputs:
#   - cfg: Dict[str, Any]
#   - args: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - strip, VStore, tombstone, get, isinstance, _vstore_config, str
# Returns / emits: Tuple[bool, Any, str]
# Key locals:
#   - entry_ids, layer, res, store
# === End NoemaForge Autodoc Function Header ===
def _vstore_tombstone(cfg: Dict[str, Any], args: Dict[str, Any]) -> Tuple[bool, Any, str]:
    try:
        layer = str(args.get("layer") or "").strip()
        entry_ids = args.get("entry_ids") or []
        if not layer:
            return False, None, "vstore:missing_layer"
        if not isinstance(entry_ids, list):
            return False, None, "vstore:entry_ids_not_list"
        store = VStore(layer, _vstore_config(cfg))
        res = store.tombstone([str(x) for x in entry_ids])
        return True, res, "ok"
    except Exception as e:
        return False, {"error": str(e)}, "vstore:tombstone_error"


# --- Roadmap tools (v0.9.5) -----------------------------------------------

# === NoemaForge Autodoc Function Header ===
# Function: _roadmap_record(cfg: Dict[str, Any], actor: Dict[str, Any], args: Dict[str, Any])
# Purpose: Record a roadmap signal (e.g., repeated architect request).
# Inputs:
#   - cfg: Dict[str, Any]
#   - actor: Dict[str, Any]
#   - args: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - strip, record_signal, str, get
# Returns / emits: Tuple[bool, Any, str]
# Key locals:
#   - description, key, process_id, requested_by, sig, target_role, title
# === End NoemaForge Autodoc Function Header ===
def _roadmap_record(cfg: Dict[str, Any], actor: Dict[str, Any], args: Dict[str, Any]) -> Tuple[bool, Any, str]:
    """Record a roadmap signal (e.g., repeated architect request)."""
    try:
        target_role = str(args.get("target_role") or "solution_architect").strip()
        key = str(args.get("key") or "").strip()
        title = str(args.get("title") or "").strip()
        description = str(args.get("description") or "").strip()
        process_id = str(args.get("process_id") or "").strip()

        requested_by = {
            "stream_id": actor.get("stream_id") or "unknown",
            "role": actor.get("role") or "unknown",
            "project_id": actor.get("project_id") or "",
            "run_id": actor.get("run_id") or "",
            "process_id": process_id or "",
        }
        sig = record_signal(
            target_role=target_role,
            key=key,
            title=title,
            description=description,
            requested_by=requested_by,
        )
        return True, sig, "ok"
    except Exception as e:
        return False, {"error": str(e)}, "roadmap:record_error"


# === NoemaForge Autodoc Function Header ===
# Function: _roadmap_list(cfg: Dict[str, Any], epoch_dir: str, args: Dict[str, Any])
# Purpose: List prioritized roadmap items.
# Inputs:
#   - cfg: Dict[str, Any]
#   - epoch_dir: str
#   - args: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - int, roadmap_list_items, strip, get, str
# Returns / emits: Tuple[bool, Any, str]
# Key locals:
#   - limit, out, target_role
# === End NoemaForge Autodoc Function Header ===
def _roadmap_list(cfg: Dict[str, Any], epoch_dir: str, args: Dict[str, Any]) -> Tuple[bool, Any, str]:
    """List prioritized roadmap items."""
    try:
        target_role = str(args.get("target_role") or "").strip() or None
        limit = int(args.get("limit") or 50)
        out = roadmap_list_items(epoch_dir=epoch_dir, target_role=target_role, limit=limit)
        return True, out, "ok"
    except Exception as e:
        return False, {"error": str(e)}, "roadmap:list_error"


# === NoemaForge Autodoc Function Header ===
# Function: _roadmap_export(cfg: Dict[str, Any], epoch_dir: str, args: Dict[str, Any])
# Purpose: Export a roadmap report artifact for Surgeon/SR/SSR.
# Inputs:
#   - cfg: Dict[str, Any]
#   - epoch_dir: str
#   - args: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - bool, int, roadmap_export_report, strip, get, str
# Returns / emits: Tuple[bool, Any, str]
# Key locals:
#   - include_role_roadmaps, limit, res, target_role
# === End NoemaForge Autodoc Function Header ===
def _roadmap_export(cfg: Dict[str, Any], epoch_dir: str, args: Dict[str, Any]) -> Tuple[bool, Any, str]:
    """Export a roadmap report artifact for Surgeon/SR/SSR."""
    try:
        target_role = str(args.get("target_role") or "").strip() or None
        include_role_roadmaps = bool(args.get("include_role_roadmaps", True))
        limit = int(args.get("limit") or 100)
        res = roadmap_export_report(
            epoch_dir=epoch_dir,
            target_role=target_role,
            include_role_roadmaps=include_role_roadmaps,
            limit=limit,
        )
        return True, res, "ok"
    except Exception as e:
        return False, {"error": str(e)}, "roadmap:export_error"



# socketserver.UnixStreamServer is Unix-only. Off Unix the class still needs to
# *define* so the module imports and the test suite collects; the AF_UNIX gateway is
# started only on the Linux target (guarded at the call site below), so a harmless
# concrete fallback base keeps import-safety without changing Unix behaviour.
# The capability is captured once at import so the class base and the runtime guard
# always agree, even if socketserver.UnixStreamServer is injected later (e.g. a stub).
_HAS_UNIX_STREAM_SERVER = hasattr(socketserver, "UnixStreamServer")
_UnixStreamServerBase = socketserver.UnixStreamServer if _HAS_UNIX_STREAM_SERVER else socketserver.TCPServer


class ThreadedUnixServer(socketserver.ThreadingMixIn, _UnixStreamServerBase):
    daemon_threads = True


class Handler(socketserver.BaseRequestHandler):
    # === NoemaForge Autodoc Function Header ===
    # Function: handle(self)
    # Purpose: Implement the routine 'handle'.
    # Inputs:
    #   - self
    # Called by:
    #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
    # Calls:
    #   - int, str, _epoch_contract_path, bool, get, recv, uuid4, loads, _load_quarantine_policy, _load_role_affirmations, _load_sandbox_policy, verify_token
    # Returns / emits: None
    # Key locals:
    #   - action, actor, aff, aff_txt, allow_explicit, ar, areas, args, args2, bind_meta, candidates, cap_pol
    # === End NoemaForge Autodoc Function Header ===
    def handle(self) -> None:
        cfg = self.server.cfg  # type: ignore[attr-defined]
        limits = cfg.get("limits", {}) or {}
        max_req = int(limits.get("max_request_bytes", 1_048_576))
        tokens_dir = str(cfg.get("tokens_dir") or "/var/lib/noemaforge/.sys/cap_tokens")

        # Load stream/policy/registry per request (simple + robust for MVP).
        streams_path = _epoch_contract_path(cfg, "streams.yaml", str(cfg.get("streams_config_path") or "/opt/noemaforge/configs/streams.yaml"))
        reg_path = _epoch_contract_path(cfg, "tool-registry.yaml", str(cfg.get("tool_registry_path") or "/opt/noemaforge/configs/tool-registry.yaml"))
        pol_path = _epoch_contract_path(cfg, "tool-policy.yaml", str(cfg.get("tool_policy_path") or "/opt/noemaforge/configs/tool-policy.yaml"))

        enforcement = cfg.get("enforcement") or {}
        require_stream = bool(enforcement.get("require_stream_id", True))
        bind_meta = bool(enforcement.get("enforce_issued_to_match_meta", True))

        # Read all (single request per connection)
        raw = b""
        while True:
            chunk = self.request.recv(4096)
            if not chunk:
                break
            raw += chunk
            if len(raw) > max_req:
                break

        trace_id = str(uuid.uuid4())
        try:
            if len(raw) > max_req:
                raise ValueError("request_too_large")
            req = json.loads(raw.decode("utf-8"))
            trace_id = str(((req.get("meta") or {}).get("trace_id")) or trace_id)

            token = str(req.get("token") or "")
            action = str(req.get("action") or "")
            args = req.get("args") or {}
            meta = req.get("meta") or {}

            role = str(meta.get("role") or "")
            project_id = str(meta.get("project_id") or "")
            run_id = str(meta.get("run_id") or "")
            stream_id = str(meta.get("stream_id") or "")

            actor = {
                "subsystem": "toolproxy",
                "role": role,
                "project_id": project_id,
                "run_id": run_id,
                "stream_id": stream_id,
            }

            # Security policy (epoch-scoped): quarantine + redaction.
            qpol = _load_quarantine_policy(cfg)
            aff = _load_role_affirmations(cfg)
            spol = _load_sandbox_policy(cfg)

            # === NoemaForge Autodoc Function Header ===
            # Function: _respond_deny(reason: str)
            # Purpose: Implement the routine ' respond deny'.
            # Inputs:
            #   - reason: str
            # Called by:
            #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
            # Calls:
            #   - _should_quarantine_on_deny, _evt, _user_error, _send, create_incident, str, incident_open, strip, get, split
            # Returns / emits: None
            # Side effects:
            #   - reads or writes files
            #   - sends a response or network payload
            # Key locals:
            #   - dedupe, reason_key, resp, src_role, src_stream
            # === End NoemaForge Autodoc Function Header ===
            def _respond_deny(reason: str) -> None:
                # Quarantine certain denies (high-signal).
                if _should_quarantine_on_deny(qpol, reason):
                    qid, qdir, _ = create_incident(policy=qpol, actor=actor, trace_id=trace_id, action=action, reason=reason, request_obj=req, incident_kind="toolproxy_quarantine", incident_severity="S2")
                    _evt("S2", "TOOLPROXY_QUARANTINE", actor, "quarantine", trace_id, {"reason": reason, "action": action, "incident_id": qid})
                    user_err, dbg = _user_error(qpol, role, "quarantine", reason)
                    resp = {"ok": False, "trace_id": trace_id, "error": user_err, "error_class": "quarantine", "quarantine_id": qid}
                    if dbg:
                        resp["code"] = dbg
                    self._send(resp)
                    return

                _evt("S2", "TOOLPROXY_DENY", actor, "deny", trace_id, {"reason": reason, "action": action})
                # Promote deny to Incident (lifecycle) for repeat tracking.
                try:
                    src_stream = str(actor.get("stream_id") or "unknown")
                    src_role = str(actor.get("role") or "unknown")
                    reason_key = str(reason).split(":")[0].strip() or "deny"
                    dedupe = f"toolproxy_deny:{action}:{reason_key}:{src_stream}:{src_role}"
                    incident_open(
                        kind="toolproxy_deny",
                        severity="S1",
                        title=f"ToolProxy deny: {action}",
                        details={"trace_id": trace_id, "action": action, "reason": reason_key},
                        source=actor,
                        tags=["toolproxy", "deny"],
                        artifacts={},
                        dedupe_key=dedupe,
                    )
                except Exception:
                    pass

                user_err, dbg = _user_error(qpol, role, "deny", reason)
                resp = {"ok": False, "trace_id": trace_id, "error": user_err, "error_class": "deny"}
                if dbg:
                    resp["code"] = dbg
                self._send(resp)

            # === NoemaForge Autodoc Function Header ===
            # Function: _respond_quarantine(reason: str)
            # Purpose: Implement the routine ' respond quarantine'.
            # Inputs:
            #   - reason: str
            # Called by:
            #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
            # Calls:
            #   - create_incident, _evt, _user_error, _send
            # Returns / emits: None
            # Side effects:
            #   - sends a response or network payload
            # Key locals:
            #   - resp
            # === End NoemaForge Autodoc Function Header ===
            def _respond_quarantine(reason: str) -> None:
                qid, qdir, _ = create_incident(policy=qpol, actor=actor, trace_id=trace_id, action=action, reason=reason, request_obj=req, incident_kind="toolproxy_quarantine", incident_severity="S2")
                _evt("S2", "TOOLPROXY_QUARANTINE", actor, "quarantine", trace_id, {"reason": reason, "action": action, "incident_id": qid})
                user_err, dbg = _user_error(qpol, role, "quarantine", reason)
                resp = {"ok": False, "trace_id": trace_id, "error": user_err, "error_class": "quarantine", "quarantine_id": qid}
                if dbg:
                    resp["code"] = dbg
                self._send(resp)

            # === NoemaForge Autodoc Function Header ===
            # Function: _respond_error(reason: str, result = None)
            # Purpose: Implement the routine ' respond error'.
            # Inputs:
            #   - reason: str
            #   - result = None
            # Called by:
            #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
            # Calls:
            #   - _evt, _user_error, _send
            # Returns / emits: None
            # Side effects:
            #   - sends a response or network payload
            # Key locals:
            #   - resp
            # === End NoemaForge Autodoc Function Header ===
            def _respond_error(reason: str, result: Any = None) -> None:
                _evt("S2", "TOOLPROXY_ERROR", actor, "error", trace_id, {"reason": reason, "action": action})
                user_err, dbg = _user_error(qpol, role, "error", reason)
                resp: Dict[str, Any] = {"ok": False, "trace_id": trace_id, "error": user_err, "error_class": "error"}
                if dbg:
                    resp["code"] = dbg
                    resp["result"] = result
                self._send(resp)

            if require_stream and not stream_id:
                _respond_deny("missing_stream_id")
                return

            ok, rec, reason = verify_token(tokens_dir, token)
            if not ok or not rec:
                _respond_deny(str(reason))
                return


            # Epoch binding: tokens are valid only inside the current contract epoch.
            cur_epoch = current_epoch_id(str(cfg.get("contracts_root") or os.environ.get("NOEMAFORGE_CONTRACTS_ROOT") or "/var/lib/noemaforge/contracts"))
            tok_epoch = str(rec.get("epoch_id") or "00000")
            if tok_epoch != cur_epoch:
                _respond_deny("epoch_mismatch")
                return

            # Optional: bind token record to meta
            if bind_meta:
                issued_to = rec.get("issued_to") or {}
                if str(issued_to.get("run_id") or "") != run_id or str(issued_to.get("role") or "") != role or str(issued_to.get("project_id") or "") != project_id:
                    _respond_deny("issued_to_mismatch")
                    return

            # Capability token allows action?
            if not _cap_allows(rec, action):
                _respond_deny("cap_missing")
                return

            # Stream exists?
            try:
                cat = _load_yaml(streams_path)
            except Exception:
                cat = {}
            if stream_id and not _stream_exists(cat, stream_id):
                _respond_deny("unknown_stream")
                return

            stream_cfg = _stream_cfg(cat, stream_id) if stream_id else {}

            # Tool registry + enabled?
            try:
                reg = _load_yaml(reg_path)
            except Exception:
                reg = {}
            reg_map = _registry_map(reg)
            ok_tool, tool_reason = _tool_enabled(reg_map, action)
            if not ok_tool:
                _respond_deny(str(tool_reason))
                return

            tool_entry = reg_map.get(action) if isinstance(reg_map.get(action), dict) else {}

            # Tool policy allowlist?
            try:
                pol = _load_yaml(pol_path)
            except Exception:
                pol = {}
            if not _policy_allows(pol, stream_id, role, action):
                _respond_deny("policy_deny")
                return

            # Arg-rule quarantine before execution (keeps protocol details off the executor).
            ar = _arg_rule_decision(qpol, action, args)
            if ar is not None:
                decision, why = ar
                if decision == "deny":
                    _respond_deny(why)
                    return
                _respond_quarantine(why)
                return

            # Execute
            if action == "llm.chat":
                ok_req, prepared_args, rr = _prepare_llm_chat_request(cfg, aff, args, stream_id, role, actor, trace_id)
                if not ok_req:
                    _respond_deny(rr)
                    return

                t0 = time.time()
                ok2, result, r = _llm_chat(cfg, prepared_args)
                elapsed_ms = int((time.time() - t0) * 1000)
                if telemetry is not None:
                    try:
                        telemetry.record_llm_call(
                            actor=actor,
                            trace_id=trace_id,
                            action="llm.chat",
                            request_payload=prepared_args,
                            ok=bool(ok2),
                            result=result,
                            reason=str(r or ""),
                            elapsed_ms=elapsed_ms,
                        )
                    except Exception:
                        pass
                if ok2:
                    assistant_text = ""
                    try:
                        if isinstance(result, dict):
                            ch = result.get("choices")
                            if isinstance(ch, list) and ch:
                                msg0 = ch[0].get("message") if isinstance(ch[0], dict) else {}
                                assistant_text = str((msg0 or {}).get("content") or "")
                    except Exception:
                        assistant_text = ""
                    hk_post = _scan_for_honeykey_leak(cfg, assistant_text)
                    if bool(hk_post.get("hit")) and bool(hk_post.get("quarantine", True)):
                        _respond_quarantine("honeykey_leak_detected")
                        return
                    _evt("S1", "TOOLPROXY_ALLOW", actor, "allow", trace_id, {"action": action, "model": str(prepared_args.get("model") or "")})
                    self._send({"ok": True, "trace_id": trace_id, "result": result})
                else:
                    _respond_error(r, result)
                return

            if action == "llm.embed":
                # Same routing logic as llm.chat (capability = embed).
                try:
                    rmp = _load_role_model_policy(cfg)
                    tmp = _load_team_model_policy(cfg)
                    reg_doc = model_router.load_model_registry(str(cfg.get("model_registry_path") or "/var/lib/modelstore/model_registry.json"))
                    scorecards_dir = str(cfg.get("model_scorecards_dir") or "/var/lib/noemaforge/model_scorecards")

                    cap_pol = model_router.resolve_cap_policy(policy_doc=rmp, stream_id=stream_id, role=role, cap="embed")
                    fallback = str(cap_pol.get("fallback_model") or "main")
                    min_trust = str(cap_pol.get("min_trust") or "unknown")
                    require_scorecard = bool(cap_pol.get("require_scorecard") or False)
                    allow_explicit = bool(cap_pol.get("allow_explicit") or False)
                    candidates = [str(x).strip() for x in (cap_pol.get("candidates") or []) if str(x).strip()]
                    if not candidates:
                        candidates = [fallback]

                    requested = str(args.get("model") or "").strip()
                    if requested:
                        if not allow_explicit and requested not in set(candidates + [fallback]):
                            _respond_deny("model_not_allowed")
                            return
                        tmp_policy = {
                            "defaults": {"embed": {"fallback_model": fallback, "min_trust": min_trust, "require_scorecard": require_scorecard}},
                            "roles": {"*/*": {"embed": {"candidates": [requested], "min_trust": min_trust, "require_scorecard": False}}},
                        }
                        picked, _ = model_router.select_model(
                            action="llm.embed",
                            stream_id=stream_id,
                            role=role,
                            policy_doc=tmp_policy,
                            registry_doc=reg_doc,
                            scorecards_dir=scorecards_dir,
                            team_policy_doc=None,
                        )
                        if picked != requested:
                            _respond_deny("model_trust_or_registry_reject")
                            return
                    else:
                        picked, explain = model_router.select_model(
                            action="llm.embed",
                            stream_id=stream_id,
                            role=role,
                            policy_doc=rmp,
                            registry_doc=reg_doc,
                            scorecards_dir=scorecards_dir,
                            team_policy_doc=tmp,
                        )
                        args = dict(args)
                        args["model"] = picked
                        _evt("S0", "MODEL_ROUTE", actor, "allow", trace_id, {"action": action, "model": picked, "explain": explain})
                except Exception:
                    if not str(args.get("model") or "").strip():
                        args = dict(args)
                        args["model"] = "main"

                t0 = time.time()
                ok2, result, r = _llm_embed(cfg, args)
                elapsed_ms = int((time.time() - t0) * 1000)
                if telemetry is not None:
                    try:
                        telemetry.record_llm_call(
                            actor=actor,
                            trace_id=trace_id,
                            action="llm.embed",
                            request_payload=args,
                            ok=bool(ok2),
                            result=result,
                            reason=str(r or ""),
                            elapsed_ms=elapsed_ms,
                        )
                    except Exception:
                        pass
                if ok2:
                    _evt("S1", "TOOLPROXY_ALLOW", actor, "allow", trace_id, {"action": action, "model": str(args.get("model") or "")})
                    self._send({"ok": True, "trace_id": trace_id, "result": result})
                else:
                    _respond_error(r, result)
                return

            if action == "voice.chat_turn":
                ok2, result, r = _voice_chat_turn(cfg, aff, pol, cat, actor, trace_id, args)
                if ok2:
                    _evt("S1", "TOOLPROXY_ALLOW", actor, "allow", trace_id, {"action": action, "handler": "voice_chat"})
                    self._send({"ok": True, "trace_id": trace_id, "result": result})
                else:
                    if str(r).endswith("_error") or str(r).endswith("_failed") or str(r).startswith("llm_gateway_"):
                        _respond_error(r, result)
                    else:
                        _respond_deny(r)
                return

            if action == "voice.chat_roundtrip":
                ok2, result, r = _voice_chat_roundtrip(cfg, aff, pol, cat, actor, trace_id, args)
                if ok2:
                    _evt("S1", "TOOLPROXY_ALLOW", actor, "allow", trace_id, {"action": action, "handler": "voice_roundtrip"})
                    self._send({"ok": True, "trace_id": trace_id, "result": result})
                else:
                    if str(r).endswith("_error") or str(r).endswith("_failed") or str(r).startswith("llm_gateway_"):
                        _respond_error(r, result)
                    else:
                        _respond_deny(r)
                return

            if action == "fs.read":
                ok2, result, r = _fs_read(cfg, stream_cfg, args)
                if ok2:
                    _evt("S1", "TOOLPROXY_ALLOW", actor, "allow", trace_id, {"action": action})
                    self._send({"ok": True, "trace_id": trace_id, "result": result})
                else:
                    if str(r).endswith("_error"):
                        _respond_error(r, result)
                    else:
                        _respond_deny(r)
                return

            if action == "fs.write":
                ok2, result, r = _fs_write(cfg, stream_cfg, args)
                if ok2:
                    _evt("S1", "TOOLPROXY_ALLOW", actor, "allow", trace_id, {"action": action})
                    self._send({"ok": True, "trace_id": trace_id, "result": result})
                else:
                    if str(r).endswith("_error"):
                        _respond_error(r, result)
                    else:
                        _respond_deny(r)
                return

            if action == "db.query":
                ok2, result, r = _db_query(cfg, stream_cfg, args)
                if ok2:
                    _evt("S1", "TOOLPROXY_ALLOW", actor, "allow", trace_id, {"action": action})
                    self._send({"ok": True, "trace_id": trace_id, "result": result})
                else:
                    if str(r).endswith("_error"):
                        _respond_error(r, result)
                    else:
                        _respond_deny(r)
                return

            if action == "db.write":
                ok2, result, r = _db_write(cfg, stream_cfg, args)
                if ok2:
                    _evt("S1", "TOOLPROXY_ALLOW", actor, "allow", trace_id, {"action": action})
                    self._send({"ok": True, "trace_id": trace_id, "result": result})
                else:
                    if str(r).endswith("_error"):
                        _respond_error(r, result)
                    else:
                        _respond_deny(r)
                return

            if action == "exec.run":
                ok2, result, r = _exec_run(cfg, spol, stream_cfg, args)
                if ok2:
                    _evt("S1", "TOOLPROXY_ALLOW", actor, "allow", trace_id, {"action": action})
                    self._send({"ok": True, "trace_id": trace_id, "result": result})
                else:
                    if str(r).endswith("_error") or str(r).startswith("exec:error") or str(r) == "exec:timeout":
                        _respond_error(r, result)
                    else:
                        _respond_deny(r)
                return

            if action == "glove.analyze":
                ok2, result, r = _glove_analyze(cfg, spol, qpol, actor, args)
                if ok2:
                    _evt("S1", "TOOLPROXY_ALLOW", actor, "allow", trace_id, {"action": action})
                    self._send({"ok": True, "trace_id": trace_id, "result": result})
                else:
                    _respond_error(r, result)
                return

            if action == "glove.web_sanitize":
                args2 = dict(args)
                args2["profile"] = "web_sanitize"
                ok2, result, r = _glove_analyze(cfg, spol, qpol, actor, args2)
                if ok2:
                    _evt("S1", "TOOLPROXY_ALLOW", actor, "allow", trace_id, {"action": action})
                    self._send({"ok": True, "trace_id": trace_id, "result": result})
                else:
                    _respond_error(r, result)
                return

            if action == "glove.net_inspect":
                args2 = dict(args)
                args2["profile"] = "net_inspect"
                ok2, result, r = _glove_analyze(cfg, spol, qpol, actor, args2)
                if ok2:
                    _evt("S1", "TOOLPROXY_ALLOW", actor, "allow", trace_id, {"action": action})
                    self._send({"ok": True, "trace_id": trace_id, "result": result})
                else:
                    _respond_error(r, result)
                return



            if action == "glove.rss_sanitize":
                args2 = dict(args)
                args2["profile"] = "rss_sanitize"
                ok2, result, r = _glove_analyze(cfg, spol, qpol, actor, args2)
                if ok2:
                    _evt("S1", "TOOLPROXY_ALLOW", actor, "allow", trace_id, {"action": action})
                    self._send({"ok": True, "trace_id": trace_id, "result": result})
                else:
                    _respond_error(r, result)
                return

            if action == "glove.package_inspect":
                args2 = dict(args)
                args2["profile"] = "package_inspect"
                ok2, result, r = _glove_analyze(cfg, spol, qpol, actor, args2)
                if ok2:
                    _evt("S1", "TOOLPROXY_ALLOW", actor, "allow", trace_id, {"action": action})
                    self._send({"ok": True, "trace_id": trace_id, "result": result})
                else:
                    _respond_error(r, result)
                return

            if action == "glove.git_scan":
                args2 = dict(args)
                args2["profile"] = "git_scan"
                ok2, result, r = _glove_analyze(cfg, spol, qpol, actor, args2)
                if ok2:
                    _evt("S1", "TOOLPROXY_ALLOW", actor, "allow", trace_id, {"action": action})
                    self._send({"ok": True, "trace_id": trace_id, "result": result})
                else:
                    _respond_error(r, result)
                return
            if action == "vstore.query":
                ok2, result, r = _vstore_query(cfg, args)
                if ok2:
                    _evt("S1", "TOOLPROXY_ALLOW", actor, "allow", trace_id, {"action": action})
                    self._send({"ok": True, "trace_id": trace_id, "result": result})
                else:
                    _respond_error(r, result)
                return

            if action == "vstore.upsert":
                ok2, result, r = _vstore_upsert(cfg, args)
                if ok2:
                    _evt("S1", "TOOLPROXY_ALLOW", actor, "allow", trace_id, {"action": action})
                    self._send({"ok": True, "trace_id": trace_id, "result": result})
                else:
                    _respond_error(r, result)
                return

            if action == "vstore.tombstone":
                ok2, result, r = _vstore_tombstone(cfg, args)
                if ok2:
                    _evt("S1", "TOOLPROXY_ALLOW", actor, "allow", trace_id, {"action": action})
                    self._send({"ok": True, "trace_id": trace_id, "result": result})
                else:
                    _respond_error(r, result)
                return

            if action == "roadmap.record":
                ok2, result, r = _roadmap_record(cfg, actor, args)
                if ok2:
                    _evt("S1", "TOOLPROXY_ALLOW", actor, "allow", trace_id, {"action": action})
                    self._send({"ok": True, "trace_id": trace_id, "result": result})
                else:
                    _respond_error(r, result)
                return

            if action == "roadmap.list":
                # Only for privileged roles via policy.
                epoch_dir = current_epoch_dir(str(cfg.get("contracts_root") or os.environ.get("NOEMAFORGE_CONTRACTS_ROOT") or "/var/lib/noemaforge/contracts"))
                ok2, result, r = _roadmap_list(cfg, epoch_dir, args)
                if ok2:
                    _evt("S1", "TOOLPROXY_ALLOW", actor, "allow", trace_id, {"action": action})
                    self._send({"ok": True, "trace_id": trace_id, "result": result})
                else:
                    _respond_error(r, result)
                return

            if action == "roadmap.export":
                epoch_dir = current_epoch_dir(str(cfg.get("contracts_root") or os.environ.get("NOEMAFORGE_CONTRACTS_ROOT") or "/var/lib/noemaforge/contracts"))
                ok2, result, r = _roadmap_export(cfg, epoch_dir, args)
                if ok2:
                    _evt("S1", "TOOLPROXY_ALLOW", actor, "allow", trace_id, {"action": action})
                    self._send({"ok": True, "trace_id": trace_id, "result": result})
                else:
                    _respond_error(r, result)
                return


            if action == "plan.enter":
                if plan_mode is None:
                    _respond_error("plan_mode_missing")
                    return
                try:
                    cps = args.get("checkpoints") or []
                    if not isinstance(cps, list):
                        cps = []
                    result = plan_mode.enter(
                        project_id=str(args.get("project_id") or project_id or "").strip(),
                        actor=str(role or "toolproxy"),
                        objective=str(args.get("objective") or "").strip(),
                        notes=str(args.get("notes") or "").strip(),
                        checkpoints=cps,
                    )
                    _evt("S1", "TOOLPROXY_ALLOW", actor, "allow", trace_id, {"action": action})
                    self._send({"ok": True, "trace_id": trace_id, "result": result})
                except Exception as e:
                    _respond_error(str(e))
                return

            if action == "plan.approve":
                if plan_mode is None:
                    _respond_error("plan_mode_missing")
                    return
                try:
                    result = plan_mode.approve(
                        project_id=str(args.get("project_id") or project_id or "").strip(),
                        actor=str(role or "toolproxy"),
                        note=str(args.get("note") or "").strip(),
                    )
                    _evt("S1", "TOOLPROXY_ALLOW", actor, "allow", trace_id, {"action": action})
                    self._send({"ok": True, "trace_id": trace_id, "result": result})
                except Exception as e:
                    _respond_error(str(e))
                return

            if action == "plan.exit":
                if plan_mode is None:
                    _respond_error("plan_mode_missing")
                    return
                try:
                    result = plan_mode.exit(
                        project_id=str(args.get("project_id") or project_id or "").strip(),
                        actor=str(role or "toolproxy"),
                        note=str(args.get("note") or "").strip(),
                    )
                    _evt("S1", "TOOLPROXY_ALLOW", actor, "allow", trace_id, {"action": action})
                    self._send({"ok": True, "trace_id": trace_id, "result": result})
                except Exception as e:
                    _respond_error(str(e))
                return

            if action == "plan.status":
                if plan_mode is None:
                    _respond_error("plan_mode_missing")
                    return
                try:
                    result = plan_mode.status(str(args.get("project_id") or project_id or "").strip())
                    _evt("S1", "TOOLPROXY_ALLOW", actor, "allow", trace_id, {"action": action})
                    self._send({"ok": True, "trace_id": trace_id, "result": result})
                except Exception as e:
                    _respond_error(str(e))
                return

            if action == "task.create":
                if task_tools is None:
                    _respond_error("task_tools_missing")
                    return
                try:
                    deps = args.get("depends_on") or []
                    if not isinstance(deps, list):
                        deps = []
                    result = task_tools.create_user_task(
                        project_id=str(args.get("project_id") or project_id or "").strip(),
                        title=str(args.get("title") or "").strip(),
                        description=str(args.get("description") or "").strip(),
                        kind=str(args.get("kind") or "generic").strip(),
                        status=str(args.get("status") or "queued").strip(),
                        owner=str(args.get("owner") or role or "").strip(),
                        priority_class=str(args.get("priority_class") or "normal").strip(),
                        payload=(args.get("payload") or {}) if isinstance(args.get("payload") or {}, dict) else {},
                        metadata=(args.get("metadata") or {}) if isinstance(args.get("metadata") or {}, dict) else {},
                        depends_on=deps,
                        session_id=str(args.get("session_id") or "").strip(),
                        background_module=str(args.get("background_module") or "").strip(),
                        group_key=str(args.get("group_key") or "").strip(),
                        plan_required=bool(args.get("plan_required", False)),
                        worktree_id=str(args.get("worktree_id") or "").strip(),
                        actor=str(role or "toolproxy"),
                    )
                    _evt("S1", "TOOLPROXY_ALLOW", actor, "allow", trace_id, {"action": action})
                    self._send({"ok": True, "trace_id": trace_id, "result": result})
                except Exception as e:
                    _respond_error(str(e))
                return

            if action == "task.list":
                if task_tools is None:
                    _respond_error("task_tools_missing")
                    return
                try:
                    result = task_tools.list_user_tasks(
                        project_id=str(args.get("project_id") or project_id or "").strip(),
                        status=str(args.get("status") or "").strip(),
                        limit=int(args.get("limit") or 50),
                    )
                    _evt("S1", "TOOLPROXY_ALLOW", actor, "allow", trace_id, {"action": action})
                    self._send({"ok": True, "trace_id": trace_id, "result": result})
                except Exception as e:
                    _respond_error(str(e))
                return

            if action == "task.get":
                if task_tools is None:
                    _respond_error("task_tools_missing")
                    return
                try:
                    result = task_tools.get_user_task(user_task_id=str(args.get("user_task_id") or "").strip())
                    _evt("S1", "TOOLPROXY_ALLOW", actor, "allow", trace_id, {"action": action})
                    self._send({"ok": True, "trace_id": trace_id, "result": result})
                except Exception as e:
                    _respond_error(str(e))
                return

            if action == "task.update":
                if task_tools is None:
                    _respond_error("task_tools_missing")
                    return
                try:
                    patch = args.get("patch") or {}
                    if not isinstance(patch, dict):
                        patch = {}
                    result = task_tools.update_user_task(
                        user_task_id=str(args.get("user_task_id") or "").strip(),
                        patch=patch,
                        actor=str(role or "toolproxy"),
                    )
                    _evt("S1", "TOOLPROXY_ALLOW", actor, "allow", trace_id, {"action": action})
                    self._send({"ok": True, "trace_id": trace_id, "result": result})
                except Exception as e:
                    _respond_error(str(e))
                return

            if action == "task.stop":
                if task_tools is None:
                    _respond_error("task_tools_missing")
                    return
                try:
                    result = task_tools.stop_user_task(
                        user_task_id=str(args.get("user_task_id") or "").strip(),
                        actor=str(role or "toolproxy"),
                    )
                    _evt("S1", "TOOLPROXY_ALLOW", actor, "allow", trace_id, {"action": action})
                    self._send({"ok": True, "trace_id": trace_id, "result": result})
                except Exception as e:
                    _respond_error(str(e))
                return

            if action == "task.output":
                if task_tools is None:
                    _respond_error("task_tools_missing")
                    return
                try:
                    meta2 = args.get("meta") or {}
                    if not isinstance(meta2, dict):
                        meta2 = {}
                    result = task_tools.add_output(
                        user_task_id=str(args.get("user_task_id") or "").strip(),
                        kind=str(args.get("kind") or "artifact").strip(),
                        text=str(args.get("text") or ""),
                        path=str(args.get("path") or "").strip(),
                        meta=meta2,
                        actor=str(role or "toolproxy"),
                    )
                    _evt("S1", "TOOLPROXY_ALLOW", actor, "allow", trace_id, {"action": action})
                    self._send({"ok": True, "trace_id": trace_id, "result": result})
                except Exception as e:
                    _respond_error(str(e))
                return

            if action == "worktree.enter":
                if worktree_manager is None:
                    _respond_error("worktree_manager_missing")
                    return
                try:
                    result = worktree_manager.enter(
                        project_id=str(args.get("project_id") or project_id or "").strip(),
                        repo_path=str(args.get("repo_path") or "").strip(),
                        actor=str(role or "toolproxy"),
                        base_ref=str(args.get("base_ref") or "HEAD").strip(),
                    )
                    _evt("S1", "TOOLPROXY_ALLOW", actor, "allow", trace_id, {"action": action})
                    self._send({"ok": True, "trace_id": trace_id, "result": result})
                except Exception as e:
                    _respond_error(str(e))
                return

            if action == "worktree.status":
                if worktree_manager is None:
                    _respond_error("worktree_manager_missing")
                    return
                try:
                    result = worktree_manager.status(
                        project_id=str(args.get("project_id") or project_id or "").strip(),
                        worktree_id=str(args.get("worktree_id") or "").strip(),
                    )
                    _evt("S1", "TOOLPROXY_ALLOW", actor, "allow", trace_id, {"action": action})
                    self._send({"ok": True, "trace_id": trace_id, "result": result})
                except Exception as e:
                    _respond_error(str(e))
                return

            if action == "worktree.promote":
                if worktree_manager is None:
                    _respond_error("worktree_manager_missing")
                    return
                try:
                    result = worktree_manager.promote(
                        project_id=str(args.get("project_id") or project_id or "").strip(),
                        worktree_id=str(args.get("worktree_id") or "").strip(),
                        actor=str(role or "toolproxy"),
                    )
                    _evt("S1", "TOOLPROXY_ALLOW", actor, "allow", trace_id, {"action": action})
                    self._send({"ok": True, "trace_id": trace_id, "result": result})
                except Exception as e:
                    _respond_error(str(e))
                return

            if action in ("worktree.exit", "worktree.discard"):
                if worktree_manager is None:
                    _respond_error("worktree_manager_missing")
                    return
                try:
                    result = worktree_manager.exit(
                        project_id=str(args.get("project_id") or project_id or "").strip(),
                        worktree_id=str(args.get("worktree_id") or "").strip(),
                        actor=str(role or "toolproxy"),
                        discard=(action == "worktree.discard") or bool(args.get("discard", action == "worktree.discard")),
                    )
                    _evt("S1", "TOOLPROXY_ALLOW", actor, "allow", trace_id, {"action": action})
                    self._send({"ok": True, "trace_id": trace_id, "result": result})
                except Exception as e:
                    _respond_error(str(e))
                return

            if action == "skills.list":
                if skills_registry is None:
                    _respond_error("skills_registry_missing")
                    return
                try:
                    result = skills_registry.list_skills()
                    _evt("S1", "TOOLPROXY_ALLOW", actor, "allow", trace_id, {"action": action})
                    self._send({"ok": True, "trace_id": trace_id, "result": result})
                except Exception as e:
                    _respond_error(str(e))
                return

            if action == "skills.run":
                if skills_registry is None:
                    _respond_error("skills_registry_missing")
                    return
                try:
                    inputs2 = args.get("inputs") or {}
                    if not isinstance(inputs2, dict):
                        inputs2 = {}
                    result = skills_registry.run_skill(
                        skill_id=str(args.get("skill_id") or "").strip(),
                        project_id=str(args.get("project_id") or project_id or "").strip(),
                        inputs=inputs2,
                        actor=str(role or "toolproxy"),
                    )
                    _evt("S1", "TOOLPROXY_ALLOW", actor, "allow", trace_id, {"action": action})
                    self._send({"ok": True, "trace_id": trace_id, "result": result})
                except Exception as e:
                    _respond_error(str(e))
                return

            if action == "notify.emit":
                if notifier is None:
                    _respond_error("notifier_missing")
                    return
                try:
                    links2 = args.get("links") or []
                    if not isinstance(links2, list):
                        links2 = []
                    result = notifier.emit(
                        severity=str(args.get("severity") or "info"),
                        message=str(args.get("message") or ""),
                        project_id=str(args.get("project_id") or project_id or "").strip(),
                        links=links2,
                        topic=str(args.get("topic") or "").strip(),
                        actor=str(role or "toolproxy"),
                    )
                    _evt("S1", "TOOLPROXY_ALLOW", actor, "allow", trace_id, {"action": action})
                    self._send({"ok": True, "trace_id": trace_id, "result": result})
                except Exception as e:
                    _respond_error(str(e))
                return

            if action == "notify.list":
                if notifier is None:
                    _respond_error("notifier_missing")
                    return
                try:
                    result = notifier.list_notifications(limit=int(args.get("limit") or 50), only_unacked=bool(args.get("only_unacked", False)))
                    _evt("S1", "TOOLPROXY_ALLOW", actor, "allow", trace_id, {"action": action})
                    self._send({"ok": True, "trace_id": trace_id, "result": result})
                except Exception as e:
                    _respond_error(str(e))
                return

            if action == "notify.ack":
                if notifier is None:
                    _respond_error("notifier_missing")
                    return
                try:
                    result = notifier.ack(str(args.get("notification_id") or "").strip(), actor=str(role or "toolproxy"))
                    _evt("S1", "TOOLPROXY_ALLOW", actor, "allow", trace_id, {"action": action})
                    self._send({"ok": True, "trace_id": trace_id, "result": result})
                except Exception as e:
                    _respond_error(str(e))
                return

            if action == "coordinator.fanout":
                if coordinator_fanout is None:
                    _respond_error("coordinator_fanout_missing")
                    return
                try:
                    areas = args.get("focus_areas") or []
                    if not isinstance(areas, list):
                        areas = []
                    result = coordinator_fanout.fanout(
                        project_id=str(args.get("project_id") or project_id or "").strip(),
                        prompt=str(args.get("prompt") or "").strip(),
                        worker_count=int(args.get("worker_count") or 3),
                        focus_areas=areas,
                        actor=str(role or "toolproxy"),
                    )
                    _evt("S1", "TOOLPROXY_ALLOW", actor, "allow", trace_id, {"action": action})
                    self._send({"ok": True, "trace_id": trace_id, "result": result})
                except Exception as e:
                    _respond_error(str(e))
                return

            if action == "team_memory.export":
                if team_memory_sync is None:
                    _respond_error("team_memory_sync_missing")
                    return
                try:
                    result = team_memory_sync.export_bundle(str(args.get("project_id") or project_id or "").strip())
                    _evt("S1", "TOOLPROXY_ALLOW", actor, "allow", trace_id, {"action": action})
                    self._send({"ok": True, "trace_id": trace_id, "result": result})
                except Exception as e:
                    _respond_error(str(e))
                return

            if action == "team_memory.import":
                if team_memory_sync is None:
                    _respond_error("team_memory_sync_missing")
                    return
                try:
                    result = team_memory_sync.import_bundle(
                        str(args.get("path") or "").strip(),
                        project_id=str(args.get("project_id") or project_id or "").strip(),
                    )
                    if result.get("ok"):
                        _evt("S1", "TOOLPROXY_ALLOW", actor, "allow", trace_id, {"action": action})
                        self._send({"ok": True, "trace_id": trace_id, "result": result})
                    else:
                        _respond_quarantine(str(result.get("decision") or result.get("error") or "team_memory_import_failed"))
                except Exception as e:
                    _respond_error(str(e))
                return

            if action == "team_memory.scan":
                if team_memory_sync is None:
                    _respond_error("team_memory_sync_missing")
                    return
                try:
                    result = team_memory_sync.scan_bundle(str(args.get("path") or "").strip())
                    _evt("S1", "TOOLPROXY_ALLOW", actor, "allow", trace_id, {"action": action})
                    self._send({"ok": True, "trace_id": trace_id, "result": result})
                except Exception as e:
                    _respond_error(str(e))
                return

            # Generic handler dispatch (plugins)
            handler = str((tool_entry or {}).get("handler") or "").strip()

            mode, payload, preflight_reason = _plugin_facade_or_args(cfg, action, args)
            if mode == "local_result":
                _evt("S1", "TOOLPROXY_ALLOW", actor, "allow", trace_id, {"action": action, "handler": "local_facade"})
                self._send({"ok": True, "trace_id": trace_id, "result": payload})
                return
            if mode == "error":
                rr = str(preflight_reason or "preflight_failed")
                if rr.endswith("_error") or rr.endswith("_failed"):
                    _respond_error(rr, payload)
                else:
                    _respond_deny(rr)
                return
            if mode == "plugin_args":
                args = payload
                ok2, result, r = _plugin_run(cfg, spol, stream_cfg, tool_entry, args)
                if ok2:
                    _evt("S1", "TOOLPROXY_ALLOW", actor, "allow", trace_id, {"action": action, "handler": handler or "plugin"})
                    self._send({"ok": True, "trace_id": trace_id, "result": result})
                else:
                    rr = str(r)
                    if rr in ("plugin:degraded_sandbox", "plugin:attestation_failed", "plugin:manifest_invalid", "plugin:id_mismatch"):
                        _respond_quarantine(rr)
                    elif rr.startswith("plugin:exec_failed") or rr.endswith("_error") or rr.startswith("plugin:error"):
                        _respond_error(rr, result)
                    else:
                        _respond_deny(rr)
                return

            if handler == "plugin":
                ok2, result, r = _plugin_run(cfg, spol, stream_cfg, tool_entry, args)
                if ok2:
                    _evt("S1", "TOOLPROXY_ALLOW", actor, "allow", trace_id, {"action": action, "handler": handler})
                    self._send({"ok": True, "trace_id": trace_id, "result": result})
                else:
                    rr = str(r)
                    if rr in ("plugin:degraded_sandbox", "plugin:attestation_failed", "plugin:manifest_invalid", "plugin:id_mismatch"):
                        _respond_quarantine(rr)
                    elif rr.startswith("plugin:exec_failed") or rr.endswith("_error") or rr.startswith("plugin:error"):
                        _respond_error(rr, result)
                    else:
                        _respond_deny(rr)
                return


            if handler == "web_gateway":
                # Pre-start only by policy; when allowed, this downloads into quarantine.
                url = str((args or {}).get("url") or "").strip()
                channel = str((args or {}).get("channel") or "packages").strip()
                ok2, result, r = webgw_fetch(
                    epoch_dir=current_epoch_dir(str(cfg.get("contracts_root") or os.environ.get("NOEMAFORGE_CONTRACTS_ROOT") or "/var/lib/noemaforge/contracts")),
                    actor=actor,
                    trace_id=trace_id,
                    url=url,
                    channel=channel,
                )
                if ok2:
                    _evt("S1", "TOOLPROXY_ALLOW", actor, "allow", trace_id, {"action": action, "handler": handler, "incident_id": result.get("incident_id")})
                    self._send({"ok": True, "trace_id": trace_id, "result": result})
                else:
                    rr = str(r)
                    # WebGateway failures are treated conservatively.
                    if rr in ("mime_not_allowed", "size_exceeded") or rr.startswith("fetch_failed"):
                        _respond_quarantine(rr)
                    else:
                        _respond_deny(rr)
                return

            if handler == "local_gateway":
                epoch_dir = current_epoch_dir(str(cfg.get("contracts_root") or os.environ.get("NOEMAFORGE_CONTRACTS_ROOT") or "/var/lib/noemaforge/contracts"))

                if action == "localgw.preflight":
                    suite = str((args or {}).get("suite") or "auto").strip().lower()
                    ok2, result, r = localgw_preflight(epoch_dir=epoch_dir, actor=actor, trace_id=trace_id, requested_suite=suite)
                    if ok2:
                        _evt("S1", "TOOLPROXY_ALLOW", actor, "allow", trace_id, {"action": action, "handler": handler})
                        self._send({"ok": True, "trace_id": trace_id, "result": result})
                    else:
                        # LAN preflight failures should generally quarantine, not deny.
                        if str((result or {}).get("decision") or "") == "quarantine" or str(r) in ("unknown_devices",):
                            _respond_quarantine(str(r))
                        else:
                            _respond_deny(str(r))
                    return

                if action == "localgw.discover":
                    try:
                        pol = _load_yaml(os.path.join(epoch_dir, "local-gateway-policy.yaml")) if epoch_dir else {}
                    except Exception:
                        pol = {}
                    devices = localgw_discover(pol)
                    _evt("S1", "TOOLPROXY_ALLOW", actor, "allow", trace_id, {"action": action, "handler": handler, "devices": len(devices)})
                    self._send({"ok": True, "trace_id": trace_id, "result": {"devices": devices[:100], "count": len(devices)}})
                    return

                if action == "localgw.nids_snapshot":
                    force = bool((args or {}).get("force", False))
                    ok2, result, r = nids_snapshot_and_analyze(epoch_dir=epoch_dir, actor=actor, trace_id=trace_id, force=force)
                    if ok2:
                        # If decision is quarantine, escalate.
                        if str((result or {}).get("decision") or "") == "quarantine":
                            _respond_quarantine(str(r))
                        else:
                            _evt("S1", "TOOLPROXY_ALLOW", actor, "allow", trace_id, {"action": action, "handler": handler})
                            self._send({"ok": True, "trace_id": trace_id, "result": result})
                    else:
                        _respond_deny(str(r))
                    return

                if action == "localgw.call":
                    tok = str((args or {}).get("lan_session_token") or "")
                    connector = str((args or {}).get("connector") or "")
                    method = str((args or {}).get("method") or "")
                    params = (args or {}).get("params") or {}
                    if not isinstance(params, dict):
                        params = {}
                    ok2, result, r = localgw_call(
                        epoch_dir=epoch_dir,
                        actor=actor,
                        trace_id=trace_id,
                        lan_session_token=tok,
                        connector=connector,
                        method=method,
                        params=params,
                    )
                    if ok2:
                        _evt("S1", "TOOLPROXY_ALLOW", actor, "allow", trace_id, {"action": action, "handler": handler})
                        self._send({"ok": True, "trace_id": trace_id, "result": result})
                    else:
                        # Network calls failing are quarantined by default.
                        _respond_quarantine(str(r))
                    return

            # Should never happen if registry/policy are correct.
            _respond_deny("handler_not_implemented")

        except Exception as e:
            self._send({"ok": False, "trace_id": trace_id, "error": f"bad_request:{e!r}"})

    # === NoemaForge Autodoc Function Header ===
    # Function: _send(self, obj: Dict[str, Any])
    # Purpose: Implement the routine ' send'.
    # Inputs:
    #   - self
    #   - obj: Dict[str, Any]
    # Called by:
    #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
    # Calls:
    #   - encode, sendall, dumps
    # Returns / emits: None
    # Side effects:
    #   - serializes structured data
    #   - sends a response or network payload
    # Key locals:
    #   - data
    # === End NoemaForge Autodoc Function Header ===
    def _send(self, obj: Dict[str, Any]) -> None:
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        try:
            self.request.sendall(data)
        except Exception:
            pass


# === NoemaForge Autodoc Function Header ===
# Function: serve(cfg_path: str)
# Purpose: Implement the routine 'serve'.
# Inputs:
#   - cfg_path: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _load_yaml, str, makedirs, ThreadedUnixServer, _evt, dirname, remove, chmod, serve_forever, server_close, open, write
# Returns / emits: int
# Side effects:
#   - reads or writes files
#   - creates directories
# Key locals:
#   - cfg, f, socket_path, srv, tokens_dir
# === End NoemaForge Autodoc Function Header ===
def serve(cfg_path: str) -> int:
    cfg = _load_yaml(cfg_path)

    # Signal runtime mode (best-effort). Pre-start tooling should refuse to run canaries in runtime.
    try:
        os.makedirs("/run/noemaforge", exist_ok=True)
        with open("/run/noemaforge/mode", "w", encoding="utf-8") as f:
            f.write("runtime\n")
    except Exception:
        pass

    socket_path = str(cfg.get("socket_path") or "/run/noemaforge/toolproxy.sock")
    os.makedirs(os.path.dirname(socket_path), exist_ok=True)

    # Ensure tokens dir exists
    tokens_dir = str(cfg.get("tokens_dir") or "/var/lib/noemaforge/.sys/cap_tokens")
    os.makedirs(tokens_dir, exist_ok=True)

    # Remove old socket
    try:
        os.remove(socket_path)
    except FileNotFoundError:
        pass

    if not _HAS_UNIX_STREAM_SERVER:
        raise RuntimeError(
            "ToolProxy AF_UNIX gateway requires a Unix platform "
            "(socketserver.UnixStreamServer is unavailable on this OS)."
        )
    srv = ThreadedUnixServer(socket_path, Handler)
    srv.cfg = cfg  # type: ignore[attr-defined]

    # Permissions: allow noemaforge group members. MVP: 0660.
    try:
        os.chmod(socket_path, 0o660)
    except Exception:
        pass

    _evt("S1", "TOOLPROXY_START", {"subsystem": "toolproxy"}, "start", str(uuid.uuid4()), {"socket": socket_path})

    try:
        srv.serve_forever()
    finally:
        srv.server_close()
    return 0


# === NoemaForge Autodoc Function Header ===
# Function: main(argv: list[str])
# Purpose: Implement the routine 'main'.
# Inputs:
#   - argv: list[str]
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
#   - ArgumentParser, add_argument, parse_args, serve
# Returns / emits: int
# Key locals:
#   - ap, args
# === End NoemaForge Autodoc Function Header ===
def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=CFG_PATH)
    args = ap.parse_args(argv)
    return serve(args.config)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
