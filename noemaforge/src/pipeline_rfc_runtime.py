#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/pipeline_rfc_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate Pipeline_RFC contracts for self-development and pipeline mutation gates.
Inputs: noemaforge/configs/pipeline-rfc-policy.json and PipelineRFC examples.
Outputs: JSON-compatible PipelineRFCValidationReport artifacts.
Side effects: None unless run as a CLI, which writes JSON to stdout.
Tests: noemaforge/tests/test_pipeline_rfc_runtime.py
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


API_VERSION = "noemaforge.pipeline-rfc/v1"
POLICY_KIND = "PipelineRFCPolicy"
SET_KIND = "PipelineRFCSet"
RFC_KIND = "PipelineRFC"
REPORT_KIND = "PipelineRFCValidationReport"

VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
REQUIRED_STAGE_ORDER = ["rfc", "dry_run", "eval", "rollback", "approval", "apply"]
REQUIRED_EVAL_CHECKS = {"pipeline_eval", "safety_eval", "rollback_plan"}
VALID_MUTATION_TYPES = {"pipeline_config", "role_flow", "tool_policy", "model_route", "code_patch"}
VALID_APPROVAL_STATES = {"not_requested", "requested", "approved", "rejected"}
VALID_RFC_STATUSES = {"draft", "ready_for_review", "ready_to_apply", "blocked", "applied"}
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
            return {"ok": True, "ref": ref, "resolved_under": base_name, "path": _display_path(path), "checked": checked}
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


def _policy_dict(payload: Dict[str, Any]) -> Dict[str, Any]:
    return payload.get("policy") if isinstance(payload.get("policy"), dict) else payload


def _approval_is_explicit(approval: Dict[str, Any]) -> bool:
    return (
        str(approval.get("state") or "") == "approved"
        and approval.get("explicit") is True
        and bool(str(approval.get("approver_role") or "").strip())
        and bool(str(approval.get("approved_at") or "").strip())
    )


def _eval_statuses(rfc: Dict[str, Any]) -> Dict[str, str]:
    evidence = rfc.get("eval_evidence") if isinstance(rfc.get("eval_evidence"), list) else []
    return {str(item.get("id") or ""): str(item.get("status") or "") for item in evidence if isinstance(item, dict)}


def _readiness_failures(rfc: Dict[str, Any], policy_payload: Dict[str, Any]) -> List[str]:
    policy = _policy_dict(policy_payload)
    failures: List[str] = []
    rfc_id = str(rfc.get("id") or "<missing>")
    dry_run = rfc.get("dry_run") if isinstance(rfc.get("dry_run"), dict) else {}
    if policy.get("dry_run_required") is True:
        if dry_run.get("performed") is not True:
            failures.append(f"rfc_dry_run_missing:{rfc_id}")
        if dry_run.get("side_effects") is not False:
            failures.append(f"rfc_dry_run_has_side_effects:{rfc_id}")
        if not str(dry_run.get("artifact_ref") or "").strip():
            failures.append(f"rfc_dry_run_artifact_missing:{rfc_id}")
    eval_statuses = _eval_statuses(rfc)
    for check_id in _as_string_list(policy.get("required_eval_checks")):
        if eval_statuses.get(check_id) != "passed":
            failures.append(f"rfc_eval_check_not_passed:{rfc_id}:{check_id}:{eval_statuses.get(check_id, '<missing>')}")
    rollback = rfc.get("rollback_plan") if isinstance(rfc.get("rollback_plan"), dict) else {}
    if policy.get("rollback_plan_required") is True:
        if rollback.get("present") is not True:
            failures.append(f"rfc_rollback_plan_missing:{rfc_id}")
        if not str(rollback.get("artifact_ref") or "").strip():
            failures.append(f"rfc_rollback_artifact_missing:{rfc_id}")
        if not _as_string_list(rollback.get("steps")):
            failures.append(f"rfc_rollback_steps_missing:{rfc_id}")
    approval = rfc.get("approval") if isinstance(rfc.get("approval"), dict) else {}
    if policy.get("explicit_approval_required") is True and not _approval_is_explicit(approval):
        failures.append(f"rfc_explicit_approval_missing:{rfc_id}")
    proposed = rfc.get("proposed_diff") if isinstance(rfc.get("proposed_diff"), dict) else {}
    if proposed.get("dangerous_action") is True and not _approval_is_explicit(approval):
        failures.append(f"rfc_dangerous_action_not_approved:{rfc_id}")
    return failures


