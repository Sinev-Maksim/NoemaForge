#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/scary_sweep.py
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
# File: src/scary_sweep.py
# Purpose: Provide the module 'scary_sweep'.
# Invoked by / imported from:
#   - No inbound Python import detected; treat as library leaf or direct entrypoint.
# Public API / entry functions:
#   - sweep
#   - main
# Inputs:
#   - Common path inputs: /var/lib/noemaforge, /workspace/outbox/scary/fixtures, /opt/noemaforge/configs/incident-policy.yaml, /var/lib/noemaforge/.sys/fixture_samples/quarantine, noemaforge.prestart/v1, /opt/noemaforge/configs
#   - Imports: __future__, datetime, json, os, uuid, typing, seclog, epoch
# Output formats / side effects:
#   - JSON files
#   - YAML files
#   - Markdown files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""scary_sweep.py (v0.12.6)

"Scary" (security persona) sweep.

Runs in the SECURITY domain during maintenance dispatch.

What it does (MVP):
- Summarize quarantine incidents and tool denials
- Emit roadmap signals to grow fixtures/gloves/supply-chain checks
- Export roadmap reports (explicit route; repetition increases priority)
- Produce a ScaryReport packet

Constraints:
- No runtime canaries (only pre-start unless user explicitly requests)
- No network required

New in v0.12.6:
- Auto-generation is now **TaskQueue-first**:
    repeated Incident -> SECURITY task (security.autogen_fixture) -> stage -> bundle -> draft PreStartChangeRequest
  This keeps runtime deterministic and avoids spamming many tiny requests.
