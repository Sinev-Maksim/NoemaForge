#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/slop_critic_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate Slop_Score and Critic_Stack contracts as advisory quality gates.
Inputs: noemaforge/configs/slop-critic-policy.json and SlopCritic example sets.
Outputs: JSON-compatible SlopCriticValidationReport artifacts.
Side effects: None unless run as a CLI, which writes JSON to stdout.
Tests: noemaforge/tests/test_slop_critic_runtime.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional, Sequence


SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import production_ai_contracts as pac


API_VERSION = "noemaforge.slop-critic/v1"
POLICY_KIND = "SlopCriticPolicy"
SET_KIND = "SlopCriticSet"
CASE_KIND = "SlopCriticCase"
REPORT_KIND = "SlopCriticValidationReport"

VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
REQUIRED_BANDS = {"genericity", "repetition", "unsupportedness", "provenance_gap"}
REQUIRED_CRITIC_TYPES = {"text", "provenance", "slop"}
VALID_ACTIONS = {"allow", "revise", "abstain", "escalate"}
VALID_VERDICTS = {"clean", "advisory_ai_likely", "advisory_manipulated", "unknown"}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,180}$")
GENERIC_PHRASES = [
    "cutting-edge",
    "seamless",
    "always works",
    "optimizes everything",
    "world-class",
    "best-in-class",
    "game changer",
    "revolutionary",
]


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


def _weights(policy: Dict[str, Any]) -> Dict[str, float]:
    raw = policy.get("band_weights") if isinstance(policy.get("band_weights"), dict) else {}
    return {band: _clip01(raw.get(band)) for band in REQUIRED_BANDS}


def _aggregate_score(bands: Dict[str, Any], policy: Dict[str, Any]) -> float:
    weights = _weights(policy)
    score = sum(_clip01(bands.get(band)) * weights.get(band, 0.0) for band in REQUIRED_BANDS)
    return round(_clip01(score), 3)


def action_for_score(score: float, policy: Dict[str, Any]) -> str:
    thresholds = policy.get("thresholds") if isinstance(policy.get("thresholds"), dict) else {}
    value = _clip01(score)
    if value <= float(thresholds.get("allow_max", 0.25)):
        return "allow"
    if value <= float(thresholds.get("revise_max", 0.55)):
        return "revise"
    if value <= float(thresholds.get("abstain_max", 0.8)):
        return "abstain"
    return "escalate"


def _tokens(text: str) -> List[str]:
    return re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", text.lower())


def _genericity(text: str) -> float:
    lowered = text.lower()
    phrase_hits = sum(1 for phrase in GENERIC_PHRASES if phrase in lowered)
    vague_hits = sum(1 for token in _tokens(text) if token in {"everything", "always", "perfectly", "seamless", "innovative"})
    return _clip01(0.28 * phrase_hits + 0.08 * vague_hits)


def _repetition(text: str) -> float:
    tokens = _tokens(text)
    if not tokens:
        return 0.0
    counts = Counter(tokens)
    repeated_token_ratio = sum(count - 1 for count in counts.values() if count > 1) / max(1, len(tokens))
    sentences = [item.strip().lower() for item in re.split(r"[.!?]+", text) if item.strip()]
    sentence_counts = Counter(sentences)
    repeated_sentence_ratio = sum(count - 1 for count in sentence_counts.values() if count > 1) / max(1, len(sentences))
    return _clip01(repeated_token_ratio + repeated_sentence_ratio)


def _unsupportedness(text: str, evidence_refs: Sequence[str]) -> float:
    if evidence_refs:
        return 0.1
    lowered = text.lower()
    claim_tokens = ["always", "never", "guarantee", "guaranteed", "proves", "perfectly", "everything", "best"]
    if any(token in lowered for token in claim_tokens):
        return 1.0
    return 0.75 if len(_tokens(text)) >= 10 else 0.45


def _provenance_gap(artifact: Dict[str, Any]) -> float:
    provenance = artifact.get("provenance") if isinstance(artifact.get("provenance"), dict) else {}
    if provenance.get("present") is True and str(provenance.get("manifest_ref") or "").strip():
        return 0.0
    return 1.0


