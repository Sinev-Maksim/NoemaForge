#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/fixture_bundle.py
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
# File: src/fixture_bundle.py
# Purpose: Provide the module 'fixture_bundle'.
# Invoked by / imported from:
#   - src/task_runner.py
# Public API / entry functions:
#   - load_fixture_autogen_cfg
#   - stage_fixture
#   - load_staged_fixtures
#   - build_bundle_request
#   - write_prestart_request
#   - flush_staged_bundle
# Inputs:
#   - Common path inputs: /var/lib/noemaforge, /opt/noemaforge/configs/incident-policy.yaml, /workspace/outbox/scary/fixtures, noemaforge.security/v1, noemaforge.prestart/v1
#   - Imports: __future__, datetime, json, os, re, uuid, typing, yaml
# Output formats / side effects:
#   - JSON files
#   - YAML files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""fixture_bundle.py (v0.12.6)

Staging + bundling for auto-generated SecurityFixtures.

Why
---
We want runtime to be able to *propose* new canary scenarios (fixtures) without:
- running canaries at runtime
- spamming many tiny PreStartChangeRequests

So we split into two deterministic steps:
  1) stage: generate a fixture from an Incident and write it to a staging dir
  2) flush: bundle staged fixtures into ONE draft PreStartChangeRequest

Security posture
----------------
- Staged records store fixture objects (already sanitized by fixture_autogen).
- No raw quarantine content is embedded; only hash-only sample_ref.
- All emitted changes remain PRE-START ONLY.

