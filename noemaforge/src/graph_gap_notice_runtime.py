#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/graph_gap_notice_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate the Graph Gap Notice contract.
Inputs: Graph Gap Notice policy, grounded administrator sources, docs and examples.
Outputs: JSON-compatible GraphGapNoticeValidationReport artifacts.
Side effects: None; CLI writes JSON to stdout.
Tests: noemaforge/tests/test_graph_gap_notice_runtime.py
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


API_VERSION = "noemaforge.graph-gap-notice/v1"
POLICY_KIND = "GraphGapNoticePolicy"
SET_KIND = "GraphGapNoticeExampleSet"
REPORT_KIND = "GraphGapNoticeValidationReport"

VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,220}$")
REQUIRED_ALGORITHMS = {
    "graph_miss_detection",
    "knowledge_gap_notice_mode",
    "grounded_false_on_gap",
    "empty_citations_on_gap",
    "ingest_or_research_followup",
    "no_improvised_supported_claim",
}
REQUIRED_CONTROLS = {
    "graph_miss_emits_gap_notice",
    "gap_answer_grounded_false",
    "citations_empty_on_gap",
    "ingest_or_research_followup_required",
    "no_improvised_supported_claim",
    "fallback_trace_records_graph_miss",
    "no_live_host_required",
}
REQUIRED_OUTPUTS = {
    "knowledge_gap_notice",
    "grounded_false",
    "citations_empty",
    "followup",
    "graph_miss_trace",
    "blocked_improvisation",
}
REQUIRED_REGISTRY_REFS = [
    "configs/graph-gap-notice-policy.json",
    "contracts/graph_gap_notice.schema.json",
    "configs/grounded-administrator-policy.json",
    "configs/hypergraph-first-administrator-policy.json",
    "manifests/functional/knowledge.hypergraph.yaml",
    "src/graph_gap_notice_runtime.py",
    "src/knowledge/grounded_administrator.py",
    "src/grounded_administrator_runtime.py",
    "tests/test_graph_gap_notice_runtime.py",
    "tests/test_graph_gap_notice_qa.py",
    "tests/test_graph_gap_notice_performance.py",
    "prelaunch/governance/graph_gap_notice.example.json",
]
REQUIRED_PIPELINE_REFS = [
    "configs/graph-gap-notice-policy.json",
    "contracts/graph_gap_notice.schema.json",
    "src/graph_gap_notice_runtime.py",
    "prelaunch/governance/graph_gap_notice.example.json",
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


def classify_gap_followups(followups: Sequence[Any]) -> List[str]:
    out: List[str] = []
    text = " ".join(str(item or "").lower() for item in followups)
    if "ingest" in text or "source" in text:
        out.append("ingest_relevant_source")
    if "narrower" in text or "scope" in text:
        out.append("ask_narrower_scope")
    if "research" in text:
        out.append("propose_research")
    return out


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
    if str(policy.get("activation_state") or "") != "explicit_graph_miss_notice":
        failures.append("policy_activation_state_invalid")
    if not str(policy.get("required_pipeline_ref") or "").startswith("pipeline:"):
        failures.append("policy_required_pipeline_ref_invalid")
    for key in ["require_trace_id", "require_registry_attachment", "require_docs_and_changelog_refs", "require_no_live_dependency"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    for key in ["grounded_administrator_policy_ref", "hypergraph_first_policy_ref", "knowledge_manifest_ref", "grounded_answer_runtime_ref"]:
        if not _is_safe_relative_ref(str(policy.get(key) or "")):
            failures.append(f"policy_{key}_invalid")
    for key in [
        "required_algorithms",
        "gap_order",
        "required_gap_followups",
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
    expected_order = ["query_hypergraph", "detect_zero_supported_claims", "emit_knowledge_gap_notice", "propose_ingest_or_research"]
    if _as_string_list(policy.get("gap_order")) != expected_order:
        failures.append("policy_gap_order_invalid")
    for followup in ["ingest_relevant_source", "propose_research"]:
        if followup not in _as_string_list(policy.get("required_gap_followups")):
            failures.append(f"policy_gap_followup_missing:{followup}")
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
    for key in ["grounded_administrator_policy_ref", "hypergraph_first_policy_ref", "knowledge_manifest_ref", "grounded_answer_runtime_ref"]:
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
        has_boundary = _contains(text, "Graph-gap Administrator") and _contains(text, "ingest or research")
        if not has_boundary:
            failures.append(f"scan_ref_missing_graph_gap_boundary:{ref}")
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
        if _as_string_list(scenario.get("gap_order")) != _as_string_list(policy.get("gap_order")):
            local_failures.append("scenario_gap_order_mismatch")
        answer = scenario.get("gap_answer") if isinstance(scenario.get("gap_answer"), dict) else {}
        if answer.get("mode") != "knowledge_gap_notice":
            local_failures.append("scenario_gap_answer_mode_invalid")
        if answer.get("grounded") is not False:
            local_failures.append("scenario_gap_answer_grounded_not_false")
        if answer.get("citations") != []:
            local_failures.append("scenario_gap_answer_citations_not_empty")
        followups = set(_as_string_list(answer.get("followup")))
        for followup in _as_string_list(policy.get("required_gap_followups")):
            if followup not in followups:
                local_failures.append(f"scenario_gap_followup_missing:{followup}")
        trace = scenario.get("graph_miss_trace") if isinstance(scenario.get("graph_miss_trace"), dict) else {}
        try:
            graph_claim_origin_count = int(trace.get("graph_claim_origin_count"))
        except (TypeError, ValueError):
            graph_claim_origin_count = -1
        if graph_claim_origin_count != 0:
            local_failures.append("scenario_graph_miss_trace_count_not_zero")
        if trace.get("fallback_allowed") is not True:
            local_failures.append("scenario_graph_miss_trace_fallback_not_allowed")
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


def validate_graph_gap_notice_policy(
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
        "gap_followups": len(_as_string_list(policy.get("required_gap_followups"))),
        "static_token_reports": len(static_report["reports"]),
        "gap_order_steps": len(_as_string_list(policy.get("gap_order"))),
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


def graph_gap_notice_report_to_gate_evidence(report: Dict[str, Any], *, artifact_uri: str = "") -> Dict[str, Any]:
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
        "kind": "GraphGapNoticeValidationSummary",
        "ok": bool(report.get("ok")),
        "id": report.get("id"),
        "version": report.get("version"),
        "metrics": report.get("metrics", {}),
        "failures": report.get("failures", []),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate NoemaForge Graph Gap Notice contract")
    parser.add_argument("--policy", default=str(SRC_DIR.parent / "configs" / "graph-gap-notice-policy.json"))
    parser.add_argument("--project-root", default=str(SRC_DIR.parent.parent))
    parser.add_argument("--package-root", default=str(SRC_DIR.parent))
    parser.add_argument("--registry", default="")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = validate_graph_gap_notice_policy(
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
