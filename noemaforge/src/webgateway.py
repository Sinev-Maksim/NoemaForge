#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/webgateway.py
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
# File: src/webgateway.py
# Purpose: Fetch and stage external web content through policy gates and quarantine promotion.
# Invoked by / imported from:
#   - src/brainctl.py
#   - src/toolproxy.py
# Public API / entry functions:
#   - load_web_gateway_policy
#   - incident_dir_for_id
#   - channel_profile_for_incident
#   - fetch_to_quarantine
#   - approve_incident
#   - promote_incident
# Inputs:
#   - Common path inputs: /run/noemaforge/mode, /var/lib/noemaforge/quarantine/incidents, /workspace/role-runs, NoemaForge-WebGW/0.25, /var/lib/noemaforge/toolvault/artifacts, /var/lib/noemaforge/toolvault/manifests, noemaforge.toolvault/v1, /var/lib/noemaforge/docs
#   - Imports: __future__, datetime, json, os, re, shutil, urllib.parse, urllib.request
# Output formats / side effects:
#   - JSON files
#   - copied filesystem artifacts
#   - YAML files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""webgateway.py (v0.11.0)

WebGateway = strict network intake valve.

Key ideas:
- Always download into quarantine.
- Return metadata only.
- Channelized policy: packages / rss / git / generic.
- Promotion is a separate operator action (pre-start), gated by glove review + approval.

