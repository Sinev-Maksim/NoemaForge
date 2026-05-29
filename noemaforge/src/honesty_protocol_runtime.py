#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/honesty_protocol_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Validate Honesty Protocol contracts for unknown, need-research and error-attribution states.
Inputs: noemaforge/configs/honesty-protocol-policy.json and HonestyProtocol example sets.
Outputs: JSON-compatible HonestyProtocolValidationReport artifacts.
Side effects: None unless run as a CLI, which writes JSON to stdout.
Tests: noemaforge/tests/test_honesty_protocol_runtime.py
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


API_VERSION = "noemaforge.honesty-protocol/v1"
POLICY_KIND = "HonestyProtocolPolicy"
SET_KIND = "HonestyProtocolSet"
CASE_KIND = "HonestyCase"
REPORT_KIND = "HonestyProtocolValidationReport"

VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
REQUIRED_TEMPLATE_STATES = {"unknown", "need_research", "error_attribution"}
VALID_HONESTY_STATES = {
    "sufficient_evidence",
    "unknown",
    "need_research",
    "insufficient_evidence",
    "policy_blocked",
    "error_attribution",
}
VALID_UNCERTAIN_STATES = {"unknown", "need_research", "insufficient_evidence", "policy_blocked"}
VALID_ACTIONS = {"answer", "ask_clarification", "request_research", "defer", "correct_error", "block"}
VALID_ERROR_CLASSES = {
    "model_error",
    "source_error",
    "data_missing",
    "policy_block",
    "external_constraint",
    "operator_input_ambiguous",
    "tool_error",
}
VALID_OWNERS = {"model", "system", "source", "policy", "external", "operator_input"}
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


def _non_empty_text(value: Any) -> bool:
    return bool(str(value or "").strip())


def _clip01(value: Any) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = 0.0
    if numeric < 0.0:
        return 0.0
    if numeric > 1.0:
        return 1.0
    return numeric


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


def load_example_set(example_path: Path | str) -> Dict[str, Any]:
    return json.loads(Path(example_path).read_text(encoding="utf-8"))


def _policy_dict(payload: Dict[str, Any]) -> Dict[str, Any]:
    return payload.get("policy") if isinstance(payload.get("policy"), dict) else payload


