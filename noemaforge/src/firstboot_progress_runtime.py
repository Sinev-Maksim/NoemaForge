#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/firstboot_progress_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Render and validate human-readable firstboot progress from JSON status/events artifacts.
Inputs: Firstboot Progress View policy, firstboot status/events, staffing summary and offline examples.
Outputs: FirstbootProgressView JSON or text progress output.
Side effects: None; CLI writes to stdout.
Tests: noemaforge/tests/test_firstboot_progress_runtime.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Sequence


SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import unified_registry_runtime as urr


API_VERSION = "noemaforge.firstboot-progress-view/v1"
POLICY_KIND = "FirstbootProgressViewPolicy"
SET_KIND = "FirstbootProgressViewExampleSet"
VIEW_KIND = "FirstbootProgressView"
REPORT_KIND = "FirstbootProgressViewValidationReport"

VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,220}$")
REQUIRED_PHASES = [
    "seed_copy",
    "host_preflight",
    "vault_scan",
    "inbox_normalize",
    "candidate_staging",
    "role_staffing",
    "epoch_apply",
    "reboot_pending",
]
PHASE_LABELS = {
    "seed_copy": "Seed copy",
    "host_preflight": "Host preflight",
    "vault_scan": "Vault scan",
    "inbox_normalize": "Inbox normalize",
    "candidate_staging": "Candidate staging",
    "role_staffing": "Role staffing",
    "epoch_apply": "Epoch apply",
    "reboot_pending": "Reboot pending",
}
STEP_TO_PHASE = {
    "start": "seed_copy",
    "seed": "seed_copy",
    "seed_copy": "seed_copy",
    "host_preflight": "host_preflight",
    "preflight": "host_preflight",
    "vault": "vault_scan",
    "vault_scan": "vault_scan",
    "inbox": "inbox_normalize",
    "inbox_normalize": "inbox_normalize",
    "inventory": "candidate_staging",
    "dataset_assurance": "candidate_staging",
    "candidate_staging": "candidate_staging",
    "role_tournament": "role_staffing",
    "staffing_gate": "role_staffing",
    "role_staffing": "role_staffing",
    "prestart_request": "epoch_apply",
    "build_epoch": "epoch_apply",
    "epoch_apply": "epoch_apply",
    "complete": "reboot_pending",
    "reboot_pending": "reboot_pending",
}
FINAL_FIELDS = {"state", "current_phase", "completed_phases", "next_actions"}
REGISTRY_REFS = [
    "configs/firstboot-progress-view-policy.json",
    "contracts/firstboot_progress_view.schema.json",
    "src/firstboot_progress_runtime.py",
    "src/firstboot_status.py",
    "src/first_start_summary.py",
    "bin/noemaforge",
    "tests/test_firstboot_progress_runtime.py",
    "tests/test_firstboot_progress_qa.py",
    "tests/test_firstboot_progress_performance.py",
    "prelaunch/governance/firstboot_progress_view.example.json",
]
PIPELINE_REFS = [
    "configs/firstboot-progress-view-policy.json",
    "contracts/firstboot_progress_view.schema.json",
    "src/firstboot_progress_runtime.py",
    "prelaunch/governance/firstboot_progress_view.example.json",
]


def _nowz() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _display_path(path: Path) -> str:
    return str(path).replace(os.sep, "/")


def _as_string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


def _policy_dict(payload: Dict[str, Any]) -> Dict[str, Any]:
    return payload.get("policy") if isinstance(payload.get("policy"), dict) else payload


def _registry_ref(entry: Dict[str, Any]) -> str:
    return f"{entry.get('kind')}:{entry.get('id')}:{entry.get('version')}"


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def _contains(text: str, needle: str) -> bool:
    return _norm(needle) in _norm(text)


def _is_safe_relative_ref(ref: str) -> bool:
    text = str(ref or "").strip().replace("\\", "/")
    if not text or text.startswith("/") or text.startswith("~"):
        return False
    parts = PurePosixPath(text).parts
    return not any(part in {"", ".", ".."} for part in parts)


