#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/ssr_cycle.py
Zone: release/package
Version: 0.31.13.alpha
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
# File: src/ssr_cycle.py
# Purpose: Provide the module 'ssr_cycle'.
# Invoked by / imported from:
#   - src/brainctl.py
#   - src/maintenance.py
# Public API / entry functions:
#   - run
#   - main
# Inputs:
#   - Common path inputs: /var/lib/noemaforge, /opt/noemaforge/configs
#   - Imports: __future__, datetime, json, os, uuid, typing, seclog, epoch
# Output formats / side effects:
#   - JSON files
#   - Markdown files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""ssr_cycle.py (v0.11.5)

SSR (System/Safety Self-Reflection) cycle.

SSR is the "safety meta-layer": it does not run canaries in runtime.
Instead it:
- summarizes security-relevant runtime observations (SEL + quarantine)
- emits roadmap signals (fixtures / glove improvements / policy hardening)
- produces an explicit SSR report artifact

The actual enforcement lives in ToolProxy + policies; SSR just produces a
route of improvements.
"""


import datetime as dt
import json
import os
import uuid
from typing import Any, Dict, List, Optional

from seclog import verify as sel_verify
from seclog import append as sel_append

import epoch
import roadmap

BASE = "/var/lib/noemaforge"
SEL_DIR = os.path.join(BASE, "sel", "segments")
QUAR_DIR = os.path.join(BASE, "quarantine")
PACKETS_SSR = os.path.join(BASE, "packets", "ssr")
PACKETS_SCARY = os.path.join(BASE, "packets", "scary")


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
# Function: _ts_id()
# Purpose: Implement the routine ' ts id'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - src/fixture_bundle.py
#   - src/scary_sweep.py
#   - src/sr_cycle.py
#   - src/surgeon_auto.py
# Calls:
#   - strftime, utcnow
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _ts_id() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


# === NoemaForge Autodoc Function Header ===
# Function: _save_json(path: str, obj)
# Purpose: Implement the routine ' save json'.
# Inputs:
#   - path: str
#   - obj
# Called by:
#   - src/audit_remediation.py
#   - src/noemaforge_core.py
#   - src/fixture_bundle.py
#   - src/model_registry.py
#   - src/model_scorecards.py
#   - src/prestart.py
#   - src/roles/role_entry.py
#   - src/scary_sweep.py
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
def _save_json(path: str, obj: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


# === NoemaForge Autodoc Function Header ===
# Function: _save_md(path: str, lines: List[str])
# Purpose: Implement the routine ' save md'.
# Inputs:
#   - path: str
#   - lines: List[str]
# Called by:
#   - src/sr_cycle.py
#   - src/surgeon_auto.py
# Calls:
#   - makedirs, dirname, open, write, join
# Returns / emits: None
# Side effects:
#   - reads or writes files
#   - creates directories
# Key locals:
#   - f
# === End NoemaForge Autodoc Function Header ===
def _save_md(path: str, lines: List[str]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("".join(lines))


# === NoemaForge Autodoc Function Header ===
# Function: _today()
# Purpose: Implement the routine ' today'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - src/planned_sweep.py
#   - src/scary_sweep.py
#   - src/seclog.py
#   - src/sr_lite.py
# Calls:
#   - strftime, utcnow
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _today() -> str:
    return dt.datetime.utcnow().strftime("%Y-%m-%d")


# === NoemaForge Autodoc Function Header ===
# Function: _read_sel(day: str, limit: int = 600)
# Purpose: Implement the routine ' read sel'.
# Inputs:
#   - day: str
#   - limit: int = 600
# Called by:
#   - src/scary_sweep.py
# Calls:
#   - join, exists, open, rstrip, append, strip, loads
# Returns / emits: List[Dict[str, Any]]
# Side effects:
#   - reads or writes files
#   - appends to logs or files
# Key locals:
#   - f, lines, ln, out, p
# === End NoemaForge Autodoc Function Header ===
def _read_sel(day: str, limit: int = 600) -> List[Dict[str, Any]]:
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
# Function: _count(events: List[Dict[str, Any]], prefix: str)
# Purpose: Implement the routine ' count'.
# Inputs:
#   - events: List[Dict[str, Any]]
#   - prefix: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - sum, startswith, str, get
# Returns / emits: int
# === End NoemaForge Autodoc Function Header ===
def _count(events: List[Dict[str, Any]], prefix: str) -> int:
    return sum(1 for e in events if str(e.get("type") or "").startswith(prefix))


# === NoemaForge Autodoc Function Header ===
# Function: _list_quarantine(limit: int = 80)
# Purpose: Implement the routine ' list quarantine'.
# Inputs:
#   - limit: int = 80
# Called by:
#   - src/scary_sweep.py
# Calls:
#   - walk, sort, isdir, join, endswith, load, append, open, str, isinstance, get
# Returns / emits: List[Dict[str, Any]]
# Side effects:
#   - reads or writes files
#   - appends to logs or files
# Key locals:
#   - fn, obj, out, p
# === End NoemaForge Autodoc Function Header ===
def _list_quarantine(limit: int = 80) -> List[Dict[str, Any]]:
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
                out.append({"path": p, **(obj if isinstance(obj, dict) else {})})
            except Exception:
                continue
    out.sort(key=lambda x: (str(x.get("ts") or ""), str(x.get("incident_id") or "")), reverse=True)
    return out[:limit]


# === NoemaForge Autodoc Function Header ===
# Function: _emit_signal(emitted: List[Dict[str, Any]], target_role: str, key: str, title: str, description: str, source_stream: str = 'system.guard', source_role: str = 'ssr', project_id: str = 'system')
# Purpose: Implement the routine ' emit signal'.
# Inputs:
#   - emitted: List[Dict[str, Any]]
#   - target_role: str
#   - key: str
#   - title: str
#   - description: str
#   - source_stream: str = 'system.guard'
#   - source_role: str = 'ssr'
#   - project_id: str = 'system'
# Called by:
#   - src/scary_sweep.py
#   - src/sr_cycle.py
# Calls:
#   - record_signal, append
# Returns / emits: None
# Side effects:
#   - appends to logs or files
# Key locals:
#   - sig
# === End NoemaForge Autodoc Function Header ===
def _emit_signal(
    *,
    emitted: List[Dict[str, Any]],
    target_role: str,
    key: str,
    title: str,
    description: str,
    source_stream: str = "system.guard",
    source_role: str = "ssr",
    project_id: str = "system",
) -> None:
    try:
        sig = roadmap.record_signal(
            target_role=target_role,
            key=key,
            title=title,
            description=description,
            requested_by={
                "stream_id": source_stream,
                "role": source_role,
                "project_id": project_id,
                "process_id": "maintenance.ssr",
            },
        )
        emitted.append(sig)
    except Exception:
        return


# === NoemaForge Autodoc Function Header ===
# Function: run(max_events: int = 600, export_roles: Optional[List[str]] = None, export_limit: int = 100)
# Purpose: Implement the routine 'run'.
# Inputs:
#   - max_events: int = 600
#   - export_roles: Optional[List[str]] = None
#   - export_limit: int = 100
# Called by:
#   - src/bootdoctor.py
#   - src/brainctl.py
#   - src/firstboot_eval.py
#   - src/hwscan.py
#   - src/knowledge_maintainer.py
#   - src/lan_discovery.py
#   - src/localgateway.py
#   - src/localgw_connectors/ipp.py
# Calls:
#   - makedirs, current_epoch_id, _today, _read_sel, bool, _count, sum, _list_quarantine, _ts_id, join, _save_json, replace
# Returns / emits: Dict[str, Any]
# Side effects:
#   - creates directories
# Key locals:
#   - day, denies, e_dir, eid, emitted, events, export_roles, exports, hand, hand_path, inj, key
# === End NoemaForge Autodoc Function Header ===
def run(
    *,
    max_events: int = 600,
    export_roles: Optional[List[str]] = None,
    export_limit: int = 100,
) -> Dict[str, Any]:
    os.makedirs(PACKETS_SSR, exist_ok=True)
    os.makedirs(PACKETS_SCARY, exist_ok=True)

    eid = epoch.current_epoch_id()
    e_dir = epoch.current_epoch_dir() or "/opt/noemaforge/configs"
    epoch_before = {"epoch_id": eid, "epoch_dir": e_dir}

    day = _today()
    events = _read_sel(day, limit=int(max_events))

    sel_ok = bool(sel_verify(day))

    denies = _count(events, "TOOLPROXY_DENY")
    quarantines = _count(events, "TOOLPROXY_QUARANTINE")
    supply = sum(1 for e in events if "SUPPLY" in str(e.get("type") or ""))
    inj = sum(1 for e in events if "INJECT" in str(e.get("type") or ""))

    qs = _list_quarantine()

    # Metrics snapshot (LLM/flow/incidents) for safety context.
    metrics_snapshot_path = ""
    try:
        from metrics_snapshot import save_snapshot

        metrics_snapshot_path = save_snapshot(window_hours=24)
    except Exception:
        metrics_snapshot_path = ""

    # Emit safety improvement signals
    emitted: List[Dict[str, Any]] = []

    if not sel_ok:
        _emit_signal(
            emitted=emitted,
            target_role="scary",
            key="scary.sel.integrity",
            title="SEL integrity verification failed",
            description="SSR confirms SEL verify failed for today; investigate immediately.",
        )

    if quarantines > 0:
        _emit_signal(
            emitted=emitted,
            target_role="scary",
            key="scary.fixtures.v1",
            title="Evolve security fixtures",
            description=f"Quarantine events observed ({quarantines}). Add/extend fixtures to cover these patterns in pre-start canaries.",
        )
        _emit_signal(
            emitted=emitted,
            target_role="surgeon",
            key="surgeon.prestart_discipline.v1",
            title="Harden pre-start discipline",
            description="Quarantine pressure suggests we should tighten install/update flows and verify bundles before epoch switch.",
        )

    if supply > 0:
        _emit_signal(
            emitted=emitted,
            target_role="scary",
            key="scary.supplychain.audit",
            title="Supply-chain audit",
            description="Supply-chain relevant events detected; review tool/plugin allowlists, hashes and bundle provenance.",
        )

    if inj > 0 or denies > 0:
        _emit_signal(
            emitted=emitted,
            target_role="scary",
            key="scary.gloves.v1",
            title="Improve glove sterilization",
            description="Injection/deny signals suggest more boundaries need gloves (one-shot amnesic SLM) for untrusted content.",
        )

    # Export roadmap reports
    export_roles = export_roles or ["", "ssr", "scary", "surgeon"]
    exports: Dict[str, Dict[str, Any]] = {}
    for r in export_roles:
        key = (r or "ALL").strip() or "ALL"
        try:
            exports[key] = roadmap.export_report(epoch_dir=e_dir, target_role=r if r else None, include_role_roadmaps=True, limit=int(export_limit))
        except Exception as e:
            exports[key] = {"ok": False, "error": repr(e)}

    # Runtime epoch immutability verification
    epoch_after = {"epoch_id": epoch.current_epoch_id(), "epoch_dir": epoch.current_epoch_dir() or "/opt/noemaforge/configs"}
    epoch_immutable_ok = bool(epoch_before == epoch_after)
    paranoia_quality = {
        "signal_count": int(len(emitted)),
        "quarantine_count": int(len(qs)),
        "metrics_snapshot_present": bool(metrics_snapshot_path),
        "epoch_immutable_ok": bool(epoch_immutable_ok),
        "quality_score": float(min(1.0, (len(emitted) * 0.15) + (0.2 if metrics_snapshot_path else 0.0) + (0.3 if epoch_immutable_ok else 0.0) + (0.2 if sel_ok else 0.0))),
    }

    # Build SSR report
    rid = uuid.uuid4().hex
    ts = _ts_id()
    rep = {
        "schema_version": "v1",
        "kind": "SSRReport",
        "report_id": rid,
        "created_at": _nowz(),
        "epoch_id": eid,
        "epoch_dir": e_dir,
        "day": day,
        "epoch_before": epoch_before,
        "epoch_after": epoch_after,
        "epoch_immutable_ok": epoch_immutable_ok,
        "sel_ok": sel_ok,
        "counts": {
            "tool_denies": int(denies),
            "tool_quarantines": int(quarantines),
            "supplychain_events": int(supply),
            "injection_signals": int(inj),
            "quarantine_incidents": int(len(qs)),
        },
        "metrics_snapshot": metrics_snapshot_path,
        "latest_quarantine": [
            {"incident_id": q.get("incident_id"), "reason": q.get("reason"), "action": q.get("action"), "path": q.get("path")}
            for q in qs[:10]
        ],
        "roadmap_exports": {
            k: {"report_path": v.get("report_path"), "markdown_path": v.get("markdown_path"), "ok": bool(v.get("ok", True))}
            for k, v in exports.items()
        },
        "paranoia_quality": paranoia_quality,
        "signals_emitted": [
            {"signal_id": s.get("signal_id"), "target_role": s.get("target_role"), "key": s.get("key"), "created_at": s.get("created_at")}
            for s in emitted
        ],
        "paranoia_notes": [
            "SSR is the sword-and-shield loop: internal red-team knowledge is used to strengthen the shield.",
            "No runtime canaries; propose fixtures and suites for pre-start only.",
        ],
    }

    out_json = os.path.join(PACKETS_SSR, f"{ts}_ssr_report.json")
    _save_json(out_json, rep)

    out_md = out_json.replace(".json", ".md")
    md = [f"# SSR report ({ts})\n\n", f"day: {day}\n\n", f"SEL integrity: {'OK' if sel_ok else '**FAIL**'}\n\n"]
    md.append("## Counters\n")
    for k, v in rep.get("counts", {}).items():
        md.append(f"- {k}: {v}\n")
    if metrics_snapshot_path:
        md.append(f"\n## Metrics snapshot\n- {metrics_snapshot_path}\n")
    md.append("\n## Signals emitted\n")
    if emitted:
        for s in emitted:
            md.append(f"- **{s.get('target_role')}** `{s.get('key')}` ({s.get('signal_id')})\n")
    else:
        md.append("- (none)\n")
    md.append("\n## Quarantine (latest)\n")
    for q in rep.get("latest_quarantine", []):
        md.append(f"- {q.get('incident_id')} — {q.get('reason')} ({q.get('action')})\n")
    _save_md(out_md, md)

    # Handoff to scary (SSR is a meta-layer, but scary executes)
    hand = {
        "schema_version": "v1",
        "kind": "HandoffPacket",
        "created_at": rep["created_at"],
        "from": {"role": "ssr"},
        "to": {"role": "scary"},
        "epoch_id": eid,
        "ssr_report": out_json,
        "metrics_snapshot": metrics_snapshot_path,
        "notes": [
            "Review quarantine incidents with gloves; convert patterns into fixtures and canary suites (pre-start).",
            "LocalGW/WebGW changes must be proposed as pre-start requests; runtime must remain immutable.",
        ],
    }
    hand_path = os.path.join(PACKETS_SCARY, f"{ts}_handoff_from_ssr.json")
    _save_json(hand_path, hand)

    try:
        sel_append(
            {
                "evt_id": os.urandom(8).hex(),
                "ts": rep["created_at"],
                "severity": "S1" if sel_ok else "S3",
                "type": "SSR_REPORT",
                "actor": {"role": "ssr"},
                "decision": "emit",
                "trace_id": os.urandom(8).hex(),
                "report": out_json,
                "handoff_scary": hand_path,
            }
        )
    except Exception:
        pass

    return {
        "ok": True,
        "ssr_report": out_json,
        "ssr_report_md": out_md,
        "handoff_scary": hand_path,
        "roadmap_exports": exports,
        "signals_emitted": emitted,
        "sel_ok": sel_ok,
        "counts": rep.get("counts"),
    }


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
#   - run, print, get
# Returns / emits: int
# Side effects:
#   - spawns subprocesses or workers
# Key locals:
#   - rep
# === End NoemaForge Autodoc Function Header ===
def main() -> int:
    rep = run()
    print(rep.get("ssr_report"))
    return 0 if rep.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
