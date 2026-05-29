#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/incidents.py
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
# File: src/incidents.py
# Purpose: Provide the module 'incidents'.
# Invoked by / imported from:
#   - src/audit_remediation.py
#   - src/brainctl.py
#   - src/incident_metrics.py
#   - src/nids_lite.py
#   - src/quarantine.py
#   - src/scary_sweep.py
#   - src/task_runner.py
#   - src/toolproxy.py
# Public API / entry functions:
#   - open_incident
#   - update_incident
#   - attach_artifact
#   - get_incident
#   - list_incidents
# Inputs:
#   - Common path inputs: /var/lib/noemaforge, /opt/noemaforge/configs/incident-policy.yaml
#   - Imports: __future__, datetime, hashlib, json, os, re, sqlite3, typing
# Output formats / side effects:
#   - SQLite databases
#   - JSON files
#   - YAML files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""incidents.py (v0.12.3)

Incident lifecycle (spine) + incident-driven roadmap signals.

New in v0.12.3:
- ToolProxy deny/quarantine and quarantine snapshots are promoted to first-class Incidents.
- Repeated Incidents can emit Roadmap signals (thresholded) to drive SR/SSR/Scary/Surgeon work,
  without any runtime policy mutation.

Design notes:
- Incidents are JSON files (human inspectable) + a sqlite index for listing.
- Deduplication via dedupe_key allows repeat counting across equivalent events.
- Roadmap emission is conservative: threshold crossings only, controlled by an epoch-scoped
  IncidentPolicy contract (incident-policy.yaml). If unavailable, safe defaults apply.

Constraints:
- No network.
- Deterministic defaults.
- No contract/policy changes at runtime.
"""


import datetime as dt
import hashlib
import json
import os
import re
import sqlite3
from typing import Any, Dict, List, Optional

from seclog import append as sel_append

# Optional: emit roadmap signals (offline-first).
try:  # pragma: no cover
    from roadmap import record_signal as roadmap_record_signal
except Exception:  # pragma: no cover
    roadmap_record_signal = None  # type: ignore

try:  # pragma: no cover
    import yaml
except Exception:  # pragma: no cover
    yaml = None  # type: ignore

try:  # pragma: no cover
    from epoch import current_epoch_dir
except Exception:  # pragma: no cover
    current_epoch_dir = None  # type: ignore


BASE = "/var/lib/noemaforge"
INC_DIR = os.path.join(BASE, "incidents")
DB_PATH = os.path.join(INC_DIR, "incidents.db")

# Default policy locations (epoch overrides are preferred).
DEFAULT_POLICY_PATH = "/opt/noemaforge/configs/incident-policy.yaml"

KIND_RE = re.compile(r"^[a-z0-9_]{1,64}$")
ID_RE = re.compile(r"^[a-f0-9]{16,64}$")

STATUS_OPEN = "open"
STATUS_ACK = "acknowledged"
STATUS_ESC = "escalated"
STATUS_CLOSED = "closed"

ALLOWED_STATUSES = {STATUS_OPEN, STATUS_ACK, STATUS_ESC, STATUS_CLOSED}
ALLOWED_ACTIONS = {"ack": STATUS_ACK, "close": STATUS_CLOSED, "escalate": STATUS_ESC}


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
# Function: _safe_kind(kind: str)
# Purpose: Implement the routine ' safe kind'.
# Inputs:
#   - kind: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - lower, replace, sub, strip, match
# Returns / emits: str
# Key locals:
#   - k
# === End NoemaForge Autodoc Function Header ===
def _safe_kind(kind: str) -> str:
    k = (kind or "").strip().lower()
    k = k.replace("-", "_").replace(" ", "_")
    k = re.sub(r"[^a-z0-9_]+", "_", k)
    k = k.strip("_") or "generic"
    if not KIND_RE.match(k):
        return "generic"
    return k


# === NoemaForge Autodoc Function Header ===
# Function: _mk_id()
# Purpose: Implement the routine ' mk id'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - hex, urandom
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _mk_id() -> str:
    return os.urandom(12).hex() + os.urandom(4).hex()


# === NoemaForge Autodoc Function Header ===
# Function: _sha256(s: str)
# Purpose: Implement the routine ' sha256'.
# Inputs:
#   - s: str
# Called by:
#   - src/fixture_autogen.py
# Calls:
#   - hexdigest, sha256, encode
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _sha256(s: str) -> str:
    return hashlib.sha256((s or "").encode("utf-8", errors="ignore")).hexdigest()


# === NoemaForge Autodoc Function Header ===
# Function: _ensure_db()
# Purpose: Implement the routine ' ensure db'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - makedirs, connect, execute, commit, close
# Returns / emits: None
# Side effects:
#   - opens a database or socket connection
#   - executes SQL or shell-like commands
#   - creates directories
# Key locals:
#   - con
# === End NoemaForge Autodoc Function Header ===
def _ensure_db() -> None:
    os.makedirs(INC_DIR, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    try:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS incidents (
              incident_id TEXT PRIMARY KEY,
              kind TEXT NOT NULL,
              severity TEXT NOT NULL,
              status TEXT NOT NULL,
              title TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              dedupe_key TEXT,
              path TEXT NOT NULL
            );
            """
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_incidents_status ON incidents(status);")
        con.execute("CREATE INDEX IF NOT EXISTS idx_incidents_kind ON incidents(kind);")
        con.execute("CREATE INDEX IF NOT EXISTS idx_incidents_dedupe ON incidents(dedupe_key);")
        con.commit()
    finally:
        con.close()


