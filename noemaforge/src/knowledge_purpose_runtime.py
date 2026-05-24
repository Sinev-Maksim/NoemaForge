#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/knowledge_purpose_runtime.py
Zone: release/package
Version: 0.31.21.alpha
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate typed purpose artifacts for knowledge realm/project ingest, lint and review.
Inputs: Knowledge Purpose policy, unified registry, docs and offline examples.
Outputs: JSON-compatible KnowledgePurposeValidationReport artifacts.
Side effects: None; CLI writes JSON to stdout.
Tests: noemaforge/tests/test_knowledge_purpose_runtime.py
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


API_VERSION = "noemaforge.knowledge-purpose/v1"
POLICY_KIND = "KnowledgePurposePolicy"
SET_KIND = "KnowledgePurposeExampleSet"
REPORT_KIND = "KnowledgePurposeValidationReport"

VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,220}$")
REQUIRED_ARTIFACT_FIELDS = {
    "artifact_kind",
    "realm_id",
    "mission",
    "scope_boundaries",
    "out_of_scope",
    "expected_source_quality",
    "update_policy",
    "owners",
    "review_cadence",
    "applies_to",
}
REQUIRED_DECISION_STAGES = {"ingest", "lint", "review"}
REQUIRED_CONTROLS = {
    "purpose_ref_required",
    "mission_required",
    "scope_boundaries_required",
    "out_of_scope_topics_required",
    "source_quality_floor_required",
    "update_policy_required",
    "ingest_uses_purpose",
    "lint_uses_purpose",
    "review_uses_purpose",
    "no_live_host_required",
}
REQUIRED_REGISTRY_REFS = [
    "configs/knowledge-purpose-policy.json",
    "contracts/knowledge_purpose.schema.json",
    "manifests/functional/knowledge.hypergraph.yaml",
    "src/knowledge_purpose_runtime.py",
    "tests/test_knowledge_purpose_runtime.py",
    "tests/test_knowledge_purpose_qa.py",
    "tests/test_knowledge_purpose_performance.py",
    "prelaunch/governance/knowledge_purpose.example.json",
]
REQUIRED_PIPELINE_REFS = [
    "configs/knowledge-purpose-policy.json",
    "contracts/knowledge_purpose.schema.json",
    "src/knowledge_purpose_runtime.py",
    "prelaunch/governance/knowledge_purpose.example.json",
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


def load_policy(policy_path: Path | str) -> Dict[str, Any]:
    return json.loads(Path(policy_path).read_text(encoding="utf-8"))


def load_example_set(example_path: Path | str) -> Dict[str, Any]:
    return json.loads(Path(example_path).read_text(encoding="utf-8"))


def evaluate_knowledge_item_against_purpose(purpose: Dict[str, Any], knowledge_item: Dict[str, Any], *, stage: str) -> Dict[str, Any]:
    failures: List[str] = []
    if stage not in REQUIRED_DECISION_STAGES:
        failures.append(f"unknown_stage:{stage}")
    applies_to = set(_as_string_list(purpose.get("applies_to")))
    if stage not in applies_to:
        failures.append(f"purpose_not_applied_to_stage:{stage}")

    topic = str(knowledge_item.get("topic") or "")
    scope = _as_string_list(purpose.get("scope_boundaries"))
    out_of_scope = _as_string_list(purpose.get("out_of_scope"))
    if not any(_contains(topic, item) or _contains(item, topic) for item in scope):
        failures.append("topic_not_in_scope")
    if any(_contains(topic, item) or _contains(item, topic) for item in out_of_scope):
        failures.append("topic_out_of_scope")

    source_quality = str(knowledge_item.get("source_quality") or "")
    expected_quality = purpose.get("expected_source_quality") if isinstance(purpose.get("expected_source_quality"), dict) else {}
    accepted_quality = set(_as_string_list(expected_quality.get("accepted")))
    rejected_quality = set(_as_string_list(expected_quality.get("rejected")))
    if source_quality in rejected_quality or source_quality not in accepted_quality:
        failures.append("source_quality_below_purpose_floor")

    update_policy = purpose.get("update_policy") if isinstance(purpose.get("update_policy"), dict) else {}
    stale_after = int(update_policy.get("stale_after_days") or 0)
    age_days = int(knowledge_item.get("age_days") or 0)
    stale = stale_after > 0 and age_days > stale_after

    if any(item in failures for item in ["topic_out_of_scope", "source_quality_below_purpose_floor"]):
        decision = "reject"
    elif stale or failures:
        decision = "defer"
    else:
        decision = "accept"
    reasons = list(failures)
    if stale:
        reasons.append("update_policy_review_required")
    return {"stage": stage, "decision": decision, "reasons": reasons, "purpose_ref": purpose.get("realm_id")}


def _purpose_artifact_failures(purpose: Dict[str, Any], *, required_fields: Sequence[str]) -> List[str]:
    failures: List[str] = []
    for field in required_fields:
        if field not in purpose:
            failures.append(f"purpose_field_missing:{field}")
    if purpose.get("artifact_kind") != "KnowledgeRealmPurpose":
        failures.append("purpose_artifact_kind_invalid")
    if not str(purpose.get("realm_id") or "").startswith("realm:"):
        failures.append("purpose_realm_id_invalid")
    for field in ["mission", "review_cadence"]:
        if not str(purpose.get(field) or "").strip():
            failures.append(f"purpose_{field}_empty")
    for field in ["scope_boundaries", "out_of_scope", "owners", "applies_to"]:
        if not _as_string_list(purpose.get(field)):
            failures.append(f"purpose_{field}_empty")
    quality = purpose.get("expected_source_quality") if isinstance(purpose.get("expected_source_quality"), dict) else {}
    if not str(quality.get("minimum") or "").strip():
        failures.append("purpose_expected_source_quality_minimum_missing")
    if not _as_string_list(quality.get("accepted")):
        failures.append("purpose_expected_source_quality_accepted_empty")
    update_policy = purpose.get("update_policy") if isinstance(purpose.get("update_policy"), dict) else {}
    if update_policy.get("requires_review") is not True:
        failures.append("purpose_update_policy_requires_review_not_true")
    if int(update_policy.get("stale_after_days") or 0) <= 0:
        failures.append("purpose_update_policy_stale_after_days_invalid")
    stages = set(_as_string_list(purpose.get("applies_to")))
    for stage in REQUIRED_DECISION_STAGES:
        if stage not in stages:
            failures.append(f"purpose_applies_to_stage_missing:{stage}")
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
    if str(policy.get("activation_state") or "") != "purpose_scoped_knowledge_growth":
        failures.append("policy_activation_state_invalid")
    if not str(policy.get("required_pipeline_ref") or "").startswith("pipeline:"):
        failures.append("policy_required_pipeline_ref_invalid")
    for key in ["require_trace_id", "require_registry_attachment", "require_docs_and_changelog_refs", "require_no_live_dependency"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    if not _is_safe_relative_ref(str(policy.get("knowledge_manifest_ref") or "")):
        failures.append("policy_knowledge_manifest_ref_invalid")
    artifact_fields = set(_as_string_list(policy.get("required_artifact_fields")))
    for field in REQUIRED_ARTIFACT_FIELDS:
        if field not in artifact_fields:
            failures.append(f"policy_artifact_field_missing:{field}")
    stages = set(_as_string_list(policy.get("required_decision_stages")))
    for stage in REQUIRED_DECISION_STAGES:
        if stage not in stages:
            failures.append(f"policy_decision_stage_missing:{stage}")
    for key in ["required_decisions", "required_boundary_refs", "required_example_sets"]:
        if not _as_string_list(policy.get(key)):
            failures.append(f"policy_{key}_empty")
    controls = policy.get("controls") if isinstance(policy.get("controls"), dict) else {}
    for key in REQUIRED_CONTROLS:
        if controls.get(key) is not True:
            failures.append(f"policy_control_{key}_not_true")
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


def _example_failures(example_set: Dict[str, Any], *, policy: Dict[str, Any]) -> Dict[str, Any]:
    failures: List[str] = []
    scenario_reports: List[Dict[str, Any]] = []
    passing_scenarios = 0
    required_fields = _as_string_list(policy.get("required_artifact_fields"))
    required_stages = set(_as_string_list(policy.get("required_decision_stages")))
    if example_set.get("apiVersion") != API_VERSION:
        failures.append("example_api_version_invalid")
    if example_set.get("kind") != SET_KIND:
        failures.append("example_kind_invalid")
    scenarios = example_set.get("scenarios") if isinstance(example_set.get("scenarios"), list) else []
    if not scenarios:
        failures.append("example_scenarios_empty")
    for scenario in scenarios:
        sid = str(scenario.get("id") or "scenario")
        local_failures: List[str] = []
        if not str(scenario.get("trace_id") or "").startswith("trace:"):
            local_failures.append("scenario_trace_id_invalid")
        purpose = scenario.get("purpose_artifact") if isinstance(scenario.get("purpose_artifact"), dict) else {}
        local_failures.extend(_purpose_artifact_failures(purpose, required_fields=required_fields))
        decisions = scenario.get("decisions") if isinstance(scenario.get("decisions"), list) else []
        seen_stages = {str(item.get("stage") or "") for item in decisions if isinstance(item, dict)}
        for stage in required_stages:
            if stage not in seen_stages:
                local_failures.append(f"scenario_decision_stage_missing:{stage}")
        for decision in decisions:
            if not isinstance(decision, dict):
                local_failures.append("scenario_decision_not_object")
                continue
            stage = str(decision.get("stage") or "")
            expected = str(decision.get("expected_decision") or "")
            item = decision.get("knowledge_item") if isinstance(decision.get("knowledge_item"), dict) else {}
            result = evaluate_knowledge_item_against_purpose(purpose, item, stage=stage)
            if result["decision"] != expected:
                local_failures.append(f"scenario_decision_mismatch:{stage}:{expected}:{result['decision']}")
        scenario_reports.append({"id": sid, "ok": not local_failures, "failures": local_failures})
        if local_failures:
            failures.extend([f"scenario:{sid}:{item}" for item in local_failures])
        else:
            passing_scenarios += 1
    return {"failures": failures, "scenario_reports": scenario_reports, "scenarios": len(scenarios), "passing_scenarios": passing_scenarios}


def validate_knowledge_purpose_policy(
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
    manifest_ref = str(policy.get("knowledge_manifest_ref") or "")
    manifest_resolved = _resolve_ref(manifest_ref, project_root=project, package_root=package)
    if not manifest_resolved.get("ok"):
        failures.append(f"knowledge_manifest_missing:{manifest_ref}")
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
        example_report = _example_failures(load_example_set(resolved["path"]), policy=policy)
        failures.extend(example_report["failures"])
        example_reports.append({"ref": ref, **example_report})
    metrics = {
        "refs": len(_as_string_list(payload.get("refs"))),
        "resolved_refs": len(ref_report["resolved_refs"]),
        "boundary_refs": len(docs_report["boundary_reports"]),
        "artifact_fields": len(_as_string_list(policy.get("required_artifact_fields"))),
        "decision_stages": len(_as_string_list(policy.get("required_decision_stages"))),
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
        "manifest": manifest_resolved,
        "registry": registry_report,
        "docs": docs_report,
        "examples": example_reports,
    }


def build_summary(report: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "apiVersion": API_VERSION,
        "kind": "KnowledgePurposeValidationSummary",
        "ok": bool(report.get("ok")),
        "id": report.get("id"),
        "version": report.get("version"),
        "metrics": report.get("metrics", {}),
        "failures": report.get("failures", []),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate NoemaForge knowledge purpose artifact contract")
    parser.add_argument("--policy", default=str(SRC_DIR.parent / "configs" / "knowledge-purpose-policy.json"))
    parser.add_argument("--project-root", default=str(SRC_DIR.parent.parent))
    parser.add_argument("--package-root", default=str(SRC_DIR.parent))
    parser.add_argument("--registry", default="")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = validate_knowledge_purpose_policy(
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