This module is intentionally dependency-light.
"""


import datetime as dt
import json
import os
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple

try:  # pragma: no cover
    import yaml
except Exception:  # pragma: no cover
    yaml = None  # type: ignore


BASE = "/var/lib/noemaforge"

DEFAULT_POLICY_FALLBACK = "/opt/noemaforge/configs/incident-policy.yaml"

DEFAULT_REQUESTS_DIR = os.path.join(BASE, "requests", "prestart")
DEFAULT_OUTBOX_DIR = "/workspace/outbox/scary/fixtures"
DEFAULT_STATE_PATH = os.path.join(BASE, ".sys", "scary_autogen_fixtures.json")

DEFAULT_STAGING_DIR = os.path.join(BASE, ".sys", "fixture_autogen", "staging")
DEFAULT_SENT_DIR = os.path.join(BASE, ".sys", "fixture_autogen", "sent")


SHA_RE = re.compile(r"^[a-f0-9]{32,64}$")


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
#   - src/glove_agent.py
# Calls:
#   - isoformat, utcnow
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _nowz() -> str:
    return dt.datetime.utcnow().isoformat() + "Z"


# === NoemaForge Autodoc Function Header ===
# Function: _ts_id()
# Purpose: Implement the routine ' ts id'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - src/scary_sweep.py
#   - src/sr_cycle.py
#   - src/ssr_cycle.py
#   - src/surgeon_auto.py
# Calls:
#   - strftime, utcnow
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _ts_id() -> str:
    return dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")


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
#   - src/flow_metrics.py
#   - src/incidents.py
#   - src/knowledge/policy.py
#   - src/llm_backends_manager.py
# Calls:
#   - open, safe_load
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads or writes files
# Key locals:
#   - f
# === End NoemaForge Autodoc Function Header ===
def _load_yaml(path: str) -> Dict[str, Any]:
    if yaml is None:
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


# === NoemaForge Autodoc Function Header ===
# Function: _save_yaml(path: str, obj: Dict[str, Any])
# Purpose: Implement the routine ' save yaml'.
# Inputs:
#   - path: str
#   - obj: Dict[str, Any]
# Called by:
#   - src/noemaforge_core.py
#   - src/prestart.py
#   - src/tool_onboard.py
# Calls:
#   - makedirs, replace, RuntimeError, dirname, open, safe_dump
# Returns / emits: None
# Side effects:
#   - reads or writes files
#   - serializes structured data
#   - creates directories
# Key locals:
#   - f, tmp
# === End NoemaForge Autodoc Function Header ===
def _save_yaml(path: str, obj: Dict[str, Any]) -> None:
    if yaml is None:
        raise RuntimeError("yaml_missing")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        yaml.safe_dump(obj, f, sort_keys=False, allow_unicode=True)
    os.replace(tmp, path)


# === NoemaForge Autodoc Function Header ===
# Function: _load_json(path: str)
# Purpose: Implement the routine ' load json'.
# Inputs:
#   - path: str
# Called by:
#   - src/noemaforge_core.py
#   - src/glove_agent.py
#   - src/model_installer_plan.py
#   - src/model_registry.py
#   - src/model_router.py
#   - src/roles/role_entry.py
#   - src/scary_sweep.py
#   - src/team_installer_plan.py
# Calls:
#   - open, load
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads or writes files
# Key locals:
#   - f
# === End NoemaForge Autodoc Function Header ===
def _load_json(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


# === NoemaForge Autodoc Function Header ===
# Function: _save_json(path: str, obj: Dict[str, Any])
# Purpose: Implement the routine ' save json'.
# Inputs:
#   - path: str
#   - obj: Dict[str, Any]
# Called by:
#   - src/audit_remediation.py
#   - src/noemaforge_core.py
#   - src/model_registry.py
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
def _save_json(path: str, obj: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


# === NoemaForge Autodoc Function Header ===
# Function: _policy_path(epoch_dir: str, fallback: str = DEFAULT_POLICY_FALLBACK)
# Purpose: Implement the routine ' policy path'.
# Inputs:
#   - epoch_dir: str
#   - fallback: str = DEFAULT_POLICY_FALLBACK
# Called by:
#   - src/incidents.py
#   - src/llm_backends_manager.py
#   - src/telemetry.py
# Calls:
#   - join, exists, strip, str
# Returns / emits: str
# Key locals:
#   - cand
# === End NoemaForge Autodoc Function Header ===
def _policy_path(epoch_dir: str, fallback: str = DEFAULT_POLICY_FALLBACK) -> str:
    cand = os.path.join(str(epoch_dir or "").strip() or "", "incident-policy.yaml")
    if cand and os.path.exists(cand):
        return cand
    return fallback


# === NoemaForge Autodoc Function Header ===
# Function: load_fixture_autogen_cfg(epoch_dir: str, fallback_policy_path: str = DEFAULT_POLICY_FALLBACK)
# Purpose: Load fixture autogen config from IncidentPolicy (epoch-scoped).
# Inputs:
#   - epoch_dir: str
#   - fallback_policy_path: str = DEFAULT_POLICY_FALLBACK
# Called by:
#   - src/task_runner.py
# Calls:
#   - str, _load_yaml, isinstance, get, bool, lower, int, _policy_path, strip
# Returns / emits: Dict[str, Any]
# Key locals:
#   - bundle, fx, paths, pol, sent_dir, staging_dir
# === End NoemaForge Autodoc Function Header ===
def load_fixture_autogen_cfg(
    *,
    epoch_dir: str,
    fallback_policy_path: str = DEFAULT_POLICY_FALLBACK,
) -> Dict[str, Any]:
    """Load fixture autogen config from IncidentPolicy (epoch-scoped)."""

    pol = _load_yaml(_policy_path(epoch_dir, fallback_policy_path)) or {}
    fx = pol.get("fixtures") if isinstance(pol, dict) else None
    if not isinstance(fx, dict):
        fx = {}

    paths = fx.get("paths") if isinstance(fx.get("paths"), dict) else {}
    bundle = fx.get("bundle") if isinstance(fx.get("bundle"), dict) else {}

    staging_dir = str(paths.get("staging_dir") or DEFAULT_STAGING_DIR)
    sent_dir = str(paths.get("sent_dir") or DEFAULT_SENT_DIR)

    return {
        "enabled": bool(fx.get("enabled", True)),
        "emit_mode": str(fx.get("emit_mode") or "tasks").strip().lower(),
        "requests_dir": str(paths.get("requests_dir") or DEFAULT_REQUESTS_DIR),
        "outbox_dir": str(paths.get("outbox_dir") or DEFAULT_OUTBOX_DIR),
        "state_path": str(paths.get("state_path") or DEFAULT_STATE_PATH),
        "staging_dir": staging_dir,
        "sent_dir": sent_dir,
        "requires_canary": str(fx.get("requires_canary") or "full"),
        "bundle_enabled": bool(bundle.get("enabled", True)),
        "bundle_max_fixtures": int(bundle.get("max_fixtures_per_request", 25) or 25),
        "bundle_risk_level": str(bundle.get("risk_level") or "medium"),
        "bundle_track": str(bundle.get("track") or "policy"),
    }


# === NoemaForge Autodoc Function Header ===
# Function: _staged_filename(fixture_id: str, digest: str)
# Purpose: Implement the routine ' staged filename'.
# Inputs:
#   - fixture_id: str
#   - digest: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - strip, sub
# Returns / emits: str
# Key locals:
#   - d, dshort, fid, safe
# === End NoemaForge Autodoc Function Header ===
def _staged_filename(fixture_id: str, digest: str) -> str:
    fid = (fixture_id or "").strip()
    d = (digest or "").strip()
    dshort = d[:12] if d else "nodigest"
    safe = re.sub(r"[^a-zA-Z0-9_\-]+", "_", fid)[:80] or "fixture"
    return f"{safe}__{dshort}.yaml"


# === NoemaForge Autodoc Function Header ===
# Function: stage_fixture(fixture: Dict[str, Any], digest: str, cfg: Dict[str, Any], source_incident_id: str = '', source_incident_path: str = '')
# Purpose: Write a staged fixture record to disk.
# Inputs:
#   - fixture: Dict[str, Any]
#   - digest: str
#   - cfg: Dict[str, Any]
#   - source_incident_id: str = ''
#   - source_incident_path: str = ''
# Called by:
#   - src/task_runner.py
# Calls:
#   - str, makedirs, strip, isinstance, join, replace, get, lower, _nowz, _staged_filename, open, safe_dump
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads or writes files
#   - serializes structured data
#   - creates directories
# Key locals:
#   - doc, f, fid, out_path, sha, sr, staging_dir, tmp
# === End NoemaForge Autodoc Function Header ===
def stage_fixture(
    *,
    fixture: Dict[str, Any],
    digest: str,
    cfg: Dict[str, Any],
    source_incident_id: str = "",
    source_incident_path: str = "",
) -> Dict[str, Any]:
    """Write a staged fixture record to disk."""

    if yaml is None:
        return {"ok": False, "error": "yaml_missing"}

    staging_dir = str(cfg.get("staging_dir") or DEFAULT_STAGING_DIR)
    os.makedirs(staging_dir, exist_ok=True)

    fid = str(fixture.get("id") or "").strip()
    if not fid:
        return {"ok": False, "error": "missing_fixture.id"}

    # Optional sample_ref sanity (hash-only)
    sr = fixture.get("sample_ref") if isinstance(fixture.get("sample_ref"), dict) else None
    if isinstance(sr, dict):
        sha = str(sr.get("sha256") or "").strip().lower()
        if sha and not SHA_RE.match(sha):
            # Do not block staging; just redact invalid ref.
            sr["sha256"] = ""
            fixture["sample_ref"] = sr

    doc: Dict[str, Any] = {
        "schema_version": "v1",
        "kind": "StagedSecurityFixture",
        "staged_at": _nowz(),
        "fixture_id": fid,
        "digest": str(digest or ""),
        "source_incident": {
            "incident_id": str(source_incident_id or ""),
            "path": "<redacted>" if source_incident_path else "",
        },
        "fixture": fixture,
    }

    out_path = os.path.join(staging_dir, _staged_filename(fid, str(digest or "")))
    tmp = out_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        yaml.safe_dump(doc, f, sort_keys=False, allow_unicode=True)
    os.replace(tmp, out_path)
    try:
        os.chmod(out_path, 0o600)
    except Exception:
        pass

    return {"ok": True, "staged": True, "path": out_path, "fixture_id": fid, "digest": str(digest or "")}


# === NoemaForge Autodoc Function Header ===
# Function: _iter_staged_files(staging_dir: str)
# Purpose: Implement the routine ' iter staged files'.
# Inputs:
#   - staging_dir: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - listdir, sort, isdir, endswith, append, join
# Returns / emits: List[str]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - fn, out
# === End NoemaForge Autodoc Function Header ===
def _iter_staged_files(staging_dir: str) -> List[str]:
    if not os.path.isdir(staging_dir):
        return []
    out: List[str] = []
    for fn in os.listdir(staging_dir):
        if fn.endswith(".yaml") or fn.endswith(".yml"):
            out.append(os.path.join(staging_dir, fn))
    out.sort()
    return out


# === NoemaForge Autodoc Function Header ===
# Function: load_staged_fixtures(staging_dir: str)
# Purpose: Load staged fixture docs.
# Inputs:
#   - staging_dir: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _iter_staged_files, _load_yaml, isinstance, append, get
# Returns / emits: List[Dict[str, Any]]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - obj, out, p
# === End NoemaForge Autodoc Function Header ===
def load_staged_fixtures(*, staging_dir: str) -> List[Dict[str, Any]]:
    """Load staged fixture docs."""
    if yaml is None:
        return []
    out: List[Dict[str, Any]] = []
    for p in _iter_staged_files(staging_dir):
        try:
            obj = _load_yaml(p)
            if isinstance(obj, dict) and obj.get("kind") == "StagedSecurityFixture":
                obj["_path"] = p
                out.append(obj)
        except Exception:
            continue
    return out


# === NoemaForge Autodoc Function Header ===
# Function: build_bundle_request(fixtures: List[Dict[str, Any]], cfg: Dict[str, Any], actor: Optional[Dict[str, Any]] = None)
# Purpose: Create a draft PreStartChangeRequest that adds multiple fixtures.
# Inputs:
#   - fixtures: List[Dict[str, Any]]
#   - cfg: Dict[str, Any]
#   - actor: Optional[Dict[str, Any]] = None
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _nowz, str, _ts_id, get, len, uuid4
# Returns / emits: Dict[str, Any]
# Key locals:
#   - patch, rid, who
# === End NoemaForge Autodoc Function Header ===
def build_bundle_request(
    *,
    fixtures: List[Dict[str, Any]],
    cfg: Dict[str, Any],
    actor: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Create a draft PreStartChangeRequest that adds multiple fixtures."""

    rid = f"scary-fixture-bundle-{_ts_id()}-{uuid.uuid4().hex[:8]}"

    patch = {
        "apiVersion": "noemaforge.security/v1",
        "kind": "SecurityFixtures",
        "fixtures": fixtures,
    }

    who = actor or {"actor_type": "scary", "actor_id": "fixture_bundle"}

    return {
        "apiVersion": "noemaforge.prestart/v1",
        "kind": "PreStartChangeRequest",
        "schema_version": "v1",
        "request_id": rid,
        "created_at": _nowz(),
        "created_by": who,
        "status": "draft",
        "track": str(cfg.get("bundle_track") or "policy"),
        "risk_level": str(cfg.get("bundle_risk_level") or "medium"),
        "requires_canary": str(cfg.get("requires_canary") or "full"),
        "user_comment": f"AUTO-GENERATED bundle: add {len(fixtures)} security fixture(s). Review in PRE-START.",
        "requested_changes": {
            "security_fixtures_patch": patch,
        },
        "notes": [
            "No runtime canaries: this request only adds fixtures; they execute during PRE-START FULL canary.",
            "Bundling reduces review noise; each fixture has source_incident metadata.",
        ],
    }