def build_pipeline_rfc(
    mutation_type: str,
    proposed_diff: Dict[str, Any],
    dry_run: Dict[str, Any],
    eval_evidence: Sequence[Dict[str, Any]],
    rollback_plan: Dict[str, Any],
    approval: Dict[str, Any],
    policy_payload: Dict[str, Any],
    *,
    trace_id: str = "trace:pipeline-rfc:inline",
    rfc_id: str = "pipeline-rfc:inline",
    title: str = "Inline Pipeline RFC",
    apply_requested: bool = True,
) -> Dict[str, Any]:
    rfc = {
        "apiVersion": API_VERSION,
        "kind": RFC_KIND,
        "id": rfc_id,
        "trace_id": trace_id,
        "status": "draft",
        "mutation_type": mutation_type,
        "title": title,
        "summary": str(proposed_diff.get("mutation_summary") or title),
        "stage_order": list(REQUIRED_STAGE_ORDER),
        "proposed_diff": dict(proposed_diff),
        "dry_run": dict(dry_run),
        "eval_evidence": [dict(item) for item in eval_evidence],
        "rollback_plan": dict(rollback_plan),
        "approval": dict(approval),
        "finalization": {
            "apply_requested": bool(apply_requested),
            "apply_allowed": False,
            "applied": False,
        },
        "refs": [],
    }
    ready = not _readiness_failures(rfc, policy_payload)
    rfc["finalization"]["apply_allowed"] = bool(apply_requested and ready)
    rfc["status"] = "ready_to_apply" if rfc["finalization"]["apply_allowed"] else ("blocked" if apply_requested else "ready_for_review")
    return rfc


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
        "rfc_required_for_mutation",
        "dry_run_required",
        "eval_evidence_required",
        "rollback_plan_required",
        "explicit_approval_required",
        "apply_blocked_without_approval",
        "dangerous_action_review_required",
    ]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    if policy.get("dry_run_side_effects_allowed") is not False:
        failures.append("policy_dry_run_side_effects_allowed_not_false")
    if set(_as_string_list(policy.get("mutation_types"))) != VALID_MUTATION_TYPES:
        failures.append("policy_mutation_types_incomplete")
    if _as_string_list(policy.get("required_stage_order")) != REQUIRED_STAGE_ORDER:
        failures.append("policy_required_stage_order_invalid")
    if set(_as_string_list(policy.get("required_eval_checks"))) != REQUIRED_EVAL_CHECKS:
        failures.append("policy_required_eval_checks_incomplete")
    if set(_as_string_list(policy.get("approval_states"))) != VALID_APPROVAL_STATES:
        failures.append("policy_approval_states_incomplete")
    if set(_as_string_list(policy.get("rfc_statuses"))) != VALID_RFC_STATUSES:
        failures.append("policy_rfc_statuses_incomplete")
    if not _as_string_list(policy.get("required_example_sets")):
        failures.append("policy_required_example_sets_empty")
    return failures


def _rfc_refs(rfc: Dict[str, Any]) -> List[str]:
    refs = _as_string_list(rfc.get("refs"))
    dry_run = rfc.get("dry_run") if isinstance(rfc.get("dry_run"), dict) else {}
    rollback = rfc.get("rollback_plan") if isinstance(rfc.get("rollback_plan"), dict) else {}
    refs.extend(_as_string_list([dry_run.get("artifact_ref"), rollback.get("artifact_ref")]))
    for item in rfc.get("eval_evidence") if isinstance(rfc.get("eval_evidence"), list) else []:
        if isinstance(item, dict):
            refs.extend(_as_string_list([item.get("artifact_ref")]))
    return sorted(set(refs))


