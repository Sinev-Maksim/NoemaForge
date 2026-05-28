#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/quarantine.py
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
# File: src/quarantine.py
# Purpose: Provide the module 'quarantine'.
# Invoked by / imported from:
#   - src/toolproxy.py
#   - src/webgateway.py
# Public API / entry functions:
#   - create_incident
# Inputs:
#   - Common path inputs: /var/lib/noemaforge/quarantine/incidents, /workspace/role-runs
#   - Imports: __future__, datetime, hashlib, json, os, shutil, uuid, typing
# Output formats / side effects:
#   - JSON files
#   - copied filesystem artifacts
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""quarantine.py (v0.12.3)

Quarantine = forensic capture for suspicious tool usage.

v0.12.3 upgrades:
- Every quarantine snapshot can also be promoted to a first-class Incident object
  (incidents.py) with dedupe+repeat counting.
- Quarantine snapshots remain separate, immutable forensic artifacts; Incident objects
  act as the lifecycle/triage layer.

Design constraints:
- Executors should NOT learn internal security protocol details.
- ToolProxy may return redacted errors; full detail is in SEL/WORM + incident snapshot.
- Snapshots are best-effort and dependency-light.
"""


import datetime as dt
import hashlib
import json
import os
import shutil
import uuid
from typing import Any, Dict, List, Optional, Tuple

# Optional: promote quarantine snapshots to Incident objects.
try:  # pragma: no cover
    from incidents import open_incident as open_lifecycle_incident
except Exception:  # pragma: no cover
    open_lifecycle_incident = None  # type: ignore


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
# Function: _safe_json_dump(path: str, obj)
# Purpose: Implement the routine ' safe json dump'.
# Inputs:
#   - path: str
#   - obj
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
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
def _safe_json_dump(path: str, obj: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


# === NoemaForge Autodoc Function Header ===
# Function: _sha256_bytes(b: bytes)
# Purpose: Implement the routine ' sha256 bytes'.
# Inputs:
#   - b: bytes
# Called by:
#   - src/quarantine_samples.py
#   - src/task_tools.py
# Calls:
#   - sha256, update, hexdigest
# Returns / emits: str
# Key locals:
#   - h
# === End NoemaForge Autodoc Function Header ===
def _sha256_bytes(b: bytes) -> str:
    h = hashlib.sha256()
    h.update(b)
    return h.hexdigest()


# === NoemaForge Autodoc Function Header ===
# Function: _sha256_str(s: str)
# Purpose: Implement the routine ' sha256 str'.
# Inputs:
#   - s: str
# Called by:
#   - src/quarantine_samples.py
# Calls:
#   - hexdigest, sha256, encode
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _sha256_str(s: str) -> str:
    return hashlib.sha256((s or "").encode("utf-8", errors="ignore")).hexdigest()


# === NoemaForge Autodoc Function Header ===
# Function: _file_meta(path: str, sample_bytes: int = 0)
# Purpose: Implement the routine ' file meta'.
# Inputs:
#   - path: str
#   - sample_bytes: int = 0
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - stat, update, isfile, _sha256_bytes, len, int, float, open, read, str
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads or writes files
# Key locals:
#   - blob, f, out, st
# === End NoemaForge Autodoc Function Header ===
def _file_meta(path: str, sample_bytes: int = 0) -> Dict[str, Any]:
    out: Dict[str, Any] = {"path": path}
    try:
        st = os.stat(path)
        out.update({
            "exists": True,
            "size": int(st.st_size),
            "mtime": float(st.st_mtime),
            "mode": int(st.st_mode),
        })
        if sample_bytes > 0 and os.path.isfile(path):
            with open(path, "rb") as f:
                blob = f.read(sample_bytes)
            out["sample_sha256"] = _sha256_bytes(blob)
            out["sample_bytes"] = len(blob)
    except Exception as e:
        out.update({"exists": False, "error": str(e)})
    return out


# === NoemaForge Autodoc Function Header ===
# Function: create_incident(policy: Dict[str, Any], actor: Dict[str, Any], trace_id: str, action: str, reason: str, request_obj: Optional[Dict[str, Any]] = None, response_obj: Optional[Dict[str, Any]] = None, incident_kind: str = 'quarantine', incident_severity: str = 'S2', incident_dedupe_key: str = '', promote_to_incidents: bool = True)
# Purpose: Create a quarantine incident snapshot.
# Inputs:
#   - policy: Dict[str, Any]
#   - actor: Dict[str, Any]
#   - trace_id: str
#   - action: str
#   - reason: str
#   - request_obj: Optional[Dict[str, Any]] = None
#   - response_obj: Optional[Dict[str, Any]] = None
#   - incident_kind: str = 'quarantine'
#   - incident_severity: str = 'S2'
#   - incident_dedupe_key: str = ''
#   - promote_to_incidents: bool = True
# Called by:
#   - src/toolproxy.py
#   - src/webgateway.py
# Calls:
#   - str, bool, int, join, makedirs, _safe_json_dump, get, uuid4, dict, _nowz, chmod, listdir
# Returns / emits: Tuple[str, str, Dict[str, Any]]
# Side effects:
#   - serializes structured data
#   - creates directories
# Key locals:
#   - args, capture_file_meta, capture_req, capture_role_ctx, ctx_path, dst, fn, idir, incident, incident_dedupe_key, k, key_candidates
# === End NoemaForge Autodoc Function Header ===
def create_incident(
    *,
    policy: Dict[str, Any],
    actor: Dict[str, Any],
    trace_id: str,
    action: str,
    reason: str,
    request_obj: Optional[Dict[str, Any]] = None,
    response_obj: Optional[Dict[str, Any]] = None,
    # v0.12.3: promote to lifecycle incident (optional)
    incident_kind: str = "quarantine",
    incident_severity: str = "S2",
    incident_dedupe_key: str = "",
    promote_to_incidents: bool = True,
) -> Tuple[str, str, Dict[str, Any]]:
    """Create a quarantine incident snapshot.

    Returns: (quarantine_id, quarantine_dir, quarantine_record)
    """

    paths = policy.get("paths") or {}
    root = str(paths.get("quarantine_root") or "/var/lib/noemaforge/quarantine/incidents")
    role_runs_root = str(paths.get("role_runs_root") or "/workspace/role-runs")

    snap = policy.get("snapshot") or {}
    capture_req = bool(snap.get("capture_request", True))
    capture_role_ctx = bool(snap.get("capture_role_context", True))
    capture_file_meta = bool(snap.get("capture_file_metadata", True))
    max_inline = int(snap.get("max_inline_bytes") or 200000)
    sample_bytes = int(snap.get("max_file_sample_bytes") or 4096)

    quarantine_id = str(uuid.uuid4())
    idir = os.path.join(root, quarantine_id)
    os.makedirs(idir, exist_ok=True)

    # Redact tokens before writing.
    req_red = None
    if request_obj and capture_req:
        req_red = dict(request_obj)
        if "token" in req_red:
            req_red["token"] = "<redacted>"
        # Truncate huge blobs conservatively
        try:
            raw = json.dumps(req_red, ensure_ascii=False).encode("utf-8")
            if len(raw) > max_inline:
                req_red = {"_truncated": True, "bytes": len(raw), "meta": request_obj.get("meta"), "action": request_obj.get("action")}
        except Exception:
            pass

    resp_red = None
    if response_obj:
        resp_red = dict(response_obj)
        try:
            raw = json.dumps(resp_red, ensure_ascii=False).encode("utf-8")
            if len(raw) > max_inline:
                resp_red = {"_truncated": True, "bytes": len(raw), "ok": response_obj.get("ok"), "trace_id": response_obj.get("trace_id")}
        except Exception:
            pass

    incident: Dict[str, Any] = {
        "quarantine_id": quarantine_id,
        "ts": _nowz(),
        "trace_id": trace_id,
        "decision": "quarantine",
        "action": action,
        "reason": reason,
        "actor": actor,
        "artifacts": [],
    }
    if req_red is not None:
        incident["request"] = req_red
    if resp_red is not None:
        incident["response"] = resp_red

    _safe_json_dump(os.path.join(idir, "incident.json"), incident)

    # Optional: capture role context snapshot (best-effort)
    if capture_role_ctx:
        try:
            project_id = str(actor.get("project_id") or "").strip()
            run_id = str(actor.get("run_id") or "").strip()
            if project_id and run_id:
                ctx_path = os.path.join(role_runs_root, project_id, run_id, "context.json")
                if os.path.exists(ctx_path):
                    dst = os.path.join(idir, "role_context.json")
                    shutil.copy2(ctx_path, dst)
                    incident["artifacts"].append({"kind": "role_context", "path": "role_context.json"})
        except Exception:
            pass

    # Optional: capture file metadata for common arg keys
    if capture_file_meta and request_obj:
        try:
            args = request_obj.get("args") or {}
            key_candidates = ["path", "db_path", "cwd"]
            metas: List[Dict[str, Any]] = []
            for k in key_candidates:
                v = args.get(k)
                if isinstance(v, str) and v.strip():
                    p = v.strip()
                    # Only metadata (and sample hash), no full content.
                    metas.append(_file_meta(p, sample_bytes=sample_bytes))
            if metas:
                _safe_json_dump(os.path.join(idir, "file_meta.json"), {"files": metas})
                incident["artifacts"].append({"kind": "file_meta", "path": "file_meta.json"})
        except Exception:
            pass

    # Promote to lifecycle incident (best-effort)
    linked = None
    if promote_to_incidents and open_lifecycle_incident is not None:
        try:
            if not incident_dedupe_key:
                # Stable-ish key: kind|action|reason_hash|source stream/role
                src_stream = str((actor or {}).get("stream_id") or "unknown")
                src_role = str((actor or {}).get("role") or "unknown")
                incident_dedupe_key = f"{incident_kind}:{action}:{_sha256_str(reason)[:16]}:{src_stream}:{src_role}"
            linked = open_lifecycle_incident(
                kind=incident_kind,
                severity=incident_severity,
                title=f"{incident_kind}: {action}",
                details={"trace_id": trace_id, "action": action, "reason": reason},
                source=actor or {},
                tags=["quarantine"],
                artifacts={"quarantine_id": quarantine_id, "quarantine_dir": idir, "snapshot": "incident.json"},
                dedupe_key=incident_dedupe_key,
            )
            incident["linked_incident_id"] = str((linked or {}).get("incident_id") or "")
        except Exception:
            pass

    # Rewrite incident with artifacts / linkage if changed
    try:
        _safe_json_dump(os.path.join(idir, "incident.json"), incident)
    except Exception:
        pass

    # Tighten permissions (best-effort)
    try:
        os.chmod(idir, 0o700)
        for fn in os.listdir(idir):
            os.chmod(os.path.join(idir, fn), 0o600)
    except Exception:
        pass

    return quarantine_id, idir, incident
