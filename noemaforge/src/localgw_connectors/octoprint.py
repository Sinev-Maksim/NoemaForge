#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/localgw_connectors/octoprint.py
Zone: release/package
Version: 0.31.13.alpha-patched1
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
# File: src/localgw_connectors/octoprint.py
# Purpose: Provide the module 'octoprint'.
# Invoked by / imported from:
#   - No inbound Python import detected; treat as library leaf or direct entrypoint.
# Public API / entry functions:
#   - manifest
#   - call
# Inputs:
#   - Common path inputs: application/json
#   - Imports: __future__, json, os, urllib.request, urllib.error, urllib.parse, typing, localgw_secrets
# Output formats / side effects:
#   - JSON files
#   - YAML files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""localgw_connectors.octoprint (v0.16.0)

OctoPrint connector (typed).

This connector is intentionally conservative:
- Only supports a small set of methods.
- Requires an API key reference (api_key_ref) stored in localgw secret store.
- Does not perform broad discovery.
- Best-effort networking via urllib (no extra deps).

Stage C1:
- upload_gcode is executed via disposable uplink glove (podman slirp / microVM when available)

Policy integration
------------------
Expected device profile in local-gateway-policy.yaml:

devices:
  allowlist:
    - device_uid: lan:...
      name: my_octoprint
      connectors:
        octoprint:
          base_url: http://192.168.1.50
          api_key_ref: octoprint_api_key_1

Methods
-------
- version: GET /api/version
- printer: GET /api/printer
- job: GET /api/job
- upload_gcode: POST /api/files/local (multipart) [dangerous]
- start_print: POST /api/files/local/<path> (select+print) [dangerous]

