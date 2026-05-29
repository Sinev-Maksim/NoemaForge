#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/provenance_watermark_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate provenance/watermark hooks and aggregated Detection_Verdict contracts.
Inputs: noemaforge/configs/provenance-watermark-policy.json and example verdict sets.
Outputs: JSON-compatible ProvenanceWatermarkValidationReport artifacts.
Side effects: None unless run as a CLI, which writes JSON to stdout.
Tests: noemaforge/tests/test_provenance_watermark_runtime.py
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


API_VERSION = "noemaforge.provenance-watermark/v1"
POLICY_KIND = "ProvenanceWatermarkPolicy"
SET_KIND = "ProvenanceWatermarkSet"
CASE_KIND = "ProvenanceWatermarkCase"
REPORT_KIND = "ProvenanceWatermarkValidationReport"

VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
REQUIRED_HOOK_TYPES = {"manifest", "signature", "watermark", "content_hash"}
REQUIRED_SIGNAL_INPUTS = {"provenance_manifest", "signature_check", "watermark_signal", "content_consistency"}
REQUIRED_RISK_WEIGHTS = {"manifest_missing", "signature_invalid", "watermark_unverified", "content_mismatch"}
VALID_ACTIONS = {"allow", "revise", "abstain", "escalate"}
VALID_VERDICTS = {"clean", "advisory_ai_likely", "advisory_manipulated", "unknown"}
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


def _risk_weights(policy: Dict[str, Any]) -> Dict[str, float]:
    raw = policy.get("risk_weights") if isinstance(policy.get("risk_weights"), dict) else {}
    return {name: _clip01(raw.get(name)) for name in REQUIRED_RISK_WEIGHTS}


def action_for_score(score: float, policy: Dict[str, Any]) -> str:
    thresholds = policy.get("thresholds") if isinstance(policy.get("thresholds"), dict) else {}
    value = _clip01(score)
    if value <= float(thresholds.get("allow_max", 0.2)):
        return "allow"
    if value <= float(thresholds.get("revise_max", 0.45)):
        return "revise"
    if value <= float(thresholds.get("abstain_max", 0.7)):
        return "abstain"
    return "escalate"


def _hook_types(artifact: Dict[str, Any]) -> List[str]:
    hooks = artifact.get("hooks") if isinstance(artifact.get("hooks"), list) else []
    return [str(item.get("type") or "") for item in hooks if isinstance(item, dict)]