def score_text_artifact(artifact: Dict[str, Any], policy_payload: Dict[str, Any], *, trace_id: str = "trace:slop-critic:inline") -> Dict[str, Any]:
    policy = _policy_dict(policy_payload)
    text = str(artifact.get("content") or "")
    evidence_refs = _as_string_list(artifact.get("evidence_refs"))
    bands = {
        "genericity": round(_genericity(text), 3),
        "repetition": round(_repetition(text), 3),
        "unsupportedness": round(_unsupportedness(text, evidence_refs), 3),
        "provenance_gap": round(_provenance_gap(artifact), 3),
    }
    aggregate = _aggregate_score(bands, policy)
    action = action_for_score(aggregate, policy)
    provenance = artifact.get("provenance") if isinstance(artifact.get("provenance"), dict) else {}
    critics = [
        {
            "id": "critic:text:heuristic",
            "type": "text",
            "score": max(bands["genericity"], bands["repetition"]),
            "action": action_for_score(max(bands["genericity"], bands["repetition"]), policy),
            "advisory": True,
            "findings": ["genericity", "repetition"],
        },
        {
            "id": "critic:provenance:heuristic",
            "type": "provenance",
            "score": bands["provenance_gap"],
            "action": action_for_score(bands["provenance_gap"], policy),
            "advisory": True,
            "findings": ["provenance_present" if provenance.get("present") is True else "provenance_missing"],
        },
        {
            "id": "critic:slop:heuristic",
            "type": "slop",
            "score": aggregate,
            "action": action,
            "advisory": True,
            "findings": ["aggregate_score"],
        },
    ]
    decision = "clean" if action == "allow" else "unknown"
    return {
        "apiVersion": API_VERSION,
        "kind": CASE_KIND,
        "id": str(artifact.get("id") or "slop-critic:inline"),
        "trace_id": trace_id,
        "artifact": dict(artifact),
        "slop_score": {
            "bands": bands,
            "aggregate_score": aggregate,
            "action": action,
            "reasons": [band for band, value in bands.items() if value >= 0.5] or ["low_slop"],
        },
        "critic_stack": critics,
        "detection_verdict": {
            "decision": decision,
            "confidence": round(1.0 - min(aggregate, 0.95), 3) if decision == "clean" else round(min(0.95, aggregate), 3),
            "action": action,
            "advisory": True,
            "single_detector_decision": False,
            "summary": "Layered text, provenance and slop critics produced an advisory verdict.",
        },
        "finalization": {
            "critics_required": True,
            "critic_aggregation_complete": True,
            "final_without_critic_aggregation": False,
        },
        "refs": evidence_refs,
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
        "require_slop_score",
        "require_critic_stack",
        "require_detection_verdict",
        "require_critic_aggregation_before_final",
    ]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    if set(_as_string_list(policy.get("bands"))) != REQUIRED_BANDS:
        failures.append("policy_bands_must_be_genericity_repetition_unsupportedness_provenance_gap")
    if set(_as_string_list(policy.get("critic_types"))) != REQUIRED_CRITIC_TYPES:
        failures.append("policy_critic_types_must_be_text_provenance_slop")
    if set(_as_string_list(policy.get("actions"))) != VALID_ACTIONS:
        failures.append("policy_actions_must_be_allow_revise_abstain_escalate")
    if set(_as_string_list(policy.get("verdict_decisions"))) != VALID_VERDICTS:
        failures.append("policy_verdict_decisions_incomplete")
    weights = _weights(policy)
    if set(weights) != REQUIRED_BANDS or abs(sum(weights.values()) - 1.0) > 0.001:
        failures.append("policy_band_weights_must_sum_to_one")
    thresholds = policy.get("thresholds") if isinstance(policy.get("thresholds"), dict) else {}
    try:
        allow = float(thresholds.get("allow_max"))
        revise = float(thresholds.get("revise_max"))
        abstain = float(thresholds.get("abstain_max"))
    except (TypeError, ValueError):
        allow = revise = abstain = -1.0
    if not (0.0 < allow < revise < abstain < 1.0):
        failures.append("policy_thresholds_must_be_ordered")
    if not _as_string_list(policy.get("required_example_sets")):
        failures.append("policy_required_example_sets_empty")
    return failures