"""


import datetime as dt
import json
import os
import uuid
from typing import Any, Dict, List

from seclog import verify as sel_verify
from seclog import append as sel_append

import epoch
import roadmap
import nids_lite

try:
    import taskqueue
except Exception:  # pragma: no cover
    taskqueue = None  # type: ignore

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None  # type: ignore

try:
    from fixture_autogen import fixture_from_incident, fixtures_patch_for_fixture, canonical_fixture_digest
except Exception:  # pragma: no cover
    fixture_from_incident = None  # type: ignore
    fixtures_patch_for_fixture = None  # type: ignore
    canonical_fixture_digest = None  # type: ignore

try:
    import incidents
except Exception:  # pragma: no cover
    incidents = None  # type: ignore


BASE = "/var/lib/noemaforge"
SEL_DIR = os.path.join(BASE, "sel", "segments")
QUAR_DIR = os.path.join(BASE, "quarantine")
PACKETS_DIR = os.path.join(BASE, "packets", "scary")

DEFAULT_REQUESTS_DIR = os.path.join(BASE, "requests", "prestart")
DEFAULT_OUTBOX_DIR = "/workspace/outbox/scary/fixtures"
DEFAULT_STATE_PATH = os.path.join(BASE, ".sys", "scary_autogen_fixtures.json")

# Fixture autogen now stages in runtime state, then bundles into one prestart request.
DEFAULT_STAGING_DIR = os.path.join(BASE, ".sys", "fixture_autogen", "staging")


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
# Function: _today()
# Purpose: Implement the routine ' today'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - src/planned_sweep.py
#   - src/seclog.py
#   - src/sr_lite.py
#   - src/ssr_cycle.py
# Calls:
#   - strftime, utcnow
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _today() -> str:
    return dt.datetime.utcnow().strftime("%Y-%m-%d")


# === NoemaForge Autodoc Function Header ===
# Function: _ts_id()
# Purpose: Implement the routine ' ts id'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - src/fixture_bundle.py
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
# Function: _read_sel(day: str, limit: int = 400)
# Purpose: Implement the routine ' read sel'.
# Inputs:
#   - day: str
#   - limit: int = 400
# Called by:
#   - src/ssr_cycle.py
# Calls:
#   - join, exists, open, rstrip, append, strip, loads
# Returns / emits: List[Dict[str, Any]]
# Side effects:
#   - reads or writes files
#   - appends to logs or files
# Key locals:
#   - f, lines, ln, out, p
# === End NoemaForge Autodoc Function Header ===
def _read_sel(day: str, limit: int = 400) -> List[Dict[str, Any]]:
    p = os.path.join(SEL_DIR, f"{day}.jsonl")
    if not os.path.exists(p):
        return []
    out: List[Dict[str, Any]] = []
    try:
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            lines = [ln.rstrip("\n") for ln in f if ln.strip()]
        for ln in lines[-limit:]:
            try:
                out.append(json.loads(ln))
            except Exception:
                continue
    except Exception:
        return []
    return out


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
    if yaml is None:
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


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
#   - src/team_installer_plan.py
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
# Function: _save_json(path: str, obj: Dict[str, Any])
# Purpose: Implement the routine ' save json'.
# Inputs:
#   - path: str
#   - obj: Dict[str, Any]
# Called by:
#   - src/audit_remediation.py
#   - src/noemaforge_core.py
#   - src/fixture_bundle.py
#   - src/model_registry.py
#   - src/model_scorecards.py
#   - src/prestart.py
#   - src/roles/role_entry.py
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
# Function: _fixture_ids_from_epoch(epoch_dir: str)
# Purpose: Implement the routine ' fixture ids from epoch'.
# Inputs:
#   - epoch_dir: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - join, _load_yaml, exists, get, isinstance, strip, append, str
# Returns / emits: List[str]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - doc, fx, out, p
# === End NoemaForge Autodoc Function Header ===
def _fixture_ids_from_epoch(epoch_dir: str) -> List[str]:
    p = os.path.join(epoch_dir, "security-fixtures.yaml")
    doc = _load_yaml(p) if p and os.path.exists(p) else {}
    out: List[str] = []
    for fx in (doc.get("fixtures") or []) or []:
        if isinstance(fx, dict) and str(fx.get("id") or "").strip():
            out.append(str(fx.get("id")).strip())
    return out


# === NoemaForge Autodoc Function Header ===
# Function: _autogen_cfg(epoch_dir: str)
# Purpose: Implement the routine ' autogen cfg'.
# Inputs:
#   - epoch_dir: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - join, bool, str, lower, exists, _load_yaml, isinstance, get, int, strip
# Returns / emits: Dict[str, Any]
# Key locals:
#   - bundle, emit_mode, fx, p, paths, pol, qsample_dir, use_qsamples
# === End NoemaForge Autodoc Function Header ===
def _autogen_cfg(epoch_dir: str) -> Dict[str, Any]:
    # Use epoch-scoped incident policy if present.
    p = os.path.join(epoch_dir, "incident-policy.yaml")
    pol = _load_yaml(p) if os.path.exists(p) else _load_yaml("/opt/noemaforge/configs/incident-policy.yaml")
    fx = pol.get("fixtures") if isinstance(pol, dict) else None
    if not isinstance(fx, dict):
        fx = {}

    paths = fx.get("paths") if isinstance(fx.get("paths"), dict) else {}

    use_qsamples = bool(fx.get("use_quarantine_samples", True))
    # Optional: where to store *slim* quarantine samples (hash-only references).
    qsample_dir = str(paths.get("quarantine_sample_store_dir") or "/var/lib/noemaforge/.sys/fixture_samples/quarantine")
    if not use_qsamples:
        qsample_dir = ""

    bundle = fx.get("bundle") if isinstance(fx.get("bundle"), dict) else {}
    emit_mode = str(fx.get("emit_mode") or "tasks").strip().lower()

    return {
        "enabled": bool(fx.get("enabled", True)),
        "emit_mode": emit_mode,
        "min_repeats": int(fx.get("min_repeats", 3) or 3),
        "max_new_requests": int(fx.get("max_new_requests_per_sweep", 5) or 5),
        "kinds": fx.get("kinds") if isinstance(fx.get("kinds"), dict) else {},
        "requests_dir": str(paths.get("requests_dir") or DEFAULT_REQUESTS_DIR),
        "outbox_dir": str(paths.get("outbox_dir") or DEFAULT_OUTBOX_DIR),
        "state_path": str(paths.get("state_path") or DEFAULT_STATE_PATH),
        "requires_canary": str(fx.get("requires_canary") or "full"),
        "quarantine_sample_store_dir": qsample_dir,
        "use_quarantine_samples": use_qsamples,

        # New: taskqueue + staging/bundling
        "staging_dir": str(paths.get("staging_dir") or DEFAULT_STAGING_DIR),
        "bundle_enabled": bool(bundle.get("enabled", True)),
    }


# === NoemaForge Autodoc Function Header ===
# Function: _severity_to_priority(sev: str)
# Purpose: Implement the routine ' severity to priority'.
# Inputs:
#   - sev: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - upper, startswith, strip, str
# Returns / emits: str
# Key locals:
#   - s
# === End NoemaForge Autodoc Function Header ===
def _severity_to_priority(sev: str) -> str:
    s = str(sev or "S2").strip().upper()
    # Conservative mapping: only S3+ becomes urgent.
    if s.startswith("S4") or s.startswith("S5"):
        return "critical"
    if s.startswith("S3"):
        return "urgent"
    return "normal"


# === NoemaForge Autodoc Function Header ===
# Function: _maybe_enqueue_fixture_tasks(epoch_dir: str, open_incidents: List[Dict[str, Any]])
# Purpose: Enqueue SECURITY tasks that will stage + bundle fixture drafts.
# Inputs:
#   - epoch_dir: str
#   - open_incidents: List[Dict[str, Any]]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _autogen_cfg, max, bool, lower, int, min, get, str, _severity_to_priority, load, enqueue_task, append
# Returns / emits: List[Dict[str, Any]]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - cfg, gk, iid, ik, kinds_allow, max_new, meta, min_rep, obj, out, p, payload
# === End NoemaForge Autodoc Function Header ===
def _maybe_enqueue_fixture_tasks(
    *,
    epoch_dir: str,
    open_incidents: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Enqueue SECURITY tasks that will stage + bundle fixture drafts.

    This is TaskQueue-first. If TaskQueue is unavailable, returns empty.
    """

    if taskqueue is None:
        return []

    cfg = _autogen_cfg(epoch_dir)
    if not bool(cfg.get("enabled")):
        return []
    if str(cfg.get("emit_mode") or "tasks").strip().lower() != "tasks":
        return []

    min_rep = max(1, int(cfg.get("min_repeats") or 3))
    max_new = max(0, min(50, int(cfg.get("max_new_requests") or 5)))
    kinds_allow = cfg.get("kinds") or {}

    out: List[Dict[str, Any]] = []
    for meta in open_incidents:
        if max_new and len(out) >= max_new:
            break
        try:
            p = str(meta.get("path") or "")
            if not p or not os.path.exists(p):
                continue
            obj = json.load(open(p, "r", encoding="utf-8"))
        except Exception:
            continue

        ik = str(obj.get("incident_kind") or meta.get("kind") or "").strip().lower()
        if kinds_allow and not bool(kinds_allow.get(ik, False)):
            continue

        repeats = int(obj.get("repeats") or 0)
        if repeats < min_rep:
            continue

        iid = str(obj.get("incident_id") or "").strip().lower()
        if not iid:
            continue

        sev = str(obj.get("severity") or "S2")
        pr = _severity_to_priority(sev)

        # One task per incident; repeats auto-boost priority.
        gk = f"security.autogen_fixture:{iid}"
        payload = {"incident_id": iid, "incident_path": p}
        try:
            res = taskqueue.enqueue_task(
                domain="SECURITY",
                kind="security.autogen_fixture",
                priority_class=pr,
                title=f"Autogen security fixture from incident {iid}",
                description=f"Generate staged fixture draft from repeated incident (kind={ik}, repeats={repeats}).",
                payload=payload,
                group_key=gk,
            )
            out.append({"task": res, "incident_id": iid, "kind": ik, "repeats": repeats})
        except Exception:
            continue

    # Best-effort: enqueue a bundle flush task (deduped). The autogen task will
    # also enqueue flush after staging, so this is just a safety net.
    if out:
        try:
            taskqueue.enqueue_task(
                domain="SECURITY",
                kind="security.flush_fixture_bundle",
                priority_class="background",
                title="Flush staged security fixture bundle",
                description="Bundle staged fixtures into a single draft PreStartChangeRequest.",
                payload={},
                group_key="security.flush_fixture_bundle",
            )
        except Exception:
            pass

    return out