def classify_honesty_event(event: Dict[str, Any], policy_payload: Dict[str, Any]) -> Dict[str, Any]:
    policy = _policy_dict(policy_payload)
    max_uncertain = _clip01(policy.get("max_uncertain_confidence", 0.49))
    confidence = _clip01(event.get("confidence", 0.0))
    evidence_refs = _as_string_list(event.get("evidence_refs"))
    trace_id = str(event.get("trace_id") or "trace:honesty:inline")
    error = event.get("error") if isinstance(event.get("error"), dict) else {}
    policy_blocked = event.get("policy_blocked") is True
    freshness_required = event.get("freshness_required") is True

    if error:
        state = "error_attribution"
        next_action = "correct_error"
        error_class = str(error.get("class") or "tool_error")
        owner = "system"
        reason = str(error.get("summary") or "A tool or runtime error requires attribution before continuing.")
        user_message = "A tool or runtime error occurred, so I need to attribute it before claiming success."
    elif policy_blocked:
        state = "policy_blocked"
        next_action = "block"
        error_class = "policy_block"
        owner = "policy"
        confidence = min(confidence, max_uncertain)
        reason = "The requested action is blocked by policy."
        user_message = "I cannot proceed because the request is blocked by policy."
    elif freshness_required:
        state = "need_research"
        next_action = "request_research"
        error_class = "data_missing"
        owner = "external"
        confidence = min(confidence, max_uncertain)
        reason = "Fresh verification is required before making the claim."
        user_message = "This needs fresh verification before I can answer it responsibly."
    elif confidence <= max_uncertain or not evidence_refs:
        state = "unknown"
        next_action = "ask_clarification"
        error_class = "data_missing"
        owner = "system"
        confidence = min(confidence, max_uncertain)
        reason = "Available evidence is insufficient for a reliable answer."
        user_message = "I do not have enough evidence to answer that reliably."
    else:
        state = "sufficient_evidence"
        next_action = "answer"
        error_class = "data_missing"
        owner = "system"
        reason = "Evidence is available and confidence exceeds the uncertainty threshold."
        user_message = "The available evidence is sufficient to answer."

    if error_class not in set(_as_string_list(policy.get("error_classes"))) and error_class not in VALID_ERROR_CLASSES:
        error_class = "tool_error"

    return {
        "apiVersion": API_VERSION,
        "kind": CASE_KIND,
        "id": str(event.get("id") or f"honesty:{state}"),
        "trace_id": trace_id,
        "state": state,
        "trigger": str(event.get("trigger") or "classified_honesty_event"),
        "confidence": round(confidence, 3),
        "uncertainty_reason": reason,
        "evidence_refs": evidence_refs,
        "error_attribution": {
            "class": error_class,
            "owned_by": owner,
            "summary": reason,
        },
        "response_template": {
            "summary": f"{state} response",
            "user_message": user_message,
            "next_action": next_action,
            "repair_action": "Collect evidence, clarify scope, or correct the failed step before continuing.",
        },
        "guards": {
            "fabricated_citations": False,
            "blame_shift": False,
            "can_proceed_without_evidence": state == "sufficient_evidence",
        },
        "refs": list(evidence_refs),
    }


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
        "require_honesty_state",
        "require_uncertainty_reason",
        "require_next_action",
        "require_error_attribution",
        "require_repair_action_for_errors",
        "forbid_confident_unknowns",
        "forbid_fabricated_citations",
        "forbid_blame_shift",
    ]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    states = set(_as_string_list(policy.get("honesty_states")))
    uncertain_states = set(_as_string_list(policy.get("uncertain_states")))
    template_states = set(_as_string_list(policy.get("required_template_states")))
    actions = set(_as_string_list(policy.get("allowed_actions")))
    errors = set(_as_string_list(policy.get("error_classes")))
    if not VALID_HONESTY_STATES.issubset(states):
        failures.append("policy_honesty_states_incomplete")
    failures.extend(f"policy_unknown_honesty_state:{item}" for item in sorted(states - VALID_HONESTY_STATES))
    if not VALID_UNCERTAIN_STATES.issubset(uncertain_states):
        failures.append("policy_uncertain_states_incomplete")
    failures.extend(f"policy_unknown_uncertain_state:{item}" for item in sorted(uncertain_states - VALID_UNCERTAIN_STATES))
    if not REQUIRED_TEMPLATE_STATES.issubset(template_states):
        failures.append("policy_required_template_states_incomplete")
    failures.extend(f"policy_action_not_allowed:{item}" for item in sorted(actions - VALID_ACTIONS))
    failures.extend(f"policy_error_class_not_allowed:{item}" for item in sorted(errors - VALID_ERROR_CLASSES))
    try:
        max_uncertain = float(policy.get("max_uncertain_confidence"))
    except (TypeError, ValueError):
        max_uncertain = -1.0
    if max_uncertain <= 0.0 or max_uncertain >= 1.0:
        failures.append("policy_max_uncertain_confidence_invalid")
    if not _as_string_list(policy.get("required_example_sets")):
        failures.append("policy_required_example_sets_empty")
    return failures