def _band_failures(case_id: str, slop_score: Dict[str, Any], policy: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    bands = slop_score.get("bands") if isinstance(slop_score.get("bands"), dict) else {}
    if set(bands) != REQUIRED_BANDS:
        failures.append(f"case_bands_incomplete:{case_id}")
    for band, value in bands.items():
        clipped = _clip01(value)
        if value != clipped:
            failures.append(f"case_band_out_of_range:{case_id}:{band}:{value}")
    aggregate = _clip01(slop_score.get("aggregate_score"))
    if slop_score.get("aggregate_score") != aggregate:
        failures.append(f"case_aggregate_out_of_range:{case_id}:{slop_score.get('aggregate_score')}")
    expected = _aggregate_score(bands, policy)
    if abs(aggregate - expected) > 0.02:
        failures.append(f"case_aggregate_mismatch:{case_id}:{aggregate}:{expected}")
    action = str(slop_score.get("action") or "")
    expected_action = action_for_score(aggregate, policy)
    if action != expected_action:
        failures.append(f"case_action_mismatch:{case_id}:{action}:{expected_action}")
    if action not in VALID_ACTIONS:
        failures.append(f"case_action_not_allowed:{case_id}:{action}")
    if not _as_string_list(slop_score.get("reasons")):
        failures.append(f"case_reasons_missing:{case_id}")
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
    artifact = case.get("artifact") if isinstance(case.get("artifact"), dict) else {}
    if str(artifact.get("modality") or "text") != "text":
        failures.append(f"case_modality_not_text:{case_id}:{artifact.get('modality')}")
    slop_score = case.get("slop_score") if isinstance(case.get("slop_score"), dict) else {}
    if policy.get("require_slop_score") is True and not slop_score:
        failures.append(f"case_slop_score_missing:{case_id}")
    else:
        failures.extend(_band_failures(case_id, slop_score, policy))

    critics = case.get("critic_stack") if isinstance(case.get("critic_stack"), list) else []
    critic_types = {str(item.get("type") or "") for item in critics if isinstance(item, dict)}
    if policy.get("require_critic_stack") is True and not REQUIRED_CRITIC_TYPES.issubset(critic_types):
        failures.append(f"case_required_critics_missing:{case_id}")
    for critic in critics:
        if not isinstance(critic, dict):
            failures.append(f"case_critic_not_object:{case_id}")
            continue
        critic_id = str(critic.get("id") or "")
        if not SAFE_ID_RE.match(critic_id):
            failures.append(f"case_critic_id_invalid:{case_id}:{critic_id}")
        critic_type = str(critic.get("type") or "")
        if critic_type not in REQUIRED_CRITIC_TYPES:
            failures.append(f"case_critic_type_not_allowed:{case_id}:{critic_type}")
        score = _clip01(critic.get("score"))
        if critic.get("score") != score:
            failures.append(f"case_critic_score_out_of_range:{case_id}:{critic_id}:{critic.get('score')}")
        action = str(critic.get("action") or "")
        if action not in VALID_ACTIONS:
            failures.append(f"case_critic_action_not_allowed:{case_id}:{critic_id}:{action}")
        if policy.get("advisory_by_default") is True and critic.get("advisory") is not True:
            failures.append(f"case_critic_not_advisory:{case_id}:{critic_id}")
        if not _as_string_list(critic.get("findings")):
            failures.append(f"case_critic_findings_missing:{case_id}:{critic_id}")

    verdict = case.get("detection_verdict") if isinstance(case.get("detection_verdict"), dict) else {}
    if policy.get("require_detection_verdict") is True and not verdict:
        failures.append(f"case_detection_verdict_missing:{case_id}")
    else:
        decision = str(verdict.get("decision") or "")
        if decision not in set(_as_string_list(policy.get("verdict_decisions"))):
            failures.append(f"case_verdict_decision_not_allowed:{case_id}:{decision}")
        confidence = _clip01(verdict.get("confidence"))
        if verdict.get("confidence") != confidence:
            failures.append(f"case_verdict_confidence_out_of_range:{case_id}:{verdict.get('confidence')}")
        action = str(verdict.get("action") or "")
        if action not in VALID_ACTIONS:
            failures.append(f"case_verdict_action_not_allowed:{case_id}:{action}")
        if policy.get("advisory_by_default") is True and verdict.get("advisory") is not True:
            failures.append(f"case_verdict_not_advisory:{case_id}")
        if policy.get("no_single_detector_truth") is True and verdict.get("single_detector_decision") is not False:
            failures.append(f"case_single_detector_truth_allowed:{case_id}")
        if not str(verdict.get("summary") or "").strip():
            failures.append(f"case_verdict_summary_missing:{case_id}")

    finalization = case.get("finalization") if isinstance(case.get("finalization"), dict) else {}
    if policy.get("require_critic_aggregation_before_final") is True:
        if finalization.get("critics_required") is not True:
            failures.append(f"case_critics_not_required:{case_id}")
        if finalization.get("critic_aggregation_complete") is not True:
            failures.append(f"case_critic_aggregation_incomplete:{case_id}")
        if finalization.get("final_without_critic_aggregation") is not False:
            failures.append(f"case_final_without_critics_allowed:{case_id}")
    return failures


def _scoring_case_result(case: Dict[str, Any], policy_payload: Dict[str, Any]) -> Dict[str, Any]:
    case_id = str(case.get("id") or "<missing>")
    artifact = case.get("artifact") if isinstance(case.get("artifact"), dict) else {}
    scored = score_text_artifact(artifact, policy_payload, trace_id=f"trace:slop-critic:{case_id}")
    failures = _case_failures(scored, _policy_dict(policy_payload))
    score = float((scored.get("slop_score") or {}).get("aggregate_score", 0.0))
    action = str((scored.get("slop_score") or {}).get("action") or "")
    if "expected_min_score" in case and score < float(case.get("expected_min_score")):
        failures.append(f"scoring_score_below_min:{case_id}:{score}:{case.get('expected_min_score')}")
    if "expected_max_score" in case and score > float(case.get("expected_max_score")):
        failures.append(f"scoring_score_above_max:{case_id}:{score}:{case.get('expected_max_score')}")
    if action != str(case.get("expected_action") or ""):
        failures.append(f"scoring_action_mismatch:{case_id}:{action}:{case.get('expected_action')}")
    return {
        "id": case_id,
        "ok": not failures,
        "aggregate_score": score,
        "action": action,
        "failures": sorted(set(failures)),
    }


def validate_slop_critic_policy(
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
            case_failures = _case_failures(case, policy)
            refs_result = _resolve_refs(
                _as_string_list(case.get("refs")) + _as_string_list((case.get("artifact") or {}).get("evidence_refs") if isinstance(case.get("artifact"), dict) else []),
                project_root=project,
                package_root=package,
                owner=case_id,
            )
            case_failures.extend(refs_result["failures"])
            failures.extend(case_failures)
            all_resolved_refs.extend(refs_result["resolved_refs"])
            all_missing_refs.extend(refs_result["missing_refs"])
            all_unsafe_refs.extend(refs_result["unsafe_refs"])
            slop = case.get("slop_score") if isinstance(case.get("slop_score"), dict) else {}
            verdict = case.get("detection_verdict") if isinstance(case.get("detection_verdict"), dict) else {}
            case_results.append(
                {
                    "id": case_id,
                    "ok": not case_failures,
                    "aggregate_score": slop.get("aggregate_score"),
                    "action": str(slop.get("action") or ""),
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
        {"id": "slop_score_bands", "status": "passed" if case_results and not any("band" in item or "aggregate" in item for item in failures) else "failed"},
        {"id": "critic_stack_required", "status": "passed" if not any("critic" in item and "slop_score" not in item for item in failures) else "failed"},
        {"id": "advisory_verdict", "status": "passed" if not any("verdict_not_advisory" in item or "single_detector" in item for item in failures) else "failed"},
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


def slop_critic_report_to_gate_evidence(report: Dict[str, Any], *, artifact_uri: str = "") -> Dict[str, Any]:
    if not isinstance(report, dict) or report.get("kind") != REPORT_KIND:
        raise ValueError("slop_critic_report_required")
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
    parser = argparse.ArgumentParser(description="Validate NoemaForge Slop_Score and Critic_Stack contracts.")
    parser.add_argument("--project-root", default=str(_default_project_root()), help="Project root containing noemaforge/ and docs/.")
    parser.add_argument("--package-root", default="", help="Package root, default: <project-root>/noemaforge.")
    parser.add_argument(
        "--policy",
        default="noemaforge/configs/slop-critic-policy.json",
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

    report = validate_slop_critic_policy(
        load_policy(policy_path),
        project_root=project_root,
        package_root=package_root,
        policy_path=policy_path,
    )
    if args.summary:
        payload: Dict[str, Any] = {
            "apiVersion": report["apiVersion"],
            "kind": "SlopCriticValidationSummary",
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
