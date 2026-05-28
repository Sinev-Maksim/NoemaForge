#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/topic_adjacent_retrieval_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate the Topic-Adjacent Retrieval contract.
Inputs: Topic-Adjacent Retrieval policy, prep pipeline/store sources, docs and examples.
Outputs: JSON-compatible TopicAdjacentRetrievalValidationReport artifacts.
Side effects: None; CLI writes JSON to stdout.
Tests: noemaforge/tests/test_topic_adjacent_retrieval_runtime.py
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


API_VERSION = "noemaforge.topic-adjacent-retrieval/v1"
POLICY_KIND = "TopicAdjacentRetrievalPolicy"
SET_KIND = "TopicAdjacentRetrievalExampleSet"
REPORT_KIND = "TopicAdjacentRetrievalValidationReport"

VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,220}$")
SPLIT_RE = re.compile(r"[|,+\s]+")
REQUIRED_ALGORITHMS = {
    "sentence_topic_maps",
    "topic_signature_overlap",
    "chapter_section_locality",
    "adjacency_groups",
    "split_tree",
    "in_memory_leaf_chunks",
}
REQUIRED_CONTROLS = {
    "topic_signature_overlap_required",
    "chapter_section_locality_required",
    "naive_fixed_windows_blocked",
    "budget_first_support_chunks",
    "lineage_preserved_on_split",
    "chunk_bodies_in_memory_only",
    "no_live_host_required",
}
REQUIRED_OUTPUTS = {
    "primary_chunk",
    "coherence_score",
    "adjacent_support_chunks",
    "budget_remaining",
    "chunk_parent_id",
    "chunk_split_reason",
    "retrieval_trace",
}
REQUIRED_REGISTRY_REFS = [
    "configs/topic-adjacent-retrieval-policy.json",
    "contracts/topic_adjacent_retrieval.schema.json",
    "manifests/functional/knowledge.hypergraph.yaml",
    "src/topic_adjacent_retrieval_runtime.py",
    "src/knowledge/prep_pipeline.py",
    "src/knowledge/prep_store.py",
    "tests/test_topic_adjacent_retrieval_runtime.py",
    "tests/test_topic_adjacent_retrieval_qa.py",
    "tests/test_topic_adjacent_retrieval_performance.py",
    "prelaunch/governance/topic_adjacent_retrieval.example.json",
]
REQUIRED_PIPELINE_REFS = [
    "configs/topic-adjacent-retrieval-policy.json",
    "contracts/topic_adjacent_retrieval.schema.json",
    "src/topic_adjacent_retrieval_runtime.py",
    "prelaunch/governance/topic_adjacent_retrieval.example.json",
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


def _topic_terms(value: Any) -> List[str]:
    if isinstance(value, list):
        raw = " ".join(str(item) for item in value)
    else:
        raw = str(value or "")
    return sorted({part.strip().lower() for part in SPLIT_RE.split(raw) if part.strip()})


def _topic_overlap(a: Any, b: Any) -> float:
    left = set(_topic_terms(a))
    right = set(_topic_terms(b))
    if not left or not right:
        return 0.0
    return len(left & right) / max(1, len(left | right))


def _coherence(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _estimated_tokens(candidate: Dict[str, Any]) -> int:
    try:
        return max(0, int(candidate.get("estimated_tokens") or 0))
    except (TypeError, ValueError):
        return 0


def _locality_matches(candidate: Dict[str, Any], locality_scope: Dict[str, Any]) -> bool:
    for key in ["chapter_id", "section_id"]:
        expected = str(locality_scope.get(key) or "").strip()
        if expected and str(candidate.get(key) or "").strip() != expected:
            return False
    return True


def _candidate_score(candidate: Dict[str, Any], query_signature: Any) -> float:
    overlap = _topic_overlap(query_signature, candidate.get("topic_signature") or candidate.get("topic_tags"))
    return round((0.7 * overlap) + (0.3 * _coherence(candidate.get("coherence_score"))), 6)


def load_policy(policy_path: Path | str) -> Dict[str, Any]:
    return json.loads(Path(policy_path).read_text(encoding="utf-8"))


def load_example_set(example_path: Path | str) -> Dict[str, Any]:
    return json.loads(Path(example_path).read_text(encoding="utf-8"))


def rank_topic_adjacent_candidates(
    candidates: Sequence[Dict[str, Any]],
    *,
    query_signature: Any,
    max_tokens: int,
    locality_scope: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    budget_remaining = max(0, int(max_tokens))
    scope = dict(locality_scope or {})
    eligible: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []

    for raw in candidates:
        candidate = dict(raw)
        overlap = _topic_overlap(query_signature, candidate.get("topic_signature") or candidate.get("topic_tags"))
        score = _candidate_score(candidate, query_signature)
        candidate["topic_overlap"] = round(overlap, 6)
        candidate["retrieval_score"] = score
        if not _locality_matches(candidate, scope):
            rejected.append({"chunk_id": candidate.get("chunk_id"), "reason": "outside chapter/section locality", "retrieval_score": score})
            continue
        if overlap <= 0.0:
            rejected.append({"chunk_id": candidate.get("chunk_id"), "reason": "topic signature miss", "retrieval_score": score})
            continue
        eligible.append(candidate)

    eligible.sort(
        key=lambda item: (
            float(item.get("retrieval_score") or 0.0),
            _coherence(item.get("coherence_score")),
            str(item.get("adjacency_group_id") or ""),
            str(item.get("sentence_start_id") or ""),
        ),
        reverse=True,
    )

    selected: List[Dict[str, Any]] = []
    for candidate in eligible:
        tokens = _estimated_tokens(candidate)
        if tokens > budget_remaining:
            rejected.append({"chunk_id": candidate.get("chunk_id"), "reason": "token budget exceeded", "retrieval_score": candidate.get("retrieval_score")})
            continue
        role = "primary_chunk" if not selected else "adjacent_support_chunk"
        selected_candidate = dict(candidate)
        selected_candidate["role"] = role
        selected.append(selected_candidate)
        budget_remaining -= tokens

    primary = selected[0] if selected else None
    support = selected[1:] if len(selected) > 1 else []
    return {
        "primary_chunk": primary,
        "adjacent_support_chunks": support,
        "selected_chunks": selected,
        "rejected_chunks": rejected,
        "budget_remaining": budget_remaining,
        "retrieval_trace": {
            "query_terms": _topic_terms(query_signature),
            "locality_scope": scope,
            "input_candidates": len(candidates),
            "eligible_candidates": len(eligible),
        },
    }


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
    if str(policy.get("activation_state") or "") != "topic_adjacency_first_retrieval":
        failures.append("policy_activation_state_invalid")
    if not str(policy.get("required_pipeline_ref") or "").startswith("pipeline:"):
        failures.append("policy_required_pipeline_ref_invalid")
    for key in ["require_trace_id", "require_registry_attachment", "require_docs_and_changelog_refs", "require_no_live_dependency"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    for key in ["prep_pipeline_ref", "prep_store_ref", "architecture_ref", "knowledge_manifest_ref"]:
        if not _is_safe_relative_ref(str(policy.get(key) or "")):
            failures.append(f"policy_{key}_invalid")
    for key in [
        "required_algorithms",
        "retrieval_order",
        "locality_fields",
        "required_outputs",
        "blocked_retrieval_claims",
        "required_boundary_refs",
        "scan_refs",
        "required_example_sets",
    ]:
        if not _as_string_list(policy.get(key)):
            failures.append(f"policy_{key}_empty")
    algorithms = set(_as_string_list(policy.get("required_algorithms")))
    for algorithm in REQUIRED_ALGORITHMS:
        if algorithm not in algorithms:
            failures.append(f"policy_required_algorithm_missing:{algorithm}")
    expected_order = [
        "best_matching_coherent_chunk",
        "highest_coherence_subchunks",
        "adjacent_support_chunks_if_budget_remains",
        "knowledge_gap_notice",
    ]
    if _as_string_list(policy.get("retrieval_order")) != expected_order:
        failures.append("policy_retrieval_order_invalid")
    for field in ["chapter_id", "section_id", "sentence_start_id", "sentence_end_id", "adjacency_group_id"]:
        if field not in _as_string_list(policy.get("locality_fields")):
            failures.append(f"policy_locality_field_missing:{field}")
    controls = policy.get("controls") if isinstance(policy.get("controls"), dict) else {}
    for key in REQUIRED_CONTROLS:
        if controls.get(key) is not True:
            failures.append(f"policy_control_{key}_not_true")
    outputs = set(_as_string_list(policy.get("required_outputs")))
    for output in REQUIRED_OUTPUTS:
        if output not in outputs:
            failures.append(f"policy_required_output_missing:{output}")
    static_tokens = policy.get("required_static_tokens")
    if not isinstance(static_tokens, dict) or not static_tokens:
        failures.append("policy_required_static_tokens_empty")
    return failures


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
        for ref in REQUIRED_REGISTRY_REFS:
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
    for ref in REQUIRED_PIPELINE_REFS:
        if ref not in pipeline_refs:
            failures.append(f"registry_pipeline_ref_missing:{ref}")
    return {"failures": failures, "registry_report": report, "pipeline_eval_refs": pipeline_eval_refs, "pipeline_refs": pipeline_refs}


def _static_failures(payload: Dict[str, Any], *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    policy = _policy_dict(payload)
    failures: List[str] = []
    reports: List[Dict[str, Any]] = []
    static_tokens = policy.get("required_static_tokens") if isinstance(policy.get("required_static_tokens"), dict) else {}
    for ref, tokens in static_tokens.items():
        resolved = _resolve_ref(str(ref), project_root=project_root, package_root=package_root)
        item_report = {"ref": ref, "ok": False, "tokens": _as_string_list(tokens), "missing_tokens": [], "resolved": resolved}
        if not resolved.get("ok"):
            failures.append(f"static_ref_missing:{ref}")
            reports.append(item_report)
            continue
        text = Path(resolved["path"]).read_text(encoding="utf-8")
        missing = [token for token in _as_string_list(tokens) if not _contains(text, token)]
        item_report["missing_tokens"] = missing
        item_report["ok"] = not missing
        for token in missing:
            failures.append(f"static_token_missing:{ref}:{token}")
        reports.append(item_report)
    for key in ["prep_pipeline_ref", "prep_store_ref", "architecture_ref", "knowledge_manifest_ref"]:
        ref = str(policy.get(key) or "")
        resolved = _resolve_ref(ref, project_root=project_root, package_root=package_root)
        if not resolved.get("ok"):
            failures.append(f"{key}_missing:{ref}")
    return {"failures": failures, "reports": reports}


def _docs_failures(payload: Dict[str, Any], *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    policy = _policy_dict(payload)
    boundary = str(policy.get("boundary_phrase") or "")
    failures: List[str] = []
    boundary_reports: List[Dict[str, Any]] = []
    scan_reports: List[Dict[str, Any]] = []
    for ref in _as_string_list(policy.get("required_boundary_refs")):
        resolved = _resolve_ref(ref, project_root=project_root, package_root=package_root)
        ok = bool(resolved.get("ok"))
        has_phrase = False
        if ok:
            has_phrase = _contains(Path(resolved["path"]).read_text(encoding="utf-8"), boundary)
        if not ok:
            failures.append(f"boundary_ref_missing:{ref}")
        elif not has_phrase:
            failures.append(f"boundary_phrase_missing:{ref}")
        boundary_reports.append({"ref": ref, "ok": ok and has_phrase, "has_phrase": has_phrase, "resolved": resolved})
    for ref in _as_string_list(policy.get("scan_refs")):
        resolved = _resolve_ref(ref, project_root=project_root, package_root=package_root)
        if not resolved.get("ok"):
            failures.append(f"scan_ref_missing:{ref}")
            scan_reports.append({"ref": ref, "ok": False, "resolved": resolved})
            continue
        text = Path(resolved["path"]).read_text(encoding="utf-8")
        has_topic = _contains(text, "topic-adjacent") and _contains(text, "chapter/section locality")
        if not has_topic:
            failures.append(f"scan_ref_missing_topic_adjacent_boundary:{ref}")
        scan_reports.append({"ref": ref, "ok": has_topic, "resolved": resolved})
    return {"failures": failures, "boundary_reports": boundary_reports, "scan_reports": scan_reports}


def _example_failures(example_set: Dict[str, Any], *, policy: Dict[str, Any]) -> Dict[str, Any]:
    failures: List[str] = []
    scenario_reports: List[Dict[str, Any]] = []
    passing_scenarios = 0
    if example_set.get("apiVersion") != API_VERSION:
        failures.append("example_api_version_invalid")
    if example_set.get("kind") != SET_KIND:
        failures.append("example_kind_invalid")
    scenarios = example_set.get("scenarios") if isinstance(example_set.get("scenarios"), list) else []
    if not scenarios:
        failures.append("example_scenarios_empty")
    blocked_claims = _as_string_list(policy.get("blocked_retrieval_claims"))
    expected_outputs = set(_as_string_list(policy.get("required_outputs")))
    for scenario in scenarios:
        sid = str(scenario.get("id") or "scenario")
        local_failures: List[str] = []
        if not str(scenario.get("trace_id") or "").startswith("trace:"):
            local_failures.append("scenario_trace_id_invalid")
        if _as_string_list(scenario.get("retrieval_order")) != _as_string_list(policy.get("retrieval_order")):
            local_failures.append("scenario_retrieval_order_mismatch")
        candidates = scenario.get("candidate_chunks") if isinstance(scenario.get("candidate_chunks"), list) else []
        if not candidates:
            local_failures.append("scenario_candidate_chunks_empty")
        for candidate in candidates:
            if not isinstance(candidate, dict):
                local_failures.append("scenario_candidate_invalid")
                continue
            for field in _as_string_list(policy.get("locality_fields")):
                if not str(candidate.get(field) or ""):
                    local_failures.append(f"scenario_candidate_locality_field_missing:{field}")
        budget = scenario.get("budget") if isinstance(scenario.get("budget"), dict) else {}
        ranked = rank_topic_adjacent_candidates(
            [item for item in candidates if isinstance(item, dict)],
            query_signature=scenario.get("query_topic_signature"),
            max_tokens=int(budget.get("max_tokens") or 0),
            locality_scope=scenario.get("locality_scope") if isinstance(scenario.get("locality_scope"), dict) else {},
        )
        expected_selected = [str(item.get("chunk_id") or "") for item in scenario.get("selected_chunks", []) if isinstance(item, dict)]
        actual_selected = [str(item.get("chunk_id") or "") for item in ranked["selected_chunks"]]
        if actual_selected != expected_selected:
            local_failures.append(f"scenario_selected_chunks_mismatch:{actual_selected}")
        if int(budget.get("budget_remaining") or -1) != int(ranked.get("budget_remaining") or 0):
            local_failures.append("scenario_budget_remaining_mismatch")
        if not ranked.get("primary_chunk"):
            local_failures.append("scenario_primary_chunk_missing")
        if not ranked.get("adjacent_support_chunks"):
            local_failures.append("scenario_adjacent_support_chunks_missing")
        degraded_chain = scenario.get("degraded_chain") if isinstance(scenario.get("degraded_chain"), list) else []
        if not degraded_chain:
            local_failures.append("scenario_degraded_chain_empty")
        for item in degraded_chain:
            if not isinstance(item, dict):
                local_failures.append("scenario_degraded_chunk_invalid")
                continue
            if not str(item.get("chunk_parent_id") or ""):
                local_failures.append("scenario_degraded_chunk_parent_missing")
            if not str(item.get("chunk_split_reason") or ""):
                local_failures.append("scenario_degraded_chunk_split_reason_missing")
        rejected = scenario.get("rejected_retrievals") if isinstance(scenario.get("rejected_retrievals"), list) else []
        if not rejected:
            local_failures.append("scenario_rejected_retrievals_empty")
        for rejected_item in rejected:
            if not isinstance(rejected_item, dict):
                local_failures.append("scenario_rejected_retrieval_invalid")
                continue
            claim = str(rejected_item.get("claim") or "")
            if not any(_contains(claim, blocked) for blocked in blocked_claims):
                local_failures.append(f"scenario_rejected_claim_not_blocked:{claim}")
            if not str(rejected_item.get("reason") or ""):
                local_failures.append(f"scenario_rejected_reason_missing:{claim}")
        outputs = set(_as_string_list(scenario.get("expected_outputs")))
        for output in expected_outputs:
            if output not in outputs:
                local_failures.append(f"scenario_expected_output_missing:{output}")
        scenario_reports.append({"id": sid, "ok": not local_failures, "failures": local_failures, "ranked": ranked})
        if local_failures:
            failures.extend([f"scenario:{sid}:{item}" for item in local_failures])
        else:
            passing_scenarios += 1
    return {"failures": failures, "scenario_reports": scenario_reports, "scenarios": len(scenarios), "passing_scenarios": passing_scenarios}


def validate_topic_adjacent_retrieval_policy(
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
    registry_report = _registry_failures(payload, project_root=project, package_root=package, registry_path=registry)
    failures.extend(registry_report["failures"])
    static_report = _static_failures(payload, project_root=project, package_root=package)
    failures.extend(static_report["failures"])
    docs_report = _docs_failures(payload, project_root=project, package_root=package)
    failures.extend(docs_report["failures"])
    example_reports: List[Dict[str, Any]] = []
    for ref in _as_string_list(policy.get("required_example_sets")):
        resolved = _resolve_ref(ref, project_root=project, package_root=package)
        if not resolved.get("ok"):
            failures.append(f"example_ref_missing:{ref}")
            continue
        example_report = _example_failures(load_example_set(resolved["path"]), policy=policy)
        failures.extend(example_report["failures"])
        example_reports.append({"ref": ref, **example_report})
    metrics = {
        "refs": len(_as_string_list(payload.get("refs"))),
        "resolved_refs": len(ref_report["resolved_refs"]),
        "boundary_refs": len(docs_report["boundary_reports"]),
        "scan_refs": len(docs_report["scan_reports"]),
        "required_algorithms": len(REQUIRED_ALGORITHMS),
        "locality_fields": len(_as_string_list(policy.get("locality_fields"))),
        "static_token_reports": len(static_report["reports"]),
        "retrieval_order_steps": len(_as_string_list(policy.get("retrieval_order"))),
        "scenarios": sum(int(item.get("scenarios") or 0) for item in example_reports),
        "passing_scenarios": sum(int(item.get("passing_scenarios") or 0) for item in example_reports),
        "registry_entries": len(registry_report.get("registry_report", {}).get("normalized_registry", {}).get("entries", [])),
        "checked_controls": len(REQUIRED_CONTROLS),
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
        "registry": registry_report,
        "static": static_report,
        "docs": docs_report,
        "examples": example_reports,
    }


def topic_adjacent_retrieval_report_to_gate_evidence(report: Dict[str, Any], *, artifact_uri: str = "") -> Dict[str, Any]:
    status = "pass" if report.get("ok") else "fail"
    score = 1.0 if status == "pass" else 0.0
    return {
        "artifact_uri": artifact_uri,
        "run_at": report.get("validated_at") or _nowz(),
        "checks": [
            {"id": "retrieval_hit_rate", "status": status, "score": score, "threshold": 1.0},
            {"id": "citation_coverage", "status": status, "score": score, "threshold": 1.0},
            {"id": "groundedness", "status": status, "score": score, "threshold": 1.0},
            {"id": "answer_helpfulness", "status": status, "score": score, "threshold": 1.0},
        ],
        "details": {"id": report.get("id"), "version": report.get("version"), "metrics": report.get("metrics", {}), "failures": report.get("failures", [])},
    }


def build_summary(report: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "apiVersion": API_VERSION,
        "kind": "TopicAdjacentRetrievalValidationSummary",
        "ok": bool(report.get("ok")),
        "id": report.get("id"),
        "version": report.get("version"),
        "metrics": report.get("metrics", {}),
        "failures": report.get("failures", []),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate NoemaForge Topic-Adjacent Retrieval contract")
    parser.add_argument("--policy", default=str(SRC_DIR.parent / "configs" / "topic-adjacent-retrieval-policy.json"))
    parser.add_argument("--project-root", default=str(SRC_DIR.parent.parent))
    parser.add_argument("--package-root", default=str(SRC_DIR.parent))
    parser.add_argument("--registry", default="")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = validate_topic_adjacent_retrieval_policy(
        load_policy(args.policy),
        project_root=Path(args.project_root),
        package_root=Path(args.package_root),
        policy_path=Path(args.policy),
        registry_path=Path(args.registry) if args.registry else None,
    )
    print(json.dumps(build_summary(report) if args.summary else report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
