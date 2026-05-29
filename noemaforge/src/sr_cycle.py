#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/sr_cycle.py
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
# File: src/sr_cycle.py
# Purpose: Provide the module 'sr_cycle'.
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

"""sr_cycle.py (v0.11.5)

SR (Self-Reflection) cycle for NoemaForge.

This module exists to make SR/SSR less "magical":
- SR produces explicit artifacts (reports + roadmap exports)
- SR emits roadmap *signals* (repeatable, attributable)
- SR creates handoff packets for Surgeon and Scary

Important: SR is deterministic in MVP (no LLM). It must be safe offline.
"""


import datetime as dt
import json
import os
import uuid
from typing import Any, Dict, List, Optional

from seclog import append as sel_append

import epoch
import roadmap
from sr_lite import run as sr_lite_run

BASE = "/var/lib/noemaforge"
PACKETS_SR = os.path.join(BASE, "packets", "sr")
PACKETS_SURGEON = os.path.join(BASE, "packets", "surgeon")
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
#   - src/ssr_cycle.py
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
#   - src/ssr_cycle.py
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
# Function: _emit_signal(emitted: List[Dict[str, Any]], target_role: str, key: str, title: str, description: str, source_stream: str = 'system.guard', source_role: str = 'sr', project_id: str = 'system')
# Purpose: Implement the routine ' emit signal'.
# Inputs:
#   - emitted: List[Dict[str, Any]]
#   - target_role: str
#   - key: str
#   - title: str
#   - description: str
#   - source_stream: str = 'system.guard'
#   - source_role: str = 'sr'
#   - project_id: str = 'system'
# Called by:
#   - src/scary_sweep.py
#   - src/ssr_cycle.py
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
    source_role: str = "sr",
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
                "process_id": "maintenance.sr",
            },
        )
        emitted.append(sig)
    except Exception:
        return


