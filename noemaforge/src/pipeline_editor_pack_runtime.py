#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/pipeline_editor_pack_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate the offline Pipeline Editor pack contract for draft edit/clone/review flows.
Inputs: pipeline-editor-pack policy, pipeline catalog and Admin GUI draft surfaces.
Outputs: JSON-compatible PipelineEditorPackValidationReport artifacts.
Side effects: None; CLI writes JSON to stdout.
Tests: noemaforge/tests/test_pipeline_editor_pack_runtime.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Sequence


SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import pipeline_runtime


API_VERSION = "noemaforge.pipeline-editor-pack/v1"
POLICY_KIND = "PipelineEditorPackPolicy"
REPORT_KIND = "PipelineEditorPackValidationReport"
VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,220}$")
STAGE_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")


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


def _is_safe_relative_ref(ref: str) -> bool:
    text = str(ref or "").strip().replace("\\", "/")
    if not text or text.startswith("/") or text.startswith("~"):
        return False
    parts = PurePosixPath(text).parts
    return not any(part in {"", ".", ".."} for part in parts)


def _resolve_ref(ref: str, *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    candidates = [("project", project_root / ref), ("package", package_root / ref)]
    if not ref.startswith("noemaforge/"):
        candidates.append(("project_noemaforge", project_root / "noemaforge" / ref))
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


def load_text(path: Path | str) -> str:
    return Path(path).read_text(encoding="utf-8")


def _safe_stage(value: Any) -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "").strip()).strip("_")
    return text[:80] or "stage"


def _insert_after(stages: List[str], stage: str, after: str) -> List[str]:
    if stage in stages:
        return stages
    if after in stages:
        idx = stages.index(after) + 1
        return stages[:idx] + [stage] + stages[idx:]
    return stages + [stage]


def _normalize_drag_event(index: int, operation: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "event_id": f"drag_event_{index + 1:03d}",
        "event_type": "drag_drop_stage_edit",
        "operation": str(operation.get("op") or ""),
        "stage": _safe_stage(operation.get("stage") or operation.get("to") or operation.get("from")),
        "source_index": int(operation.get("source_index") or index),
        "target_index": int(operation.get("target_index") or index + 1),
        "raw": copy.deepcopy(operation),
    }


def clone_as_new_pipeline_class(
    catalog: Dict[str, Dict[str, Any]],
    *,
    source_id: str,
    new_pipeline_id: str,
    operations: Sequence[Dict[str, Any]],
    review_chain: Sequence[str] = ("Scary", "Architecture", "Admin"),
) -> Dict[str, Any]:
    if source_id not in catalog:
        raise ValueError(f"unknown source pipeline: {source_id}")
    if source_id == new_pipeline_id:
        raise ValueError("new pipeline id must differ from source pipeline id")
    source = copy.deepcopy(catalog[source_id])
    clone = copy.deepcopy(source)
    clone["pipeline_id"] = new_pipeline_id
    clone["source_pipeline_id"] = source_id
    clone["pipeline_class"] = "operator_draft_clone"
    clone["activation_state"] = "draft_review_required"
    clone["permission_mode"] = str(clone.get("permission_mode") or "plan_only")
    clone["stages"] = [_safe_stage(stage) for stage in clone.get("stages", []) if _safe_stage(stage)]
    clone.setdefault("deliverables", [])
    clone.setdefault("quality_gates", [])
    clone["editor_contract"] = {
        "review_chain": list(review_chain),
        "requires_review_before_activation": True,
        "auto_activate": False,
        "applied": False,
    }

    for operation in operations:
        op = str(operation.get("op") or "")
        if op == "add_stage":
            clone["stages"] = _insert_after(clone["stages"], _safe_stage(operation.get("stage")), _safe_stage(operation.get("after")))
        elif op == "rename_stage":
            old = _safe_stage(operation.get("from"))
            new = _safe_stage(operation.get("to"))
            clone["stages"] = [new if stage == old else stage for stage in clone["stages"]]
        elif op == "remove_stage":
            stage = _safe_stage(operation.get("stage"))
            clone["stages"] = [item for item in clone["stages"] if item != stage]
        elif op == "set_permission_mode":
            clone["permission_mode"] = str(operation.get("value") or clone.get("permission_mode") or "plan_only")
        elif op == "set_llm_policy":
            value = operation.get("value") if isinstance(operation.get("value"), dict) else {}
            clone["llm_policy"] = {"mode": str(value.get("mode") or "switchable"), "max_active_llms": int(value.get("max_active_llms") or 1)}
        elif op == "set_deliverable":
            deliverable = _safe_stage(operation.get("value"))
            if deliverable not in clone["deliverables"]:
                clone["deliverables"].append(deliverable)
        elif op == "annotate_edge":
            clone.setdefault("editor_edges", []).append(
                {"from": _safe_stage(operation.get("from")), "to": _safe_stage(operation.get("to")), "note": str(operation.get("note") or "")[:240]}
            )

    for reviewer in review_chain:
        stage = _safe_stage(f"{reviewer.lower()}_review")
        if stage not in clone["stages"]:
            clone["stages"].append(stage)
    if "editor_review_required" not in clone["quality_gates"]:
        clone["quality_gates"].append("editor_review_required")
    return clone