This is not a general web tool.
"""


import datetime as dt
import json
import os
import re
import shutil
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional, Tuple

import yaml

try:
    import httpx  # type: ignore
except Exception:  # pragma: no cover
    httpx = None  # type: ignore

from quarantine import create_incident
from platform_paths import DEFAULT_PATHS as _pp

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
#   - src/nids_lite.py
#   - src/toolproxy.py
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
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


# === NoemaForge Autodoc Function Header ===
# Function: load_web_gateway_policy(epoch_dir: str)
# Purpose: Implement the routine 'load web gateway policy'.
# Inputs:
#   - epoch_dir: str
# Called by:
#   - src/brainctl.py
# Calls:
#   - _load_yaml, join
# Returns / emits: Dict[str, Any]
# === End NoemaForge Autodoc Function Header ===
def load_web_gateway_policy(epoch_dir: str) -> Dict[str, Any]:
    return _load_yaml(os.path.join(epoch_dir, "web-gateway-policy.yaml"))


# === NoemaForge Autodoc Function Header ===
# Function: _deep_merge(a: Dict[str, Any], b: Dict[str, Any])
# Purpose: Implement the routine ' deep merge'.
# Inputs:
#   - a: Dict[str, Any]
#   - b: Dict[str, Any]
# Called by:
#   - src/prestart.py
# Calls:
#   - dict, items, isinstance, _deep_merge, get
# Returns / emits: Dict[str, Any]
# Key locals:
#   - out
# === End NoemaForge Autodoc Function Header ===
def _deep_merge(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(a)
    for k, v in (b or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)  # type: ignore
        else:
            out[k] = v
    return out


# === NoemaForge Autodoc Function Header ===
# Function: _effective_policy(pol: Dict[str, Any], channel: str)
# Purpose: Compute effective policy for a channel.
# Inputs:
#   - pol: Dict[str, Any]
#   - channel: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - strip, bool, get, isinstance, _deep_merge
# Returns / emits: Tuple[Dict[str, Any], str]
# Key locals:
#   - base, ch, chans, chpol, key
# === End NoemaForge Autodoc Function Header ===
def _effective_policy(pol: Dict[str, Any], channel: str) -> Tuple[Dict[str, Any], str]:
    """Compute effective policy for a channel.

    Returns (effective_policy, reason)
    """
    ch = (channel or "generic").strip() or "generic"

    base = {
        "enabled": bool(pol.get("enabled", False)),
        "mode": pol.get("mode") or {},
        "network": pol.get("network") or {},
        "downloads": pol.get("downloads") or {},
        "moderation": pol.get("moderation") or {},
        "imports": pol.get("imports") or {},
        "channels": pol.get("channels") or {},
    }

    chans = base.get("channels") or {}
    if isinstance(chans, dict) and ch in chans:
        chpol = chans.get(ch) or {}
        if isinstance(chpol, dict) and bool(chpol.get("enabled", True)) is False:
            return base, "channel_disabled"
        # Merge per channel overrides
        for key in ("mode", "network", "downloads", "moderation", "imports"):
            if isinstance(chpol, dict) and isinstance(chpol.get(key), dict):
                base[key] = _deep_merge(base.get(key) or {}, chpol.get(key) or {})
        base["_channel"] = ch
        base["_channel_promote"] = (chpol.get("promote") or {}) if isinstance(chpol, dict) else {}
    else:
        base["_channel"] = ch
        base["_channel_promote"] = {}

    return base, "ok"


# === NoemaForge Autodoc Function Header ===
# Function: _is_ip_literal(host: str)
# Purpose: Implement the routine ' is ip literal'.
# Inputs:
#   - host: str
# Called by:
#   - src/localgw_uplink.py
# Calls:
#   - fullmatch, startswith, endswith
# Returns / emits: bool
# === End NoemaForge Autodoc Function Header ===
def _is_ip_literal(host: str) -> bool:
    if not host:
        return False
    # crude v4
    if re.fullmatch(r"\d+\.\d+\.\d+\.\d+", host):
        return True
    # v6 in []
    if host.startswith("[") and host.endswith("]"):
        return True
    return False


# === NoemaForge Autodoc Function Header ===
# Function: _is_private_v4(host: str)
# Purpose: Implement the routine ' is private v4'.
# Inputs:
#   - host: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - int, len, split
# Returns / emits: bool
# Key locals:
#   - parts
# === End NoemaForge Autodoc Function Header ===
def _is_private_v4(host: str) -> bool:
    # host is v4 literal
    try:
        parts = [int(x) for x in host.split(".")]
        if len(parts) != 4:
            return False
        a, b, _c, _d = parts
        if a == 10:
            return True
        if a == 172 and 16 <= b <= 31:
            return True
        if a == 192 and b == 168:
            return True
        if a == 127:
            return True
        if a == 169 and b == 254:
            return True
    except Exception:
        return False
    return False


# === NoemaForge Autodoc Function Header ===
# Function: _allowed_content_type(ct: str, allowed_prefixes: list[str], denied_prefixes: list[str])
# Purpose: Implement the routine ' allowed content type'.
# Inputs:
#   - ct: str
#   - allowed_prefixes: list[str]
#   - denied_prefixes: list[str]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - lower, strip, startswith, split
# Returns / emits: bool
# Key locals:
#   - ap, ct, dp
# === End NoemaForge Autodoc Function Header ===
def _allowed_content_type(ct: str, allowed_prefixes: list[str], denied_prefixes: list[str]) -> bool:
    ct = (ct or "").split(";")[0].strip().lower()
    for dp in denied_prefixes:
        dp = (dp or "").lower().strip()
        if dp and ct.startswith(dp):
            return False
    if not allowed_prefixes:
        return False
    for ap in allowed_prefixes:
        ap = (ap or "").lower().strip()
        if ap and ct.startswith(ap):
            return True
    return False


# === NoemaForge Autodoc Function Header ===
# Function: _mode_guard(eff: Dict[str, Any])
# Purpose: Return (allowed, reason).
# Inputs:
#   - eff: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - bool, get, open, strip, read
# Returns / emits: Tuple[bool, str]
# Side effects:
#   - reads or writes files
# Key locals:
#   - current_mode, f, mode, prestart_only, runtime_allowed
# === End NoemaForge Autodoc Function Header ===
def _mode_guard(eff: Dict[str, Any]) -> Tuple[bool, str]:
    """Return (allowed, reason)."""
    # Global mode: if prestart_only, only allow in prestart unless runtime_allowed.
    mode = eff.get("mode") or {}
    prestart_only = bool(mode.get("prestart_only", True))
    runtime_allowed = bool(mode.get("runtime_allowed", False))

    try:
        with open(str(_pp.runtime_dir / "mode"), "r", encoding="utf-8") as f:
            current_mode = (f.read() or "").strip()
    except Exception:
        current_mode = "prestart"

    if current_mode == "runtime":
        if prestart_only and not runtime_allowed:
            return False, "webgw_prestart_only"
        return True, "ok"

    return True, "ok"


# === NoemaForge Autodoc Function Header ===
# Function: _quarantine_root(eff: Dict[str, Any])
# Purpose: Implement the routine ' quarantine root'.
# Inputs:
#   - eff: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - str, get
# Returns / emits: str
# Key locals:
#   - dl
# === End NoemaForge Autodoc Function Header ===
def _quarantine_root(eff: Dict[str, Any]) -> str:
    dl = eff.get("downloads") or {}
    return str(dl.get("quarantine_root") or str(_pp.data_root / "quarantine" / "incidents"))


# === NoemaForge Autodoc Function Header ===
# Function: incident_dir_for_id(pol: Dict[str, Any], incident_id: str)
# Purpose: Implement the routine 'incident dir for id'.
# Inputs:
#   - pol: Dict[str, Any]
#   - incident_id: str
# Called by:
#   - src/brainctl.py
# Calls:
#   - _effective_policy, _quarantine_root, join, str
# Returns / emits: str
# Key locals:
#   - root
# === End NoemaForge Autodoc Function Header ===
def incident_dir_for_id(pol: Dict[str, Any], incident_id: str) -> str:
    eff, _r = _effective_policy(pol, "generic")
    root = _quarantine_root(eff)
    return os.path.join(root, str(incident_id))


# === NoemaForge Autodoc Function Header ===
# Function: channel_profile_for_incident(pol: Dict[str, Any], incident_dir: str)
# Purpose: Derive glove profile for this incident based on stored meta + channel policy.
# Inputs:
#   - pol: Dict[str, Any]
#   - incident_dir: str
# Called by:
#   - src/brainctl.py
# Calls:
#   - _effective_policy, strip, load, get, open, str, join
# Returns / emits: str
# Side effects:
#   - reads or writes files
# Key locals:
#   - ch, meta, mod, prof
# === End NoemaForge Autodoc Function Header ===
def channel_profile_for_incident(pol: Dict[str, Any], incident_dir: str) -> str:
    """Derive glove profile for this incident based on stored meta + channel policy."""
    try:
        meta = json.load(open(os.path.join(incident_dir, "webgw_meta.json"), "r", encoding="utf-8"))
    except Exception:
        meta = {}
    ch = str(meta.get("channel") or "generic").strip() or "generic"
    eff, _ = _effective_policy(pol, ch)
    mod = eff.get("moderation") or {}
    prof = str(mod.get("glove_profile") or "generic").strip()
    return prof or "generic"


# === NoemaForge Autodoc Function Header ===
# Function: fetch_to_quarantine(epoch_dir: str, actor: Dict[str, Any], trace_id: str, url: str, channel: str = 'packages')
# Purpose: Fetch a URL into quarantine.
# Inputs:
#   - epoch_dir: str
#   - actor: Dict[str, Any]
#   - trace_id: str
#   - url: str
#   - channel: str = 'packages'
# Called by:
#   - src/brainctl.py
# Calls:
#   - load_web_gateway_policy, _effective_policy, _mode_guard, strip, urlparse, lower, int, _quarantine_root, str, makedirs, create_incident, join
# Returns / emits: Tuple[bool, Dict[str, Any], str]
# Side effects:
#   - creates directories
# Key locals:
#   - allow_domains, allow_schemes, allowed_prefixes, bytes_written, chunk, client, content_type, cur_url, denied_prefixes, dl, f, final_url
# === End NoemaForge Autodoc Function Header ===
def fetch_to_quarantine(
    *,
    epoch_dir: str,
    actor: Dict[str, Any],
    trace_id: str,
    url: str,
    channel: str = "packages",
) -> Tuple[bool, Dict[str, Any], str]:
    """Fetch a URL into quarantine.

    Returns (ok, result, reason). Result is metadata-only.
    """

    pol0 = load_web_gateway_policy(epoch_dir)
    eff, why = _effective_policy(pol0, channel)
    if why != "ok":
        return False, {"channel": channel}, why

    if not bool(eff.get("enabled", False)):
        return False, {"channel": channel}, "webgw_disabled"

    ok_mode, r_mode = _mode_guard(eff)
    if not ok_mode:
        return False, {"channel": channel}, r_mode

    net = eff.get("network") or {}
    dl = eff.get("downloads") or {}
    mod = eff.get("moderation") or {}

    u = str(url or "").strip()
    if not u:
        return False, {}, "url_missing"

    parsed = urllib.parse.urlparse(u)
    scheme = (parsed.scheme or "").lower()
    allow_schemes = [str(x).lower() for x in (net.get("allow_schemes") or ["https"]) if isinstance(x, str)]
    if scheme not in allow_schemes:
        return False, {"scheme": scheme, "allow_schemes": allow_schemes}, "scheme_not_allowed"

    host = parsed.hostname or ""
    if not host:
        return False, {}, "host_missing"

    if bool(net.get("deny_ip_literals", True)) and _is_ip_literal(host):
        return False, {"host": host}, "ip_literal_denied"
    if bool(net.get("deny_private_ranges", True)) and _is_ip_literal(host) and _is_private_v4(host):
        return False, {"host": host}, "private_range_denied"

    allow_domains = [str(x).lower().strip() for x in (net.get("allow_domains") or []) if isinstance(x, str)]
    if allow_domains:
        if host.lower() not in allow_domains and not any(host.lower().endswith("." + d) for d in allow_domains):
            return False, {"host": host, "allow_domains": allow_domains}, "domain_not_allowed"
    else:
        # empty allowlist => deny by default
        return False, {"host": host}, "domain_allowlist_empty"

    max_bytes = int(dl.get("max_bytes") or 200_000_000)
    max_redirects = int(dl.get("max_redirects") or 3)
    allowed_prefixes = [str(x) for x in (dl.get("allowed_mime_prefixes") or [])]
    denied_prefixes = [str(x) for x in (dl.get("denied_mime_prefixes") or [])]

    quarantine_root = _quarantine_root(eff)
    incoming_subdir = str(dl.get("incoming_subdir") or "incoming")

    os.makedirs(quarantine_root, exist_ok=True)

    # Create incident first (so we can store meta even if fetch fails later)
    incident_id, idir, _ = create_incident(
        policy={
            "paths": {"quarantine_root": quarantine_root, "role_runs_root": "/workspace/role-runs"},
            "snapshot": {
                "capture_request": True,
                "capture_role_context": False,
                "capture_file_metadata": False,
            },
        },
        actor=actor,
        trace_id=trace_id,
        action="webgw.fetch",
        reason="intake",
        request_obj={
            "args": {"url": u, "channel": channel},
            "policy": {"webgw": True, "channel": channel},
        },
        incident_kind="webgateway_quarantine",
        incident_severity="S2",
    )

    payload_path = os.path.join(idir, "payload.bin")
    meta_path = os.path.join(idir, "webgw_meta.json")

    # follow redirects manually (bounded)
    cur_url = u
    redirects = 0
    bytes_written = 0
    content_type = ""
    final_url = u

    try:
        while True:
            timeout_sec = int(dl.get("timeout_sec", 30))
            headers = {"User-Agent": str(dl.get("user_agent") or "NoemaForge-WebGW/0.25"), "Accept": "*/*"}
            prefer_httpx = bool(dl.get("prefer_httpx", True))

            if httpx is not None and prefer_httpx:
                with httpx.Client(follow_redirects=False, timeout=timeout_sec) as client:  # type: ignore
                    resp = client.get(cur_url, headers=headers)
                    status = int(resp.status_code)
                    final_url = str(resp.url)
                    content_type = str(resp.headers.get("Content-Type") or "")
                    if status in (301, 302, 303, 307, 308):
                        if redirects >= max_redirects:
                            raise RuntimeError("too_many_redirects")
                        loc = str(resp.headers.get("Location") or "")
                        if not loc:
                            raise RuntimeError("redirect_missing_location")
                        cur_url = urllib.parse.urljoin(cur_url, loc)
                        redirects += 1
                        continue

                    if not _allowed_content_type(content_type, allowed_prefixes, denied_prefixes):
                        with open(meta_path, "w", encoding="utf-8") as f:
                            json.dump(
                                {
                                    "ts": _nowz(),
                                    "channel": channel,
                                    "url": u,
                                    "final_url": final_url,
                                    "host": host,
                                    "content_type": content_type,
                                    "redirects": redirects,
                                    "bytes": 0,
                                    "note": "mime_not_allowed",
                                },
                                f,
                                ensure_ascii=False,
                                indent=2,
                            )
                        _evt("S0", "WEBGW_FETCH", actor, "deny", trace_id, {"incident_id": incident_id, "reason": "mime_not_allowed", "content_type": content_type, "channel": channel})
                        return False, {"incident_id": incident_id, "content_type": content_type}, "mime_not_allowed"

                    with open(payload_path, "wb") as out:
                        for chunk in resp.iter_bytes():
                            if not chunk:
                                continue
                            out.write(chunk)
                            bytes_written += len(chunk)
                            if bytes_written > max_bytes:
                                raise RuntimeError("size_exceeded")

                    break

            # Fallback: urllib
            req = urllib.request.Request(cur_url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
                status = int(getattr(resp, "status", 200))
                final_url = str(resp.geturl() or cur_url)
                content_type = str(resp.headers.get("Content-Type") or "")
                # Redirect handling
                if status in (301, 302, 303, 307, 308):
                    if redirects >= max_redirects:
                        raise RuntimeError("too_many_redirects")
                    loc = resp.headers.get("Location") or ""
                    if not loc:
                        raise RuntimeError("redirect_missing_location")
                    cur_url = urllib.parse.urljoin(cur_url, loc)
                    redirects += 1
                    continue

                # Content-type gate
                if not _allowed_content_type(content_type, allowed_prefixes, denied_prefixes):
                    # still write meta, but no payload
                    with open(meta_path, "w", encoding="utf-8") as f:
                        json.dump(
                            {
                                "ts": _nowz(),
                                "channel": channel,
                                "url": u,
                                "final_url": final_url,
                                "host": host,
                                "content_type": content_type,
                                "redirects": redirects,
                                "bytes": 0,
                                "note": "mime_not_allowed",
                            },
                            f,
                            ensure_ascii=False,
                            indent=2,
                        )
                    _evt("S0", "WEBGW_FETCH", actor, "deny", trace_id, {"incident_id": incident_id, "reason": "mime_not_allowed", "content_type": content_type, "channel": channel})
                    return False, {"incident_id": incident_id, "content_type": content_type}, "mime_not_allowed"

                # Download to payload.bin
                with open(payload_path, "wb") as out:
                    while True:
                        chunk = resp.read(1024 * 64)
                        if not chunk:
                            break
                        out.write(chunk)
                        bytes_written += len(chunk)
                        if bytes_written > max_bytes:
                            raise RuntimeError("size_exceeded")

                break

    except Exception as e:
        # Write meta anyway
        try:
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "ts": _nowz(),
                        "channel": channel,
                        "url": u,
                        "final_url": final_url,
                        "host": host,
                        "content_type": content_type,
                        "redirects": redirects,
                        "bytes": bytes_written,
                        "error": repr(e),
                    },
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
        except Exception:
            pass

        rr = "fetch_failed" if "size_exceeded" not in repr(e) else "size_exceeded"
        _evt("S0", "WEBGW_FETCH", actor, "deny", trace_id, {"incident_id": incident_id, "reason": rr, "error": repr(e), "channel": channel})
        return False, {"incident_id": incident_id, "bytes": bytes_written, "content_type": content_type}, rr

    # Persist meta
    try:
        # filename guess from final_url
        p2 = urllib.parse.urlparse(final_url)
        fn = os.path.basename(p2.path or "")
        if not fn:
            fn = "payload.bin"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "ts": _nowz(),
                    "channel": channel,
                    "url": u,
                    "final_url": final_url,
                    "host": host,
                    "content_type": content_type,
                    "redirects": redirects,
                    "bytes": bytes_written,
                    "filename_guess": fn,
                },
                f,
                ensure_ascii=False,
                indent=2,
            )
    except Exception:
        pass

    # Hash payload
    sha = ""
    try:
        import hashlib

        h = hashlib.sha256()
        with open(payload_path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        sha = h.hexdigest()
    except Exception:
        sha = ""

    # Update meta with payload sha256 (still within pre-chmod window)
    try:
        m = _load_json(meta_path)
        if isinstance(m, dict):
            m["artifact_sha256"] = sha
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(m, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    # Always keep evidence immutable-ish
    try:
        os.chmod(payload_path, 0o400)
        os.chmod(meta_path, 0o400)
    except Exception:
        pass

    # Tool response redaction: do not return raw paths by default.
    result = {
        "incident_id": incident_id,
        "channel": channel,
        "bytes": bytes_written,
        "content_type": content_type,
        "artifact_sha256": sha,
        "final_url": final_url,
        "redirects": redirects,
    }

    _evt("S0", "WEBGW_FETCH", actor, "allow", trace_id, {**result})

    return True, result, "ok"


# -------------------------
# Approve + promote (operator-only)
# -------------------------


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
#   - src/model_registry.py
#   - src/model_router.py
#   - src/roles/role_entry.py
#   - src/scary_sweep.py
# Calls:
#   - load, open
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads or writes files
# === End NoemaForge Autodoc Function Header ===
def _load_json(path: str) -> Dict[str, Any]:
    try:
        return json.load(open(path, "r", encoding="utf-8"))
    except Exception:
        return {}


# === NoemaForge Autodoc Function Header ===
# Function: _require_file(path: str)
# Purpose: Implement the routine ' require file'.
# Inputs:
#   - path: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - bool, exists, isfile
# Returns / emits: bool
# === End NoemaForge Autodoc Function Header ===
def _require_file(path: str) -> bool:
    return bool(path and os.path.exists(path) and os.path.isfile(path))


# === NoemaForge Autodoc Function Header ===
# Function: approve_incident(epoch_dir: str, incident_dir: str, actor: Dict[str, Any], trace_id: str, comment: str)
# Purpose: Implement the routine 'approve incident'.
# Inputs:
#   - epoch_dir: str
#   - incident_dir: str
#   - actor: Dict[str, Any]
#   - trace_id: str
#   - comment: str
# Called by:
#   - src/brainctl.py
# Calls:
#   - load_web_gateway_policy, _load_json, _effective_policy, join, _evt, strip, _nowz, str, chmod, open, dump, get
# Returns / emits: Tuple[bool, Dict[str, Any], str]
# Side effects:
#   - reads or writes files
#   - serializes structured data
# Key locals:
#   - approval_path, ch, f, meta, pol0, rec
# === End NoemaForge Autodoc Function Header ===
def approve_incident(
    *,
    epoch_dir: str,
    incident_dir: str,
    actor: Dict[str, Any],
    trace_id: str,
    comment: str,
) -> Tuple[bool, Dict[str, Any], str]:
    pol0 = load_web_gateway_policy(epoch_dir)

    meta = _load_json(os.path.join(incident_dir, "webgw_meta.json"))
    ch = str(meta.get("channel") or "generic").strip() or "generic"
    eff, why = _effective_policy(pol0, ch)
    if why != "ok":
        return False, {"channel": ch}, why

    if not comment.strip():
        return False, {}, "comment_required"

    approval_path = os.path.join(incident_dir, "webgw_approval.json")
    rec = {
        "schema_version": "v1",
        "kind": "WebGWApproval",
        "ts": _nowz(),
        "incident_id": str(_load_json(os.path.join(incident_dir, "incident.json")).get("incident_id") or ""),
        "channel": ch,
        "actor": actor,
        "comment": comment.strip(),
    }

    try:
        with open(approval_path, "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False, indent=2)
        os.chmod(approval_path, 0o400)
    except Exception as e:
        return False, {"error": repr(e)}, "approval_write_failed"

    _evt("S0", "WEBGW_APPROVE", actor, "allow", trace_id, {"incident_id": rec["incident_id"], "channel": ch})

    return True, {"approval_path": approval_path, "incident_id": rec["incident_id"], "channel": ch}, "ok"


# === NoemaForge Autodoc Function Header ===
# Function: _toolvault_paths(eff: Dict[str, Any])
# Purpose: Implement the routine ' toolvault paths'.
# Inputs:
#   - eff: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - str, get
# Returns / emits: Tuple[str, str]
# Key locals:
#   - artifacts, imp, manifests
# === End NoemaForge Autodoc Function Header ===
def _toolvault_paths(eff: Dict[str, Any]) -> Tuple[str, str]:
    imp = eff.get("imports") or {}
    artifacts = str(imp.get("artifacts_dir") or str(_pp.vault_dir / "artifacts"))
    manifests = str(imp.get("manifests_dir") or str(_pp.vault_dir / "manifests"))
    return artifacts, manifests


# === NoemaForge Autodoc Function Header ===
# Function: promote_incident(epoch_dir: str, incident_dir: str, actor: Dict[str, Any], trace_id: str, target: str = '', comment: str = '')
# Purpose: Promote a reviewed incident into a local vault.
# Inputs:
#   - epoch_dir: str
#   - incident_dir: str
#   - actor: Dict[str, Any]
#   - trace_id: str
#   - target: str = ''
#   - comment: str = ''
# Called by:
#   - src/brainctl.py
# Calls:
#   - load_web_gateway_policy, _load_json, _effective_policy, bool, strip, join, _evt, get, _require_file, splitext, _nowz, _toolvault_paths
# Returns / emits: Tuple[bool, Dict[str, Any], str]
# Key locals:
#   - allow_targets, artifact_sha, bundle_id, ch, chunk, code_root, day, default_target, docs_root, dst, dst_dir, dst_meta
# === End NoemaForge Autodoc Function Header ===
def promote_incident(
    *,
    epoch_dir: str,
    incident_dir: str,
    actor: Dict[str, Any],
    trace_id: str,
    target: str = "",
    comment: str = "",
) -> Tuple[bool, Dict[str, Any], str]:
    """Promote a reviewed incident into a local vault.

    Targets (MVP):
      - toolvault.artifact
      - docsvault.rss_item
      - codevault.snapshot

    All promotions leave quarantine evidence intact.
    """

    pol0 = load_web_gateway_policy(epoch_dir)

    incident = _load_json(os.path.join(incident_dir, "incident.json"))
    meta = _load_json(os.path.join(incident_dir, "webgw_meta.json"))
    ch = str(meta.get("channel") or "generic").strip() or "generic"

    eff, why = _effective_policy(pol0, ch)
    if why != "ok":
        return False, {"channel": ch}, why

    mod = eff.get("moderation") or {}

    # Require glove report?
    if bool(mod.get("require_glove_review", True)):
        if not _require_file(os.path.join(incident_dir, "glove_report.json")):
            return False, {"incident_id": incident.get("incident_id"), "channel": ch}, "glove_report_missing"
        # If glove output flags high-severity PI patterns, do not promote.
        try:
            gr = _load_json(os.path.join(incident_dir, "glove_report.json"))
            sev = str(((gr or {}).get("outputs") or {}).get("pi_severity") or "").strip().lower()
            if sev == "high":
                return False, {"incident_id": incident.get("incident_id"), "channel": ch, "pi_severity": sev}, "pi_high_severity"
        except Exception:
            return False, {"incident_id": incident.get("incident_id"), "channel": ch}, "glove_report_unreadable"

    # Require human approval?
    if bool(mod.get("require_human_approval", True)):
        if not _require_file(os.path.join(incident_dir, "webgw_approval.json")):
            return False, {"incident_id": incident.get("incident_id"), "channel": ch}, "approval_missing"

    promote_cfg = eff.get("_channel_promote") or {}
    allow_targets = promote_cfg.get("allow_targets") or []
    default_target = str(promote_cfg.get("default_target") or "toolvault.artifact").strip()

    t = (target or "").strip() or default_target
    if allow_targets and t not in [str(x) for x in allow_targets if isinstance(x, str)]:
        return False, {"target": t, "allow_targets": allow_targets, "channel": ch}, "target_not_allowed"

    payload_path = os.path.join(incident_dir, "payload.bin")
    if not _require_file(payload_path):
        return False, {"incident_id": incident.get("incident_id")}, "payload_missing"

    artifact_sha = str(meta.get("artifact_sha256") or "").strip()
    if not artifact_sha:
        # compute quickly
        try:
            import hashlib

            h = hashlib.sha256()
            with open(payload_path, "rb") as f:
                for chunk in iter(lambda: f.read(1024 * 1024), b""):
                    h.update(chunk)
            artifact_sha = h.hexdigest()
        except Exception:
            artifact_sha = ""

    fn_guess = str(meta.get("filename_guess") or "payload.bin").strip()
    ext = os.path.splitext(fn_guess)[1]
    if ext and len(ext) > 10:
        ext = ""

    out: Dict[str, Any] = {
        "incident_id": incident.get("incident_id"),
        "channel": ch,
        "target": t,
        "artifact_sha256": artifact_sha,
        "ts": _nowz(),
        "comment": comment.strip(),
    }

    # Perform promotion
    if t == "toolvault.artifact":
        artifacts_dir, _man_dir = _toolvault_paths(eff)
        os.makedirs(artifacts_dir, exist_ok=True)
        dst = os.path.join(artifacts_dir, artifact_sha + (ext or ".bin"))
        if not os.path.exists(dst):
            shutil.copy2(payload_path, dst)
            try:
                os.chmod(dst, 0o600)
            except Exception:
                pass
        out.update({"toolvault_artifact_path": dst})

        # For supply-chain hardening, package/driver/tool channels also emit a
        # ToolVault bundle manifest (+ optional signature) so scary/surgeon
        # can reason about provenance and canaries can pin it by sha.
        try:
            import toolvault  # local module
            sc_path = os.path.join(epoch_dir, 'supplychain-policy.yaml')
            sc_pol = toolvault.load_yaml(sc_path) if os.path.exists(sc_path) else {}
            _tv_root, tv_man_dir, _tv_art_dir = toolvault.vault_paths(sc_pol if isinstance(sc_pol, dict) else {})
        except Exception:
            toolvault = None
            sc_pol = {}
            tv_man_dir = _man_dir

        if toolvault is not None and ch in ('packages', 'drivers', 'tool', 'plugins', 'extensions'):
            os.makedirs(tv_man_dir, exist_ok=True)
            bundle_id = str(meta.get('bundle_id') or f'bundle-{artifact_sha[:16]}')
            mpath = os.path.join(tv_man_dir, f'{bundle_id}.yaml')
            if not os.path.exists(mpath):
                mf = {
                    'apiVersion': 'noemaforge.toolvault/v1',
                    'kind': 'BundleManifest',
                    'bundle_id': bundle_id,
                    'created_at': _nowz(),
                    'artifact_format': 'raw.bin',
                    'artifact_sha256': artifact_sha,
                    'origin': {
                        'channel': ch,
                        'url': meta.get('url'),
                        'final_url': meta.get('final_url'),
                        'host': meta.get('host'),
                        'incident_id': incident.get('incident_id'),
                        'fetched_at': meta.get('ts') or meta.get('fetched_at') or _nowz(),
                        'approved_by': actor,
                    },
                }
                toolvault.dump_yaml(mf, mpath)

            # Prefer signing if a local key exists or can be created (pre-start).
            ok_sig, r_sig = toolvault.sign_manifest_inplace(mpath, sc_pol if isinstance(sc_pol, dict) else {})
            out.update({
                'toolvault_bundle_id': bundle_id,
                'toolvault_manifest_path': mpath,
                'toolvault_manifest_sha256': toolvault.sha256_file(mpath) if os.path.exists(mpath) else '',
                'toolvault_manifest_signed': bool(ok_sig),
                'toolvault_manifest_sign_reason': r_sig,
            })

    elif t in ("docsvault.rss_item", "docsvault.page"):
        docs_root = str(promote_cfg.get("docs_root") or str(_pp.data_root / "docs"))
        os.makedirs(docs_root, exist_ok=True)
        host = str(meta.get("host") or "unknown")
        day = dt.datetime.now(dt.UTC).replace(tzinfo=None).strftime("%Y/%m/%d")
        kind_dir = "rss" if t == "docsvault.rss_item" else "pages"
        dst_dir = os.path.join(docs_root, kind_dir, host, day, str(incident.get("incident_id") or "incident"))
        os.makedirs(dst_dir, exist_ok=True)

        # Prefer sanitized text produced by glove.
        sani = os.path.join(incident_dir, "glove_sanitized.txt")
        if os.path.exists(sani):
            src_text = sani
            sanitized = True
        else:
            src_text = payload_path
            sanitized = False

        dst_text = os.path.join(dst_dir, "content.txt")
        shutil.copy2(src_text, dst_text)
        try:
            os.chmod(dst_text, 0o600)
        except Exception:
            pass

        dst_meta = os.path.join(dst_dir, "meta.json")
        with open(dst_meta, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "ts": _nowz(),
                    "incident_id": incident.get("incident_id"),
                    "channel": ch,
                    "source": {"url": meta.get("url"), "final_url": meta.get("final_url"), "host": host},
                    "artifact_sha256": artifact_sha,
                    "sanitized": sanitized,
                    "glove_report_present": _require_file(os.path.join(incident_dir, "glove_report.json")),
                },
                f,
                ensure_ascii=False,
                indent=2,
            )
        out.update({"docsvault_path": dst_dir, "sanitized": sanitized})

    elif t == "codevault.snapshot":
        code_root = str(promote_cfg.get("code_root") or str(_pp.data_root / "codevault"))
        os.makedirs(code_root, exist_ok=True)
        dst_dir = os.path.join(code_root, "git", "snapshots")
        os.makedirs(dst_dir, exist_ok=True)
        dst = os.path.join(dst_dir, artifact_sha + (ext or ".bin"))
        if not os.path.exists(dst):
            shutil.copy2(payload_path, dst)
            try:
                os.chmod(dst, 0o600)
            except Exception:
                pass
        meta_out = os.path.join(dst_dir, artifact_sha + ".meta.json")
        with open(meta_out, "w", encoding="utf-8") as f:
            json.dump({"ts": _nowz(), "incident_id": incident.get("incident_id"), "source": meta, "artifact": {"sha256": artifact_sha, "path": dst}}, f, ensure_ascii=False, indent=2)
        out.update({"codevault_snapshot": dst, "codevault_meta": meta_out})

    else:
        return False, {"target": t}, "unknown_target"

    # Record promotion record in incident dir (evidence)
    rec_path = os.path.join(incident_dir, "webgw_promotion.json")
    try:
        with open(rec_path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        os.chmod(rec_path, 0o400)
    except Exception:
        pass

    _evt("S0", "WEBGW_PROMOTE", actor, "allow", trace_id, {"incident_id": incident.get("incident_id"), "channel": ch, "target": t})

    return True, out, "ok"