# === NoemaForge Autodoc Function Header ===
# Function: _maybe_autogen_fixture_requests(epoch_dir: str, open_incidents: List[Dict[str, Any]])
# Purpose: Create draft prestart requests that add new SecurityFixtures entries.
# Inputs:
#   - epoch_dir: str
#   - open_incidents: List[Dict[str, Any]]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _autogen_cfg, max, set, _load_json, makedirs, _nowz, bool, int, min, get, _fixture_ids_from_epoch, str
# Returns / emits: List[Dict[str, Any]]
# Side effects:
#   - creates directories
# Key locals:
#   - cfg, digest, emitted, existing_ids, f, fid, fx, ik, kinds_allow, max_new, meta, min_rep
# === End NoemaForge Autodoc Function Header ===
def _maybe_autogen_fixture_requests(
    *,
    epoch_dir: str,
    open_incidents: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Create draft prestart requests that add new SecurityFixtures entries.

    Returns a list of emitted request metadata.
    """
    if fixture_from_incident is None or fixtures_patch_for_fixture is None:
        return []

    cfg = _autogen_cfg(epoch_dir)
    if not bool(cfg.get("enabled")):
        return []

    min_rep = max(1, int(cfg.get("min_repeats") or 3))
    max_new = max(0, min(50, int(cfg.get("max_new_requests") or 5)))
    kinds_allow = cfg.get("kinds") or {}

    existing_ids = set(_fixture_ids_from_epoch(epoch_dir))

    st = _load_json(str(cfg.get("state_path")))
    emitted = st.get("emitted") if isinstance(st.get("emitted"), dict) else {}

    os.makedirs(str(cfg.get("requests_dir")), exist_ok=True)
    os.makedirs(str(cfg.get("outbox_dir")), exist_ok=True)

    out: List[Dict[str, Any]] = []
    for meta in open_incidents:
        if max_new and len(out) >= max_new:
            break
        try:
            p = str(meta.get("path") or "")
            if not p or not os.path.exists(p):
                continue
            obj = json.load(open(p, "r", encoding="utf-8"))
        except Exception:
            continue

        # Filter by kind (optional)
        ik = str(obj.get("incident_kind") or meta.get("kind") or "").strip().lower()
        if kinds_allow:
            if not bool(kinds_allow.get(ik, False)):
                continue

        repeats = int(obj.get("repeats") or 0)
        if repeats < min_rep:
            continue

        fx = fixture_from_incident(obj, quarantine_sample_store_dir=str(cfg.get("quarantine_sample_store_dir") or ""))
        if not fx:
            continue
        fid = str(fx.get("id") or "").strip()
        if not fid:
            continue

        if fid in existing_ids:
            continue

        digest = canonical_fixture_digest(fx) if canonical_fixture_digest is not None else fid
        if str(emitted.get(fid) or "") == str(digest):
            continue

        # Build draft prestart request
        rid = f"scary-fixture-{_ts_id()}-{uuid.uuid4().hex[:8]}"
        req = {
            "apiVersion": "noemaforge.prestart/v1",
            "kind": "PreStartChangeRequest",
            "schema_version": "v1",
            "request_id": rid,
            "created_at": _nowz(),
            "created_by": {"actor_type": "scary", "actor_id": "scary_sweep"},
            "status": "draft",
            "track": "policy",
            "risk_level": "medium",
            "requires_canary": str(cfg.get("requires_canary") or "full"),
            "user_comment": f"AUTO-GENERATED from repeated incident {obj.get('incident_id')} (kind={ik}, repeats={repeats}). Review in PRE-START.",
            "requested_changes": {
                "security_fixtures_patch": fixtures_patch_for_fixture(fx),
            },
            "notes": [
                "No runtime canaries: this request only adds a fixture. It will execute during PRE-START FULL canary.",
                "Autogen is conservative (deny expectations) and redacts secrets.",
            ],
        }

        # Write to outbox + queue
        outbox_path = os.path.join(str(cfg.get("outbox_dir")), f"{rid}.prestart_request.yaml")
        queue_path = os.path.join(str(cfg.get("requests_dir")), f"{rid}.yaml")
        try:
            with open(outbox_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(req, f, sort_keys=False, allow_unicode=True)  # type: ignore
            with open(queue_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(req, f, sort_keys=False, allow_unicode=True)  # type: ignore
        except Exception:
            continue

        # Mark state so we don't spam identical fixtures.
        emitted[fid] = digest
        out.append({"request_id": rid, "fixture_id": fid, "incident_id": str(obj.get("incident_id") or ""), "outbox": outbox_path, "queue": queue_path})

        # Attach to Incident object for traceability (best-effort)
        try:
            if incidents and hasattr(incidents, "attach_artifact"):
                incidents.attach_artifact(
                    incident_id=str(obj.get("incident_id") or ""),
                    artifact={"kind": "security_fixture_request", "fixture_id": fid, "request_id": rid, "path": queue_path},
                    actor={"subsystem": "scary_sweep", "role": "scary"},
                    comment="autogen fixture request",
                )
        except Exception:
            pass

    st["updated_at"] = _nowz()
    st["emitted"] = emitted
    try:
        _save_json(str(cfg.get("state_path")), st)
    except Exception:
        pass

    return out


# === NoemaForge Autodoc Function Header ===
# Function: _count_prefix(events: List[Dict[str, Any]], prefix: str)
# Purpose: Implement the routine ' count prefix'.
# Inputs:
#   - events: List[Dict[str, Any]]
#   - prefix: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - sum, startswith, str, get
# Returns / emits: int
# === End NoemaForge Autodoc Function Header ===
def _count_prefix(events: List[Dict[str, Any]], prefix: str) -> int:
    return sum(1 for e in events if str(e.get("type") or "").startswith(prefix))


# === NoemaForge Autodoc Function Header ===
# Function: _list_quarantine(limit: int = 50)
# Purpose: Implement the routine ' list quarantine'.
# Inputs:
#   - limit: int = 50
# Called by:
#   - src/ssr_cycle.py
# Calls:
#   - walk, sort, isdir, join, endswith, load, isinstance, append, open, str, get
# Returns / emits: List[Dict[str, Any]]
# Side effects:
#   - reads or writes files
#   - appends to logs or files
# Key locals:
#   - fn, obj, out, p
# === End NoemaForge Autodoc Function Header ===
def _list_quarantine(limit: int = 50) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not os.path.isdir(QUAR_DIR):
        return out
    for root, _dirs, files in os.walk(QUAR_DIR):
        for fn in files:
            if not fn.endswith(".json"):
                continue
            p = os.path.join(root, fn)
            try:
                obj = json.load(open(p, "r", encoding="utf-8"))
                if isinstance(obj, dict):
                    obj = {"path": p, **obj}
                else:
                    obj = {"path": p, "raw": obj}
                out.append(obj)
            except Exception:
                continue
    out.sort(key=lambda x: (str(x.get("ts") or ""), str(x.get("incident_id") or "")), reverse=True)
    return out[:limit]


# === NoemaForge Autodoc Function Header ===
# Function: _emit_signal(emitted: List[Dict[str, Any]], key: str, title: str, description: str)
# Purpose: Implement the routine ' emit signal'.
# Inputs:
#   - emitted: List[Dict[str, Any]]
#   - key: str
#   - title: str
#   - description: str
# Called by:
#   - src/sr_cycle.py
#   - src/ssr_cycle.py
# Calls:
#   - record_signal, append
# Returns / emits: None
# Side effects:
#   - appends to logs or files
# Key locals:
#   - sig
# === End NoemaForge Autodoc Function Header ===
def _emit_signal(emitted: List[Dict[str, Any]], key: str, title: str, description: str) -> None:
    try:
        sig = roadmap.record_signal(
            target_role="scary",
            key=key,
            title=title,
            description=description,
            requested_by={"stream_id": "system.guard", "role": "scary", "project_id": "system", "process_id": "maintenance.scary"},
        )
        emitted.append(sig)
    except Exception:
        return


# === NoemaForge Autodoc Function Header ===
# Function: sweep()
# Purpose: Implement the routine 'sweep'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - src/planned_sweep.py
# Calls:
#   - makedirs, current_epoch_id, _today, _read_sel, _count_prefix, bool, _list_quarantine, _ts_id, join, replace, append, items
# Returns / emits: Dict[str, Any]
# Side effects:
#   - creates directories
#   - appends to logs or files
# Key locals:
#   - all_inc, cfg_fx, day, denies, e_dir, eid, emit_mode, emitted, events, export_all, export_scary, f
# === End NoemaForge Autodoc Function Header ===
def sweep() -> Dict[str, Any]:
    os.makedirs(PACKETS_DIR, exist_ok=True)

    eid = epoch.current_epoch_id()
    e_dir = epoch.current_epoch_dir() or "/opt/noemaforge/configs"

    day = _today()
    events = _read_sel(day)
    denies = _count_prefix(events, "TOOLPROXY_DENY")
    quarantines = _count_prefix(events, "TOOLPROXY_QUARANTINE")
    sel_ok = bool(sel_verify(day))

    qs = _list_quarantine()

    # Incidents (first-class lifecycle objects)
    open_incidents: List[Dict[str, Any]] = []
    try:
        if incidents:
            all_inc = incidents.list_incidents(limit=200)
            open_incidents = [x for x in all_inc if str(x.get('status') or '') != 'closed']
    except Exception:
        open_incidents = []

    # NIDS-lite (local network hygiene)
    nids_report: Dict[str, Any] = {"ok": False, "reason": "not_run"}
    try:
        okn, repn, _ = nids_lite.snapshot_and_analyze(epoch_dir=e_dir, actor={"role": "scary", "process_id": "maintenance.scary"}, trace_id=str(uuid.uuid4().hex), force=False)
        if okn:
            nids_report = repn or {}
        else:
            nids_report = repn or {"ok": False, "reason": "nids_failed"}
    except Exception as e:
        nids_report = {"ok": False, "error": repr(e)}

    if str(nids_report.get("decision") or "") == "quarantine":
        _emit_signal(
            emitted,
            "scary.localnet.quarantine",
            "Local network quarantine triggered",
            "NIDS-lite detected unknown LAN devices. Consider blocking LAN access and updating allowlist/policies.",
        )

    # Autogen fixtures (pre-start canary scenarios) from repeated incidents.
    # v0.12.6: prefer TaskQueue-first staging+bundling.
    fixture_tasks: List[Dict[str, Any]] = []
    fixture_requests: List[Dict[str, Any]] = []
    try:
        cfg_fx = _autogen_cfg(e_dir)
        emit_mode = str(cfg_fx.get("emit_mode") or "tasks").strip().lower()
        if emit_mode == "tasks":
            fixture_tasks = _maybe_enqueue_fixture_tasks(epoch_dir=e_dir, open_incidents=open_incidents)
        else:
            fixture_requests = _maybe_autogen_fixture_requests(epoch_dir=e_dir, open_incidents=open_incidents)
    except Exception:
        fixture_tasks = []
        fixture_requests = []

    emitted: List[Dict[str, Any]] = []
    if not sel_ok:
        _emit_signal(
            emitted,
            "scary.sel.integrity",
            "SEL integrity verification failed",
            "SEL verify failed for today; treat as tampering/disk issue until proven otherwise.",
        )
    if quarantines > 0:
        _emit_signal(
            emitted,
            "scary.fixtures.v1",
            "Evolve security fixtures",
            f"Saw {quarantines} quarantine events; convert patterns into pre-start fixtures/canaries.",
        )
        _emit_signal(
            emitted,
            "scary.gloves.v1",
            "Improve glove sterilization",
            "Quarantine pressure suggests more untrusted inputs should be processed via one-shot glove agents.",
        )
    if denies > 0:
        _emit_signal(
            emitted,
            "scary.tool_misuse",
            "Tool misuse/overreach checks",
            f"Saw {denies} denies; review patterns for misaligned tool usage or injection attempts.",
        )

    # Roadmap exports
    try:
        export_scary = roadmap.export_report(epoch_dir=e_dir, target_role="scary", include_role_roadmaps=True, limit=80)
        export_all = roadmap.export_report(epoch_dir=e_dir, target_role=None, include_role_roadmaps=True, limit=80)
    except Exception as e:
        export_scary = {"ok": False, "error": repr(e)}
        export_all = {"ok": False, "error": repr(e)}

    report_id = uuid.uuid4().hex
    ts = _ts_id()
    rep = {
        "schema_version": "v1",
        "kind": "ScaryReport",
        "report_id": report_id,
        "created_at": _nowz(),
        "epoch_id": eid,
        "day": day,
        "sel_ok": sel_ok,
        "nids": nids_report,
        "counts": {
            "tool_denies": int(denies),
            "tool_quarantines": int(quarantines),
            "quarantine_incidents": int(len(qs)),
            "open_incidents": int(len(open_incidents)),
            "autogen_fixture_tasks": int(len(fixture_tasks)),
            "autogen_fixture_requests": int(len(fixture_requests)),
        },
        "latest_incidents": [
            {
                "incident_id": i.get("incident_id"),
                "kind": i.get("kind"),
                "severity": i.get("severity"),
                "status": i.get("status"),
                "title": i.get("title"),
                "created_at": i.get("created_at"),
            }
            for i in open_incidents[:10]
        ],
        "latest_quarantine": [
            {"incident_id": q.get("incident_id"), "reason": q.get("reason"), "action": q.get("action"), "path": q.get("path")}
            for q in qs[:10]
        ],
        "roadmaps": {
            "all": {"report_path": export_all.get("report_path"), "ok": export_all.get("ok", True)},
            "scary": {"report_path": export_scary.get("report_path"), "ok": export_scary.get("ok", True)},
        },
        "signals_emitted": [
            {"signal_id": s.get("signal_id"), "key": s.get("key"), "created_at": s.get("created_at")}
            for s in emitted
        ],
        "fixture_tasks": fixture_tasks,
        "fixture_requests": fixture_requests,
        "recommendations": [
            "Maintain airlocks: WebGW and LocalGW are subordinate to Scary.",
            "Convert every repeated quarantine pattern into a fixture + pre-start canary.",
            "Use gloves for untrusted content: emails, web pages, RSS entries, attachments.",
        ],
    }

    out_json = os.path.join(PACKETS_DIR, f"{ts}_scary_report.json")
    tmp = out_json + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=2)
    os.replace(tmp, out_json)

    out_md = out_json.replace(".json", ".md")
    md = []
    md.append(f"# Scary sweep report ({ts})\n\n")
    md.append(f"day: {day}\n\n")
    md.append(f"SEL: {'OK' if sel_ok else '**FAIL**'}\n\n")
    md.append("## Counters\n")
    for k, v in rep.get("counts", {}).items():
        md.append(f"- {k}: {v}\n")
    md.append("\n## Incidents (open/active)\n")
    if rep.get("latest_incidents"):
        for it in rep.get("latest_incidents"):
            md.append(f"- {it.get('incident_id')} [{it.get('severity')} {it.get('status')}] {it.get('title')}\n")
    else:
        md.append("- (none)\n")

    md.append("\n## Quarantine (latest)\n")
    for q in rep.get("latest_quarantine", []):
        md.append(f"- {q.get('incident_id')} — {q.get('reason')} ({q.get('action')})\n")
    md.append("\n## Roadmaps\n")
    md.append(f"- ALL: {export_all.get('report_path') if export_all.get('ok') else '(failed)'}\n")
    md.append(f"- scary: {export_scary.get('report_path') if export_scary.get('ok') else '(failed)'}\n")
    with open(out_md, "w", encoding="utf-8") as f:
        f.write("".join(md))

    try:
        sel_append(
            {
                "evt_id": os.urandom(8).hex(),
                "ts": rep["created_at"],
                "severity": "S1" if sel_ok else "S3",
                "type": "SCARY_SWEEP",
                "actor": {"role": "scary"},
                "decision": "emit",
                "trace_id": os.urandom(8).hex(),
                "report": out_json,
            }
        )
    except Exception:
        pass

    return {"ok": True, "report": out_json, "markdown": out_md}


# === NoemaForge Autodoc Function Header ===
# Function: main()
# Purpose: Implement the routine 'main'.
# Inputs:
#   - No explicit parameters.
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
#   - sweep, print, get
# Returns / emits: int
# Key locals:
#   - rep
# === End NoemaForge Autodoc Function Header ===
def main() -> int:
    rep = sweep()
    print(rep.get("report"))
    return 0 if rep.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