def aggregate_detection_verdict(
    artifact: Dict[str, Any],
    policy_payload: Dict[str, Any],
    *,
    trace_id: str = "trace:provenance-watermark:inline",
) -> Dict[str, Any]:
    policy = _policy_dict(policy_payload)
    weights = _risk_weights(policy)
    signature = artifact.get("signature") if isinstance(artifact.get("signature"), dict) else {}
    watermark = artifact.get("watermark") if isinstance(artifact.get("watermark"), dict) else {}
    consistency = artifact.get("consistency") if isinstance(artifact.get("consistency"), dict) else {}
    minimum_watermark_confidence = _clip01(policy.get("minimum_watermark_confidence", 0.7))

    reasons: List[str] = []
    score = 0.0
    if not str(artifact.get("source_manifest_ref") or "").strip():
        score += weights["manifest_missing"]
        reasons.append("manifest_missing")
    if signature.get("present") is not True or signature.get("verified") is not True:
        score += weights["signature_invalid"]
        reasons.append("signature_invalid")
    if (
        watermark.get("present") is not True
        or watermark.get("verified") is not True
        or _clip01(watermark.get("confidence")) < minimum_watermark_confidence
    ):
        score += weights["watermark_unverified"]
        reasons.append("watermark_unverified")
    if consistency.get("content_hash_match") is not True or consistency.get("manifest_subject_match") is not True:
        score += weights["content_mismatch"]
        reasons.append("content_mismatch")

    risk_score = round(_clip01(score), 3)
    action = action_for_score(risk_score, policy)
    if "content_mismatch" in reasons or (signature.get("present") is True and signature.get("verified") is False):
        decision = "advisory_manipulated"
    elif action == "allow":
        decision = "clean"
    else:
        decision = "unknown"

    confidence = round(1.0 - min(risk_score, 0.95), 3) if decision == "clean" else round(min(0.95, max(risk_score, 0.5)), 3)
    return {
        "apiVersion": API_VERSION,
        "kind": CASE_KIND,
        "id": str(artifact.get("id") or "provenance-watermark:inline"),
        "trace_id": trace_id,
        "artifact": dict(artifact),
        "aggregated_detection_verdict": {
            "decision": decision,
            "confidence": confidence,
            "risk_score": risk_score,
            "action": action,
            "advisory": True,
            "single_detector_decision": False,
            "aggregated_from": sorted(REQUIRED_SIGNAL_INPUTS),
            "reasons": reasons or ["all_hooks_consistent"],
            "summary": "Manifest, signature, watermark and content consistency hooks were aggregated into an advisory verdict.",
        },
        "finalization": {
            "hooks_required": True,
            "critic_aggregation_complete": True,
            "final_without_critic_aggregation": False,
        },
        "refs": _as_string_list([artifact.get("source_manifest_ref")]),
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
        "advisory_by_default",
        "no_single_detector_truth",
        "require_trace_id",
        "require_source_manifest",
        "require_watermark_hooks",
        "require_aggregated_detection_verdict",
        "require_critic_aggregation_before_final",
    ]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    if set(_as_string_list(policy.get("hook_types"))) != REQUIRED_HOOK_TYPES:
        failures.append("policy_hook_types_incomplete")
    if set(_as_string_list(policy.get("signal_inputs"))) != REQUIRED_SIGNAL_INPUTS:
        failures.append("policy_signal_inputs_incomplete")
    if set(_as_string_list(policy.get("actions"))) != VALID_ACTIONS:
        failures.append("policy_actions_must_be_allow_revise_abstain_escalate")
    if set(_as_string_list(policy.get("verdict_decisions"))) != VALID_VERDICTS:
        failures.append("policy_verdict_decisions_incomplete")
    weights = _risk_weights(policy)
    if set(weights) != REQUIRED_RISK_WEIGHTS or abs(sum(weights.values()) - 1.0) > 0.001:
        failures.append("policy_risk_weights_must_sum_to_one")
    thresholds = policy.get("thresholds") if isinstance(policy.get("thresholds"), dict) else {}
    try:
        allow = float(thresholds.get("allow_max"))
        revise = float(thresholds.get("revise_max"))
        abstain = float(thresholds.get("abstain_max"))
    except (TypeError, ValueError):
        allow = revise = abstain = -1.0
    if not (0.0 < allow < revise < abstain < 1.0):
        failures.append("policy_thresholds_must_be_ordered")
    if not (0.0 <= _clip01(policy.get("minimum_watermark_confidence")) <= 1.0):
        failures.append("policy_minimum_watermark_confidence_invalid")
    if not _as_string_list(policy.get("required_example_sets")):
        failures.append("policy_required_example_sets_empty")
    return failures


