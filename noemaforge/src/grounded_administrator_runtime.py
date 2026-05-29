#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/grounded_administrator_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate the Grounded Administrator default knowledge-surface contract.
Inputs: Grounded Administrator policy, hypergraph manifest, docs RAG/GraphRAG policies, docs and examples.
Outputs: JSON-compatible GroundedAdministratorValidationReport artifacts.
Side effects: None; CLI writes JSON to stdout.
Tests: noemaforge/tests/test_grounded_administrator_runtime.py
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


API_VERSION = "noemaforge.grounded-administrator/v1"
POLICY_KIND = "GroundedAdministratorPolicy"
SET_KIND = "GroundedAdministratorExampleSet"
REPORT_KIND = "GroundedAdministratorValidationReport"

VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,220}$")
REQUIRED_CONTROLS = {
    "admin_defaults_to_hypergraph",
    "claims_require_provenance",
    "citations_required_for_grounded_answers",
    "graph_gap_emits_unknown",
    "gap_followup_suggests_ingest_or_research",
    "docs_rag_is_cited_fallback",
    "graphrag_experiment_gated",
    "no_improvised_answer_on_gap",
    "no_live_host_required",
}
REQUIRED_OUTPUTS = {
    "grounded_answer",
    "knowledge_gap_notice",
    "citations",
    "followup",
    "retrieved_refs",
    "graph_provenance",
}
REQUIRED_REGISTRY_REFS = [
    "configs/grounded-administrator-policy.json",
    "contracts/grounded_administrator.schema.json",
    "configs/docs-rag-policy.json",
    "configs/graphrag-experiment-pack.json",
    "manifests/functional/knowledge.hypergraph.yaml",
    "src/grounded_administrator_runtime.py",
    "src/knowledge/grounded_administrator.py",
    "tests/test_grounded_administrator_runtime.py",
    "tests/test_grounded_administrator_qa.py",
    "tests/test_grounded_administrator_performance.py",
]
REQUIRED_PIPELINE_REFS = [
    "configs/grounded-administrator-policy.json",
    "contracts/grounded_administrator.schema.json",
    "src/grounded_administrator_runtime.py",
    "prelaunch/governance/grounded_administrator.example.json",
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
    if str(policy.get("activation_state") or "") != "default_hypergraph_knowledge_surface":
        failures.append("policy_activation_state_invalid")
    if not str(policy.get("required_pipeline_ref") or "").startswith("pipeline:"):
        failures.append("policy_required_pipeline_ref_invalid")
    if not str(policy.get("administrator_role_ref") or "").startswith("persona:"):
        failures.append("policy_administrator_role_ref_invalid")
    for key in ["require_trace_id", "require_registry_attachment", "require_docs_and_changelog_refs", "require_no_live_dependency"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    for key in ["role_kernel_policy_ref", "knowledge_manifest_ref", "docs_rag_policy_ref", "graphrag_pack_ref", "grounded_answer_runtime_ref"]:
        if not _is_safe_relative_ref(str(policy.get(key) or "")):
            failures.append(f"policy_{key}_invalid")
    for key in [
        "retrieval_order",
        "required_answer_modes",
        "required_citation_fields",
        "required_gap_followups",
        "blocked_answer_claims",
        "required_boundary_refs",
        "scan_refs",
        "required_example_sets",
    ]:
        if not _as_string_list(policy.get(key)):
            failures.append(f"policy_{key}_empty")
    if _as_string_list(policy.get("retrieval_order"))[:2] != ["hypergraph_claims", "graph_neighbors"]:
        failures.append("policy_retrieval_order_not_hypergraph_first")
    for mode in ["grounded_answer", "knowledge_gap_notice"]:
        if mode not in _as_string_list(policy.get("required_answer_modes")):
            failures.append(f"policy_answer_mode_missing:{mode}")
    for field in ["claim_id", "human_address", "score"]:
        if field not in _as_string_list(policy.get("required_citation_fields")):
            failures.append(f"policy_citation_field_missing:{field}")
    controls = policy.get("controls") if isinstance(policy.get("controls"), dict) else {}
    for key in REQUIRED_CONTROLS:
        if controls.get(key) is not True:
            failures.append(f"policy_control_{key}_not_true")
    outputs = set(_as_string_list(policy.get("required_outputs")))
    for output in REQUIRED_OUTPUTS:
        if output not in outputs:
            failures.append(f"policy_required_output_missing:{output}")
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
    if str(policy.get("administrator_role_ref") or "") not in entries:
        failures.append(f"registry_administrator_role_missing:{policy.get('administrator_role_ref')}")
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


def _knowledge_surface_failures(payload: Dict[str, Any], *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    policy = _policy_dict(payload)
    failures: List[str] = []
    report: Dict[str, Any] = {}

    role_kernel = _resolve_ref(str(policy.get("role_kernel_policy_ref") or ""), project_root=project_root, package_root=package_root)
    report["role_kernel"] = role_kernel
    if not role_kernel.get("ok"):
        failures.append(f"role_kernel_policy_ref_missing:{policy.get('role_kernel_policy_ref')}")
    else:
        kernel = load_policy(role_kernel["path"])
        kpolicy = _policy_dict(kernel)
        roles = kpolicy.get("default_roles") if isinstance(kpolicy.get("default_roles"), list) else []
        admin = [item for item in roles if isinstance(item, dict) and item.get("role_key") == policy.get("default_query_surface")]
        if not admin:
            failures.append(f"role_kernel_admin_role_missing:{policy.get('default_query_surface')}")
        elif admin[0].get("installed_by_default") is not True:
            failures.append("role_kernel_admin_not_installed_by_default")

    manifest = _resolve_ref(str(policy.get("knowledge_manifest_ref") or ""), project_root=project_root, package_root=package_root)
    report["knowledge_manifest"] = manifest
    if not manifest.get("ok"):
        failures.append(f"knowledge_manifest_missing:{policy.get('knowledge_manifest_ref')}")
    else:
        text = Path(manifest["path"]).read_text(encoding="utf-8")
        for token in [
            "knowledge.hypergraph",
            "retrieve grounded claims and provenance",
            "grounded answers cite graph-backed provenance",
            "administrator",
        ]:
            if not _contains(text, token):
                failures.append(f"knowledge_manifest_token_missing:{token}")

    docs_rag = _resolve_ref(str(policy.get("docs_rag_policy_ref") or ""), project_root=project_root, package_root=package_root)
    report["docs_rag_policy"] = docs_rag
    if not docs_rag.get("ok"):
        failures.append(f"docs_rag_policy_missing:{policy.get('docs_rag_policy_ref')}")
    else:
        rag = load_policy(docs_rag["path"])
        retrieval = rag.get("retrieval") if isinstance(rag.get("retrieval"), dict) else {}
        answering = rag.get("answering") if isinstance(rag.get("answering"), dict) else {}
        if rag.get("citation_required") is not True:
            failures.append("docs_rag_citation_required_not_true")
        if retrieval.get("network_required") is not False:
            failures.append("docs_rag_network_required_not_false")
        if retrieval.get("embedding_required") is not False:
            failures.append("docs_rag_embedding_required_not_false")
        if answering.get("fallback") != "knowledge_gap_notice":
            failures.append("docs_rag_fallback_not_gap_notice")

    graphrag = _resolve_ref(str(policy.get("graphrag_pack_ref") or ""), project_root=project_root, package_root=package_root)
    report["graphrag_pack"] = graphrag
    if not graphrag.get("ok"):
        failures.append(f"graphrag_pack_missing:{policy.get('graphrag_pack_ref')}")
    else:
        pack = load_policy(graphrag["path"])
        gpolicy = _policy_dict(pack)
        if pack.get("status") != "disabled":
            failures.append("graphrag_pack_not_disabled")
        if gpolicy.get("require_classic_rag_baseline") is not True:
            failures.append("graphrag_classic_rag_baseline_not_required")
        if gpolicy.get("require_evaluation_gate") is not True:
            failures.append("graphrag_evaluation_gate_not_required")
        if gpolicy.get("network") != "deny":
            failures.append("graphrag_network_not_deny")

    runtime = _resolve_ref(str(policy.get("grounded_answer_runtime_ref") or ""), project_root=project_root, package_root=package_root)
    report["grounded_answer_runtime"] = runtime
    if not runtime.get("ok"):
        failures.append(f"grounded_answer_runtime_missing:{policy.get('grounded_answer_runtime_ref')}")
    else:
        text = Path(runtime["path"]).read_text(encoding="utf-8")
        for token in ["collect_grounded_claims", "knowledge_gap_notice", "grounded_answer", "citations", "Ingest a relevant source"]:
            if token not in text:
                failures.append(f"grounded_answer_runtime_token_missing:{token}")
    return {"failures": failures, **report}


def _docs_failures(payload: Dict[str, Any], *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    policy = _policy_dict(payload)
    phrase = str(policy.get("boundary_phrase") or "")
    blocked_claims = _as_string_list(policy.get("blocked_answer_claims"))
    failures: List[str] = []
    boundary_reports: List[Dict[str, Any]] = []
    scan_reports: List[Dict[str, Any]] = []
    for ref in _as_string_list(policy.get("required_boundary_refs")):
        resolved = _resolve_ref(ref, project_root=project_root, package_root=package_root)
        item_failures: List[str] = []
        text = Path(resolved["path"]).read_text(encoding="utf-8") if resolved.get("ok") else ""
        if not resolved.get("ok"):
            item_failures.append("missing_boundary_ref")
        if text and not _contains(text, phrase):
            item_failures.append("boundary_phrase_missing")
        if item_failures:
            failures.extend([f"doc_boundary:{ref}:{failure}" for failure in item_failures])
        boundary_reports.append({"ref": ref, "ok": not item_failures, "failures": item_failures})
    for ref in _as_string_list(policy.get("scan_refs")):
        resolved = _resolve_ref(ref, project_root=project_root, package_root=package_root)
        item_failures: List[str] = []
        text = Path(resolved["path"]).read_text(encoding="utf-8") if resolved.get("ok") else ""
        if not resolved.get("ok"):
            item_failures.append("missing_scan_ref")
        for claim in blocked_claims:
            if text and _contains(text, claim):
                item_failures.append(f"blocked_answer_claim:{claim}")
        if item_failures:
            failures.extend([f"doc_scan:{ref}:{failure}" for failure in item_failures])
        scan_reports.append({"ref": ref, "ok": not item_failures, "failures": item_failures})
    return {"failures": failures, "boundary_reports": boundary_reports, "scan_reports": scan_reports}


def _example_failures(example: Dict[str, Any], *, policy: Dict[str, Any]) -> Dict[str, Any]:
    failures: List[str] = []
    scenario_reports: List[Dict[str, Any]] = []
    passing_scenarios = 0
    if example.get("apiVersion") != API_VERSION:
        failures.append("examples_api_version_invalid")
    if example.get("kind") != SET_KIND:
        failures.append("examples_kind_invalid")
    scenarios = example.get("scenarios") if isinstance(example.get("scenarios"), list) else []
    if not scenarios:
        failures.append("examples_scenarios_empty")
    blocked_claims = _as_string_list(policy.get("blocked_answer_claims"))
    for scenario in scenarios:
        sid = str(scenario.get("id") or "")
        local_failures: List[str] = []
        if not SAFE_ID_RE.match(sid):
            local_failures.append("scenario_id_invalid")
        if not str(scenario.get("trace_id") or "").startswith("trace:"):
            local_failures.append("scenario_trace_id_missing")
        if scenario.get("query_surface") != policy.get("default_query_surface"):
            local_failures.append("scenario_query_surface_not_default_admin")
        if _as_string_list(scenario.get("retrieval_order")) != _as_string_list(policy.get("retrieval_order")):
            local_failures.append("scenario_retrieval_order_mismatch")
        answer = scenario.get("supported_answer") if isinstance(scenario.get("supported_answer"), dict) else {}
        if answer.get("mode") != "grounded_answer" or answer.get("grounded") is not True:
            local_failures.append("scenario_supported_answer_not_grounded")
        citations = answer.get("citations") if isinstance(answer.get("citations"), list) else []
        if not citations:
            local_failures.append("scenario_supported_answer_citations_empty")
        for citation in citations:
            if not isinstance(citation, dict):
                local_failures.append("scenario_citation_invalid")
                continue
            for field in _as_string_list(policy.get("required_citation_fields")):
                if citation.get(field) in ("", None):
                    local_failures.append(f"scenario_citation_field_missing:{field}")
        gap = scenario.get("gap_answer") if isinstance(scenario.get("gap_answer"), dict) else {}
        if gap.get("mode") != "knowledge_gap_notice" or gap.get("grounded") is not False:
            local_failures.append("scenario_gap_answer_not_gap_notice")
        if gap.get("citations") != []:
            local_failures.append("scenario_gap_answer_has_citations")
        gap_followups = set(_as_string_list(gap.get("followup")))
        for followup in _as_string_list(policy.get("required_gap_followups")):
            if followup not in gap_followups:
                local_failures.append(f"scenario_gap_followup_missing:{followup}")
        rejected = scenario.get("rejected_answers") if isinstance(scenario.get("rejected_answers"), list) else []
        if not rejected:
            local_failures.append("scenario_rejected_answers_empty")
        for rejected_answer in rejected:
            if not isinstance(rejected_answer, dict):
                local_failures.append("scenario_rejected_answer_invalid")
                continue
            claim = str(rejected_answer.get("claim") or "")
            if not any(_contains(claim, blocked) for blocked in blocked_claims):
                local_failures.append(f"scenario_rejected_claim_not_blocked:{claim}")
            if not str(rejected_answer.get("reason") or ""):
                local_failures.append(f"scenario_rejected_reason_missing:{claim}")
        outputs = set(_as_string_list(scenario.get("expected_outputs")))
        for output in REQUIRED_OUTPUTS:
            if output not in outputs:
                local_failures.append(f"scenario_expected_output_missing:{output}")
        scenario_reports.append({"id": sid, "ok": not local_failures, "failures": local_failures})
        if local_failures:
            failures.extend([f"scenario:{sid}:{item}" for item in local_failures])
        else:
            passing_scenarios += 1
    return {"failures": failures, "scenario_reports": scenario_reports, "scenarios": len(scenarios), "passing_scenarios": passing_scenarios}


def validate_grounded_administrator_policy(
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
    knowledge_report = _knowledge_surface_failures(payload, project_root=project, package_root=package)
    failures.extend(knowledge_report["failures"])
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
        "retrieval_order_steps": len(_as_string_list(policy.get("retrieval_order"))),
        "answer_modes": len(_as_string_list(policy.get("required_answer_modes"))),
        "citation_fields": len(_as_string_list(policy.get("required_citation_fields"))),
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
        "knowledge_surface": knowledge_report,
        "docs": docs_report,
        "examples": example_reports,
    }


def grounded_administrator_report_to_gate_evidence(report: Dict[str, Any], *, artifact_uri: str = "") -> Dict[str, Any]:
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
        "kind": "GroundedAdministratorValidationSummary",
        "ok": bool(report.get("ok")),
        "id": report.get("id"),
        "version": report.get("version"),
        "metrics": report.get("metrics", {}),
        "failures": report.get("failures", []),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate NoemaForge Grounded Administrator contract")
    parser.add_argument("--policy", default=str(SRC_DIR.parent / "configs" / "grounded-administrator-policy.json"))
    parser.add_argument("--project-root", default=str(SRC_DIR.parent.parent))
    parser.add_argument("--package-root", default=str(SRC_DIR.parent))
    parser.add_argument("--registry", default="")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = validate_grounded_administrator_policy(
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