def build_pipeline_editor_draft(
    catalog: Dict[str, Dict[str, Any]],
    *,
    source_id: str = "evolution",
    new_pipeline_id: str = "evolution_operator_draft",
    operations: Sequence[Dict[str, Any]] | None = None,
    review_chain: Sequence[str] = ("Scary", "Architecture", "Admin"),
) -> Dict[str, Any]:
    ops = list(operations or [])
    clone = clone_as_new_pipeline_class(catalog, source_id=source_id, new_pipeline_id=new_pipeline_id, operations=ops, review_chain=review_chain)
    return {
        "apiVersion": API_VERSION,
        "kind": "PipelineEditorDraft",
        "draft_id": f"pipeline_editor_{new_pipeline_id}",
        "created_at": _nowz(),
        "source_pipeline_id": source_id,
        "new_pipeline_id": new_pipeline_id,
        "status": "draft_only",
        "activation_state": "draft_review_required",
        "auto_activate": False,
        "applied": False,
        "requires_review": True,
        "review_chain": list(review_chain),
        "operations": ops,
        "drag_drop_events": [_normalize_drag_event(index, op) for index, op in enumerate(ops)],
        "clone": clone,
        "forbidden_actions": ["activate", "overwrite_source", "bypass_review", "run_privileged_job", "auto_apply"],
    }