# === NoemaForge Autodoc Function Header ===
# Function: run(max_events: int = 600, export_roles: Optional[List[str]] = None, export_limit: int = 100, include_role_roadmaps: bool = True)
# Purpose: Run SR cycle.
# Inputs:
#   - max_events: int = 600
#   - export_roles: Optional[List[str]] = None
#   - export_limit: int = 100
#   - include_role_roadmaps: bool = True
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
#   - makedirs, current_epoch_id, sr_lite_run, int, bool, _ts_id, join, _save_json, replace, append, items, _save_md
# Returns / emits: Dict[str, Any]
# Side effects:
#   - creates directories
#   - spawns subprocesses or workers
#   - appends to logs or files
# Key locals:
#   - counts, denies, e_dir, eid, emitted, export_roles, exports, hand_scary, hand_surgeon, hc_json, hs_json, key
# === End NoemaForge Autodoc Function Header ===
def run(
    *,
    max_events: int = 600,
    export_roles: Optional[List[str]] = None,
    export_limit: int = 100,
    include_role_roadmaps: bool = True,
) -> Dict[str, Any]:
    """Run SR cycle.

    Returns a dict with paths to SR artifacts.
    """
    os.makedirs(PACKETS_SR, exist_ok=True)

    eid = epoch.current_epoch_id()
    e_dir = epoch.current_epoch_dir() or "/opt/noemaforge/configs"
    epoch_before = {"epoch_id": eid, "epoch_dir": e_dir}

    # 1) SR-lite base scan
    sr_lite_path, findings = sr_lite_run(max_events=int(max_events))

    counts = (findings.get("counts") or {}) if isinstance(findings, dict) else {}
    denies = int(counts.get("tool_denies") or 0)
    quarantines = int(counts.get("tool_quarantines") or 0)
    memcrit = int(counts.get("mem_critical") or 0)
    rec_fail = int(counts.get("recurring_failed") or 0)
    missing_daily = int(counts.get("missing_daily") or 0)
    sel_ok = bool(findings.get("sel_ok", True))

    # 1.5) Unified metrics snapshot (LLM/flow/incidents) to ground SR roadmaps.
    # Best-effort: SR must never fail due to metrics.
    metrics_snapshot_path = ""
    try:
        from metrics_snapshot import save_snapshot

        metrics_snapshot_path = save_snapshot(window_hours=24)
        if isinstance(counts, dict):
            counts["metrics_snapshot"] = metrics_snapshot_path
    except Exception:
        metrics_snapshot_path = ""

    # 2) Emit roadmap signals (repeat raises priority)
    emitted: List[Dict[str, Any]] = []

    if not sel_ok:
        _emit_signal(
            emitted=emitted,
            target_role="scary",
            key="scary.sel.integrity",
            title="SEL integrity verification failed",
            description="SR-lite detected sel_ok=false. Treat as tampering/disk issue until proven otherwise.",
        )

    if quarantines > 0:
        _emit_signal(
            emitted=emitted,
            target_role="scary",
            key="scary.quarantine.review",
            title="Review quarantine incidents",
            description=f"SR-lite saw {quarantines} ToolProxy quarantine events today; generate/extend fixtures and glove flows.",
        )

    if denies > 0:
        _emit_signal(
            emitted=emitted,
            target_role="solution_architect",
            key="arch.tool_policy.gaps",
            title="Tool policy gaps (denies)",
            description=f"SR-lite saw {denies} ToolProxy denies today. Likely missing capability contracts or package pre-start step.",
        )

    if rec_fail > 0:
        _emit_signal(
            emitted=emitted,
            target_role="solution_architect",
            key="arch.recurring.failures",
            title="Recurring task failures",
            description=f"SR-lite saw {rec_fail} recurring failures. Needs clearer verifier/contract or better error surfacing.",
        )

    if missing_daily > 0:
        _emit_signal(
            emitted=emitted,
            target_role="pm",
            key="pm.daily.sla",
            title="Daily SLA tasks missing",
            description=f"SR-lite saw {missing_daily} must-run daily tasks missing. Check due windows and per-task resource needs.",
        )

    if memcrit > 0:
        _emit_signal(
            emitted=emitted,
            target_role="sr",
            key="sr.memory.pressure",
            title="Memory pressure reached M2/M3",
            description="Memory pressure was critical. Improve spill policies + context compaction for the next epoch.",
        )
        _emit_signal(
            emitted=emitted,
            target_role="surgeon",
            key="surgeon.memory.spill",
            title="Improve spill/compaction plan",
            description="Critical memory pressure indicates we need better spill-to-storage and context checkpointing contracts.",
        )

    # 3) Export roadmap reports (for SR/SSR/Surgeon/Scary and ALL)
    export_roles = export_roles or ["", "surgeon", "scary", "sr", "ssr", "solution_architect"]
    exports: Dict[str, Dict[str, Any]] = {}
    for r in export_roles:
        key = (r or "ALL").strip() or "ALL"
        try:
            exports[key] = roadmap.export_report(
                epoch_dir=e_dir,
                target_role=r if r else None,
                include_role_roadmaps=include_role_roadmaps,
                limit=int(export_limit),
            )
        except Exception as e:
            exports[key] = {"ok": False, "error": repr(e)}

    # 3.5) Runtime epoch immutability verification
    epoch_after = {"epoch_id": epoch.current_epoch_id(), "epoch_dir": epoch.current_epoch_dir() or "/opt/noemaforge/configs"}
    epoch_immutable_ok = bool(epoch_before == epoch_after)

    rec_count = len(findings.get("recommendations") or []) if isinstance(findings, dict) else 0
    signal_count = len(emitted)
    reflection_quality = {
        "recommendation_count": int(rec_count),
        "signal_count": int(signal_count),
        "metrics_snapshot_present": bool(metrics_snapshot_path),
        "epoch_immutable_ok": bool(epoch_immutable_ok),
        "quality_score": float(min(1.0, (rec_count * 0.2) + (signal_count * 0.1) + (0.2 if metrics_snapshot_path else 0.0) + (0.3 if epoch_immutable_ok else 0.0))),
    }

    # 4) SR report artifact
    rid = uuid.uuid4().hex
    ts = _ts_id()
    report = {
        "schema_version": "v1",
        "kind": "SRReport",
        "report_id": rid,
        "created_at": _nowz(),
        "epoch_id": eid,
        "epoch_dir": e_dir,
        "inputs": {"max_events": int(max_events)},
        "epoch_before": epoch_before,
        "epoch_after": epoch_after,
        "epoch_immutable_ok": epoch_immutable_ok,
        "sr_lite": {"path": sr_lite_path, "counts": counts, "sel_ok": sel_ok},
        "metrics_snapshot": metrics_snapshot_path,
        "roadmap_exports": {
            k: {"report_path": v.get("report_path"), "markdown_path": v.get("markdown_path"), "ok": bool(v.get("ok", True))}
            for k, v in exports.items()
        },
        "signals_emitted": [
            {"signal_id": s.get("signal_id"), "target_role": s.get("target_role"), "key": s.get("key"), "created_at": s.get("created_at")}
            for s in emitted
        ],
        "recommendations": findings.get("recommendations") if isinstance(findings, dict) else [],
        "reflection_quality": reflection_quality,
        "notes": [
            "SR is deterministic in MVP. It emits roadmap artifacts + signals, but does not change contracts.",
            "Repeated signals increase priority; multiple sources increase priority even faster.",
        ],
    }

    out_json = os.path.join(PACKETS_SR, f"{ts}_sr_report.json")
    _save_json(out_json, report)

    out_md = out_json.replace(".json", ".md")
    md = [f"# SR report ({ts})\n\n", f"epoch_id: {eid}\n\n"]
    md.append(f"SR-lite: {sr_lite_path}\n\n")
    md.append("## Counters\n")
    for k, v in (counts or {}).items():
        md.append(f"- {k}: {v}\n")
    if metrics_snapshot_path:
        md.append(f"\n## Metrics snapshot\n- {metrics_snapshot_path}\n")
    md.append("\n## Signals emitted\n")
    if emitted:
        for s in emitted:
            md.append(f"- **{s.get('target_role')}** `{s.get('key')}` ({s.get('signal_id')})\n")
    else:
        md.append("- (none)\n")
    md.append("\n## Roadmap exports\n")
    for k, v in exports.items():
        if v.get("ok"):
            md.append(f"- {k}: {v.get('report_path')}\n")
        else:
            md.append(f"- {k}: (failed) {v.get('error')}\n")
    _save_md(out_md, md)

    # 5) Handoff packets for Surgeon + Scary (Step 2 in your intended idle-cycle)
    os.makedirs(PACKETS_SURGEON, exist_ok=True)
    os.makedirs(PACKETS_SCARY, exist_ok=True)

    hand_surgeon = {
        "schema_version": "v1",
        "kind": "HandoffPacket",
        "created_at": report["created_at"],
        "from": {"role": "sr"},
        "to": {"role": "surgeon"},
        "epoch_id": eid,
        "sr_report": out_json,
        "metrics_snapshot": metrics_snapshot_path,
        "roadmap_report_all": exports.get("ALL", {}).get("report_path"),
        "roadmap_report_surgeon": exports.get("surgeon", {}).get("report_path"),
        "notes": [
            "Surgeon may plan experiments and propose pre-start requests; no runtime contract/policy changes.",
            "Prefer sterile analysis via gloves (one-shot amnesic SLM) when reviewing untrusted inputs.",
            "For critical steps: do a second pass and compare conclusions (multilingual prompts in future).",
        ],
    }
    hand_scary = {
        "schema_version": "v1",
        "kind": "HandoffPacket",
        "created_at": report["created_at"],
        "from": {"role": "sr"},
        "to": {"role": "scary"},
        "epoch_id": eid,
        "sr_report": out_json,
        "metrics_snapshot": metrics_snapshot_path,
        "roadmap_report_all": exports.get("ALL", {}).get("report_path"),
        "roadmap_report_scary": exports.get("scary", {}).get("report_path"),
        "notes": [
            "Scary owns airlocks (webgw/localgw) and quarantine workflow.",
            "No runtime canaries; propose fixtures and canary suites for pre-start.",
        ],
    }

    hs_json = os.path.join(PACKETS_SURGEON, f"{ts}_handoff_from_sr.json")
    hc_json = os.path.join(PACKETS_SCARY, f"{ts}_handoff_from_sr.json")
    _save_json(hs_json, hand_surgeon)
    _save_json(hc_json, hand_scary)

    # SEL record
    try:
        sel_append(
            {
                "evt_id": os.urandom(8).hex(),
                "ts": report["created_at"],
                "severity": "S1" if sel_ok else "S3",
                "type": "SR_REPORT",
                "actor": {"role": "sr"},
                "decision": "emit",
                "trace_id": os.urandom(8).hex(),
                "report": out_json,
                "handoff_surgeon": hs_json,
                "handoff_scary": hc_json,
            }
        )
    except Exception:
        pass

    return {
        "ok": True,
        "sr_report": out_json,
        "sr_report_md": out_md,
        "sr_lite": sr_lite_path,
        "handoff_surgeon": hs_json,
        "handoff_scary": hc_json,
        "roadmap_exports": exports,
        "signals_emitted": emitted,
        "counts": counts,
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
    print(rep.get("sr_report"))
    return 0 if rep.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