# === NoemaForge Autodoc Function Header ===
# Function: _obj_path(kind: str, incident_id: str)
# Purpose: Implement the routine ' obj path'.
# Inputs:
#   - kind: str
#   - incident_id: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _safe_kind, join, makedirs
# Returns / emits: str
# Side effects:
#   - creates directories
# Key locals:
#   - d, k
# === End NoemaForge Autodoc Function Header ===
def _obj_path(kind: str, incident_id: str) -> str:
    k = _safe_kind(kind)
    d = os.path.join(INC_DIR, k)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{incident_id}.json")


# === NoemaForge Autodoc Function Header ===
# Function: _load_obj(path: str)
# Purpose: Implement the routine ' load obj'.
# Inputs:
#   - path: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - load, open
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads or writes files
# === End NoemaForge Autodoc Function Header ===
def _load_obj(path: str) -> Dict[str, Any]:
    return json.load(open(path, "r", encoding="utf-8"))


# === NoemaForge Autodoc Function Header ===
# Function: _save_obj(path: str, obj: Dict[str, Any])
# Purpose: Implement the routine ' save obj'.
# Inputs:
#   - path: str
#   - obj: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
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
def _save_obj(path: str, obj: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


# === NoemaForge Autodoc Function Header ===
# Function: _sel_emit(evt_type: str, payload: Dict[str, Any], severity: str = 'S1')
# Purpose: Implement the routine ' sel emit'.
# Inputs:
#   - evt_type: str
#   - payload: Dict[str, Any]
#   - severity: str = 'S1'
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - sel_append, hex, _nowz, urandom
# Returns / emits: None
# Side effects:
#   - appends to logs or files
# === End NoemaForge Autodoc Function Header ===
def _sel_emit(evt_type: str, payload: Dict[str, Any], severity: str = "S1") -> None:
    try:
        sel_append(
            {
                "evt_id": os.urandom(8).hex(),
                "ts": _nowz(),
                "severity": severity,
                "type": evt_type,
                "actor": {"subsystem": "incidents"},
                "decision": "record",
                "trace_id": os.urandom(8).hex(),
                **payload,
            }
        )
    except Exception:
        pass


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
# Function: _policy_path()
# Purpose: Implement the routine ' policy path'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - src/fixture_bundle.py
#   - src/llm_backends_manager.py
#   - src/telemetry.py
# Calls:
#   - current_epoch_dir, join, exists
# Returns / emits: str
# Key locals:
#   - cand, e
# === End NoemaForge Autodoc Function Header ===
def _policy_path() -> str:
    # Prefer epoch-scoped policy if available.
    try:
        if current_epoch_dir is not None:
            e = current_epoch_dir()
            if e:
                cand = os.path.join(e, "incident-policy.yaml")
                if os.path.exists(cand):
                    return cand
    except Exception:
        pass
    return DEFAULT_POLICY_PATH


# === NoemaForge Autodoc Function Header ===
# Function: _policy()
# Purpose: Implement the routine ' policy'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - setdefault, _load_yaml, isinstance, get, _policy_path
# Returns / emits: Dict[str, Any]
# Key locals:
#   - pol, rm
# === End NoemaForge Autodoc Function Header ===
def _policy() -> Dict[str, Any]:
    pol = _load_yaml(_policy_path()) or {}
    # Safe defaults: roadmap emission ON, conservative thresholds.
    if not isinstance(pol, dict):
        pol = {}
    if "roadmap" not in pol or not isinstance(pol.get("roadmap"), dict):
        pol["roadmap"] = {
            "enabled": True,
            "repeat_thresholds": [3, 6, 12],
            "default_targets": ["scary"],
            "kind_overrides": {},
        }
    rm = pol.get("roadmap") or {}
    rm.setdefault("enabled", True)
    rm.setdefault("repeat_thresholds", [3, 6, 12])
    rm.setdefault("default_targets", ["scary"])
    rm.setdefault("kind_overrides", {})
    pol["roadmap"] = rm
    return pol


# === NoemaForge Autodoc Function Header ===
# Function: _roadmap_targets(kind: str, pol: Dict[str, Any])
# Purpose: Implement the routine ' roadmap targets'.
# Inputs:
#   - kind: str
#   - pol: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _safe_kind, isinstance, get, str, strip
# Returns / emits: Dict[str, Any]
# Key locals:
#   - kd, ov, overrides, rm
# === End NoemaForge Autodoc Function Header ===
def _roadmap_targets(kind: str, pol: Dict[str, Any]) -> Dict[str, Any]:
    rm = pol.get("roadmap") or {}
    overrides = rm.get("kind_overrides") or {}
    kd = _safe_kind(kind)
    ov = overrides.get(kd) if isinstance(overrides, dict) else None
    if isinstance(ov, dict):
        return {
            "targets": [str(x) for x in (ov.get("targets") or []) if str(x).strip()] or [str(x) for x in (rm.get("default_targets") or [])],
            "key_prefix": str(ov.get("key_prefix") or f"security.incident.{kd}"),
        }
    return {
        "targets": [str(x) for x in (rm.get("default_targets") or []) if str(x).strip()] or ["scary"],
        "key_prefix": f"security.incident.{kd}",
    }


# === NoemaForge Autodoc Function Header ===
# Function: _merge_related_artifact(obj: Dict[str, Any], art: Dict[str, Any])
# Purpose: Implement the routine ' merge related artifact'.
# Inputs:
#   - obj: Dict[str, Any]
#   - art: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - setdefault, get, append, isinstance, _nowz
# Returns / emits: None
# Side effects:
#   - appends to logs or files
# Key locals:
#   - rel
# === End NoemaForge Autodoc Function Header ===
def _merge_related_artifact(obj: Dict[str, Any], art: Dict[str, Any]) -> None:
    if not art:
        return
    obj.setdefault("artifacts", {})
    if not isinstance(obj.get("artifacts"), dict):
        obj["artifacts"] = {}
    rel = obj["artifacts"].get("related")
    if not isinstance(rel, list):
        rel = []
    rel.append({"ts": _nowz(), **art})
    obj["artifacts"]["related"] = rel


# === NoemaForge Autodoc Function Header ===
# Function: _maybe_emit_roadmap(obj: Dict[str, Any], kind: str, source: Dict[str, Any], pol: Dict[str, Any])
# Purpose: Implement the routine ' maybe emit roadmap'.
# Inputs:
#   - obj: Dict[str, Any]
#   - kind: str
#   - source: Dict[str, Any]
#   - pol: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - int, sorted, get, set, _roadmap_targets, str, bool, isinstance, add, _safe_kind, roadmap_record_signal, isdigit
# Returns / emits: None
# Key locals:
#   - emitted, emitted_set, key_prefix, mapinfo, repeats, rm, sev, t, targets, thresholds, title, trg
# === End NoemaForge Autodoc Function Header ===
def _maybe_emit_roadmap(obj: Dict[str, Any], *, kind: str, source: Dict[str, Any], pol: Dict[str, Any]) -> None:
    # Conservative: only emit on threshold crossings, and only if roadmap is available.
    rm = pol.get("roadmap") or {}
    if not bool(rm.get("enabled", True)):
        return
    if roadmap_record_signal is None:
        return

    repeats = int(obj.get("repeats") or 0)
    thresholds = [int(x) for x in (rm.get("repeat_thresholds") or []) if int(x) > 0]
    thresholds = sorted(set(thresholds))
    if not thresholds:
        return

    emitted = obj.get("roadmap_emitted_thresholds")
    if not isinstance(emitted, list):
        emitted = []
    emitted_set = set(int(x) for x in emitted if isinstance(x, int) or (isinstance(x, str) and str(x).isdigit()))

    mapinfo = _roadmap_targets(kind, pol)
    targets = mapinfo.get("targets") or []
    key_prefix = str(mapinfo.get("key_prefix") or f"security.incident.{_safe_kind(kind)}")

    # Avoid putting raw sensitive details into the roadmap; keep it structural.
    title = str(obj.get("title") or f"Incident: {_safe_kind(kind)}")
    sev = str(obj.get("severity") or "S2")

    for t in thresholds:
        if repeats >= t and t not in emitted_set:
            for trg in targets:
                try:
                    roadmap_record_signal(
                        target_role=trg,
                        key=f"{key_prefix}.repeat.{t}",
                        requested_by=source or {"stream_id": "system.guard", "role": "incidents"},
                        title=f"{sev} {title} (repeat≥{t})",
                        description=f"Incident kind={_safe_kind(kind)} repeats={repeats} status={obj.get('status')}",
                    )
                except Exception:
                    pass
            emitted_set.add(t)

    obj["roadmap_emitted_thresholds"] = sorted(emitted_set)


# === NoemaForge Autodoc Function Header ===
# Function: _find_by_dedupe(con: sqlite3.Connection, dedupe_key: str)
# Purpose: Implement the routine ' find by dedupe'.
# Inputs:
#   - con: sqlite3.Connection
#   - dedupe_key: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - execute, fetchone
# Returns / emits: Optional[Dict[str, Any]]
# Side effects:
#   - executes SQL or shell-like commands
# Key locals:
#   - cur, row
# === End NoemaForge Autodoc Function Header ===
def _find_by_dedupe(con: sqlite3.Connection, dedupe_key: str) -> Optional[Dict[str, Any]]:
    if not dedupe_key:
        return None
    cur = con.execute(
        "SELECT incident_id, kind, severity, status, title, created_at, updated_at, dedupe_key, path FROM incidents "
        "WHERE dedupe_key=? AND status!=? ORDER BY created_at DESC LIMIT 1",
        (dedupe_key, STATUS_CLOSED),
    )
    row = cur.fetchone()
    if not row:
        return None
    return {
        "incident_id": row[0],
        "kind": row[1],
        "severity": row[2],
        "status": row[3],
        "title": row[4],
        "created_at": row[5],
        "updated_at": row[6],
        "dedupe_key": row[7],
        "path": row[8],
    }


# === NoemaForge Autodoc Function Header ===
# Function: open_incident(kind: str, severity: str, title: str, details: Optional[Dict[str, Any]] = None, source: Optional[Dict[str, Any]] = None, tags: Optional[List[str]] = None, artifacts: Optional[Dict[str, Any]] = None, dedupe_key: str = '')
# Purpose: Open an incident (or return existing via dedupe_key).
# Inputs:
#   - kind: str
#   - severity: str
#   - title: str
#   - details: Optional[Dict[str, Any]] = None
#   - source: Optional[Dict[str, Any]] = None
#   - tags: Optional[List[str]] = None
#   - artifacts: Optional[Dict[str, Any]] = None
#   - dedupe_key: str = ''
# Called by:
#   - src/audit_remediation.py
#   - src/brainctl.py
#   - src/nids_lite.py
# Calls:
#   - _ensure_db, _policy, _safe_kind, upper, connect, _sel_emit, strip, str, _mk_id, _nowz, _obj_path, _save_obj
# Returns / emits: Dict[str, Any]
# Side effects:
#   - opens a database or socket connection
# Key locals:
#   - art, con, created, d, existing, incident_id, k, meta, obj, path, pol, sev
# === End NoemaForge Autodoc Function Header ===
def open_incident(
    *,
    kind: str,
    severity: str,
    title: str,
    details: Optional[Dict[str, Any]] = None,
    source: Optional[Dict[str, Any]] = None,
    tags: Optional[List[str]] = None,
    artifacts: Optional[Dict[str, Any]] = None,
    dedupe_key: str = "",
) -> Dict[str, Any]:
    """Open an incident (or return existing via dedupe_key).

    Returns metadata including incident_id and path.
    """
    _ensure_db()
    pol = _policy()

    k = _safe_kind(kind)
    sev = (severity or "S2").strip().upper()
    ttl = (title or "").strip() or f"Incident: {k}"
    d = details or {}
    src = source or {}
    tg = [str(x) for x in (tags or []) if str(x).strip()]
    art = artifacts or {}

    con = sqlite3.connect(DB_PATH)
    try:
        existing = _find_by_dedupe(con, dedupe_key) if dedupe_key else None
        if existing:
            # Update object history with a "repeat" marker + merge artifacts best-effort.
            try:
                obj = _load_obj(existing["path"])
                obj["updated_at"] = _nowz()
                obj.setdefault("repeats", 0)
                obj["repeats"] = int(obj.get("repeats") or 0) + 1
                obj.setdefault("history", []).append(
                    {
                        "ts": _nowz(),
                        "action": "repeat",
                        "actor": {"subsystem": "incidents"},
                        "comment": "dedupe_key match; increment repeat counter",
                    }
                )
                if art:
                    _merge_related_artifact(obj, art)
                # Keep the last seen details snapshot in a safe, bounded way.
                if d:
                    obj["details_last"] = d
                _maybe_emit_roadmap(obj, kind=k, source=src, pol=pol)
                _save_obj(existing["path"], obj)
                con.execute("UPDATE incidents SET updated_at=? WHERE incident_id=?", (obj["updated_at"], existing["incident_id"]))
                con.commit()
            except Exception:
                pass
            _sel_emit("INCIDENT_REPEAT", {"incident": existing, "dedupe_key": dedupe_key}, severity="S1")
            return {"ok": True, "deduped": True, **existing}

        incident_id = _mk_id()
        created = _nowz()
        obj = {
            "schema_version": "v1",
            "kind": "Incident",
            "incident_id": incident_id,
            "incident_kind": k,
            "severity": sev,
            "status": STATUS_OPEN,
            "title": ttl,
            "created_at": created,
            "updated_at": created,
            "dedupe_key": dedupe_key or "",
            "repeats": 0,
            "source": src,
            "tags": tg,
            "details": d,
            "artifacts": art,
            "roadmap_emitted_thresholds": [],
            "history": [
                {
                    "ts": created,
                    "action": "open",
                    "actor": {"subsystem": "incidents"},
                    "comment": "opened",
                }
            ],
        }
        path = _obj_path(k, incident_id)
        _save_obj(path, obj)

        con.execute(
            "INSERT INTO incidents (incident_id, kind, severity, status, title, created_at, updated_at, dedupe_key, path) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (incident_id, k, sev, STATUS_OPEN, ttl, created, created, dedupe_key or None, path),
        )
        con.commit()
    finally:
        con.close()

    meta = {
        "incident_id": incident_id,
        "kind": k,
        "severity": sev,
        "status": STATUS_OPEN,
        "title": ttl,
        "created_at": created,
        "updated_at": created,
        "dedupe_key": dedupe_key or "",
        "path": path,
    }
    _sel_emit("INCIDENT_OPENED", {"incident": meta}, severity=sev if sev.startswith("S") else "S2")
    return {"ok": True, **meta}


# === NoemaForge Autodoc Function Header ===
# Function: update_incident(incident_id: str, action: str, actor: Optional[Dict[str, Any]] = None, comment: str = '')
# Purpose: Update incident state by action: ack/close/escalate.
# Inputs:
#   - incident_id: str
#   - action: str
#   - actor: Optional[Dict[str, Any]] = None
#   - comment: str = ''
# Called by:
#   - src/brainctl.py
#   - src/task_runner.py
# Calls:
#   - lower, strip, _ensure_db, connect, _sel_emit, ValueError, execute, fetchone, _load_obj, _nowz, append, _save_obj
# Returns / emits: Dict[str, Any]
# Side effects:
#   - opens a database or socket connection
#   - executes SQL or shell-like commands
#   - appends to logs or files
# Key locals:
#   - act, cmt, con, cur, iid, meta, new_status, obj, row, who
# === End NoemaForge Autodoc Function Header ===
def update_incident(*, incident_id: str, action: str, actor: Optional[Dict[str, Any]] = None, comment: str = "") -> Dict[str, Any]:
    """Update incident state by action: ack/close/escalate."""
    iid = (incident_id or "").strip().lower()
    if not iid or not ID_RE.match(iid):
        raise ValueError("invalid_incident_id")
    act = (action or "").strip().lower()
    if act not in ALLOWED_ACTIONS:
        raise ValueError("invalid_action")
    new_status = ALLOWED_ACTIONS[act]
    who = actor or {"subsystem": "unknown"}
    cmt = (comment or "").strip()

    _ensure_db()
    con = sqlite3.connect(DB_PATH)
    try:
        cur = con.execute("SELECT path, status, severity, kind, title FROM incidents WHERE incident_id=?", (iid,))
        row = cur.fetchone()
        if not row:
            raise FileNotFoundError("incident_not_found")
        path, old_status, sev, kind, title = row[0], row[1], row[2], row[3], row[4]

        obj = _load_obj(path)
        obj["updated_at"] = _nowz()
        obj["status"] = new_status
        obj.setdefault("history", []).append({"ts": obj["updated_at"], "action": act, "actor": who, "comment": cmt})
        _save_obj(path, obj)

        con.execute("UPDATE incidents SET status=?, updated_at=? WHERE incident_id=?", (new_status, obj["updated_at"], iid))
        con.commit()
    finally:
        con.close()

    meta = {
        "incident_id": iid,
        "kind": kind,
        "severity": sev,
        "title": title,
        "from": old_status,
        "to": new_status,
        "path": path,
    }
    _sel_emit("INCIDENT_UPDATED", {"update": meta, "actor": who, "comment": cmt}, severity=sev if str(sev).startswith("S") else "S2")
    return {"ok": True, **meta}


# === NoemaForge Autodoc Function Header ===
# Function: attach_artifact(incident_id: str, artifact: Dict[str, Any], actor: Optional[Dict[str, Any]] = None, comment: str = '')
# Purpose: Attach a related artifact to an Incident without changing status/repeats.
# Inputs:
#   - incident_id: str
#   - artifact: Dict[str, Any]
#   - actor: Optional[Dict[str, Any]] = None
#   - comment: str = ''
# Called by:
#   - src/scary_sweep.py
#   - src/task_runner.py
# Calls:
#   - lower, strip, _ensure_db, connect, _sel_emit, ValueError, execute, fetchone, _load_obj, _nowz, append, _save_obj
# Returns / emits: Dict[str, Any]
# Side effects:
#   - opens a database or socket connection
#   - executes SQL or shell-like commands
#   - appends to logs or files
# Key locals:
#   - cmt, con, cur, iid, meta, obj, row, who
# === End NoemaForge Autodoc Function Header ===
def attach_artifact(
    *,
    incident_id: str,
    artifact: Dict[str, Any],
    actor: Optional[Dict[str, Any]] = None,
    comment: str = "",
) -> Dict[str, Any]:
    """Attach a related artifact to an Incident without changing status/repeats.

    Used for linking:
    - generated fixture IDs
    - draft PreStartChangeRequest IDs
    - quarantine snapshot paths
    """

    iid = (incident_id or "").strip().lower()
    if not iid or not ID_RE.match(iid):
        raise ValueError("invalid_incident_id")
    who = actor or {"subsystem": "unknown"}
    cmt = (comment or "").strip()

    _ensure_db()
    con = sqlite3.connect(DB_PATH)
    try:
        cur = con.execute("SELECT path, severity, kind, title FROM incidents WHERE incident_id=?", (iid,))
        row = cur.fetchone()
        if not row:
            raise FileNotFoundError("incident_not_found")
        path, sev, kind, title = row[0], row[1], row[2], row[3]

        obj = _load_obj(path)
        obj["updated_at"] = _nowz()
        if artifact:
            _merge_related_artifact(obj, artifact)
        obj.setdefault("history", []).append(
            {
                "ts": obj["updated_at"],
                "action": "attach_artifact",
                "actor": who,
                "comment": cmt,
                "artifact_kind": str(artifact.get("kind") or "related"),
            }
        )
        _save_obj(path, obj)

        con.execute("UPDATE incidents SET updated_at=? WHERE incident_id=?", (obj["updated_at"], iid))
        con.commit()
    finally:
        con.close()

    meta = {"incident_id": iid, "kind": kind, "severity": sev, "title": title, "path": path}
    _sel_emit(
        "INCIDENT_ARTIFACT",
        {"incident": meta, "actor": who, "comment": cmt, "artifact": artifact},
        severity=str(sev) if str(sev).startswith("S") else "S2",
    )
    return {"ok": True, **meta}


# === NoemaForge Autodoc Function Header ===
# Function: get_incident(incident_id: str)
# Purpose: Implement the routine 'get incident'.
# Inputs:
#   - incident_id: str
# Called by:
#   - src/brainctl.py
#   - src/task_runner.py
# Calls:
#   - lower, _ensure_db, connect, _load_obj, ValueError, execute, fetchone, close, strip, match, FileNotFoundError
# Returns / emits: Dict[str, Any]
# Side effects:
#   - opens a database or socket connection
#   - executes SQL or shell-like commands
# Key locals:
#   - con, cur, iid, path, row
# === End NoemaForge Autodoc Function Header ===
def get_incident(incident_id: str) -> Dict[str, Any]:
    iid = (incident_id or "").strip().lower()
    if not iid or not ID_RE.match(iid):
        raise ValueError("invalid_incident_id")
    _ensure_db()
    con = sqlite3.connect(DB_PATH)
    try:
        cur = con.execute("SELECT path FROM incidents WHERE incident_id=?", (iid,))
        row = cur.fetchone()
        if not row:
            raise FileNotFoundError("incident_not_found")
        path = row[0]
    finally:
        con.close()
    return _load_obj(path)


# === NoemaForge Autodoc Function Header ===
# Function: list_incidents(status: str = '', kind: str = '', limit: int = 50)
# Purpose: Implement the routine 'list incidents'.
# Inputs:
#   - status: str = ''
#   - kind: str = ''
#   - limit: int = 50
# Called by:
#   - src/brainctl.py
#   - src/scary_sweep.py
# Calls:
#   - _ensure_db, lower, max, append, connect, _safe_kind, min, execute, fetchall, close, strip, int
# Returns / emits: List[Dict[str, Any]]
# Side effects:
#   - opens a database or socket connection
#   - executes SQL or shell-like commands
#   - appends to logs or files
# Key locals:
#   - args, con, cur, kd, lim, out, q, r, rows, st, where
# === End NoemaForge Autodoc Function Header ===
def list_incidents(status: str = "", kind: str = "", limit: int = 50) -> List[Dict[str, Any]]:
    _ensure_db()
    st = (status or "").strip().lower()
    kd = _safe_kind(kind) if kind else ""
    lim = max(1, min(int(limit or 50), 500))

    where = []
    args: List[Any] = []
    if st:
        where.append("status=?")
        args.append(st)
    if kd:
        where.append("kind=?")
        args.append(kd)
    q = "SELECT incident_id, kind, severity, status, title, created_at, updated_at, dedupe_key, path FROM incidents"
    if where:
        q += " WHERE " + " AND ".join(where)
    q += " ORDER BY created_at DESC LIMIT ?"
    args.append(lim)

    con = sqlite3.connect(DB_PATH)
    try:
        cur = con.execute(q, tuple(args))
        rows = cur.fetchall()
    finally:
        con.close()

    out = []
    for r in rows:
        out.append(
            {
                "incident_id": r[0],
                "kind": r[1],
                "severity": r[2],
                "status": r[3],
                "title": r[4],
                "created_at": r[5],
                "updated_at": r[6],
                "dedupe_key": r[7] or "",
                "path": r[8],
            }
        )
    return out