def validate_pipeline_editor_draft(draft: Dict[str, Any], policy: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    allowed_ops = set(_as_string_list(policy.get("allowed_operations")))
    required_review = _as_string_list(policy.get("required_review_chain"))
    if draft.get("kind") != "PipelineEditorDraft":
        failures.append("draft_kind_invalid")
    if draft.get("status") != "draft_only":
        failures.append("draft_status_not_draft_only")
    if draft.get("activation_state") != "draft_review_required":
        failures.append("draft_activation_state_invalid")
    if draft.get("auto_activate") is not False:
        failures.append("draft_auto_activate_not_false")
    if draft.get("applied") is not False:
        failures.append("draft_applied_not_false")
    if draft.get("requires_review") is not True:
        failures.append("draft_review_not_required")
    if draft.get("source_pipeline_id") == draft.get("new_pipeline_id"):
        failures.append("draft_source_and_new_pipeline_match")
    if draft.get("review_chain") != required_review:
        failures.append("draft_review_chain_invalid")
    operations = draft.get("operations") if isinstance(draft.get("operations"), list) else []
    if not operations:
        failures.append("draft_operations_empty")
    for operation in operations:
        op = str(operation.get("op") or "")
        if op not in allowed_ops:
            failures.append(f"draft_operation_not_allowed:{op}")
    events = draft.get("drag_drop_events") if isinstance(draft.get("drag_drop_events"), list) else []
    if len(events) != len(operations):
        failures.append("drag_drop_event_count_mismatch")
    for event in events:
        if event.get("event_type") != "drag_drop_stage_edit":
            failures.append("drag_drop_event_type_invalid")
        if event.get("operation") not in allowed_ops:
            failures.append(f"drag_drop_event_operation_not_allowed:{event.get('operation')}")
    clone = draft.get("clone") if isinstance(draft.get("clone"), dict) else {}
    if clone.get("pipeline_class") != "operator_draft_clone":
        failures.append("clone_pipeline_class_invalid")
    if clone.get("activation_state") != "draft_review_required":
        failures.append("clone_activation_state_invalid")
    stages = _as_string_list(clone.get("stages"))
    for reviewer in required_review:
        if _safe_stage(f"{reviewer.lower()}_review") not in stages:
            failures.append(f"clone_review_stage_missing:{reviewer}")
    editor_contract = clone.get("editor_contract") if isinstance(clone.get("editor_contract"), dict) else {}
    if editor_contract.get("auto_activate") is not False:
        failures.append("clone_editor_contract_auto_activate_not_false")
    if editor_contract.get("applied") is not False:
        failures.append("clone_editor_contract_applied_not_false")
    for forbidden in _as_string_list(policy.get("forbidden_actions")):
        if forbidden not in draft.get("forbidden_actions", []):
            failures.append(f"draft_forbidden_action_missing:{forbidden}")
    for stage in stages:
        if not STAGE_ID_RE.match(stage):
            failures.append(f"clone_stage_id_invalid:{stage}")
    return failures


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
    if str(policy.get("activation_state") or "") != "draft_clone_review_required":
        failures.append("policy_activation_state_invalid")
    for key in [
        "require_docs_and_changelog_refs",
        "require_no_live_gui_dependency",
        "require_drag_drop_event_schema",
        "require_clone_as_new_pipeline_class",
        "forbid_auto_activation",
    ]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    if _as_string_list(policy.get("required_review_chain")) != ["Scary", "Architecture", "Admin"]:
        failures.append("policy_review_chain_invalid")
    for key in ["allowed_operations", "forbidden_actions", "required_runtime_tokens", "required_gui_tokens"]:
        if not _as_string_list(policy.get(key)):
            failures.append(f"policy_{key}_empty")
    return failures


def _source_report(policy: Dict[str, Any], *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    failures: List[str] = []
    runtime_resolved = _resolve_ref("noemaforge/src/pipeline_editor_pack_runtime.py", project_root=project_root, package_root=package_root)
    runtime_text = load_text(runtime_resolved["path"]) if runtime_resolved.get("ok") else ""
    gui_resolved = _resolve_ref("noemaforge/templates/pipeline-dashboard/app.js", project_root=project_root, package_root=package_root)
    gui_text = load_text(gui_resolved["path"]) if gui_resolved.get("ok") else ""
    admin_resolved = _resolve_ref("noemaforge/src/admin_gui_server.py", project_root=project_root, package_root=package_root)
    admin_text = load_text(admin_resolved["path"]) if admin_resolved.get("ok") else ""
    if not runtime_resolved.get("ok"):
        failures.append("runtime_source_missing")
    if not gui_resolved.get("ok"):
        failures.append("gui_source_missing")
    if not admin_resolved.get("ok"):
        failures.append("admin_gui_source_missing")
    for token in _as_string_list(policy.get("required_runtime_tokens")):
        if token not in runtime_text:
            failures.append(f"runtime_token_missing:{token}")
    gui_combined = gui_text + "\n" + admin_text
    for token in _as_string_list(policy.get("required_gui_tokens")):
        if token not in gui_combined:
            failures.append(f"gui_token_missing:{token}")
    return {
        "failures": failures,
        "runtime_chars": len(runtime_text),
        "gui_chars": len(gui_text),
        "admin_gui_chars": len(admin_text),
        "runtime_resolved": runtime_resolved,
        "gui_resolved": gui_resolved,
        "admin_resolved": admin_resolved,
    }


def build_pipeline_editor_fixture(*, package_root: Path | str) -> Dict[str, Any]:
    root = Path(package_root).resolve()
    catalog = pipeline_runtime.load_pipeline_catalog(root)
    operations = [
        {"op": "add_stage", "stage": "scary_preflight", "after": "intake"},
        {"op": "rename_stage", "from": "development", "to": "implementation"},
        {"op": "set_deliverable", "value": "editor_draft_manifest"},
        {"op": "annotate_edge", "from": "scary_preflight", "to": "implementation", "note": "Scary review must happen before implementation."},
        {"op": "set_permission_mode", "value": "ask_before_write"},
        {"op": "set_llm_policy", "value": {"mode": "switchable", "max_active_llms": 1}},
    ]
    return build_pipeline_editor_draft(
        catalog,
        source_id="evolution",
        new_pipeline_id="evolution_operator_draft",
        operations=operations,
    )


def _workflow_report(policy: Dict[str, Any], *, package_root: Path) -> Dict[str, Any]:
    draft = build_pipeline_editor_fixture(package_root=package_root)
    failures = validate_pipeline_editor_draft(draft, policy)
    clone = draft.get("clone", {})
    metrics = {
        "operations": len(draft.get("operations", [])),
        "drag_drop_events": len(draft.get("drag_drop_events", [])),
        "clone_stages": len(clone.get("stages", [])) if isinstance(clone, dict) else 0,
        "reviewers": len(draft.get("review_chain", [])),
    }
    return {"failures": failures, "fixture": draft, "metrics": metrics}


def _docs_report(payload: Dict[str, Any], *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    failures: List[str] = []
    docs = [
        project_root / "TODO.md",
        package_root / "TODO.md",
        project_root / "docs" / "TODO.md",
        package_root / "docs" / "TODO.md",
        project_root / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
        package_root / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
        project_root / "CHANGELOG.md",
        project_root / "RELEASE_NOTES.md",
        project_root / "docs" / "history" / "CHANGELOG.md",
        package_root / "docs" / "history" / "CHANGELOG.md",
    ]
    tokens = [
        str(payload.get("id") or ""),
        "drag-and-drop edit, clone as new pipeline class, Scary/Architecture/Admin review",
        "draft-only",
    ]
    reports: List[Dict[str, Any]] = []
    for path in docs:
        text = load_text(path) if path.exists() else ""
        missing = [token for token in tokens if token and token not in text]
        if missing:
            failures.append(f"docs_tokens_missing:{_display_path(path)}:{','.join(missing)}")
        reports.append({"path": _display_path(path), "ok": not missing, "missing": missing})
    return {"failures": failures, "reports": reports}


def validate_pipeline_editor_pack_policy(
    payload: Dict[str, Any],
    *,
    project_root: Path | str,
    package_root: Path | str,
    policy_path: Path | str | None = None,
    include_docs: bool = True,
) -> Dict[str, Any]:
    project = Path(project_root).resolve()
    package = Path(package_root).resolve()
    policy = _policy_dict(payload)
    failures: List[str] = []
    failures.extend(_policy_failures(payload))
    ref_report = _resolve_refs(_as_string_list(payload.get("refs")), project_root=project, package_root=package, owner=str(payload.get("id") or "policy"))
    failures.extend(ref_report["failures"])
    source = _source_report(policy, project_root=project, package_root=package)
    failures.extend(source["failures"])
    workflow = _workflow_report(policy, package_root=package)
    failures.extend(workflow["failures"])
    docs = _docs_report(payload, project_root=project, package_root=package) if include_docs else {"failures": [], "reports": []}
    failures.extend(docs["failures"])
    metrics = {
        "refs": len(_as_string_list(payload.get("refs"))),
        "resolved_refs": len(ref_report["resolved_refs"]),
        "runtime_chars": source["runtime_chars"],
        "gui_chars": source["gui_chars"],
        "admin_gui_chars": source["admin_gui_chars"],
        "operations": workflow["metrics"]["operations"],
        "drag_drop_events": workflow["metrics"]["drag_drop_events"],
        "clone_stages": workflow["metrics"]["clone_stages"],
        "docs_reports": len(docs["reports"]),
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
        "source": source,
        "workflow": workflow,
        "docs": docs,
    }


def benchmark_pipeline_editor_pack(*, package_root: Path | str, iterations: int = 120) -> Dict[str, Any]:
    root = Path(package_root).resolve()
    policy = load_policy(root / "configs" / "pipeline-editor-pack-policy.json")
    started = time.perf_counter()
    failures = 0
    for _ in range(iterations):
        report = validate_pipeline_editor_pack_policy(policy, project_root=root.parent, package_root=root, include_docs=False)
        if not report.get("ok"):
            failures += 1
    elapsed = time.perf_counter() - started
    return {
        "ok": failures == 0,
        "iterations": iterations,
        "failures": failures,
        "elapsed_seconds": round(elapsed, 6),
        "iterations_per_second": round(iterations / elapsed, 3) if elapsed else iterations,
    }


def build_summary(report: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "apiVersion": API_VERSION,
        "kind": "PipelineEditorPackValidationSummary",
        "ok": bool(report.get("ok")),
        "id": report.get("id"),
        "version": report.get("version"),
        "metrics": report.get("metrics", {}),
        "failures": report.get("failures", []),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate NoemaForge Pipeline Editor pack contract")
    parser.add_argument("--policy", default=str(SRC_DIR.parent / "configs" / "pipeline-editor-pack-policy.json"))
    parser.add_argument("--project-root", default=str(SRC_DIR.parent.parent))
    parser.add_argument("--package-root", default=str(SRC_DIR.parent))
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--skip-docs", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = validate_pipeline_editor_pack_policy(
        load_policy(args.policy),
        project_root=Path(args.project_root),
        package_root=Path(args.package_root),
        policy_path=Path(args.policy),
        include_docs=not args.skip_docs,
    )
    print(json.dumps(build_summary(report) if args.summary else report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