We mark upload/start as actuation methods (optionally invite-gated by LocalGateway).
"""


import json
import os
import urllib.request
import urllib.error
import urllib.parse
from typing import Any, Dict, Tuple

from . import base
import localgw_secrets
import localgw_uplink
from toolvault import load_yaml


# === NoemaForge Autodoc Function Header ===
# Function: manifest()
# Purpose: Implement the routine 'manifest'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - src/localgw_connectors/__init__.py
# Returns / emits: Dict[str, Any]
# === End NoemaForge Autodoc Function Header ===
def manifest() -> Dict[str, Any]:
    return {
        "id": "octoprint",
        "version": "0.15.0",
        "methods": ["version", "printer", "job", "upload_gcode", "start_print"],
        "dangerous_methods": ["upload_gcode", "start_print"],
    }


# === NoemaForge Autodoc Function Header ===
# Function: _profile(ctx: base.ConnectorContext)
# Purpose: Implement the routine ' profile'.
# Inputs:
#   - ctx: base.ConnectorContext
# Called by:
#   - src/localgw_connectors/ipp.py
# Calls:
#   - isinstance, get
# Returns / emits: Dict[str, Any]
# Key locals:
#   - oc, prof
# === End NoemaForge Autodoc Function Header ===
def _profile(ctx: base.ConnectorContext) -> Dict[str, Any]:
    prof = (ctx.device_profile or {}) if isinstance(ctx.device_profile, dict) else {}
    oc = (prof.get("connectors") or {}).get("octoprint") if isinstance(prof.get("connectors"), dict) else None
    if isinstance(oc, dict):
        return oc
    return {}


# === NoemaForge Autodoc Function Header ===
# Function: _api_key(profile: Dict[str, Any])
# Purpose: Implement the routine ' api key'.
# Inputs:
#   - profile: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - strip, load_secret, str, get
# Returns / emits: str
# Key locals:
#   - ref
# === End NoemaForge Autodoc Function Header ===
def _api_key(profile: Dict[str, Any]) -> str:
    ref = str(profile.get("api_key_ref") or "").strip()
    if not ref:
        return ""
    return localgw_secrets.load_secret(ref, default="")


# === NoemaForge Autodoc Function Header ===
# Function: _base_url(profile: Dict[str, Any])
# Purpose: Implement the routine ' base url'.
# Inputs:
#   - profile: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - rstrip, strip, str, get
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _base_url(profile: Dict[str, Any]) -> str:
    return str(profile.get("base_url") or "").strip().rstrip("/")


# === NoemaForge Autodoc Function Header ===
# Function: _http_json(method: str, url: str, headers: Dict[str, str], body = None)
# Purpose: Implement the routine ' http json'.
# Inputs:
#   - method: str
#   - url: str
#   - headers: Dict[str, str]
#   - body = None
# Called by:
#   - src/localgw_uplink_agent.py
# Calls:
#   - Request, items, isinstance, add_header, encode, dict, setdefault, upper, urlopen, bytes, read, loads
# Returns / emits: Tuple[bool, Dict[str, Any], str]
# Side effects:
#   - reads or writes files
# Key locals:
#   - data, headers, msg, obj, raw, req, resp
# === End NoemaForge Autodoc Function Header ===
def _http_json(method: str, url: str, headers: Dict[str, str], body: Any = None) -> Tuple[bool, Dict[str, Any], str]:
    data = None
    if body is not None:
        if isinstance(body, (dict, list)):
            data = json.dumps(body).encode("utf-8")
            headers = dict(headers)
            headers.setdefault("Content-Type", "application/json")
        elif isinstance(body, (bytes, bytearray)):
            data = bytes(body)
        else:
            data = str(body).encode("utf-8")

    req = urllib.request.Request(url, data=data, method=method.upper())
    for k, v in (headers or {}).items():
        req.add_header(k, v)

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read() or b"{}"
            try:
                obj = json.loads(raw.decode("utf-8", errors="replace"))
            except Exception:
                obj = {"raw": raw[:2000].decode("utf-8", errors="replace")}
            return True, obj if isinstance(obj, dict) else {"data": obj}, "ok"
    except urllib.error.HTTPError as e:
        try:
            raw = e.read() or b"{}"
            msg = raw.decode("utf-8", errors="replace")[:2000]
        except Exception:
            msg = str(e)
        return False, {"ok": False, "http": int(getattr(e, "code", 0) or 0), "error": msg}, "http_error"
    except Exception as e:
        return False, {"ok": False, "error": repr(e)}, "fetch_failed"


# === NoemaForge Autodoc Function Header ===
# Function: call(method: str, params: Dict[str, Any], ctx: base.ConnectorContext)
# Purpose: Implement the routine 'call'.
# Inputs:
#   - method: str
#   - params: Dict[str, Any]
#   - ctx: base.ConnectorContext
# Called by:
#   - src/localgateway.py
#   - src/localgw_connectors/__init__.py
# Calls:
#   - strip, _profile, _base_url, _api_key, set, _http_json, bool, load_yaml, secret_path, run_octoprint_upload, lstrip, str
# Returns / emits: Tuple[bool, Dict[str, Any], str]
# Side effects:
#   - spawns subprocesses or workers
# Key locals:
#   - api_key_file, base_url, body, dest, do_print, headers, key, local_path, m, profile, rel_path, sandbox_policy
# === End NoemaForge Autodoc Function Header ===
def call(*, method: str, params: Dict[str, Any], ctx: base.ConnectorContext) -> Tuple[bool, Dict[str, Any], str]:
    m = str(method or "").strip()
    if m not in set(manifest()["methods"]):
        return False, {"ok": False, "reason": "method_not_allowed"}, "method_not_allowed"

    profile = _profile(ctx)
    # Security: for physical actuators, the target MUST come from the device profile.
    # We do not accept arbitrary base_url in params (prevents SSRF / lateral moves).
    base_url = _base_url(profile)
    if not base_url:
        return False, {"ok": False, "reason": "missing_base_url_in_profile"}, "missing_base_url_in_profile"

    key = _api_key(profile)
    if not key:
        return False, {"ok": False, "reason": "missing_api_key"}, "missing_api_key"

    headers = {"X-Api-Key": key, "Accept": "application/json"}

    if m == "version":
        return _http_json("GET", base_url + "/api/version", headers)

    if m == "printer":
        return _http_json("GET", base_url + "/api/printer", headers)

    if m == "job":
        return _http_json("GET", base_url + "/api/job", headers)

    if m == "upload_gcode":
        local_path = str((params or {}).get("local_path") or "").strip()
        if not local_path:
            return False, {"ok": False, "reason": "missing_local_path"}, "missing_local_path"
        if not os.path.exists(local_path):
            return False, {"ok": False, "reason": "file_not_found"}, "file_not_found"
        dest = str((params or {}).get("dest_name") or "").strip() or os.path.basename(local_path)
        select = bool((params or {}).get("select", False))
        do_print = bool((params or {}).get("print", False))

        # Run upload inside a disposable uplink glove.
        sandbox_policy = load_yaml(os.path.join(ctx.epoch_dir, "sandbox-policy.yaml"))
        api_key_file = localgw_secrets.secret_path(str(profile.get("api_key_ref") or ""))
        ok2, rep, rr = localgw_uplink.run_octoprint_upload(
            epoch_dir=ctx.epoch_dir,
            sandbox_policy=sandbox_policy,
            local_gateway_policy=ctx.policy,
            base_url=base_url,
            api_key_file=api_key_file,
            local_path=local_path,
            dest_name=dest,
            select=select,
            do_print=do_print,
        )
        return ok2, rep, rr

    if m == "start_print":
        rel_path = str((params or {}).get("path") or "").strip().lstrip("/")
        if not rel_path:
            return False, {"ok": False, "reason": "missing_path"}, "missing_path"
        body = {"command": "select", "print": True}
        url = base_url + "/api/files/local/" + urllib.parse.quote(rel_path)
        return _http_json("POST", url, headers, body=body)

    return False, {"ok": False, "reason": "not_implemented"}, "not_implemented"