def _rfc_failures(rfc: Dict[str, Any], policy_payload: Dict[str, Any]) -> List[str]:
    policy = _policy_dict(policy_payload)
    failures: List[str] = []
    rfc_id = str(rfc.get("id") or "<missing>")
    if rfc.get("apiVersion") != API_VERSION:
        failures.append(f"rfc_api_version_invalid:{rfc_id}")
    if rfc.get("kind") != RFC_KIND:
        failures.append(f"rfc_kind_invalid:{rfc_id}")
    if not SAFE_ID_RE.match(rfc_id):
        failures.append(f"rfc_id_invalid:{rfc_id}")
    if policy.get("require_trace_id") is True and not SAFE_ID_RE.match(str(rfc.get("trace_id") or "")):
        failures.append(f"rfc_trace_id_invalid:{rfc_id}")
    if str(rfc.get("status") or "") not in set(_as_string_list(policy.get("rfc_statuses"))):
        failures.append(f"rfc_status_invalid:{rfc_id}:{rfc.get('status')}")
    if str(rfc.get("mutation_type") or "") not in set(_as_string_list(policy.get("mutation_types"))):
        failures.append(f"rfc_mutation_type_invalid:{rfc_id}:{rfc.get('mutation_type')}")
    if _as_string_list(rfc.get("stage_order")) != _as_string_list(policy.get("required_stage_order")):
        failures.append(f"rfc_stage_order_invalid:{rfc_id}")
    if not str(rfc.get("title") or "").strip():
        failures.append(f"rfc_title_missing:{rfc_id}")
    if not str(rfc.get("summary") or "").strip():
        failures.append(f"rfc_summary_missing:{rfc_id}")
    proposed = rfc.get("proposed_diff") if isinstance(rfc.get("proposed_diff"), dict) else {}
    if not _as_string_list(proposed.get("files")):
        failures.append(f"rfc_diff_files_missing:{rfc_id}")
    if str(proposed.get("risk_level") or "") not in {"low", "medium", "high", "critical"}:
        failures.append(f"rfc_risk_level_invalid:{rfc_id}:{proposed.get('risk_level')}")
    finalization = rfc.get("finalization") if isinstance(rfc.get("finalization"), dict) else {}
    apply_requested = finalization.get("apply_requested") is True
    apply_allowed = finalization.get("apply_allowed") is True
    applied = finalization.get("applied") is True
    readiness_failures = _readiness_failures(rfc, policy_payload)
    if apply_allowed and readiness_failures:
        failures.extend(f"rfc_apply_allowed_with_blocker:{rfc_id}:{item}" for item in readiness_failures)
    if apply_requested and not apply_allowed and str(rfc.get("status") or "") != "blocked":
        failures.append(f"rfc_apply_blocked_status_mismatch:{rfc_id}:{rfc.get('status')}")
    if apply_allowed and str(rfc.get("status") or "") not in {"ready_to_apply", "applied"}:
        failures.append(f"rfc_apply_allowed_status_mismatch:{rfc_id}:{rfc.get('status')}")
    if applied and not apply_allowed:
        failures.append(f"rfc_applied_without_apply_allowed:{rfc_id}")
    if applied and not _approval_is_explicit(rfc.get("approval") if isinstance(rfc.get("approval"), dict) else {}):
        failures.append(f"rfc_applied_without_approval:{rfc_id}")
    approval = rfc.get("approval") if isinstance(rfc.get("approval"), dict) else {}
    if str(approval.get("state") or "") not in set(_as_string_list(policy.get("approval_states"))):
        failures.append(f"rfc_approval_state_invalid:{rfc_id}:{approval.get('state')}")
    return failures


