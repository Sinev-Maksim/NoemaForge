#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/concept_frame_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Validate Concept_Frame contracts for Admin/Architect control-plane decisions.
Inputs: noemaforge/configs/concept-frame-policy.json and ConceptFrame example sets.
Outputs: JSON-compatible ConceptFrameValidationReport artifacts.
Side effects: None unless run as a CLI, which writes JSON to stdout.
Tests: noemaforge/tests/test_concept_frame_runtime.py
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
from typing import Any, Dict, List, Optional, Sequence


SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import production_ai_contracts as pac


API_VERSION = "noemaforge.concept-frame/v1"
POLICY_KIND = "ConceptFramePolicy"
FRAME_KIND = "ConceptFrame"
FRAME_SET_KIND = "ConceptFrameSet"
REPORT_KIND = "ConceptFrameValidationReport"

VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
VALID_ROLES = {"admin", "architect"}
VALID_DECISION_TYPES = {
    "control_plane_task",
    "architecture_decision",
    "pipeline_mutation",
    "persistence_export",
    "internet_research",
    "operator_question",
}
VALID_HONESTY_STATES = {"sufficient_evidence", "unknown", "need_research", "error_attribution"}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,180}$")


def _nowz() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _as_path(value: Path | str) -> Path:
    return Path(value).resolve()


def _display_path(path: Path) -> str:
    return str(path).replace(os.sep, "/")


def _as_string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


def _is_safe_relative_ref(ref: str) -> bool:
    text = str(ref or "").strip().replace("\\", "/")
    if not text or text.startswith("/") or text.startswith("~"):
        return False
    parts = PurePosixPath(text).parts
    return not any(part in {"", ".", ".."} for part in parts)


