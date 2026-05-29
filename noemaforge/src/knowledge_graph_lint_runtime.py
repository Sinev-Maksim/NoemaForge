#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/knowledge_graph_lint_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate offline graph-lint maintenance contracts for knowledge quality.
Inputs: Knowledge Graph Lint policy, unified registry, docs and offline examples.
Outputs: JSON-compatible KnowledgeGraphLintValidationReport artifacts.
Side effects: None; CLI writes JSON to stdout.
Tests: noemaforge/tests/test_knowledge_graph_lint_runtime.py
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
from typing import Any, Dict, List, Sequence, Set


SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import unified_registry_runtime as urr


API_VERSION = "noemaforge.knowledge-graph-lint/v1"
POLICY_KIND = "KnowledgeGraphLintPolicy"
SET_KIND = "KnowledgeGraphLintExampleSet"
REPORT_KIND = "KnowledgeGraphLintValidationReport"

VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,220}$")
REQUIRED_FINDING_TYPES = {
    "orphan_concept",
    "unsupported_claim",
    "stale_passage",
    "unresolved_conflict",
    "weak_realm_bridge",
}
REQUIRED_TARGET_ROLES = {"Administrator", "Surgeon"}
REQUIRED_LOOP_TARGETS = {"prestart", "scheduled_maintenance"}
REQUIRED_CONTROLS = {
    "orphan_concepts_detected",
    "unsupported_claims_detected",
    "stale_passages_detected",
    "unresolved_conflicts_detected",
    "weak_realm_bridges_detected",
    "administrator_work_items_required",
    "surgeon_work_items_required",
    "prestart_loop_target_required",
    "scheduled_maintenance_loop_target_required",
    "no_live_host_required",
}
REQUIRED_REGISTRY_REFS = [
    "configs/knowledge-graph-lint-policy.json",
    "contracts/knowledge_graph_lint.schema.json",
    "configs/knowledge-purpose-policy.json",
    "manifests/functional/knowledge.hypergraph.yaml",
    "src/knowledge_graph_lint_runtime.py",
    "src/prestart.py",
    "src/maintenance.py",
    "src/knowledge_maintainer.py",
    "tests/test_knowledge_graph_lint_runtime.py",
    "tests/test_knowledge_graph_lint_qa.py",
    "tests/test_knowledge_graph_lint_performance.py",
    "prelaunch/governance/knowledge_graph_lint.example.json",
]
REQUIRED_PIPELINE_REFS = [
    "configs/knowledge-graph-lint-policy.json",
    "contracts/knowledge_graph_lint.schema.json",
    "src/knowledge_graph_lint_runtime.py",
    "prelaunch/governance/knowledge_graph_lint.example.json",
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


def _issue(
    finding_type: str,
    entity_id: str,
    summary: str,
    *,
    severity: str = "review",
    target_roles: Sequence[str] = ("Administrator", "Surgeon"),
    loop_targets: Sequence[str] = ("prestart", "scheduled_maintenance"),
) -> Dict[str, Any]:
    return {
        "type": finding_type,
        "entity_id": entity_id,
        "severity": severity,
        "summary": summary,
        "target_roles": list(target_roles),
        "loop_targets": list(loop_targets),
        "maintenance_work": {
            "title": f"Resolve {finding_type}: {entity_id}",
            "recommended_owner": target_roles[0] if target_roles else "Administrator",
            "requires_review": True,
        },
    }


def lint_knowledge_graph(
    graph: Dict[str, Any],
    *,
    stale_after_days: int = 45,
    weak_bridge_strength_below: float = 0.5,
) -> Dict[str, Any]:
    concepts = [item for item in graph.get("concepts", []) if isinstance(item, dict)]
    claims = [item for item in graph.get("claims", []) if isinstance(item, dict)]
    passages = [item for item in graph.get("passages", []) if isinstance(item, dict)]
    conflicts = [item for item in graph.get("conflicts", []) if isinstance(item, dict)]
    bridges = [item for item in graph.get("realm_bridges", []) if isinstance(item, dict)]

    linked_concepts: Set[str] = set()
    for claim in claims:
        linked_concepts.update(_as_string_list(claim.get("concept_ids")))
    for bridge in bridges:
        linked_concepts.update(_as_string_list(bridge.get("concept_ids")))

    findings: List[Dict[str, Any]] = []
    for concept in concepts:
        cid = str(concept.get("id") or "")
        if cid and cid not in linked_concepts:
            findings.append(_issue("orphan_concept", cid, "Concept is not linked to claims or realm bridges."))

    for claim in claims:
        cid = str(claim.get("id") or "")
        status = str(claim.get("status") or "").lower()
        citations = _as_string_list(claim.get("citations"))
        passage_refs = _as_string_list(claim.get("passage_refs"))
        if status != "supported" or not citations or not passage_refs:
            findings.append(_issue("unsupported_claim", cid, "Claim lacks supported status, citations or passage refs.", severity="critical"))

    for passage in passages:
        pid = str(passage.get("id") or "")
        age_days = int(passage.get("age_days") or passage.get("last_reviewed_days_ago") or 0)
        if stale_after_days > 0 and age_days > stale_after_days:
            findings.append(_issue("stale_passage", pid, f"Passage age {age_days}d exceeds {stale_after_days}d review window."))

    for conflict in conflicts:
        cid = str(conflict.get("id") or "")
        status = str(conflict.get("status") or "").lower()
        if status in {"open", "unresolved", "pending"}:
            findings.append(_issue("unresolved_conflict", cid, "Conflict remains open and needs graph review.", severity="critical"))

    for bridge in bridges:
        bid = str(bridge.get("id") or "")
        strength = float(bridge.get("strength") or 0.0)
        evidence_refs = _as_string_list(bridge.get("evidence_refs"))
        if strength < weak_bridge_strength_below or not evidence_refs:
            findings.append(_issue("weak_realm_bridge", bid, "Realm bridge is weak or lacks evidence refs."))

    return {
        "apiVersion": API_VERSION,
        "kind": "KnowledgeGraphLintReport",
        "graph_ref": str(graph.get("graph_ref") or "graph:unknown"),
        "generated_at": _nowz(),
        "ok": not findings,
        "findings": findings,
        "maintenance_work": [item["maintenance_work"] for item in findings],
        "metrics": {
            "findings": len(findings),
            "finding_types": sorted({item["type"] for item in findings}),
            "target_roles": sorted({role for item in findings for role in item.get("target_roles", [])}),
            "loop_targets": sorted({target for item in findings for target in item.get("loop_targets", [])}),
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
    if str(policy.get("activation_state") or "") != "graph_lint_maintenance_loop":
        failures.append("policy_activation_state_invalid")
    if not str(policy.get("required_pipeline_ref") or "").startswith("pipeline:"):
        failures.append("policy_required_pipeline_ref_invalid")
    for key in ["require_trace_id", "require_registry_attachment", "require_docs_and_changelog_refs", "require_no_live_dependency"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    for key in ["knowledge_manifest_ref", "knowledge_purpose_policy_ref"]:
        if not _is_safe_relative_ref(str(policy.get(key) or "")):
            failures.append(f"policy_{key}_invalid")
    finding_types = set(_as_string_list(policy.get("required_finding_types")))
    for item in REQUIRED_FINDING_TYPES:
        if item not in finding_types:
            failures.append(f"policy_finding_type_missing:{item}")
    roles = set(_as_string_list(policy.get("required_target_roles")))
    for item in REQUIRED_TARGET_ROLES:
        if item not in roles:
            failures.append(f"policy_target_role_missing:{item}")
    loops = set(_as_string_list(policy.get("required_loop_targets")))
    for item in REQUIRED_LOOP_TARGETS:
        if item not in loops:
            failures.append(f"policy_loop_target_missing:{item}")
    if int(policy.get("stale_after_days") or 0) <= 0:
        failures.append("policy_stale_after_days_invalid")
    if float(policy.get("weak_bridge_strength_below") or 0.0) <= 0.0:
        failures.append("policy_weak_bridge_strength_below_invalid")
    for key in ["required_boundary_refs", "required_loop_refs", "required_example_sets"]:
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


def _loop_failures(payload: Dict[str, Any], *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    policy = _policy_dict(payload)
    failures: List[str] = []
    loop_reports: List[Dict[str, Any]] = []
    for ref in _as_string_list(policy.get("required_loop_refs")):
        resolved = _resolve_ref(ref, project_root=project_root, package_root=package_root)
        if not resolved.get("ok"):
            failures.append(f"loop_ref_missing:{ref}")
        loop_reports.append({"ref": ref, "ok": bool(resolved.get("ok")), "resolved": resolved})
    return {"failures": failures, "loop_reports": loop_reports}


def _example_failures(example_set: Dict[str, Any], *, policy: Dict[str, Any]) -> Dict[str, Any]:
    failures: List[str] = []
    scenario_reports: List[Dict[str, Any]] = []
    passing_scenarios = 0
    required_types = set(_as_string_list(policy.get("required_finding_types")))
    required_roles = set(_as_string_list(policy.get("required_target_roles")))
    required_loops = set(_as_string_list(policy.get("required_loop_targets")))
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
        graph = scenario.get("graph") if isinstance(scenario.get("graph"), dict) else {}
        report = lint_knowledge_graph(
            graph,
            stale_after_days=int(policy.get("stale_after_days") or 45),
            weak_bridge_strength_below=float(policy.get("weak_bridge_strength_below") or 0.5),
        )
        found_types = set(report["metrics"]["finding_types"])
        expected_types = set(_as_string_list(scenario.get("expected_finding_types")))
        if found_types != expected_types:
            local_failures.append(f"scenario_finding_types_mismatch:{sorted(found_types)}:{sorted(expected_types)}")
        if not required_types.issubset(found_types):
            local_failures.append("scenario_required_finding_types_missing")
        found_roles = set(report["metrics"]["target_roles"])
        if not required_roles.issubset(found_roles):
            local_failures.append("scenario_target_roles_missing")
        found_loops = set(report["metrics"]["loop_targets"])
        if not required_loops.issubset(found_loops):
            local_failures.append("scenario_loop_targets_missing")
        if not report.get("maintenance_work"):
            local_failures.append("scenario_maintenance_work_empty")
        scenario_reports.append({"id": sid, "ok": not local_failures, "failures": local_failures, "lint_report": report})
        if local_failures:
            failures.extend([f"scenario:{sid}:{item}" for item in local_failures])
        else:
            passing_scenarios += 1
    return {"failures": failures, "scenario_reports": scenario_reports, "scenarios": len(scenarios), "passing_scenarios": passing_scenarios}


def validate_knowledge_graph_lint_policy(
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
    for key in ["knowledge_manifest_ref", "knowledge_purpose_policy_ref"]:
        resolved = _resolve_ref(str(policy.get(key) or ""), project_root=project, package_root=package)
        if not resolved.get("ok"):
            failures.append(f"{key}_missing:{policy.get(key)}")
    registry_report = _registry_failures(payload, project_root=project, package_root=package, registry_path=registry)
    failures.extend(registry_report["failures"])
    docs_report = _docs_failures(payload, project_root=project, package_root=package)
    failures.extend(docs_report["failures"])
    loop_report = _loop_failures(payload, project_root=project, package_root=package)
    failures.extend(loop_report["failures"])
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
        "loop_refs": len(loop_report["loop_reports"]),
        "finding_types": len(_as_string_list(policy.get("required_finding_types"))),
        "target_roles": len(_as_string_list(policy.get("required_target_roles"))),
        "loop_targets": len(_as_string_list(policy.get("required_loop_targets"))),
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
        "docs": docs_report,
        "loops": loop_report,
        "examples": example_reports,
    }


def build_summary(report: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "apiVersion": API_VERSION,
        "kind": "KnowledgeGraphLintValidationSummary",
        "ok": bool(report.get("ok")),
        "id": report.get("id"),
        "version": report.get("version"),
        "metrics": report.get("metrics", {}),
        "failures": report.get("failures", []),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate NoemaForge knowledge graph lint contract")
    parser.add_argument("--policy", default=str(SRC_DIR.parent / "configs" / "knowledge-graph-lint-policy.json"))
    parser.add_argument("--project-root", default=str(SRC_DIR.parent.parent))
    parser.add_argument("--package-root", default=str(SRC_DIR.parent))
    parser.add_argument("--registry", default="")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = validate_knowledge_graph_lint_policy(
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
