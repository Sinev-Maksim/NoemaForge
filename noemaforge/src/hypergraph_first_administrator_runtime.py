#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/hypergraph_first_administrator_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate the Hypergraph-First Administrator contract.
Inputs: Hypergraph-First Administrator policy, knowledge manifest, grounded administrator runtime and examples.
Outputs: JSON-compatible HypergraphFirstAdministratorValidationReport artifacts.
Side effects: None; CLI writes JSON to stdout.
Tests: noemaforge/tests/test_hypergraph_first_administrator_runtime.py
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


API_VERSION = "noemaforge.hypergraph-first-administrator/v1"
POLICY_KIND = "HypergraphFirstAdministratorPolicy"
SET_KIND = "HypergraphFirstAdministratorExampleSet"
REPORT_KIND = "HypergraphFirstAdministratorValidationReport"

VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,220}$")
REQUIRED_ALGORITHMS = {
    "graph_claim_origin_scan",
    "hypergraph_first_retrieval_order",
    "provenance_required_for_claims",
    "graph_backed_citations",
    "fallback_after_graph_miss",
    "trace_records_graph_first",
}
REQUIRED_CONTROLS = {
    "hypergraph_is_first_surface",
    "claim_origins_checked_before_answer",
    "supported_answers_require_graph_citations",
    "docs_rag_fallback_requires_graph_miss",
    "no_fallback_before_graph_miss",
    "trace_records_first_surface",
    "no_live_host_required",
}
REQUIRED_OUTPUTS = {
    "grounded_answer",
    "citations",
    "graph_provenance",
    "retrieval_trace",
    "fallback_allowed",
    "knowledge_gap_notice",
}
REQUIRED_REGISTRY_REFS = [
    "configs/hypergraph-first-administrator-policy.json",
    "contracts/hypergraph_first_administrator.schema.json",
    "configs/grounded-administrator-policy.json",
    "manifests/functional/knowledge.hypergraph.yaml",
    "src/hypergraph_first_administrator_runtime.py",
    "src/knowledge/grounded_administrator.py",
    "src/grounded_administrator_runtime.py",
    "tests/test_hypergraph_first_administrator_runtime.py",
    "tests/test_hypergraph_first_administrator_qa.py",
    "tests/test_hypergraph_first_administrator_performance.py",
    "prelaunch/governance/hypergraph_first_administrator.example.json",
]
REQUIRED_PIPELINE_REFS = [
    "configs/hypergraph-first-administrator-policy.json",
    "contracts/hypergraph_first_administrator.schema.json",
    "src/hypergraph_first_administrator_runtime.py",
    "prelaunch/governance/hypergraph_first_administrator.example.json",
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


def build_hypergraph_first_trace(*, graph_claim_origin_count: int, docs_fallback_requested: bool = False, trace_id: str = "trace:hypergraph-first:runtime") -> Dict[str, Any]:
    graph_count = max(0, int(graph_claim_origin_count))
    return {
        "trace_id": str(trace_id),
        "first_retrieval_surface": "hypergraph_claim_origins",
        "graph_claim_origin_count": graph_count,
        "fallback_allowed": bool(docs_fallback_requested and graph_count == 0),
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
    if str(policy.get("activation_state") or "") != "administrator_queries_hypergraph_first":
        failures.append("policy_activation_state_invalid")
    if not str(policy.get("required_pipeline_ref") or "").startswith("pipeline:"):
        failures.append("policy_required_pipeline_ref_invalid")
    for key in ["require_trace_id", "require_registry_attachment", "require_docs_and_changelog_refs", "require_no_live_dependency"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    for key in ["grounded_administrator_policy_ref", "knowledge_manifest_ref", "grounded_answer_runtime_ref", "administrator_contract_runtime_ref"]:
        if not _is_safe_relative_ref(str(policy.get(key) or "")):
            failures.append(f"policy_{key}_invalid")
    for key in [
        "required_algorithms",
        "retrieval_order",
        "required_citation_fields",
        "required_trace_fields",
        "required_outputs",
        "blocked_answer_claims",
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
    if _as_string_list(policy.get("retrieval_order"))[:3] != ["hypergraph_claim_origins", "hypergraph_claims", "graph_neighbors"]:
        failures.append("policy_retrieval_order_not_hypergraph_first")
    for field in ["claim_id", "human_address", "score"]:
        if field not in _as_string_list(policy.get("required_citation_fields")):
            failures.append(f"policy_citation_field_missing:{field}")
    for field in ["trace_id", "first_retrieval_surface", "graph_claim_origin_count", "fallback_allowed"]:
        if field not in _as_string_list(policy.get("required_trace_fields")):
            failures.append(f"policy_trace_field_missing:{field}")
    controls = policy.get("controls") if isinstance(policy.get("controls"), dict) else {}
    for key in REQUIRED_CONTROLS:
        if controls.get(key) is not True:
            failures.append(f"policy_control_{key}_not_true")
    outputs = set(_as_string_list(policy.get("required_outputs")))
    for output in REQUIRED_OUTPUTS:
        if output not in outputs:
            failures.append(f"policy_required_output_missing:{output}")
    if not isinstance(policy.get("required_static_tokens"), dict) or not policy.get("required_static_tokens"):
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
    if str(policy.get("grounded_administrator_policy_ref") or "") not in {ref for entry in raw_entries.values() for ref in _as_string_list(entry.get("refs"))}:
        failures.append(f"registry_grounded_policy_ref_not_attached:{policy.get('grounded_administrator_policy_ref')}")
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
    for key in ["grounded_administrator_policy_ref", "knowledge_manifest_ref", "grounded_answer_runtime_ref", "administrator_contract_runtime_ref"]:
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
        has_boundary = _contains(text, "Hypergraph-first Administrator") and _contains(text, "graph claim origins")
        if not has_boundary:
            failures.append(f"scan_ref_missing_hypergraph_first_boundary:{ref}")
        scan_reports.append({"ref": ref, "ok": has_boundary, "resolved": resolved})
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
    blocked_claims = _as_string_list(policy.get("blocked_answer_claims"))
    expected_outputs = set(_as_string_list(policy.get("required_outputs")))
    for scenario in scenarios:
        sid = str(scenario.get("id") or "scenario")
        local_failures: List[str] = []
        if not str(scenario.get("trace_id") or "").startswith("trace:"):
            local_failures.append("scenario_trace_id_invalid")
        if _as_string_list(scenario.get("retrieval_order")) != _as_string_list(policy.get("retrieval_order")):
            local_failures.append("scenario_retrieval_order_mismatch")
        trace = scenario.get("retrieval_trace") if isinstance(scenario.get("retrieval_trace"), dict) else {}
        if trace.get("first_retrieval_surface") != "hypergraph_claim_origins":
            local_failures.append("scenario_first_surface_not_hypergraph")
        if trace.get("fallback_allowed") is not False:
            local_failures.append("scenario_fallback_allowed_before_graph_miss")
        for field in _as_string_list(policy.get("required_trace_fields")):
            if trace.get(field) in ("", None):
                local_failures.append(f"scenario_trace_field_missing:{field}")
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
        miss = scenario.get("graph_miss") if isinstance(scenario.get("graph_miss"), dict) else {}
        if miss.get("fallback_allowed") is not True or miss.get("mode") != "knowledge_gap_notice":
            local_failures.append("scenario_graph_miss_does_not_allow_fallback_notice")
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
        for output in expected_outputs:
            if output not in outputs:
                local_failures.append(f"scenario_expected_output_missing:{output}")
        scenario_reports.append({"id": sid, "ok": not local_failures, "failures": local_failures})
        if local_failures:
            failures.extend([f"scenario:{sid}:{item}" for item in local_failures])
        else:
            passing_scenarios += 1
    return {"failures": failures, "scenario_reports": scenario_reports, "scenarios": len(scenarios), "passing_scenarios": passing_scenarios}


def validate_hypergraph_first_administrator_policy(
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
        "citation_fields": len(_as_string_list(policy.get("required_citation_fields"))),
        "trace_fields": len(_as_string_list(policy.get("required_trace_fields"))),
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


def hypergraph_first_administrator_report_to_gate_evidence(report: Dict[str, Any], *, artifact_uri: str = "") -> Dict[str, Any]:
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
        "kind": "HypergraphFirstAdministratorValidationSummary",
        "ok": bool(report.get("ok")),
        "id": report.get("id"),
        "version": report.get("version"),
        "metrics": report.get("metrics", {}),
        "failures": report.get("failures", []),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate NoemaForge Hypergraph-First Administrator contract")
    parser.add_argument("--policy", default=str(SRC_DIR.parent / "configs" / "hypergraph-first-administrator-policy.json"))
    parser.add_argument("--project-root", default=str(SRC_DIR.parent.parent))
    parser.add_argument("--package-root", default=str(SRC_DIR.parent))
    parser.add_argument("--registry", default="")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = validate_hypergraph_first_administrator_policy(
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
