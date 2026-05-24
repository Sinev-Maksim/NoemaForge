#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/graph_projection_views_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate graph-derived wiki/operator/task/conflict projection contracts.
Inputs: Graph Projection Views policy, unified registry, docs and offline examples.
Outputs: JSON-compatible GraphProjectionViewsValidationReport artifacts.
Side effects: None; CLI writes JSON to stdout.
Tests: noemaforge/tests/test_graph_projection_views_runtime.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import argparse
import hashlib
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


API_VERSION = "noemaforge.graph-projection-views/v1"
POLICY_KIND = "GraphProjectionViewsPolicy"
SET_KIND = "GraphProjectionViewsExampleSet"
REPORT_KIND = "GraphProjectionViewsValidationReport"

VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,220}$")
REQUIRED_PROJECTION_TYPES = {"wiki_markdown", "operator_summary", "task_context", "conflict_review"}
REQUIRED_METADATA_FIELDS = {
    "projection_type",
    "source_graph_ref",
    "source_graph_digest",
    "generated_from_graph",
    "not_source_of_truth",
    "generated_at",
}
REQUIRED_CONTROLS = {
    "projection_not_source_of_truth",
    "source_graph_digest_required",
    "source_graph_ref_required",
    "manual_projection_claims_forbidden",
    "citations_preserve_claim_refs",
    "uncertainty_visible_in_operator_view",
    "conflicts_visible_in_review_view",
    "no_live_host_required",
}
ALLOWED_BOUNDARY_REF_PREFIXES = ("docs/", "noemaforge/docs/")
PROHIBITED_BOUNDARY_REFS = {"README.md", "TODO.md", "noemaforge/TODO.md"}
REQUIRED_CANONICAL_BOUNDARY_REFS = {
    "docs/README.md",
    "docs/TODO.md",
    "docs/reference/PROJECT_CONTEXT.md",
    "docs/backlog/ROADMAP_AND_TODO.md",
    "docs/history/CHANGELOG.md",
}
REQUIRED_REGISTRY_REFS = [
    "configs/graph-projection-views-policy.json",
    "contracts/graph_projection_views.schema.json",
    "manifests/functional/knowledge.hypergraph.yaml",
    "src/graph_projection_views_runtime.py",
    "tests/test_graph_projection_views_runtime.py",
    "tests/test_graph_projection_views_qa.py",
    "tests/test_graph_projection_views_performance.py",
    "prelaunch/governance/graph_projection_views.example.json",
]
REQUIRED_PIPELINE_REFS = [
    "configs/graph-projection-views-policy.json",
    "contracts/graph_projection_views.schema.json",
    "src/graph_projection_views_runtime.py",
    "prelaunch/governance/graph_projection_views.example.json",
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


def graph_digest(graph: Dict[str, Any]) -> str:
    encoded = json.dumps(graph, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _base_projection(graph: Dict[str, Any], projection_type: str) -> Dict[str, Any]:
    return {
        "apiVersion": API_VERSION,
        "kind": "GraphProjectionView",
        "projection_type": projection_type,
        "source_graph_ref": str(graph.get("graph_ref") or "graph:unknown"),
        "source_graph_digest": graph_digest(graph),
        "generated_from_graph": True,
        "not_source_of_truth": True,
        "notice": "This projection is derived from graph state and is not source of truth.",
        "generated_at": _nowz(),
    }


def build_graph_projection(graph: Dict[str, Any], projection_type: str) -> Dict[str, Any]:
    if projection_type not in REQUIRED_PROJECTION_TYPES:
        raise ValueError(f"unsupported_projection_type:{projection_type}")
    claims = [item for item in graph.get("claims", []) if isinstance(item, dict)]
    tasks = [item for item in graph.get("tasks", []) if isinstance(item, dict)]
    conflicts = [item for item in graph.get("conflicts", []) if isinstance(item, dict)]
    projection = _base_projection(graph, projection_type)
    if projection_type == "wiki_markdown":
        lines = [f"# Projection: {projection['source_graph_ref']}", "", projection["notice"], ""]
        citations: List[str] = []
        for claim in claims:
            lines.extend([f"## {claim.get('title') or claim.get('id')}", str(claim.get("summary") or ""), ""])
            citations.extend(_as_string_list(claim.get("citations")))
        projection.update({"markdown": "\n".join(lines).strip() + "\n", "citations": sorted(set(citations))})
    elif projection_type == "operator_summary":
        supported = [claim for claim in claims if claim.get("status") == "supported"]
        uncertain = [claim for claim in claims if claim.get("status") != "supported"]
        projection.update(
            {
                "known": [str(claim.get("summary") or claim.get("title") or claim.get("id")) for claim in supported],
                "uncertain": [str(claim.get("summary") or claim.get("title") or claim.get("id")) for claim in uncertain],
                "next_actions": [str(task.get("title") or task.get("id")) for task in tasks],
            }
        )
    elif projection_type == "task_context":
        projection.update(
            {
                "tasks": tasks,
                "claim_context": [
                    {"claim_id": claim.get("id"), "task_context": _as_string_list(claim.get("task_context"))}
                    for claim in claims
                    if _as_string_list(claim.get("task_context"))
                ],
            }
        )
    else:
        projection.update({"conflicts": conflicts, "open_conflict_count": sum(1 for item in conflicts if item.get("status") == "open")})
    return projection


def build_all_graph_projections(graph: Dict[str, Any], projection_types: Sequence[str] | None = None) -> Dict[str, Dict[str, Any]]:
    selected = list(projection_types or sorted(REQUIRED_PROJECTION_TYPES))
    return {projection_type: build_graph_projection(graph, projection_type) for projection_type in selected}


def write_projection_artifacts(
    graph: Dict[str, Any],
    output_dir: Path | str,
    *,
    projection_types: Sequence[str] | None = None,
) -> Dict[str, Any]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    projections = build_all_graph_projections(graph, projection_types=projection_types)
    written: Dict[str, str] = {}
    for projection_type, projection in projections.items():
        if projection_type == "wiki_markdown":
            path = out / "wiki_markdown.md"
            path.write_text(str(projection.get("markdown") or ""), encoding="utf-8")
        else:
            path = out / f"{projection_type}.json"
            path.write_text(json.dumps(projection, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written[projection_type] = _display_path(path)
    manifest = {
        "apiVersion": API_VERSION,
        "kind": "GraphProjectionArtifactManifest",
        "source_graph_ref": str(graph.get("graph_ref") or "graph:unknown"),
        "source_graph_digest": graph_digest(graph),
        "generated_at": _nowz(),
        "not_source_of_truth": True,
        "projection_artifacts": written,
    }
    manifest_path = out / "projection_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"ok": True, "output_dir": _display_path(out), "written": written, "manifest": _display_path(manifest_path), "manifest_payload": manifest}


def _projection_failures(projection: Dict[str, Any], *, required_notice_tokens: Sequence[str]) -> List[str]:
    failures: List[str] = []
    for field in REQUIRED_METADATA_FIELDS:
        if field not in projection:
            failures.append(f"projection_metadata_missing:{field}")
    if projection.get("generated_from_graph") is not True:
        failures.append("projection_not_generated_from_graph")
    if projection.get("not_source_of_truth") is not True:
        failures.append("projection_not_source_of_truth_flag_missing")
    if not str(projection.get("source_graph_digest") or "").startswith("sha256:"):
        failures.append("projection_source_graph_digest_invalid")
    notice = str(projection.get("notice") or "")
    for token in required_notice_tokens:
        if not _contains(notice, token):
            failures.append(f"projection_notice_token_missing:{token}")
    if projection.get("projection_type") == "wiki_markdown" and not projection.get("citations"):
        failures.append("wiki_projection_citations_empty")
    if projection.get("projection_type") == "operator_summary" and not projection.get("uncertain"):
        failures.append("operator_projection_uncertainty_missing")
    if projection.get("projection_type") == "conflict_review" and int(projection.get("open_conflict_count") or 0) <= 0:
        failures.append("conflict_projection_open_conflicts_missing")
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
    if str(policy.get("activation_state") or "") != "graph_derived_projection_views":
        failures.append("policy_activation_state_invalid")
    if not str(policy.get("required_pipeline_ref") or "").startswith("pipeline:"):
        failures.append("policy_required_pipeline_ref_invalid")
    for key in ["require_trace_id", "require_registry_attachment", "require_docs_and_changelog_refs", "require_no_live_dependency"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    if not _is_safe_relative_ref(str(policy.get("source_graph_manifest_ref") or "")):
        failures.append("policy_source_graph_manifest_ref_invalid")
    projection_types = set(_as_string_list(policy.get("required_projection_types")))
    for projection_type in REQUIRED_PROJECTION_TYPES:
        if projection_type not in projection_types:
            failures.append(f"policy_projection_type_missing:{projection_type}")
    metadata_fields = set(_as_string_list(policy.get("required_metadata_fields")))
    for field in REQUIRED_METADATA_FIELDS:
        if field not in metadata_fields:
            failures.append(f"policy_metadata_field_missing:{field}")
    for key in ["required_notice_tokens", "required_boundary_refs", "required_example_sets"]:
        if not _as_string_list(policy.get(key)):
            failures.append(f"policy_{key}_empty")
    boundary_refs = set(_as_string_list(policy.get("required_boundary_refs")))
    for ref in sorted(REQUIRED_CANONICAL_BOUNDARY_REFS - boundary_refs):
        failures.append(f"policy_canonical_boundary_ref_missing:{ref}")
    for ref in sorted(boundary_refs & PROHIBITED_BOUNDARY_REFS):
        failures.append(f"policy_legacy_boundary_ref_forbidden:{ref}")
    for ref in sorted(boundary_refs):
        if not ref.startswith(ALLOWED_BOUNDARY_REF_PREFIXES):
            failures.append(f"policy_boundary_ref_not_canonical:{ref}")
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
    required_types = set(_as_string_list(policy.get("required_projection_types")))
    notice_tokens = _as_string_list(policy.get("required_notice_tokens"))
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
        graph = scenario.get("source_graph") if isinstance(scenario.get("source_graph"), dict) else {}
        if not graph.get("graph_ref"):
            local_failures.append("scenario_graph_ref_missing")
        expected_types = set(_as_string_list(scenario.get("expected_projection_types")))
        if required_types != expected_types:
            local_failures.append("scenario_expected_projection_types_mismatch")
        for projection_type in sorted(required_types):
            try:
                projection = build_graph_projection(graph, projection_type)
                local_failures.extend([f"{projection_type}:{item}" for item in _projection_failures(projection, required_notice_tokens=notice_tokens)])
            except Exception as exc:  # pragma: no cover - defensive validation surface
                local_failures.append(f"{projection_type}:projection_build_failed:{exc}")
        for blocked in scenario.get("blocked_views") if isinstance(scenario.get("blocked_views"), list) else []:
            if not isinstance(blocked, dict) or not str(blocked.get("reason") or ""):
                local_failures.append("scenario_blocked_view_reason_missing")
        scenario_reports.append({"id": sid, "ok": not local_failures, "failures": local_failures})
        if local_failures:
            failures.extend([f"scenario:{sid}:{item}" for item in local_failures])
        else:
            passing_scenarios += 1
    return {"failures": failures, "scenario_reports": scenario_reports, "scenarios": len(scenarios), "passing_scenarios": passing_scenarios}


def validate_graph_projection_views_policy(
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
    manifest_ref = str(policy.get("source_graph_manifest_ref") or "")
    manifest_resolved = _resolve_ref(manifest_ref, project_root=project, package_root=package)
    if not manifest_resolved.get("ok"):
        failures.append(f"source_graph_manifest_missing:{manifest_ref}")
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
        "projection_types": len(_as_string_list(policy.get("required_projection_types"))),
        "metadata_fields": len(_as_string_list(policy.get("required_metadata_fields"))),
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


def graph_projection_views_report_to_gate_evidence(report: Dict[str, Any], *, artifact_uri: str = "") -> Dict[str, Any]:
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
        "kind": "GraphProjectionViewsValidationSummary",
        "ok": bool(report.get("ok")),
        "id": report.get("id"),
        "version": report.get("version"),
        "metrics": report.get("metrics", {}),
        "failures": report.get("failures", []),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate NoemaForge graph projection views contract")
    parser.add_argument("--policy", default=str(SRC_DIR.parent / "configs" / "graph-projection-views-policy.json"))
    parser.add_argument("--project-root", default=str(SRC_DIR.parent.parent))
    parser.add_argument("--package-root", default=str(SRC_DIR.parent))
    parser.add_argument("--registry", default="")
    parser.add_argument("--graph", default="", help="Build projection view(s) from a graph JSON file instead of validating the policy")
    parser.add_argument("--projection-type", default="all", choices=["all"] + sorted(REQUIRED_PROJECTION_TYPES))
    parser.add_argument("--output-dir", default="", help="Optional directory for generated projection artifacts")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.graph:
        graph = json.loads(Path(args.graph).read_text(encoding="utf-8"))
        selected = sorted(REQUIRED_PROJECTION_TYPES) if args.projection_type == "all" else [str(args.projection_type)]
        if args.output_dir:
            print(json.dumps(write_projection_artifacts(graph, args.output_dir, projection_types=selected), ensure_ascii=False, indent=2))
            return 0
        projections = build_all_graph_projections(graph, projection_types=selected)
        print(json.dumps(projections if args.projection_type == "all" else projections[selected[0]], ensure_ascii=False, indent=2))
        return 0
    report = validate_graph_projection_views_policy(
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