# === NoemaForge Autodoc Function Header ===
# Function: write_prestart_request(request_obj: Dict[str, Any], requests_dir: str, outbox_dir: str)
# Purpose: Write the request to both queue dir and outbox; returns (queue_path, outbox_path).
# Inputs:
#   - request_obj: Dict[str, Any]
#   - requests_dir: str
#   - outbox_dir: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - str, makedirs, join, RuntimeError, ValueError, open, safe_dump, get
# Returns / emits: Tuple[str, str]
# Side effects:
#   - reads or writes files
#   - serializes structured data
#   - creates directories
# Key locals:
#   - f, outbox_path, queue_path, rid
# === End NoemaForge Autodoc Function Header ===
def write_prestart_request(
    *,
    request_obj: Dict[str, Any],
    requests_dir: str,
    outbox_dir: str,
) -> Tuple[str, str]:
    """Write the request to both queue dir and outbox; returns (queue_path, outbox_path)."""

    if yaml is None:
        raise RuntimeError("yaml_missing")

    rid = str(request_obj.get("request_id") or "")
    if not rid:
        raise ValueError("missing_request_id")

    os.makedirs(requests_dir, exist_ok=True)
    os.makedirs(outbox_dir, exist_ok=True)

    queue_path = os.path.join(requests_dir, f"{rid}.yaml")
    outbox_path = os.path.join(outbox_dir, f"{rid}.prestart_request.yaml")

    with open(outbox_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(request_obj, f, sort_keys=False, allow_unicode=True)
    with open(queue_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(request_obj, f, sort_keys=False, allow_unicode=True)

    return queue_path, outbox_path


# === NoemaForge Autodoc Function Header ===
# Function: flush_staged_bundle(epoch_dir: str, cfg: Dict[str, Any], actor: Optional[Dict[str, Any]] = None)
# Purpose: Bundle staged fixtures into a draft PreStartChangeRequest.
# Inputs:
#   - epoch_dir: str
#   - cfg: Dict[str, Any]
#   - actor: Optional[Dict[str, Any]] = None
# Called by:
#   - src/task_runner.py
# Calls:
#   - str, load_staged_fixtures, max, build_bundle_request, write_prestart_request, _load_json, _nowz, append, makedirs, bool, min, strip
# Returns / emits: Dict[str, Any]
# Side effects:
#   - creates directories
#   - appends to logs or files
# Key locals:
#   - base, d, dig, dst, emitted, fid, fixtures, fixtures_meta, fx, maxn, moved, p
# === End NoemaForge Autodoc Function Header ===
def flush_staged_bundle(
    *,
    epoch_dir: str,
    cfg: Dict[str, Any],
    actor: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Bundle staged fixtures into a draft PreStartChangeRequest.

    Returns metadata, including request_id if emitted.
    """

    if yaml is None:
        return {"ok": False, "error": "yaml_missing"}

    if not bool(cfg.get("enabled", True)):
        return {"ok": True, "skipped": True, "reason": "fixtures_autogen_disabled"}

    staging_dir = str(cfg.get("staging_dir") or DEFAULT_STAGING_DIR)
    sent_dir = str(cfg.get("sent_dir") or DEFAULT_SENT_DIR)
    state_path = str(cfg.get("state_path") or DEFAULT_STATE_PATH)

    staged_docs = load_staged_fixtures(staging_dir=staging_dir)
    if not staged_docs:
        return {"ok": True, "emitted": False, "count": 0}

    maxn = max(1, min(int(cfg.get("bundle_max_fixtures") or 25), 200))

    # Collect fixtures in deterministic order.
    fixtures: List[Dict[str, Any]] = []
    used_docs: List[Dict[str, Any]] = []
    used_paths: List[str] = []
    for d in staged_docs:
        fx = d.get("fixture") if isinstance(d.get("fixture"), dict) else None
        if not isinstance(fx, dict):
            continue
        fid = str(fx.get("id") or "").strip()
        if not fid:
            continue
        fixtures.append(fx)
        used_docs.append(d)
        used_paths.append(str(d.get("_path") or ""))
        if len(fixtures) >= maxn:
            break

    if not fixtures:
        return {"ok": True, "emitted": False, "count": 0}

    req = build_bundle_request(fixtures=fixtures, cfg=cfg, actor=actor)
    queue_path, outbox_path = write_prestart_request(request_obj=req, requests_dir=str(cfg.get("requests_dir") or DEFAULT_REQUESTS_DIR), outbox_dir=str(cfg.get("outbox_dir") or DEFAULT_OUTBOX_DIR))

    # Update state: mark emitted digests by fixture id (ONLY for used docs).
    st = _load_json(state_path)
    emitted = st.get("emitted") if isinstance(st.get("emitted"), dict) else {}
    for d in used_docs:
        fx = d.get("fixture") if isinstance(d.get("fixture"), dict) else None
        if not isinstance(fx, dict):
            continue
        fid = str(fx.get("id") or "").strip()
        dig = str(d.get("digest") or "").strip()
        if fid and dig:
            emitted[fid] = dig
    st["emitted"] = emitted
    st["updated_at"] = _nowz()
    st.setdefault("bundles", []).append({"request_id": str(req.get("request_id") or ""), "created_at": str(req.get("created_at") or ""), "count": len(fixtures)})
    try:
        _save_json(state_path, st)
    except Exception:
        pass

    # Move used staging files into sent_dir for forensics.
    os.makedirs(sent_dir, exist_ok=True)
    moved: List[str] = []
    for p in used_paths:
        if not p or not os.path.exists(p):
            continue
        base = os.path.basename(p)
        dst = os.path.join(sent_dir, f"{_ts_id()}__{base}")
        try:
            os.replace(p, dst)
            moved.append(dst)
        except Exception:
            pass

    fixtures_meta: List[Dict[str, Any]] = []
    for d in used_docs:
        fx = d.get("fixture") if isinstance(d.get("fixture"), dict) else None
        if not isinstance(fx, dict):
            continue
        fixtures_meta.append(
            {
                "fixture_id": str(fx.get("id") or ""),
                "digest": str(d.get("digest") or ""),
                "source_incident_id": str(((fx.get("source_incident") or {}) if isinstance(fx.get("source_incident"), dict) else {}).get("incident_id") or ""),
            }
        )

    return {
        "ok": True,
        "emitted": True,
        "request_id": str(req.get("request_id") or ""),
        "queue_path": queue_path,
        "outbox_path": outbox_path,
        "count": len(fixtures),
        "moved": moved,
        "fixtures": fixtures_meta,
    }