def _resolve_ref(ref: str, *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    candidates = [
        ("package", package_root / ref),
        ("project", project_root / ref),
    ]
    if not str(ref).startswith("noemaforge/"):
        candidates.append(("project_noemaforge", project_root / "noemaforge" / ref))

    checked: List[str] = []
    for base_name, path in candidates:
        checked.append(_display_path(path))
        if path.exists():
            return {
                "ok": True,
                "ref": ref,
                "resolved_under": base_name,
                "path": _display_path(path),
                "checked": checked,
            }
    return {"ok": False, "ref": ref, "resolved_under": "", "path": "", "checked": checked}


def _resolve_refs(refs: Sequence[str], *, project_root: Path, package_root: Path, owner: str) -> Dict[str, Any]:
    failures: List[str] = []
    resolved_refs: List[Dict[str, Any]] = []
    missing_refs: List[Dict[str, Any]] = []
    unsafe_refs: List[Dict[str, Any]] = []
    for ref in refs:
        if not _is_safe_relative_ref(ref):
            item = {"owner": owner, "ref": ref}
            unsafe_refs.append(item)
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


def load_frame_set(frame_set_path: Path | str) -> Dict[str, Any]:
    return json.loads(Path(frame_set_path).read_text(encoding="utf-8"))


def _policy_failures(payload: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    policy = payload.get("policy") if isinstance(payload.get("policy"), dict) else {}
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
    for key in [
        "require_trace_id",
        "require_role",
        "require_context",
        "require_options",
        "require_risks",
        "require_recommendation",
        "dangerous_actions_require_admin_approval",
        "pipeline_mutation_requires_rfc",
        "persistence_export_requires_privacy_filter",
        "internet_research_requires_research_packet",
        "uncertainty_requires_honesty_state",
    ]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    roles = set(_as_string_list(policy.get("allowed_roles")))
    decision_types = set(_as_string_list(policy.get("allowed_decision_types")))
    honesty_states = set(_as_string_list(policy.get("allowed_honesty_states")))
    if roles != VALID_ROLES:
        failures.append("policy_allowed_roles_must_be_admin_architect")
    failures.extend(f"policy_invalid_decision_type:{item}" for item in sorted(decision_types - VALID_DECISION_TYPES))
    failures.extend(f"policy_invalid_honesty_state:{item}" for item in sorted(honesty_states - VALID_HONESTY_STATES))
    if not _as_string_list(policy.get("dangerous_actions")):
        failures.append("policy_dangerous_actions_empty")
    if not _as_string_list(policy.get("required_example_sets")):
        failures.append("policy_required_example_sets_empty")
    return failures


def _non_empty_text(value: Any) -> bool:
    return bool(str(value or "").strip())


def _non_empty_list(value: Any) -> bool:
    return isinstance(value, list) and any(item for item in value)


def _frame_failures(frame: Dict[str, Any], policy: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    frame_id = str(frame.get("id") or "<missing>")
    if frame.get("apiVersion") != API_VERSION:
        failures.append(f"frame_api_version_invalid:{frame_id}")
    if frame.get("kind") != FRAME_KIND:
        failures.append(f"frame_kind_invalid:{frame_id}")
    if not SAFE_ID_RE.match(frame_id):
        failures.append(f"frame_id_invalid:{frame_id}")
    if policy.get("require_trace_id") is True and not SAFE_ID_RE.match(str(frame.get("trace_id") or "")):
        failures.append(f"frame_trace_id_invalid:{frame_id}")
    allowed_roles = set(_as_string_list(policy.get("allowed_roles")))
    role = str(frame.get("role") or "")
    if policy.get("require_role") is True and role not in allowed_roles:
        failures.append(f"frame_role_not_allowed:{frame_id}:{role}")
    decision_type = str(frame.get("decision_type") or "")
    if decision_type not in set(_as_string_list(policy.get("allowed_decision_types"))):
        failures.append(f"frame_decision_type_not_allowed:{frame_id}:{decision_type}")
    if not _non_empty_text(frame.get("intent")):
        failures.append(f"frame_intent_missing:{frame_id}")

    context = frame.get("context") if isinstance(frame.get("context"), dict) else {}
    if policy.get("require_context") is True:
        if not _non_empty_text(context.get("summary")):
            failures.append(f"frame_context_summary_missing:{frame_id}")
        if not _non_empty_list(context.get("source_refs")):
            failures.append(f"frame_context_source_refs_missing:{frame_id}")
    for key, failure_key, required in [
        ("assumptions", "frame_assumptions_missing", True),
        ("constraints", "frame_constraints_missing", True),
        ("risks", "frame_risks_missing", policy.get("require_risks") is True),
        ("options", "frame_options_missing", policy.get("require_options") is True),
    ]:
        if required and not _non_empty_list(frame.get(key)):
            failures.append(f"{failure_key}:{frame_id}")

    option_ids = {
        str(option.get("id") or "")
        for option in frame.get("options") or []
        if isinstance(option, dict)
    }
    for option in frame.get("options") or []:
        if not isinstance(option, dict):
            failures.append(f"frame_option_not_object:{frame_id}")
            continue
        option_id = str(option.get("id") or "")
        if not SAFE_ID_RE.match(option_id):
            failures.append(f"frame_option_id_invalid:{frame_id}:{option_id}")
        for key in ["summary", "expected_outcome", "risk_level"]:
            if not _non_empty_text(option.get(key)):
                failures.append(f"frame_option_{key}_missing:{frame_id}:{option_id}")

    recommendation = frame.get("recommendation") if isinstance(frame.get("recommendation"), dict) else {}
    if policy.get("require_recommendation") is True:
        selected = str(recommendation.get("selected_option_id") or "")
        if selected not in option_ids:
            failures.append(f"frame_recommendation_option_invalid:{frame_id}:{selected}")
        if not _non_empty_text(recommendation.get("rationale")):
            failures.append(f"frame_recommendation_rationale_missing:{frame_id}")
        if not _non_empty_text(recommendation.get("action")):
            failures.append(f"frame_recommendation_action_missing:{frame_id}")

    gates = frame.get("gates") if isinstance(frame.get("gates"), dict) else {}
    action = str(recommendation.get("action") or "")
    dangerous_actions = set(_as_string_list(policy.get("dangerous_actions")))
    dangerous = gates.get("dangerous_action") is True or action in dangerous_actions or decision_type in {"pipeline_mutation", "persistence_export", "internet_research"}
    if dangerous and gates.get("dangerous_action") is not True:
        failures.append(f"frame_dangerous_action_not_marked:{frame_id}")
    if policy.get("dangerous_actions_require_admin_approval") is True and dangerous:
        if gates.get("approval_required") is not True:
            failures.append(f"frame_approval_not_required_for_dangerous_action:{frame_id}")
        if not _non_empty_list(gates.get("approval_refs")):
            failures.append(f"frame_approval_refs_missing:{frame_id}")
    if policy.get("pipeline_mutation_requires_rfc") is True and (decision_type == "pipeline_mutation" or action == "pipeline_mutation"):
        if gates.get("pipeline_rfc_required") is not True:
            failures.append(f"frame_pipeline_rfc_not_required:{frame_id}")
        if not _non_empty_text(gates.get("pipeline_rfc_ref")):
            failures.append(f"frame_pipeline_rfc_ref_missing:{frame_id}")
    if policy.get("persistence_export_requires_privacy_filter") is True and (decision_type == "persistence_export" or action == "export_data"):
        if gates.get("privacy_filter_required") is not True:
            failures.append(f"frame_privacy_filter_not_required:{frame_id}")
        if not _non_empty_text(gates.get("privacy_filter_ref")):
            failures.append(f"frame_privacy_filter_ref_missing:{frame_id}")
    if policy.get("internet_research_requires_research_packet") is True and (decision_type == "internet_research" or action == "network_research"):
        if gates.get("research_packet_required") is not True:
            failures.append(f"frame_research_packet_not_required:{frame_id}")
        if not _non_empty_text(gates.get("research_packet_ref")):
            failures.append(f"frame_research_packet_ref_missing:{frame_id}")
    honesty_state = str(gates.get("honesty_state") or "")
    if policy.get("uncertainty_requires_honesty_state") is True and honesty_state not in set(_as_string_list(policy.get("allowed_honesty_states"))):
        failures.append(f"frame_honesty_state_invalid:{frame_id}:{honesty_state}")
    return failures


def validate_concept_frame_policy(
    payload: Dict[str, Any],
    *,
    project_root: Path | str,
    package_root: Path | str,
    policy_path: Optional[Path | str] = None,
) -> Dict[str, Any]:
    project = _as_path(project_root)
    package = _as_path(package_root)
    if not project.exists():
        raise FileNotFoundError(project)
    if not package.exists():
        raise FileNotFoundError(package)

    policy = payload.get("policy") if isinstance(payload.get("policy"), dict) else {}
    failures: List[str] = []
    failures.extend(_policy_failures(payload))

    all_resolved_refs: List[Dict[str, Any]] = []
    all_missing_refs: List[Dict[str, Any]] = []
    all_unsafe_refs: List[Dict[str, Any]] = []
    frame_results: List[Dict[str, Any]] = []

    policy_refs = _resolve_refs(_as_string_list(payload.get("refs")), project_root=project, package_root=package, owner=str(payload.get("id") or "policy"))
    failures.extend(policy_refs["failures"])
    all_resolved_refs.extend(policy_refs["resolved_refs"])
    all_missing_refs.extend(policy_refs["missing_refs"])
    all_unsafe_refs.extend(policy_refs["unsafe_refs"])

    example_refs = _as_string_list(policy.get("required_example_sets"))
    example_ref_results = _resolve_refs(example_refs, project_root=project, package_root=package, owner="required_example_sets")
    failures.extend(example_ref_results["failures"])
    all_resolved_refs.extend(example_ref_results["resolved_refs"])
    all_missing_refs.extend(example_ref_results["missing_refs"])
    all_unsafe_refs.extend(example_ref_results["unsafe_refs"])

    seen_frame_ids = set()
    for item in example_ref_results["resolved_refs"]:
        frame_set_path = Path(item["path"])
        frame_set = load_frame_set(frame_set_path)
        if frame_set.get("apiVersion") != API_VERSION:
            failures.append(f"frame_set_api_version_invalid:{item['ref']}")
        if frame_set.get("kind") != FRAME_SET_KIND:
            failures.append(f"frame_set_kind_invalid:{item['ref']}")
        frames = frame_set.get("frames") if isinstance(frame_set.get("frames"), list) else []
        if not frames:
            failures.append(f"frame_set_empty:{item['ref']}")
        for frame in frames:
            if not isinstance(frame, dict):
                failures.append(f"frame_not_object:{item['ref']}")
                continue
            frame_id = str(frame.get("id") or "<missing>")
            if frame_id in seen_frame_ids:
                failures.append(f"frame_id_duplicate:{frame_id}")
            seen_frame_ids.add(frame_id)
            frame_failures = _frame_failures(frame, policy)
            refs_result = _resolve_refs(
                _as_string_list(frame.get("refs")) + _as_string_list((frame.get("context") or {}).get("source_refs") if isinstance(frame.get("context"), dict) else []),
                project_root=project,
                package_root=package,
                owner=frame_id,
            )
            frame_failures.extend(refs_result["failures"])
            failures.extend(frame_failures)
            all_resolved_refs.extend(refs_result["resolved_refs"])
            all_missing_refs.extend(refs_result["missing_refs"])
            all_unsafe_refs.extend(refs_result["unsafe_refs"])
            gates = frame.get("gates") if isinstance(frame.get("gates"), dict) else {}
            frame_results.append(
                {
                    "id": frame_id,
                    "ok": not frame_failures,
                    "role": str(frame.get("role") or ""),
                    "decision_type": str(frame.get("decision_type") or ""),
                    "dangerous_action": gates.get("dangerous_action") is True,
                    "approval_required": gates.get("approval_required") is True,
                    "pipeline_rfc_required": gates.get("pipeline_rfc_required") is True,
                    "honesty_state": str(gates.get("honesty_state") or ""),
                    "failures": sorted(set(frame_failures)),
                }
            )

    roles_seen = {item["role"] for item in frame_results}
    for role in VALID_ROLES:
        if role not in roles_seen:
            failures.append(f"example_role_missing:{role}")
    checks = [
        {"id": "policy_schema", "status": "passed" if not any(item.startswith("policy_") for item in failures) else "failed"},
        {"id": "admin_frame_present", "status": "passed" if "admin" in roles_seen else "failed"},
        {"id": "architect_frame_present", "status": "passed" if "architect" in roles_seen else "failed"},
        {"id": "dangerous_action_approval", "status": "passed" if not any("approval" in item for item in failures) else "failed"},
        {"id": "pipeline_rfc_gate", "status": "passed" if not any("pipeline_rfc" in item for item in failures) else "failed"},
        {"id": "refs_resolved", "status": "passed" if not all_missing_refs and not all_unsafe_refs else "failed"},
    ]
    metrics = {
        "frames": len(frame_results),
        "passing_frames": sum(1 for item in frame_results if item["ok"]),
        "admin_frames": sum(1 for item in frame_results if item["role"] == "admin"),
        "architect_frames": sum(1 for item in frame_results if item["role"] == "architect"),
        "dangerous_frames": sum(1 for item in frame_results if item["dangerous_action"]),
        "approval_required_frames": sum(1 for item in frame_results if item["approval_required"]),
        "pipeline_rfc_required_frames": sum(1 for item in frame_results if item["pipeline_rfc_required"]),
        "refs": len(all_resolved_refs) + len(all_missing_refs) + len(all_unsafe_refs),
        "resolved_refs": len(all_resolved_refs),
        "missing_refs": len(all_missing_refs),
        "unsafe_refs": len(all_unsafe_refs),
    }
    return {
        "apiVersion": API_VERSION,
        "kind": REPORT_KIND,
        "ok": not failures,
        "created_at": _nowz(),
        "policy_path": str(policy_path or ""),
        "project_root": _display_path(project),
        "package_root": _display_path(package),
        "failures": sorted(set(failures)),
        "metrics": metrics,
        "checks": checks,
        "frame_results": sorted(frame_results, key=lambda item: item["id"]),
        "resolved_refs": sorted(all_resolved_refs, key=lambda item: (item["owner"], item["ref"])),
        "missing_refs": sorted(all_missing_refs, key=lambda item: (item["owner"], item["ref"])),
        "unsafe_refs": sorted(all_unsafe_refs, key=lambda item: (item["owner"], item["ref"])),
    }


def concept_frame_report_to_gate_evidence(report: Dict[str, Any], *, artifact_uri: str = "") -> Dict[str, Any]:
    if not isinstance(report, dict) or report.get("kind") != REPORT_KIND:
        raise ValueError("concept_frame_report_required")
    status = "passed" if report.get("ok") else "failed"
    return {
        "artifact_uri": str(artifact_uri or report.get("artifact_uri") or ""),
        "run_at": str(report.get("created_at") or _nowz()),
        "checks": [
            {"id": "pipeline_eval", "status": status, "score": 1.0 if status == "passed" else 0.0, "threshold": 1.0},
            {"id": "rollback_plan", "status": status, "score": 1.0 if status == "passed" else 0.0, "threshold": 1.0},
            {"id": "safety_eval", "status": status, "score": 1.0 if status == "passed" else 0.0, "threshold": 1.0},
        ],
    }


def _default_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate NoemaForge Concept_Frame governance contracts.")
    parser.add_argument("--project-root", default=str(_default_project_root()), help="Project root containing noemaforge/ and docs/.")
    parser.add_argument("--package-root", default="", help="Package root, default: <project-root>/noemaforge.")
    parser.add_argument(
        "--policy",
        default="noemaforge/configs/concept-frame-policy.json",
        help="Policy path, absolute or relative to project root.",
    )
    parser.add_argument("--summary", action="store_true", help="Emit a compact validation summary.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    project_root = _as_path(args.project_root)
    package_root = _as_path(args.package_root) if args.package_root else project_root / "noemaforge"
    policy_path = Path(args.policy)
    if not policy_path.is_absolute():
        policy_path = project_root / policy_path

    report = validate_concept_frame_policy(
        load_policy(policy_path),
        project_root=project_root,
        package_root=package_root,
        policy_path=policy_path,
    )
    if args.summary:
        payload: Dict[str, Any] = {
            "apiVersion": report["apiVersion"],
            "kind": "ConceptFrameValidationSummary",
            "ok": report["ok"],
            "created_at": report["created_at"],
            "policy_path": report["policy_path"],
            "metrics": report["metrics"],
            "failures": report["failures"],
        }
    else:
        payload = report
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