def _artifact_failures(case_id: str, artifact: Dict[str, Any], policy: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    if not artifact:
        return [f"case_artifact_missing:{case_id}"]
    if str(artifact.get("modality") or "text") != "text":
        failures.append(f"case_modality_not_text:{case_id}:{artifact.get('modality')}")
    if policy.get("require_source_manifest") is True and not str(artifact.get("source_manifest_ref") or "").strip():
        failures.append(f"case_source_manifest_missing:{case_id}")
    if policy.get("require_watermark_hooks") is True and not REQUIRED_HOOK_TYPES.issubset(set(_hook_types(artifact))):
        failures.append(f"case_required_hooks_missing:{case_id}")
    signature = artifact.get("signature") if isinstance(artifact.get("signature"), dict) else {}
    watermark = artifact.get("watermark") if isinstance(artifact.get("watermark"), dict) else {}
    consistency = artifact.get("consistency") if isinstance(artifact.get("consistency"), dict) else {}
    for key in ["present", "verified"]:
        if not isinstance(signature.get(key), bool):
            failures.append(f"case_signature_{key}_not_bool:{case_id}")
        if not isinstance(watermark.get(key), bool):
            failures.append(f"case_watermark_{key}_not_bool:{case_id}")
    confidence = _clip01(watermark.get("confidence"))
    if watermark.get("confidence") != confidence:
        failures.append(f"case_watermark_confidence_out_of_range:{case_id}:{watermark.get('confidence')}")
    for key in ["content_hash_match", "manifest_subject_match"]:
        if not isinstance(consistency.get(key), bool):
            failures.append(f"case_consistency_{key}_not_bool:{case_id}")
    return failures


def _verdict_failures(case: Dict[str, Any], policy_payload: Dict[str, Any]) -> List[str]:
    policy = _policy_dict(policy_payload)
    failures: List[str] = []
    case_id = str(case.get("id") or "<missing>")
    artifact = case.get("artifact") if isinstance(case.get("artifact"), dict) else {}
    verdict = case.get("aggregated_detection_verdict") if isinstance(case.get("aggregated_detection_verdict"), dict) else {}
    if policy.get("require_aggregated_detection_verdict") is True and not verdict:
        return [f"case_detection_verdict_missing:{case_id}"]

    decision = str(verdict.get("decision") or "")
    if decision not in set(_as_string_list(policy.get("verdict_decisions"))):
        failures.append(f"case_verdict_decision_not_allowed:{case_id}:{decision}")
    confidence = _clip01(verdict.get("confidence"))
    if verdict.get("confidence") != confidence:
        failures.append(f"case_verdict_confidence_out_of_range:{case_id}:{verdict.get('confidence')}")
    risk_score = _clip01(verdict.get("risk_score"))
    if verdict.get("risk_score") != risk_score:
        failures.append(f"case_verdict_risk_score_out_of_range:{case_id}:{verdict.get('risk_score')}")
    action = str(verdict.get("action") or "")
    if action not in VALID_ACTIONS:
        failures.append(f"case_verdict_action_not_allowed:{case_id}:{action}")
    if policy.get("advisory_by_default") is True and verdict.get("advisory") is not True:
        failures.append(f"case_verdict_not_advisory:{case_id}")
    if policy.get("no_single_detector_truth") is True and verdict.get("single_detector_decision") is not False:
        failures.append(f"case_single_detector_truth_allowed:{case_id}")
    if not REQUIRED_SIGNAL_INPUTS.issubset(set(_as_string_list(verdict.get("aggregated_from")))):
        failures.append(f"case_required_signal_inputs_missing:{case_id}")
    if not _as_string_list(verdict.get("reasons")):
        failures.append(f"case_verdict_reasons_missing:{case_id}")
    if not str(verdict.get("summary") or "").strip():
        failures.append(f"case_verdict_summary_missing:{case_id}")

    expected = aggregate_detection_verdict(artifact, policy_payload, trace_id=str(case.get("trace_id") or "trace:missing"))
    expected_verdict = expected["aggregated_detection_verdict"]
    if abs(risk_score - float(expected_verdict["risk_score"])) > 0.02:
        failures.append(f"case_risk_score_mismatch:{case_id}:{risk_score}:{expected_verdict['risk_score']}")
    if action != expected_verdict["action"]:
        failures.append(f"case_action_mismatch:{case_id}:{action}:{expected_verdict['action']}")
    if decision != expected_verdict["decision"]:
        failures.append(f"case_decision_mismatch:{case_id}:{decision}:{expected_verdict['decision']}")
    return failures


def _case_failures(case: Dict[str, Any], policy_payload: Dict[str, Any]) -> List[str]:
    policy = _policy_dict(policy_payload)
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
    artifact = case.get("artifact") if isinstance(case.get("artifact"), dict) else {}
    failures.extend(_artifact_failures(case_id, artifact, policy))
    failures.extend(_verdict_failures(case, policy_payload))

    finalization = case.get("finalization") if isinstance(case.get("finalization"), dict) else {}
    if policy.get("require_critic_aggregation_before_final") is True:
        if finalization.get("hooks_required") is not True:
            failures.append(f"case_hooks_not_required:{case_id}")
        if finalization.get("critic_aggregation_complete") is not True:
            failures.append(f"case_critic_aggregation_incomplete:{case_id}")
        if finalization.get("final_without_critic_aggregation") is not False:
            failures.append(f"case_final_without_critics_allowed:{case_id}")
    return failures


def _scoring_case_result(case: Dict[str, Any], policy_payload: Dict[str, Any]) -> Dict[str, Any]:
    case_id = str(case.get("id") or "<missing>")
    artifact = case.get("artifact") if isinstance(case.get("artifact"), dict) else {}
    scored = aggregate_detection_verdict(artifact, policy_payload, trace_id=f"trace:provenance-watermark:{case_id}")
    failures: List[str] = []
    verdict = scored["aggregated_detection_verdict"]
    risk_score = float(verdict["risk_score"])
    action = str(verdict["action"])
    decision = str(verdict["decision"])
    if "expected_min_score" in case and risk_score < float(case.get("expected_min_score")):
        failures.append(f"scoring_score_below_min:{case_id}:{risk_score}:{case.get('expected_min_score')}")
    if "expected_max_score" in case and risk_score > float(case.get("expected_max_score")):
        failures.append(f"scoring_score_above_max:{case_id}:{risk_score}:{case.get('expected_max_score')}")
    if action != str(case.get("expected_action") or ""):
        failures.append(f"scoring_action_mismatch:{case_id}:{action}:{case.get('expected_action')}")
    if decision != str(case.get("expected_decision") or ""):
        failures.append(f"scoring_decision_mismatch:{case_id}:{decision}:{case.get('expected_decision')}")
    return {
        "id": case_id,
        "ok": not failures,
        "risk_score": risk_score,
        "action": action,
        "decision": decision,
        "failures": sorted(set(failures)),
    }


def validate_provenance_watermark_policy(
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
    case_results: List[Dict[str, Any]] = []
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
        cases = example_set.get("cases") if isinstance(example_set.get("cases"), list) else []
        if not cases:
            failures.append(f"example_set_cases_empty:{item['ref']}")
        for case in cases:
            if not isinstance(case, dict):
                failures.append(f"case_not_object:{item['ref']}")
                continue
            case_id = str(case.get("id") or "<missing>")
            case_failures = _case_failures(case, payload)
            artifact = case.get("artifact") if isinstance(case.get("artifact"), dict) else {}
            refs_result = _resolve_refs(
                _as_string_list(case.get("refs")) + _as_string_list([artifact.get("source_manifest_ref")]),
                project_root=project,
                package_root=package,
                owner=case_id,
            )
            case_failures.extend(refs_result["failures"])
            failures.extend(case_failures)
            all_resolved_refs.extend(refs_result["resolved_refs"])
            all_missing_refs.extend(refs_result["missing_refs"])
            all_unsafe_refs.extend(refs_result["unsafe_refs"])
            verdict = case.get("aggregated_detection_verdict") if isinstance(case.get("aggregated_detection_verdict"), dict) else {}
            case_results.append(
                {
                    "id": case_id,
                    "ok": not case_failures,
                    "risk_score": verdict.get("risk_score"),
                    "action": str(verdict.get("action") or ""),
                    "verdict": str(verdict.get("decision") or ""),
                    "failures": sorted(set(case_failures)),
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
        {"id": "provenance_manifest_required", "status": "passed" if not any("source_manifest" in item or "manifest_missing" in item for item in failures) else "failed"},
        {"id": "watermark_hooks_required", "status": "passed" if not any("hook" in item for item in failures) else "failed"},
        {"id": "aggregated_detection_verdict", "status": "passed" if not any("verdict" in item or "single_detector" in item for item in failures) else "failed"},
        {"id": "action_policy", "status": "passed" if not any("action" in item for item in failures) else "failed"},
        {"id": "scoring_cases", "status": "passed" if scoring_results and not any(not item["ok"] for item in scoring_results) else "failed"},
        {"id": "refs_resolved", "status": "passed" if not all_missing_refs and not all_unsafe_refs else "failed"},
    ]
    metrics = {
        "cases": len(case_results),
        "passing_cases": sum(1 for item in case_results if item["ok"]),
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
        "case_results": sorted(case_results, key=lambda item: item["id"]),
        "scoring_results": sorted(scoring_results, key=lambda item: item["id"]),
        "resolved_refs": sorted(all_resolved_refs, key=lambda item: (item["owner"], item["ref"])),
        "missing_refs": sorted(all_missing_refs, key=lambda item: (item["owner"], item["ref"])),
        "unsafe_refs": sorted(all_unsafe_refs, key=lambda item: (item["owner"], item["ref"])),
    }


def provenance_watermark_report_to_gate_evidence(report: Dict[str, Any], *, artifact_uri: str = "") -> Dict[str, Any]:
    if not isinstance(report, dict) or report.get("kind") != REPORT_KIND:
        raise ValueError("provenance_watermark_report_required")
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
    parser = argparse.ArgumentParser(description="Validate NoemaForge provenance/watermark Detection_Verdict contracts.")
    parser.add_argument("--project-root", default=str(_default_project_root()), help="Project root containing noemaforge/ and docs/.")
    parser.add_argument("--package-root", default="", help="Package root, default: <project-root>/noemaforge.")
    parser.add_argument(
        "--policy",
        default="noemaforge/configs/provenance-watermark-policy.json",
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

    report = validate_provenance_watermark_policy(
        load_policy(policy_path),
        project_root=project_root,
        package_root=package_root,
        policy_path=policy_path,
    )
    if args.summary:
        payload: Dict[str, Any] = {
            "apiVersion": report["apiVersion"],
            "kind": "ProvenanceWatermarkValidationSummary",
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