def _case_failures(case: Dict[str, Any], policy: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    case_id = str(case.get("id") or "<missing>")
    if case.get("apiVersion") != API_VERSION:
        failures.append(f"case_api_version_invalid:{case_id}")
    if case.get("kind") != CASE_KIND:
        failures.append(f"case_kind_invalid:{case_id}")
    if not SAFE_ID_RE.match(case_id):
        failures.append(f"case_id_invalid:{case_id}")
    if policy.get("require_trace_id") is True and not SAFE_ID_RE.match(str(case.get("trace_id") or "")):
        failures.append(f"case_trace_id_invalid:{case_id}")
    state = str(case.get("state") or "")
    allowed_states = set(_as_string_list(policy.get("honesty_states")))
    uncertain_states = set(_as_string_list(policy.get("uncertain_states")))
    if state not in allowed_states:
        failures.append(f"case_state_not_allowed:{case_id}:{state}")
    confidence = _clip01(case.get("confidence"))
    if case.get("confidence") != confidence:
        failures.append(f"case_confidence_out_of_range:{case_id}:{case.get('confidence')}")
    if policy.get("forbid_confident_unknowns") is True and state in uncertain_states:
        if confidence > _clip01(policy.get("max_uncertain_confidence")):
            failures.append(f"case_uncertain_confidence_too_high:{case_id}:{confidence}")
    if policy.get("require_uncertainty_reason") is True and not _non_empty_text(case.get("uncertainty_reason")):
        failures.append(f"case_uncertainty_reason_missing:{case_id}")

    evidence_refs = _as_string_list(case.get("evidence_refs"))
    if state in {"sufficient_evidence", "error_attribution"} and not evidence_refs:
        failures.append(f"case_evidence_refs_missing:{case_id}")
    attribution = case.get("error_attribution") if isinstance(case.get("error_attribution"), dict) else {}
    if policy.get("require_error_attribution") is True:
        error_class = str(attribution.get("class") or "")
        owner = str(attribution.get("owned_by") or "")
        if error_class not in set(_as_string_list(policy.get("error_classes"))):
            failures.append(f"case_error_class_not_allowed:{case_id}:{error_class}")
        if owner not in VALID_OWNERS:
            failures.append(f"case_error_owner_not_allowed:{case_id}:{owner}")
        if not _non_empty_text(attribution.get("summary")):
            failures.append(f"case_error_summary_missing:{case_id}")

    template = case.get("response_template") if isinstance(case.get("response_template"), dict) else {}
    if not _non_empty_text(template.get("user_message")):
        failures.append(f"case_user_message_missing:{case_id}")
    next_action = str(template.get("next_action") or "")
    if policy.get("require_next_action") is True and next_action not in set(_as_string_list(policy.get("allowed_actions"))):
        failures.append(f"case_next_action_not_allowed:{case_id}:{next_action}")
    if policy.get("require_repair_action_for_errors") is True and state in {"error_attribution", "policy_blocked", "need_research", "unknown"}:
        if not _non_empty_text(template.get("repair_action")):
            failures.append(f"case_repair_action_missing:{case_id}")
    if not evidence_refs and any(token in str(template.get("user_message") or "").lower() for token in ["http://", "https://", "source:", "citation"]):
        failures.append(f"case_fabricated_citation_risk:{case_id}")

    guards = case.get("guards") if isinstance(case.get("guards"), dict) else {}
    if policy.get("forbid_fabricated_citations") is True and guards.get("fabricated_citations") is not False:
        failures.append(f"case_fabricated_citations_allowed:{case_id}")
    if policy.get("forbid_blame_shift") is True and guards.get("blame_shift") is not False:
        failures.append(f"case_blame_shift_allowed:{case_id}")
    if state in uncertain_states and guards.get("can_proceed_without_evidence") is not False:
        failures.append(f"case_uncertain_can_proceed_without_evidence:{case_id}")
    return failures


def _classification_case_result(case: Dict[str, Any], policy_payload: Dict[str, Any]) -> Dict[str, Any]:
    case_id = str(case.get("id") or "<missing>")
    generated = classify_honesty_event(case.get("input") if isinstance(case.get("input"), dict) else {}, policy_payload)
    failures: List[str] = []
    if generated.get("state") != case.get("expected_state"):
        failures.append(f"classification_state_mismatch:{case_id}:{generated.get('state')}:{case.get('expected_state')}")
    next_action = ((generated.get("response_template") or {}).get("next_action") if isinstance(generated.get("response_template"), dict) else "")
    if next_action != case.get("expected_next_action"):
        failures.append(f"classification_next_action_mismatch:{case_id}:{next_action}:{case.get('expected_next_action')}")
    failures.extend(_case_failures(generated, _policy_dict(policy_payload)))
    return {
        "id": case_id,
        "ok": not failures,
        "state": str(generated.get("state") or ""),
        "next_action": str(next_action or ""),
        "failures": sorted(set(failures)),
    }


def validate_honesty_protocol_policy(
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
    case_results: List[Dict[str, Any]] = []
    classification_results: List[Dict[str, Any]] = []

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

    template_states_seen = set()
    for item in example_ref_results["resolved_refs"]:
        example_set = load_example_set(Path(item["path"]))
        if example_set.get("apiVersion") != API_VERSION:
            failures.append(f"example_set_api_version_invalid:{item['ref']}")
        if example_set.get("kind") != SET_KIND:
            failures.append(f"example_set_kind_invalid:{item['ref']}")
        cases = example_set.get("cases") if isinstance(example_set.get("cases"), list) else []
        if not cases:
            failures.append(f"example_set_cases_empty:{item['ref']}")
        for case in cases:
            if not isinstance(case, dict):
                failures.append(f"case_not_object:{item['ref']}")
                continue
            case_id = str(case.get("id") or "<missing>")
            template_states_seen.add(str(case.get("state") or ""))
            case_failures = _case_failures(case, policy)
            refs_result = _resolve_refs(
                _as_string_list(case.get("refs")) + _as_string_list(case.get("evidence_refs")),
                project_root=project,
                package_root=package,
                owner=case_id,
            )
            case_failures.extend(refs_result["failures"])
            failures.extend(case_failures)
            all_resolved_refs.extend(refs_result["resolved_refs"])
            all_missing_refs.extend(refs_result["missing_refs"])
            all_unsafe_refs.extend(refs_result["unsafe_refs"])
            template = case.get("response_template") if isinstance(case.get("response_template"), dict) else {}
            case_results.append(
                {
                    "id": case_id,
                    "ok": not case_failures,
                    "state": str(case.get("state") or ""),
                    "next_action": str(template.get("next_action") or ""),
                    "failures": sorted(set(case_failures)),
                }
            )
        for case in example_set.get("classification_cases") if isinstance(example_set.get("classification_cases"), list) else []:
            if not isinstance(case, dict):
                failures.append(f"classification_case_not_object:{item['ref']}")
                continue
            result = _classification_case_result(case, payload)
            failures.extend(result["failures"])
            classification_results.append(result)

    missing_template_states = sorted(set(_as_string_list(policy.get("required_template_states"))) - template_states_seen)
    failures.extend(f"required_template_state_missing:{item}" for item in missing_template_states)

    checks = [
        {"id": "unknown_template", "status": "passed" if "unknown" in template_states_seen else "failed"},
        {"id": "need_research_template", "status": "passed" if "need_research" in template_states_seen else "failed"},
        {"id": "error_attribution_template", "status": "passed" if "error_attribution" in template_states_seen else "failed"},
        {"id": "traceable_error_attribution", "status": "passed" if not any("trace_id" in item or "error_" in item for item in failures) else "failed"},
        {"id": "no_fabricated_citations", "status": "passed" if not any("fabricated" in item for item in failures) else "failed"},
        {"id": "refs_resolved", "status": "passed" if not all_missing_refs and not all_unsafe_refs else "failed"},
    ]
    metrics = {
        "cases": len(case_results),
        "passing_cases": sum(1 for item in case_results if item["ok"]),
        "classification_cases": len(classification_results),
        "passing_classification_cases": sum(1 for item in classification_results if item["ok"]),
        "template_states": len(template_states_seen),
        "missing_template_states": len(missing_template_states),
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
        "case_results": sorted(case_results, key=lambda item: item["id"]),
        "classification_results": sorted(classification_results, key=lambda item: item["id"]),
        "resolved_refs": sorted(all_resolved_refs, key=lambda item: (item["owner"], item["ref"])),
        "missing_refs": sorted(all_missing_refs, key=lambda item: (item["owner"], item["ref"])),
        "unsafe_refs": sorted(all_unsafe_refs, key=lambda item: (item["owner"], item["ref"])),
    }


def honesty_protocol_report_to_gate_evidence(report: Dict[str, Any], *, artifact_uri: str = "") -> Dict[str, Any]:
    if not isinstance(report, dict) or report.get("kind") != REPORT_KIND:
        raise ValueError("honesty_protocol_report_required")
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
    parser = argparse.ArgumentParser(description="Validate NoemaForge Honesty Protocol contracts.")
    parser.add_argument("--project-root", default=str(_default_project_root()), help="Project root containing noemaforge/ and docs/.")
    parser.add_argument("--package-root", default="", help="Package root, default: <project-root>/noemaforge.")
    parser.add_argument(
        "--policy",
        default="noemaforge/configs/honesty-protocol-policy.json",
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

    report = validate_honesty_protocol_policy(
        load_policy(policy_path),
        project_root=project_root,
        package_root=package_root,
        policy_path=policy_path,
    )
    if args.summary:
        payload: Dict[str, Any] = {
            "apiVersion": report["apiVersion"],
            "kind": "HonestyProtocolValidationSummary",
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