def _resolve_ref(ref: str, *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    local = str(ref or "").strip().replace("\\", "/")
    candidates = [("project", project_root / local), ("package", package_root / local)]
    if not local.startswith("noemaforge/"):
        candidates.append(("project_noemaforge", project_root / "noemaforge" / local))
    checked: List[str] = []
    for owner, path in candidates:
        checked.append(_display_path(path))
        if path.exists():
            return {"ok": True, "ref": ref, "resolved_under": owner, "path": _display_path(path), "checked": checked}
    return {"ok": False, "ref": ref, "resolved_under": "", "path": "", "checked": checked}


def _resolve_refs(refs: Sequence[str], *, project_root: Path, package_root: Path, owner: str) -> Dict[str, Any]:
    failures: List[str] = []
    resolved_refs: List[Dict[str, Any]] = []
    missing_refs: List[Dict[str, Any]] = []
    unsafe_refs: List[Dict[str, Any]] = []
    for ref in refs:
        if not _is_safe_relative_ref(ref):
            unsafe_refs.append({"owner": owner, "ref": ref})
            failures.append(f"unsafe_ref:{owner}:{ref}")
            continue
        resolved = _resolve_ref(ref, project_root=project_root, package_root=package_root)
        resolved["owner"] = owner
        if resolved["ok"]:
            resolved_refs.append(resolved)
        else:
            missing_refs.append(resolved)
            failures.append(f"missing_ref:{owner}:{ref}")
    return {"failures": failures, "resolved_refs": resolved_refs, "missing_refs": missing_refs, "unsafe_refs": unsafe_refs}


def load_policy(policy_path: Path | str) -> Dict[str, Any]:
    return json.loads(Path(policy_path).read_text(encoding="utf-8"))


def load_example_set(example_path: Path | str) -> Dict[str, Any]:
    return json.loads(Path(example_path).read_text(encoding="utf-8"))


def load_json(path: Path | str, default: Any) -> Any:
    try:
        obj = json.loads(Path(path).read_text(encoding="utf-8", errors="replace"))
        return obj if isinstance(obj, type(default)) else default
    except Exception:
        return default


def load_events(path: Path | str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    path = Path(path)
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


def _phase_for_event(event: Dict[str, Any]) -> str:
    step = str(event.get("step") or "").strip().lower().replace("-", "_")
    return STEP_TO_PHASE.get(step, "")


def _phase_state(event_state: str) -> str:
    state = str(event_state or "").strip().lower()
    if state.startswith("blocked") or state in {"failed", "error", "unstaffed"}:
        return "blocked"
    if "warn" in state or "degraded" in state:
        return "warning"
    if state in {"running", "started", "pending"}:
        return "running"
    return "complete"


def _badge_state(state: str) -> str:
    return {
        "complete": "PASS",
        "warning": "WARN",
        "blocked": "FAIL",
        "running": "RUN",
        "pending": "PENDING",
    }.get(str(state or ""), "INFO")


def _next_actions(final_state: str, current_phase: str, staffing: Dict[str, Any]) -> List[str]:
    state = str(final_state or "")
    missing = staffing.get("missing_mandatory_core_roles") if isinstance(staffing, dict) else []
    if state.startswith("blocked") or state in {"failed", "error", "unstaffed"}:
        return [
            "Review the blocker in firstboot-status.json and firstboot-events.jsonl.",
            "Run noemaforge first-start diagnostics before retrying a destructive step.",
        ]
    if missing:
        return [
            "Review firstboot-staffing-summary.json before epoch apply.",
            "Add or stage models for missing mandatory roles.",
        ]
    if state == "selection_ready_no_apply":
        return [
            "Review model-selection-decision.json and rollback_plan.json.",
            "Apply only after operator review of selected role models.",
        ]
    if state in {"applied_reboot_scheduled", "applied_no_reboot"} or state.startswith("applied"):
        return [
            "Reboot when convenient if reboot is pending.",
            "After reboot, run noemaforge status and noemaforge smoke.",
        ]
    if current_phase:
        return [f"Watch the {current_phase} phase until it advances or blocks."]
    return ["Start firstboot or run noemaforge first-start summary for historical runs."]


def build_progress_view(
    events: Sequence[Dict[str, Any]],
    *,
    status: Dict[str, Any] | None = None,
    staffing: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    status = status or {}
    staffing = staffing or {}
    phases = [
        {"id": phase_id, "label": PHASE_LABELS[phase_id], "state": "pending", "message": ""}
        for phase_id in REQUIRED_PHASES
    ]
    phase_index = {item["id"]: idx for idx, item in enumerate(phases)}
    current_phase = ""
    last_ts = ""
    for event in events:
        phase_id = _phase_for_event(event)
        if not phase_id:
            continue
        idx = phase_index[phase_id]
        for prev in phases[:idx]:
            if prev["state"] == "pending":
                prev["state"] = "complete"
        state = _phase_state(str(event.get("state") or ""))
        phases[idx]["state"] = state
        phases[idx]["message"] = str(event.get("message") or "")
        current_phase = phase_id
        last_ts = str(event.get("ts") or last_ts)

    final_state = str(status.get("state") or (events[-1].get("state") if events else "not_started"))
    if final_state in {"complete", "selection_ready_no_apply", "applied_no_reboot", "applied_reboot_scheduled"} or final_state.startswith("applied"):
        for item in phases:
            if item["state"] == "pending":
                item["state"] = "complete"
    if status.get("reboot_scheduled") is True and phases[-1]["state"] == "complete":
        phases[-1]["state"] = "running"
        phases[-1]["message"] = phases[-1]["message"] or "Reboot is pending."
        current_phase = "reboot_pending"
    if not current_phase:
        current = next((item["id"] for item in phases if item["state"] in {"running", "warning", "blocked"}), "")
        current_phase = current or next((item["id"] for item in phases if item["state"] == "pending"), "")

    completed = len([item for item in phases if item["state"] == "complete"])
    final_summary = {
        "state": final_state,
        "current_phase": current_phase,
        "completed_phases": completed,
        "next_actions": _next_actions(final_state, current_phase, staffing),
    }
    return {
        "apiVersion": API_VERSION,
        "kind": VIEW_KIND,
        "created_at": _nowz(),
        "updated_at": str(status.get("updated_at") or last_ts or ""),
        "phases": phases,
        "final_summary": final_summary,
    }


def render_progress_text(view: Dict[str, Any]) -> str:
    lines = ["NOEMAFORGE FIRSTBOOT PROGRESS", ""]
    for item in view.get("phases", []):
        badge = _badge_state(str(item.get("state") or ""))
        msg = str(item.get("message") or "").strip()
        suffix = f" - {msg}" if msg else ""
        lines.append(f"[{badge}] {item.get('id')} ({item.get('label')}): {item.get('state')}{suffix}")
    final = view.get("final_summary") if isinstance(view.get("final_summary"), dict) else {}
    lines.extend([
        "",
        "Final summary",
        f"state: {final.get('state', '')}",
        f"current_phase: {final.get('current_phase', '')}",
        f"completed_phases: {final.get('completed_phases', 0)}/{len(view.get('phases', []))}",
        "",
        "Next actions",
    ])
    for action in final.get("next_actions") or []:
        lines.append(f"- {action}")
    return "\n".join(lines) + "\n"


def _policy_failures(payload: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    policy = _policy_dict(payload)
    if payload.get("apiVersion") != API_VERSION:
        failures.append("policy_api_version_invalid")
    if payload.get("kind") != POLICY_KIND:
        failures.append("policy_kind_invalid")
    if not SAFE_ID_RE.match(str(payload.get("id") or "")):
        failures.append("policy_id_invalid")
    if str(payload.get("status") or "") not in VALID_STATUSES:
        failures.append("policy_status_invalid")
    if str(policy.get("mode") or "") != "offline_contract":
        failures.append("policy_mode_not_offline_contract")
    if str(policy.get("activation_state") or "") != "human_readable_firstboot_progress_view":
        failures.append("policy_activation_state_invalid")
    if not str(policy.get("required_pipeline_ref") or "").startswith("pipeline:"):
        failures.append("policy_required_pipeline_ref_invalid")
    for key in ["runtime_ref", "status_ref", "summary_ref"]:
        if not _is_safe_relative_ref(str(policy.get(key) or "")):
            failures.append(f"policy_{key}_invalid")
    for key in ["require_trace_id", "require_registry_attachment", "require_docs_and_changelog_refs", "require_no_live_dependency"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    if _as_string_list(policy.get("required_phases")) != REQUIRED_PHASES:
        failures.append("policy_required_phases_invalid")
    if not FINAL_FIELDS.issubset(set(_as_string_list(policy.get("required_final_summary_fields")))):
        failures.append("policy_final_summary_fields_missing")
    if not _as_string_list(policy.get("required_cli_markers")):
        failures.append("policy_required_cli_markers_empty")
    if not _as_string_list(policy.get("required_boundary_refs")):
        failures.append("policy_required_boundary_refs_empty")
    if not _as_string_list(policy.get("required_example_sets")):
        failures.append("policy_required_example_sets_empty")
    return failures


def _cli_failures(payload: Dict[str, Any], *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    policy = _policy_dict(payload)
    failures: List[str] = []
    resolved = _resolve_ref("bin/noemaforge", project_root=project_root, package_root=package_root)
    text = Path(resolved["path"]).read_text(encoding="utf-8") if resolved.get("ok") else ""
    if not resolved.get("ok"):
        failures.append("cli_missing:bin/noemaforge")
    for marker in _as_string_list(policy.get("required_cli_markers")):
        if marker == "FIRSTBOOT PROGRESS" or marker == "Next actions":
            continue
        if marker not in text:
            failures.append(f"cli_marker_missing:{marker}")
    if "progress|watch|tui" not in text:
        failures.append("cli_first_start_progress_dispatch_missing")
    if "firstboot_progress_runtime.py" not in text:
        failures.append("cli_progress_runtime_missing")
    return {"failures": failures, "resolved": resolved}


def _registry_failures(payload: Dict[str, Any], *, project_root: Path, package_root: Path, registry_path: Path) -> Dict[str, Any]:
    policy = _policy_dict(payload)
    registry = urr.load_registry(registry_path)
    report = urr.validate_unified_registry(registry, project_root=project_root, package_root=package_root, registry_path=registry_path)
    failures = [f"registry_invalid:{item}" for item in report.get("failures", [])]
    entries = {_registry_ref(entry): entry for entry in report.get("normalized_registry", {}).get("entries", []) if isinstance(entry, dict)}
    raw_entries = {_registry_ref(entry): entry for entry in registry.get("entries", []) if isinstance(entry, dict)}
    eval_ref = f"eval-pack:{payload.get('id')}:{payload.get('version')}"
    eval_entry = entries.get(eval_ref)
    if not eval_entry:
        failures.append(f"registry_eval_pack_missing:{eval_ref}")
    else:
        refs = set(_as_string_list(eval_entry.get("refs")))
        for ref in REGISTRY_REFS:
            if ref not in refs:
                failures.append(f"registry_eval_pack_ref_missing:{eval_ref}:{ref}")
    pipeline_ref = str(policy.get("required_pipeline_ref") or "")
    pipeline = raw_entries.get(pipeline_ref) or entries.get(pipeline_ref)
    pipeline_eval_refs: List[str] = []
    pipeline_refs: List[str] = []
    if not pipeline:
        failures.append(f"registry_pipeline_missing:{pipeline_ref}")
    else:
        pipeline_eval_refs = _as_string_list(pipeline.get("eval_pack_refs"))
        pipeline_refs = _as_string_list(pipeline.get("refs"))
    if eval_ref not in pipeline_eval_refs:
        failures.append(f"registry_pipeline_eval_pack_missing:{eval_ref}")
    for ref in PIPELINE_REFS:
        if ref not in pipeline_refs:
            failures.append(f"registry_pipeline_ref_missing:{ref}")
    return {"failures": failures, "registry_report": report, "pipeline_eval_refs": pipeline_eval_refs, "pipeline_refs": pipeline_refs}


def _docs_failures(payload: Dict[str, Any], *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    policy = _policy_dict(payload)
    boundary = str(policy.get("boundary_phrase") or "")
    failures: List[str] = []
    boundary_reports: List[Dict[str, Any]] = []
    for ref in _as_string_list(policy.get("required_boundary_refs")):
        resolved = _resolve_ref(ref, project_root=project_root, package_root=package_root)
        has_phrase = False
        if resolved.get("ok"):
            has_phrase = _contains(Path(resolved["path"]).read_text(encoding="utf-8"), boundary)
        else:
            failures.append(f"boundary_ref_missing:{ref}")
        if resolved.get("ok") and not has_phrase:
            failures.append(f"boundary_phrase_missing:{ref}")
        boundary_reports.append({"ref": ref, "ok": bool(resolved.get("ok")) and has_phrase, "has_phrase": has_phrase, "resolved": resolved})
    return {"failures": failures, "boundary_reports": boundary_reports}


def _example_failures(example_set: Dict[str, Any], policy_payload: Dict[str, Any]) -> Dict[str, Any]:
    failures: List[str] = []
    if example_set.get("apiVersion") != API_VERSION:
        failures.append("example_api_version_invalid")
    if example_set.get("kind") != SET_KIND:
        failures.append("example_kind_invalid")
    events = example_set.get("events") if isinstance(example_set.get("events"), list) else []
    if not events:
        failures.append("example_events_empty")
    view = build_progress_view(
        events,
        status=example_set.get("status") if isinstance(example_set.get("status"), dict) else {},
        staffing=example_set.get("staffing") if isinstance(example_set.get("staffing"), dict) else {},
    )
    text = render_progress_text(view)
    expected = example_set.get("expected") if isinstance(example_set.get("expected"), dict) else {}
    if len(view.get("phases", [])) != int(expected.get("phase_count") or len(REQUIRED_PHASES)):
        failures.append("example_phase_count_mismatch")
    if view.get("final_summary", {}).get("current_phase") != expected.get("current_phase"):
        failures.append("example_current_phase_mismatch")
    if int(view.get("final_summary", {}).get("completed_phases") or 0) < int(expected.get("completed_phases_min") or 0):
        failures.append("example_completed_phases_too_low")
    for marker in _as_string_list(expected.get("required_text")):
        if marker not in text:
            failures.append(f"example_render_marker_missing:{marker}")
    for phase_id in REQUIRED_PHASES:
        if phase_id not in text:
            failures.append(f"example_render_phase_missing:{phase_id}")
    return {"failures": failures, "view": view, "rendered": text}


def validate_firstboot_progress_policy(
    payload: Dict[str, Any],
    *,
    project_root: Path | str,
    package_root: Path | str,
    policy_path: Path | str | None = None,
    registry_path: Path | str | None = None,
) -> Dict[str, Any]:
    project = Path(project_root).resolve()
    package = Path(package_root).resolve()
    registry = Path(registry_path).resolve() if registry_path else package / "configs" / "unified-registry.json"
    policy = _policy_dict(payload)
    failures: List[str] = []
    failures.extend(_policy_failures(payload))
    ref_report = _resolve_refs(_as_string_list(payload.get("refs")), project_root=project, package_root=package, owner=str(payload.get("id") or "policy"))
    failures.extend(ref_report["failures"])
    cli_report = _cli_failures(payload, project_root=project, package_root=package)
    failures.extend(cli_report["failures"])
    registry_report = _registry_failures(payload, project_root=project, package_root=package, registry_path=registry)
    failures.extend(registry_report["failures"])
    docs_report = _docs_failures(payload, project_root=project, package_root=package)
    failures.extend(docs_report["failures"])
    example_reports: List[Dict[str, Any]] = []
    for ref in _as_string_list(policy.get("required_example_sets")):
        resolved = _resolve_ref(ref, project_root=project, package_root=package)
        if not resolved.get("ok"):
            failures.append(f"example_ref_missing:{ref}")
            continue
        example_report = _example_failures(load_example_set(resolved["path"]), payload)
        failures.extend(example_report["failures"])
        example_reports.append({"ref": ref, **example_report})
    metrics = {
        "phases": len(REQUIRED_PHASES),
        "refs": len(_as_string_list(payload.get("refs"))),
        "resolved_refs": len(ref_report["resolved_refs"]),
        "boundary_refs": len(docs_report["boundary_reports"]),
        "examples": len(example_reports),
        "registry_entries": len(registry_report.get("registry_report", {}).get("normalized_registry", {}).get("entries", [])),
    }
    return {
        "apiVersion": API_VERSION,
        "kind": REPORT_KIND,
        "id": str(payload.get("id") or ""),
        "version": str(payload.get("version") or ""),
        "ok": not failures,
        "validated_at": _nowz(),
        "policy_path": _display_path(Path(policy_path).resolve()) if policy_path else "",
        "failures": failures,
        "metrics": metrics,
        "refs": ref_report,
        "cli": cli_report,
        "registry": registry_report,
        "docs": docs_report,
        "examples": example_reports,
    }


def build_summary(report: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "apiVersion": API_VERSION,
        "kind": "FirstbootProgressViewValidationSummary",
        "ok": bool(report.get("ok")),
        "id": report.get("id"),
        "version": report.get("version"),
        "metrics": report.get("metrics", {}),
        "failures": report.get("failures", []),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render or validate NoemaForge firstboot progress")
    parser.add_argument("--bootstrap", default=os.environ.get("NOEMAFORGE_BOOTSTRAP", "/var/lib/noemaforge/bootstrap"))
    parser.add_argument("--policy", default=str(SRC_DIR.parent / "configs" / "firstboot-progress-view-policy.json"))
    parser.add_argument("--project-root", default=str(SRC_DIR.parent.parent))
    parser.add_argument("--package-root", default=str(SRC_DIR.parent))
    parser.add_argument("--registry", default="")
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.validate:
        report = validate_firstboot_progress_policy(
            load_policy(args.policy),
            project_root=Path(args.project_root),
            package_root=Path(args.package_root),
            policy_path=Path(args.policy),
            registry_path=Path(args.registry) if args.registry else None,
        )
        print(json.dumps(build_summary(report) if args.summary else report, ensure_ascii=False, indent=2))
        return 0 if report.get("ok") else 1
    boot = Path(args.bootstrap)
    view = build_progress_view(
        load_events(boot / "firstboot-events.jsonl"),
        status=load_json(boot / "firstboot-status.json", {}),
        staffing=load_json(boot / "firstboot-staffing-summary.json", {}),
    )
    if args.json:
        print(json.dumps(view, ensure_ascii=False, indent=2))
    else:
        print(render_progress_text(view), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