def _scoring_case_result(case: Dict[str, Any], policy_payload: Dict[str, Any]) -> Dict[str, Any]:
    case_id = str(case.get("id") or "<missing>")
    raw = case.get("rfc") if isinstance(case.get("rfc"), dict) else {}
    rfc = build_pipeline_rfc(
        str(raw.get("mutation_type") or ""),
        raw.get("proposed_diff") if isinstance(raw.get("proposed_diff"), dict) else {},
        raw.get("dry_run") if isinstance(raw.get("dry_run"), dict) else {},
        raw.get("eval_evidence") if isinstance(raw.get("eval_evidence"), list) else [],
        raw.get("rollback_plan") if isinstance(raw.get("rollback_plan"), dict) else {},
        raw.get("approval") if isinstance(raw.get("approval"), dict) else {},
        policy_payload,
        trace_id=f"trace:pipeline-rfc:{case_id}",
        rfc_id=f"pipeline-rfc:{case_id}",
        apply_requested=((raw.get("finalization") or {}).get("apply_requested") is True) if isinstance(raw.get("finalization"), dict) else True,
    )
    finalization = rfc["finalization"]
    result_failures: List[str] = []
    expected_status = str(case.get("expected_status") or "")
    if expected_status and rfc["status"] != expected_status:
        result_failures.append(f"scoring_status_mismatch:{case_id}:{rfc['status']}:{expected_status}")
    expected_apply_allowed = bool(case.get("expected_apply_allowed"))
    if bool(finalization["apply_allowed"]) is not expected_apply_allowed:
        result_failures.append(f"scoring_apply_allowed_mismatch:{case_id}:{finalization['apply_allowed']}:{expected_apply_allowed}")
    return {
        "id": case_id,
        "ok": not result_failures,
        "status": rfc["status"],
        "apply_allowed": bool(finalization["apply_allowed"]),
        "failures": sorted(set(result_failures)),
    }


