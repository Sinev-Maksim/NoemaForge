#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/knowledge_core_relations_runtime.py
Zone: release/package
Version: 0.31.21.alpha
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate frozen knowledge core relations and publication gates.
Inputs: Knowledge core relations policy, knowledge policy YAML, gatekeeper/store code, registry, docs and examples.
Outputs: JSON-compatible KnowledgeCoreRelationsValidationReport artifacts.
Side effects: None; CLI writes JSON to stdout.
Tests: noemaforge/tests/test_knowledge_core_relations_runtime.py
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


API_VERSION = "noemaforge.knowledge-core-relations/v1"
POLICY_KIND = "KnowledgeCoreRelationsPolicy"
SET_KIND = "KnowledgeCoreRelationsExampleSet"
REPORT_KIND = "KnowledgeCoreRelationsValidationReport"
VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,220}$")
FROZEN_OBJECT_TYPES = ["Source", "Passage", "Claim", "Entity", "Concept", "Conflict", "Trail", "TaskContext", "Decision", "Artifact"]
REQUIRED_RELATIONS = [
    "passage_cites_source",
    "claim_extracted_from_passage",
    "claim_supported_by_evidence",
    "claim_about_concept",
    "conflict_between_claims",
    "concept_defined_by_passage",
    "trail_step_references_object",
    "lineage_derives_from",
]
GATE_OBJECT_KINDS = ["passage", "claim", "conflict", "concept"]
GATE_DECISIONS = ["auto_publish", "review", "quarantine"]
REQUIRED_GATE_CODES = [
    "passage_missing_source",
    "passage_bad_anchor",
    "claim_no_passage",
    "claim_confidence_below_auto_publish",
    "conflict_missing_entities",
    "conflict_bad_status",
    "conflict_missing_realm",
    "concept_missing_labels",
]
REGISTRY_REFS = [
    "configs/knowledge-core-relations-policy.json",
    "contracts/knowledge_core_relations.schema.json",
    "configs/knowledge-policy.yaml",
    "manifests/functional/knowledge.hypergraph.yaml",
    "src/knowledge_core_relations_runtime.py",
    "src/knowledge/gatekeeper.py",
    "src/knowledge/store.py",
    "tests/test_knowledge_core_relations_runtime.py",
    "tests/test_knowledge_core_relations_qa.py",
    "tests/test_knowledge_core_relations_performance.py",
    "prelaunch/governance/knowledge_core_relations.example.json",
    "docs/backlog/ROADMAP_AND_TODO.md",
    "docs/history/CHANGELOG.md",
]
PIPELINE_REFS = [
    "configs/knowledge-core-relations-policy.json",
    "src/knowledge_core_relations_runtime.py",
    "src/knowledge/gatekeeper.py",
    "src/knowledge/store.py",
    "prelaunch/governance/knowledge_core_relations.example.json",
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
    for ref in refs:
        if not _is_safe_relative_ref(ref):
            failures.append(f"unsafe_ref:{owner}:{ref}")
            continue
        resolved = _resolve_ref(ref, project_root=project_root, package_root=package_root)
        if resolved["ok"]:
            resolved_refs.append(resolved)
        else:
            failures.append(f"missing_ref:{owner}:{ref}")
    return {"failures": failures, "resolved_refs": resolved_refs}


def load_policy(path: Path | str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_example_set(path: Path | str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def analyze_knowledge_policy_text(text: str, *, required_relations: Sequence[str]) -> Dict[str, Any]:
    failures: List[str] = []
    checks = {
        "core_relations_section": "core_relations:" in text,
        "publication_gates_section": "publication_gates:" in text,
        "required_object_gates": "required_object_gates:" in text,
        "decision_list": "decisions: [auto_publish, review, quarantine]" in text,
        "auto_publish_min_confidence": "auto_publish_min_confidence: 0.85" in text,
        "quarantine_on_invariant_violation": "quarantine_on_invariant_violation: true" in text,
    }
    for relation in required_relations:
        checks[f"relation:{relation}"] = relation in text
    for object_type in FROZEN_OBJECT_TYPES:
        checks[f"object_type:{object_type}"] = f"- {object_type}" in text
    for gate_kind in GATE_OBJECT_KINDS:
        checks[f"gate_kind:{gate_kind}"] = f"    {gate_kind}:" in text
    for key, ok in checks.items():
        if not ok:
            failures.append(f"knowledge_policy_check_failed:{key}")
    return {"ok": not failures, "failures": failures, "checks": checks}


def analyze_store_text(text: str) -> Dict[str, Any]:
    failures: List[str] = []
    table_markers = {
        "sources": "CREATE TABLE IF NOT EXISTS sources",
        "passages": "CREATE TABLE IF NOT EXISTS passages",
        "concepts": "CREATE TABLE IF NOT EXISTS concepts",
        "claims": "CREATE TABLE IF NOT EXISTS claims",
        "conflicts": "CREATE TABLE IF NOT EXISTS conflicts",
        "trails": "CREATE TABLE IF NOT EXISTS trails",
        "trail_steps": "CREATE TABLE IF NOT EXISTS trail_steps",
        "gate_reports": "CREATE TABLE IF NOT EXISTS gate_reports",
        "links": "CREATE TABLE IF NOT EXISTS links",
        "lineage_links": "CREATE TABLE IF NOT EXISTS lineage_links",
    }
    checks = {name: marker in text for name, marker in table_markers.items()}
    checks["add_link_api"] = "def add_link(" in text
    checks["add_lineage_link_api"] = "def add_lineage_link(" in text
    checks["upsert_gate_report_api"] = "def upsert_gate_report(" in text
    for key, ok in checks.items():
        if not ok:
            failures.append(f"store_check_failed:{key}")
    return {"ok": not failures, "failures": failures, "checks": checks}


def analyze_gatekeeper_text(text: str, *, gate_codes: Sequence[str]) -> Dict[str, Any]:
    failures: List[str] = []
    checks = {
        "auto_publish_min_confidence": "AUTO_PUBLISH_MIN_CONFIDENCE = 0.85" in text,
        "decisions_present": all(token in text for token in GATE_DECISIONS),
        "passage_checker": "def check_passage(" in text,
        "claim_checker": "def check_claim(" in text,
        "conflict_checker": "def check_conflict(" in text,
        "concept_checker": "def check_concept(" in text,
        "run_gatekeeper": "def run_gatekeeper(" in text,
        "conflict_columns_current": "SELECT conflict_id, entity_a, entity_b" in text,
    }
    for code in gate_codes:
        checks[f"gate_code:{code}"] = code in text
    for key, ok in checks.items():
        if not ok:
            failures.append(f"gatekeeper_check_failed:{key}")
    return {"ok": not failures, "failures": failures, "checks": checks}


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
    if str(policy.get("activation_state") or "") != "canonical_relation_gate_freeze":
        failures.append("policy_activation_state_invalid")
    if not str(policy.get("required_pipeline_ref") or "").startswith("pipeline:"):
        failures.append("policy_required_pipeline_ref_invalid")
    for key in ["knowledge_manifest_ref", "knowledge_policy_ref", "gatekeeper_ref", "store_ref"]:
        if not _is_safe_relative_ref(str(policy.get(key) or "")):
            failures.append(f"policy_{key}_invalid")
    for key in ["require_registry_attachment", "require_docs_and_changelog_refs", "require_no_live_dependency"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    if _as_string_list(policy.get("frozen_object_types")) != FROZEN_OBJECT_TYPES:
        failures.append("policy_frozen_object_types_invalid")
    if _as_string_list(policy.get("required_relations")) != REQUIRED_RELATIONS:
        failures.append("policy_required_relations_invalid")
    if _as_string_list(policy.get("publication_gate_object_kinds")) != GATE_OBJECT_KINDS:
        failures.append("policy_publication_gate_object_kinds_invalid")
    if _as_string_list(policy.get("publication_decisions")) != GATE_DECISIONS:
        failures.append("policy_publication_decisions_invalid")
    for code in REQUIRED_GATE_CODES:
        if code not in _as_string_list(policy.get("required_gate_codes")):
            failures.append(f"policy_required_gate_code_missing:{code}")
    for key in ["required_boundary_refs", "required_example_sets"]:
        if not _as_string_list(policy.get(key)):
            failures.append(f"policy_{key}_empty")
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
        for ref in REGISTRY_REFS:
            if ref not in refs:
                failures.append(f"registry_eval_pack_ref_missing:{eval_ref}:{ref}")
    pipeline_ref = str(policy.get("required_pipeline_ref") or "")
    pipeline = raw_entries.get(pipeline_ref) or entries.get(pipeline_ref)
    pipeline_eval_refs: List[str] = []
    if not pipeline:
        failures.append(f"registry_pipeline_missing:{pipeline_ref}")
    else:
        pipeline_eval_refs = _as_string_list(pipeline.get("eval_pack_refs"))
        pipeline_refs = _as_string_list(pipeline.get("refs"))
        if eval_ref not in pipeline_eval_refs:
            failures.append(f"registry_pipeline_eval_pack_ref_missing:{pipeline_ref}:{eval_ref}")
        for ref in PIPELINE_REFS:
            if ref not in pipeline_refs:
                failures.append(f"registry_pipeline_ref_missing:{pipeline_ref}:{ref}")
    return {"failures": failures, "registry_report": report, "eval_ref": eval_ref, "pipeline_eval_refs": pipeline_eval_refs}


def evaluate_example_set(example_set: Dict[str, Any]) -> Dict[str, Any]:
    failures: List[str] = []
    if example_set.get("apiVersion") != API_VERSION:
        failures.append("example_api_version_invalid")
    if example_set.get("kind") != SET_KIND:
        failures.append("example_kind_invalid")
    scenarios = example_set.get("scenarios") if isinstance(example_set.get("scenarios"), list) else []
    seen_kinds = set()
    seen_relations = set()
    for scenario in scenarios:
        kind = str(scenario.get("object_kind") or "")
        relation = str(scenario.get("relation") or "")
        seen_kinds.add(kind)
        seen_relations.add(relation)
        if kind not in GATE_OBJECT_KINDS:
            failures.append(f"example_object_kind_invalid:{kind}")
        if relation not in REQUIRED_RELATIONS:
            failures.append(f"example_relation_invalid:{relation}")
        if str(scenario.get("expected_decision") or "") not in GATE_DECISIONS:
            failures.append(f"example_decision_invalid:{kind}")
        if str(scenario.get("invalid_gate_code") or "") not in REQUIRED_GATE_CODES:
            failures.append(f"example_gate_code_invalid:{kind}")
    for kind in GATE_OBJECT_KINDS:
        if kind not in seen_kinds:
            failures.append(f"example_object_kind_missing:{kind}")
    for relation in ["passage_cites_source", "claim_extracted_from_passage", "conflict_between_claims", "concept_defined_by_passage"]:
        if relation not in seen_relations:
            failures.append(f"example_relation_missing:{relation}")
    return {"ok": not failures, "failures": failures, "scenarios": len(scenarios)}


def validate_knowledge_core_relations_policy(
    payload: Dict[str, Any],
    *,
    project_root: Path,
    package_root: Path,
    registry_path: Path | None = None,
) -> Dict[str, Any]:
    registry_path = registry_path or package_root / "configs" / "unified-registry.json"
    policy = _policy_dict(payload)
    failures = _policy_failures(payload)
    refs = _resolve_refs(payload.get("refs", []), project_root=project_root, package_root=package_root, owner=str(payload.get("id") or "policy"))
    failures.extend(refs["failures"])

    knowledge_policy_report = {"ok": False, "failures": ["knowledge_policy_ref_missing"], "checks": {}}
    knowledge_policy_ref = _resolve_ref(str(policy.get("knowledge_policy_ref") or ""), project_root=project_root, package_root=package_root)
    if knowledge_policy_ref["ok"]:
        knowledge_policy_report = analyze_knowledge_policy_text(Path(knowledge_policy_ref["path"]).read_text(encoding="utf-8"), required_relations=_as_string_list(policy.get("required_relations")) or REQUIRED_RELATIONS)
        failures.extend(knowledge_policy_report["failures"])
    else:
        failures.append("knowledge_policy_ref_missing")

    store_report = {"ok": False, "failures": ["store_ref_missing"], "checks": {}}
    store_ref = _resolve_ref(str(policy.get("store_ref") or ""), project_root=project_root, package_root=package_root)
    if store_ref["ok"]:
        store_report = analyze_store_text(Path(store_ref["path"]).read_text(encoding="utf-8"))
        failures.extend(store_report["failures"])
    else:
        failures.append("store_ref_missing")

    gatekeeper_report = {"ok": False, "failures": ["gatekeeper_ref_missing"], "checks": {}}
    gatekeeper_ref = _resolve_ref(str(policy.get("gatekeeper_ref") or ""), project_root=project_root, package_root=package_root)
    if gatekeeper_ref["ok"]:
        gatekeeper_report = analyze_gatekeeper_text(Path(gatekeeper_ref["path"]).read_text(encoding="utf-8"), gate_codes=_as_string_list(policy.get("required_gate_codes")) or REQUIRED_GATE_CODES)
        failures.extend(gatekeeper_report["failures"])
    else:
        failures.append("gatekeeper_ref_missing")

    manifest_ref = _resolve_ref(str(policy.get("knowledge_manifest_ref") or ""), project_root=project_root, package_root=package_root)
    if manifest_ref["ok"]:
        manifest_text = Path(manifest_ref["path"]).read_text(encoding="utf-8")
        for relation in REQUIRED_RELATIONS:
            if relation not in manifest_text:
                failures.append(f"manifest_relation_missing:{relation}")
    else:
        failures.append("manifest_ref_missing")

    registry = _registry_failures(payload, project_root=project_root, package_root=package_root, registry_path=registry_path)
    failures.extend(registry["failures"])

    boundary = str(policy.get("boundary_phrase") or "")
    boundary_hits = []
    for ref in _as_string_list(policy.get("required_boundary_refs")):
        resolved = _resolve_ref(ref, project_root=project_root, package_root=package_root)
        if not resolved["ok"]:
            failures.append(f"boundary_ref_missing:{ref}")
            continue
        if _contains(Path(resolved["path"]).read_text(encoding="utf-8"), boundary):
            boundary_hits.append(ref)
        else:
            failures.append(f"boundary_phrase_missing:{ref}")

    example_reports = []
    for ref in _as_string_list(policy.get("required_example_sets")):
        resolved = _resolve_ref(ref, project_root=project_root, package_root=package_root)
        if not resolved["ok"]:
            failures.append(f"example_ref_missing:{ref}")
            continue
        report = evaluate_example_set(load_example_set(resolved["path"]))
        example_reports.append({"ref": ref, **report})
        failures.extend([f"example_invalid:{ref}:{item}" for item in report["failures"]])

    return {
        "apiVersion": API_VERSION,
        "kind": REPORT_KIND,
        "created_at": _nowz(),
        "ok": not failures,
        "failures": failures,
        "policy_id": payload.get("id"),
        "knowledge_policy": knowledge_policy_report,
        "store": store_report,
        "gatekeeper": gatekeeper_report,
        "registry": {"eval_ref": registry["eval_ref"], "pipeline_eval_refs": registry["pipeline_eval_refs"]},
        "examples": example_reports,
        "resolved_refs": refs["resolved_refs"],
        "metrics": {
            "refs": len(payload.get("refs", [])) if isinstance(payload.get("refs"), list) else 0,
            "resolved_refs": len(refs["resolved_refs"]),
            "frozen_object_types": len(_as_string_list(policy.get("frozen_object_types"))),
            "relations": len(_as_string_list(policy.get("required_relations"))),
            "gate_object_kinds": len(_as_string_list(policy.get("publication_gate_object_kinds"))),
            "boundary_refs": len(boundary_hits),
            "examples": len(example_reports),
            "registry_entries": len(registry["registry_report"].get("normalized_registry", {}).get("entries", [])),
        },
    }


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Validate NoemaForge knowledge core relations and gates")
    package_root = Path(__file__).resolve().parent.parent
    project_root = package_root.parent
    ap.add_argument("--policy", default=str(package_root / "configs" / "knowledge-core-relations-policy.json"))
    ap.add_argument("--project-root", default=str(project_root))
    ap.add_argument("--package-root", default=str(package_root))
    ap.add_argument("--registry", default="")
    ap.add_argument("--summary", action="store_true")
    args = ap.parse_args(argv)
    pkg = Path(args.package_root).resolve()
    proj = Path(args.project_root).resolve()
    registry = Path(args.registry).resolve() if args.registry else pkg / "configs" / "unified-registry.json"
    report = validate_knowledge_core_relations_policy(load_policy(args.policy), project_root=proj, package_root=pkg, registry_path=registry)
    if args.summary:
        print(json.dumps({"ok": report["ok"], "failures": report["failures"], "metrics": report["metrics"]}, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