def validate_pipeline_rfc_policy(
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

    policy = _policy_dict(payload)
    failures: List[str] = []
    failures.extend(_policy_failures(payload))
    all_resolved_refs: List[Dict[str, Any]] = []
    all_missing_refs: List[Dict[str, Any]] = []
    all_unsafe_refs: List[Dict[str, Any]] = []
    rfc_results: List[Dict[str, Any]] = []
    scoring_results: List[Dict[str, Any]] = []

    policy_refs = _resolve_refs(_as_string_list(payload.get("refs")), project_root=project, package_root=package, owner=str(payload.get("id") or "policy"))
    failures.extend(policy_refs["failures"])
    all_resolved_refs.extend(policy_refs["resolved_refs"])
    all_missing_refs.extend(policy_refs["missing_refs"])
    all_unsafe_refs.extend(policy_refs["unsafe_refs"])

    example_ref_results = _resolve_refs(_as_string_list(policy.get("required_example_sets")), project_root=project, package_root=package, owner="required_example_sets")
    failures.extend(example_ref_results["failures"])
    all_resolved_refs.extend(example_ref_results["resolved_refs"])
    all_missing_refs.extend(example_ref_results["missing_refs"])
    all_unsafe_refs.extend(example_ref_results["unsafe_refs"])

    for item in example_ref_results["resolved_refs"]:
        example_set = load_example_set(Path(item["path"]))
        if example_set.get("apiVersion") != API_VERSION:
            failures.append(f"example_set_api_version_invalid:{item['ref']}")
        if example_set.get("kind") != SET_KIND:
            failures.append(f"example_set_kind_invalid:{item['ref']}")
        rfcs = example_set.get("rfcs") if isinstance(example_set.get("rfcs"), list) else []
        if not rfcs:
            failures.append(f"example_set_rfcs_empty:{item['ref']}")
        for rfc in rfcs:
            if not isinstance(rfc, dict):
                failures.append(f"rfc_not_object:{item['ref']}")
                continue
            rfc_id = str(rfc.get("id") or "<missing>")
            rfc_failures = _rfc_failures(rfc, payload)
            refs_result = _resolve_refs(_rfc_refs(rfc), project_root=project, package_root=package, owner=rfc_id)
            rfc_failures.extend(refs_result["failures"])
            failures.extend(rfc_failures)
            all_resolved_refs.extend(refs_result["resolved_refs"])
            all_missing_refs.extend(refs_result["missing_refs"])
            all_unsafe_refs.extend(refs_result["unsafe_refs"])
            rfc_results.append(
                {
                    "id": rfc_id,
                    "ok": not rfc_failures,
                    "status": str(rfc.get("status") or ""),
                    "apply_allowed": bool((rfc.get("finalization") or {}).get("apply_allowed")) if isinstance(rfc.get("finalization"), dict) else False,
                    "failures": sorted(set(rfc_failures)),
                }
            )
        for case in example_set.get("scoring_cases") if isinstance(example_set.get("scoring_cases"), list) else []:
            if not isinstance(case, dict):
                failures.append(f"scoring_case_not_object:{item['ref']}")
                continue
            result = _scoring_case_result(case, payload)
            failures.extend(result["failures"])
            scoring_results.append(result)

    checks = [
        {"id": "rfc_required", "status": "passed" if not any("rfc_" in item and "policy_" not in item for item in failures) else "failed"},
        {"id": "dry_run_required", "status": "passed" if not any("dry_run" in item for item in failures) else "failed"},
        {"id": "eval_evidence_required", "status": "passed" if not any("eval_check" in item for item in failures) else "failed"},
        {"id": "rollback_plan_required", "status": "passed" if not any("rollback" in item for item in failures) else "failed"},
        {"id": "explicit_approval_required", "status": "passed" if not any("approval" in item for item in failures) else "failed"},
        {"id": "scoring_cases", "status": "passed" if scoring_results and not any(not item["ok"] for item in scoring_results) else "failed"},
        {"id": "refs_resolved", "status": "passed" if not all_missing_refs and not all_unsafe_refs else "failed"},
    ]
    metrics = {
        "rfcs": len(rfc_results),
        "passing_rfcs": sum(1 for item in rfc_results if item["ok"]),
        "scoring_cases": len(scoring_results),
        "passing_scoring_cases": sum(1 for item in scoring_results if item["ok"]),
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
        "rfc_results": sorted(rfc_results, key=lambda item: item["id"]),
        "scoring_results": sorted(scoring_results, key=lambda item: item["id"]),
        "resolved_refs": sorted(all_resolved_refs, key=lambda item: (item["owner"], item["ref"])),
        "missing_refs": sorted(all_missing_refs, key=lambda item: (item["owner"], item["ref"])),
        "unsafe_refs": sorted(all_unsafe_refs, key=lambda item: (item["owner"], item["ref"])),
    }


def pipeline_rfc_report_to_gate_evidence(report: Dict[str, Any], *, artifact_uri: str = "") -> Dict[str, Any]:
    if not isinstance(report, dict) or report.get("kind") != REPORT_KIND:
        raise ValueError("pipeline_rfc_report_required")
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
    parser = argparse.ArgumentParser(description="Validate NoemaForge Pipeline_RFC mutation contracts.")
    parser.add_argument("--project-root", default=str(_default_project_root()), help="Project root containing noemaforge/ and docs/.")
    parser.add_argument("--package-root", default="", help="Package root, default: <project-root>/noemaforge.")
    parser.add_argument(
        "--policy",
        default="noemaforge/configs/pipeline-rfc-policy.json",
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

    report = validate_pipeline_rfc_policy(
        load_policy(policy_path),
        project_root=project_root,
        package_root=package_root,
        policy_path=policy_path,
    )
    if args.summary:
        payload: Dict[str, Any] = {
            "apiVersion": report["apiVersion"],
            "kind": "PipelineRFCValidationSummary",
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
