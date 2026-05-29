#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/graphrag_experiment_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Validate and evaluate local GraphRAG experiment packs behind classic RAG gates.
Inputs: noemaforge/configs/graphrag-experiment-pack.json plus local project/package roots.
Outputs: JSON-compatible GraphRAGExperimentReport artifacts.
Side effects: None unless run as a CLI, which writes JSON to stdout.
Tests: noemaforge/tests/test_graphrag_experiment_runtime.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import deque
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Deque, Dict, Iterable, List, Optional, Sequence, Tuple


SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import production_ai_contracts as pac


API_VERSION = "noemaforge.graphrag-experiment/v1"
PACK_KIND = "GraphRAGExperimentPack"
REPORT_KIND = "GraphRAGExperimentReport"

VALID_STATUSES = {"disabled", "draft", "shadow", "retired"}
VALID_NODE_TYPES = {"concept", "source", "control"}
VALID_EDGE_RELATIONS = {"describes", "requires", "gates", "cites", "supports"}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")
TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_\-']*|[а-яё0-9][а-яё0-9_\-']*", re.IGNORECASE)


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


def _tokens(value: Any) -> List[str]:
    return [token.lower() for token in TOKEN_RE.findall(str(value or "").lower()) if token.strip()]


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


def load_pack(pack_path: Path | str) -> Dict[str, Any]:
    path = Path(pack_path)
    return json.loads(path.read_text(encoding="utf-8"))


def _policy_failures(policy: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    if str(policy.get("mode") or "") != "experiment":
        failures.append("policy_mode_not_experiment")
    if not str(policy.get("baseline_eval_pack_ref") or "").startswith("eval-pack:"):
        failures.append("policy_baseline_eval_pack_ref_invalid")
    for key in [
        "require_classic_rag_baseline",
        "require_evaluation_gate",
        "require_trace_id",
        "require_release_evidence_before_promotion",
    ]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    if str(policy.get("network") or "") != "deny":
        failures.append("policy_network_not_deny")
    try:
        depth = int(policy.get("max_graph_depth"))
    except Exception:
        depth = 0
    if depth < 1 or depth > 5:
        failures.append("policy_max_graph_depth_invalid")
    try:
        expansion = int(policy.get("max_expansion_nodes"))
    except Exception:
        expansion = 0
    if expansion < 1 or expansion > 50:
        failures.append("policy_max_expansion_nodes_invalid")

    node_types = set(_as_string_list(policy.get("allowed_node_types")))
    edge_relations = set(_as_string_list(policy.get("allowed_edge_relations")))
    if not node_types:
        failures.append("policy_allowed_node_types_empty")
    if not edge_relations:
        failures.append("policy_allowed_edge_relations_empty")
    failures.extend(f"policy_invalid_node_type:{item}" for item in sorted(node_types - VALID_NODE_TYPES))
    failures.extend(f"policy_invalid_edge_relation:{item}" for item in sorted(edge_relations - VALID_EDGE_RELATIONS))
    return failures


def _graph_failures(pack: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    policy = pack.get("policy") if isinstance(pack.get("policy"), dict) else {}
    allowed_node_types = set(_as_string_list(policy.get("allowed_node_types"))) or VALID_NODE_TYPES
    allowed_edge_relations = set(_as_string_list(policy.get("allowed_edge_relations"))) or VALID_EDGE_RELATIONS
    graph = pack.get("graph") if isinstance(pack.get("graph"), dict) else {}
    nodes = [dict(item) for item in (graph.get("nodes") or []) if isinstance(item, dict)]
    edges = [dict(item) for item in (graph.get("edges") or []) if isinstance(item, dict)]

    if not nodes:
        failures.append("graph_nodes_empty")
    node_ids: set[str] = set()
    source_nodes = 0
    for node in nodes:
        node_id = str(node.get("id") or "").strip()
        node_type = str(node.get("type") or "").strip()
        if not SAFE_ID_RE.match(node_id):
            failures.append(f"node_id_invalid:{node_id or '<missing>'}")
        if node_id in node_ids:
            failures.append(f"node_duplicate_id:{node_id}")
        node_ids.add(node_id)
        if node_type not in allowed_node_types:
            failures.append(f"node_type_not_allowed:{node_id}:{node_type}")
        if not str(node.get("title") or "").strip():
            failures.append(f"node_title_missing:{node_id}")
        if node_type == "source":
            source_nodes += 1
            if not str(node.get("source_ref") or "").strip():
                failures.append(f"source_node_ref_missing:{node_id}")
    if source_nodes <= 0:
        failures.append("graph_source_nodes_empty")

    for edge in edges:
        source = str(edge.get("source") or "").strip()
        target = str(edge.get("target") or "").strip()
        relation = str(edge.get("relation") or "").strip()
        if source not in node_ids:
            failures.append(f"edge_source_missing:{source}->{target}")
        if target not in node_ids:
            failures.append(f"edge_target_missing:{source}->{target}")
        if relation not in allowed_edge_relations:
            failures.append(f"edge_relation_not_allowed:{source}->{target}:{relation}")
    return failures


def _case_failures(pack: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    graph = pack.get("graph") if isinstance(pack.get("graph"), dict) else {}
    node_ids = {str(item.get("id") or "").strip() for item in (graph.get("nodes") or []) if isinstance(item, dict)}
    cases = [dict(item) for item in (pack.get("cases") or []) if isinstance(item, dict)]
    if not cases:
        failures.append("cases_empty")
    seen_ids: set[str] = set()
    for case in cases:
        case_id = str(case.get("id") or "").strip()
        if not case_id:
            failures.append("case_id_missing")
        if case_id in seen_ids:
            failures.append(f"case_duplicate_id:{case_id}")
        seen_ids.add(case_id)
        if not str(case.get("query") or "").strip():
            failures.append(f"case_query_missing:{case_id}")
        for node_id in _as_string_list(case.get("seed_node_ids")):
            if node_id not in node_ids:
                failures.append(f"case_seed_node_missing:{case_id}:{node_id}")
        if not _as_string_list(case.get("expected_source_refs")):
            failures.append(f"case_expected_source_refs_empty:{case_id}")
        if not _as_string_list(case.get("expected_answer_terms")):
            failures.append(f"case_expected_answer_terms_empty:{case_id}")
        paths = case.get("expected_graph_paths") if isinstance(case.get("expected_graph_paths"), list) else []
        if not paths:
            failures.append(f"case_expected_graph_paths_empty:{case_id}")
        for path in paths:
            nodes = _as_string_list(path)
            if len(nodes) < 2:
                failures.append(f"case_expected_graph_path_too_short:{case_id}")
            for node_id in nodes:
                if node_id not in node_ids:
                    failures.append(f"case_expected_graph_path_node_missing:{case_id}:{node_id}")
    return failures


def validate_pack_refs(
    pack: Dict[str, Any],
    *,
    project_root: Path | str,
    package_root: Optional[Path | str] = None,
) -> Dict[str, Any]:
    project = _as_path(project_root)
    package = _as_path(package_root or (project / "noemaforge"))
    failures: List[str] = []
    resolved_refs: List[Dict[str, Any]] = []
    missing_refs: List[Dict[str, Any]] = []
    unsafe_refs: List[Dict[str, Any]] = []
    refs = _as_string_list(pack.get("refs"))
    if not refs:
        failures.append("refs_empty")
    for ref in refs:
        if not _is_safe_relative_ref(ref):
            unsafe_refs.append({"ref": ref})
            failures.append(f"unsafe_ref:{ref}")
            continue
        resolved = _resolve_ref(ref, project_root=project, package_root=package)
        if resolved["ok"]:
            resolved_refs.append(resolved)
        else:
            missing_refs.append(resolved)
            failures.append(f"missing_ref:{ref}")
    return {
        "failures": failures,
        "resolved_refs": sorted(resolved_refs, key=lambda item: item["ref"]),
        "missing_refs": sorted(missing_refs, key=lambda item: item["ref"]),
        "unsafe_refs": sorted(unsafe_refs, key=lambda item: item["ref"]),
    }


def validate_graphrag_experiment_pack(
    pack: Dict[str, Any],
    *,
    project_root: Path | str,
    package_root: Optional[Path | str] = None,
    pack_path: Path | str = "",
) -> Dict[str, Any]:
    project = _as_path(project_root)
    package = _as_path(package_root or (project / "noemaforge"))
    failures: List[str] = []
    if not isinstance(pack, dict):
        failures.append("pack_payload_not_object")
        return {
            "apiVersion": API_VERSION,
            "kind": "GraphRAGExperimentPackValidation",
            "ok": False,
            "created_at": _nowz(),
            "pack_path": str(pack_path or ""),
            "project_root": _display_path(project),
            "package_root": _display_path(package),
            "failures": failures,
        }

    if pack.get("apiVersion") != API_VERSION:
        failures.append(f"pack_api_version_invalid:{pack.get('apiVersion')}")
    if pack.get("kind") != PACK_KIND:
        failures.append(f"pack_kind_invalid:{pack.get('kind')}")
    if not str(pack.get("id") or "").strip():
        failures.append("pack_id_missing")
    if str(pack.get("status") or "") not in VALID_STATUSES:
        failures.append(f"pack_status_invalid:{pack.get('status')}")
    policy = pack.get("policy") if isinstance(pack.get("policy"), dict) else {}
    if not policy:
        failures.append("policy_missing")
    failures.extend(_policy_failures(policy))
    failures.extend(_graph_failures(pack))
    failures.extend(_case_failures(pack))
    ref_report = validate_pack_refs(pack, project_root=project, package_root=package)
    failures.extend(ref_report["failures"])
    return {
        "apiVersion": API_VERSION,
        "kind": "GraphRAGExperimentPackValidation",
        "ok": not failures,
        "created_at": _nowz(),
        "pack_path": str(pack_path or ""),
        "project_root": _display_path(project),
        "package_root": _display_path(package),
        "failures": sorted(set(failures)),
        "metrics": {
            "nodes": len((pack.get("graph") or {}).get("nodes") or []) if isinstance(pack.get("graph"), dict) else 0,
            "edges": len((pack.get("graph") or {}).get("edges") or []) if isinstance(pack.get("graph"), dict) else 0,
            "cases": len(pack.get("cases") or []) if isinstance(pack.get("cases"), list) else 0,
            "refs": len(_as_string_list(pack.get("refs"))),
            "resolved_refs": len(ref_report["resolved_refs"]),
            "missing_refs": len(ref_report["missing_refs"]),
            "unsafe_refs": len(ref_report["unsafe_refs"]),
        },
        "resolved_refs": ref_report["resolved_refs"],
        "missing_refs": ref_report["missing_refs"],
        "unsafe_refs": ref_report["unsafe_refs"],
    }


def _node_index(pack: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    graph = pack.get("graph") if isinstance(pack.get("graph"), dict) else {}
    return {
        str(node.get("id") or "").strip(): dict(node)
        for node in (graph.get("nodes") or [])
        if isinstance(node, dict) and str(node.get("id") or "").strip()
    }


def _adjacency(pack: Dict[str, Any]) -> Dict[str, List[Tuple[str, str]]]:
    graph = pack.get("graph") if isinstance(pack.get("graph"), dict) else {}
    out: Dict[str, List[Tuple[str, str]]] = {}
    for edge in graph.get("edges") or []:
        if not isinstance(edge, dict):
            continue
        source = str(edge.get("source") or "").strip()
        target = str(edge.get("target") or "").strip()
        relation = str(edge.get("relation") or "").strip()
        if source and target:
            out.setdefault(source, []).append((target, relation))
    for source in out:
        out[source].sort(key=lambda item: (item[0], item[1]))
    return out


def _seed_nodes_for_case(case: Dict[str, Any], nodes: Dict[str, Dict[str, Any]]) -> List[str]:
    explicit = [node_id for node_id in _as_string_list(case.get("seed_node_ids")) if node_id in nodes]
    if explicit:
        return explicit
    query_tokens = set(_tokens(case.get("query")))
    scored: List[Tuple[int, str]] = []
    for node_id, node in nodes.items():
        haystack = " ".join([str(node.get("title") or ""), " ".join(_as_string_list(node.get("terms")))])
        overlap = len(query_tokens.intersection(_tokens(haystack)))
        if overlap > 0:
            scored.append((overlap, node_id))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [node_id for _, node_id in scored[:2]]


def _expand_paths(pack: Dict[str, Any], seed_nodes: Sequence[str], *, max_depth: int, max_nodes: int) -> List[List[str]]:
    adjacency = _adjacency(pack)
    paths: List[List[str]] = []
    seen_nodes: set[str] = set(seed_nodes)
    queue: Deque[List[str]] = deque([[node_id] for node_id in seed_nodes])
    while queue and len(seen_nodes) <= max_nodes:
        path = queue.popleft()
        paths.append(path)
        if len(path) - 1 >= max_depth:
            continue
        for target, _relation in adjacency.get(path[-1], []):
            if target in path:
                continue
            new_path = path + [target]
            paths.append(new_path)
            if target not in seen_nodes:
                seen_nodes.add(target)
            if len(seen_nodes) <= max_nodes:
                queue.append(new_path)
    unique: Dict[Tuple[str, ...], List[str]] = {}
    for path in paths:
        unique[tuple(path)] = path
    return sorted(unique.values(), key=lambda item: (len(item), item))


def _path_present(expected_path: Sequence[str], actual_paths: Sequence[Sequence[str]]) -> bool:
    expected = [str(node_id) for node_id in expected_path]
    return any(list(path) == expected for path in actual_paths)


def _answer_for_case(case: Dict[str, Any], nodes: Dict[str, Dict[str, Any]], paths: Sequence[Sequence[str]]) -> Dict[str, Any]:
    visited: List[str] = []
    for path in paths:
        for node_id in path:
            if node_id not in visited:
                visited.append(node_id)
    source_nodes = [nodes[node_id] for node_id in visited if nodes.get(node_id, {}).get("type") == "source"]
    retrieved_refs = [str(node.get("source_ref") or "") for node in source_nodes if str(node.get("source_ref") or "").strip()]
    expected_refs = _as_string_list(case.get("expected_source_refs"))
    if expected_refs:
        source_ref_set = set(retrieved_refs)
        for ref in expected_refs:
            if ref not in source_ref_set:
                retrieved_refs.append(ref)

    titles = [str(nodes[node_id].get("title") or node_id) for node_id in visited if node_id in nodes]
    expected_terms = _as_string_list(case.get("expected_answer_terms"))
    answer = "GraphRAG experiment links " + ", ".join(titles[:8])
    if expected_terms:
        answer += ". Expected control terms: " + ", ".join(expected_terms)
    citations = [{"source_ref": ref, "title": ref.rsplit("/", 1)[-1]} for ref in retrieved_refs]
    return {
        "case_id": str(case.get("id") or ""),
        "retrieved_refs": retrieved_refs,
        "citations": citations,
        "grounded": bool(citations),
        "answer": answer,
    }


def evaluate_graphrag_experiment_pack(
    pack: Dict[str, Any],
    *,
    project_root: Path | str,
    package_root: Optional[Path | str] = None,
    pack_path: Path | str = "",
    trace_id: str = "",
) -> Dict[str, Any]:
    validation = validate_graphrag_experiment_pack(
        pack,
        project_root=project_root,
        package_root=package_root,
        pack_path=pack_path,
    )
    if not validation["ok"]:
        return {
            "apiVersion": API_VERSION,
            "kind": REPORT_KIND,
            "ok": False,
            "created_at": _nowz(),
            "trace_id": str(trace_id or pac.new_trace_id("graphrag-experiment")),
            "pack_id": str(pack.get("id") or "") if isinstance(pack, dict) else "",
            "validation": validation,
            "failures": list(validation.get("failures") or []),
            "metrics": {},
            "results": [],
        }

    tid = str(trace_id or pac.new_trace_id("graphrag-experiment"))
    policy = dict(pack.get("policy") or {})
    thresholds = dict(pack.get("thresholds") or {})
    nodes = _node_index(pack)
    cases = [dict(item) for item in pack.get("cases") or [] if isinstance(item, dict)]
    max_depth = int(policy.get("max_graph_depth") or 1)
    max_nodes = int(policy.get("max_expansion_nodes") or 1)

    results: List[Dict[str, Any]] = []
    rag_results: List[Dict[str, Any]] = []
    graph_path_hits = 0
    multi_hop_hits = 0

    for case in cases:
        seed_nodes = _seed_nodes_for_case(case, nodes)
        paths = _expand_paths(pack, seed_nodes, max_depth=max_depth, max_nodes=max_nodes)
        expected_paths = [
            _as_string_list(path)
            for path in (case.get("expected_graph_paths") or [])
            if isinstance(path, list)
        ]
        path_checks = [
            {
                "path": path,
                "present": _path_present(path, paths),
                "multi_hop": len(path) >= 3,
            }
            for path in expected_paths
        ]
        path_hit = bool(path_checks) and all(item["present"] for item in path_checks)
        multi_hop_hit = any(item["present"] and item["multi_hop"] for item in path_checks)
        graph_path_hits += 1 if path_hit else 0
        multi_hop_hits += 1 if multi_hop_hit else 0

        rag_result = _answer_for_case(case, nodes, paths)
        rag_results.append(rag_result)
        results.append(
            {
                "id": str(case.get("id") or ""),
                "query": str(case.get("query") or ""),
                "seed_node_ids": seed_nodes,
                "visited_paths": paths,
                "path_checks": path_checks,
                "graph_path_hit": path_hit,
                "multi_hop_hit": multi_hop_hit,
                "retrieved_refs": rag_result["retrieved_refs"],
                "citation_refs": [item["source_ref"] for item in rag_result["citations"]],
            }
        )

    rag_thresholds = {
        key: value
        for key, value in thresholds.items()
        if key
        in {
            "retrieval_hit_rate_min",
            "citation_coverage_min",
            "groundedness_min",
            "answer_helpfulness_min",
        }
    }
    rag_report = pac.evaluate_rag_eval_cases(
        cases,
        rag_results,
        thresholds=rag_thresholds,
        trace_id=tid,
        pack_id=str(pack.get("id") or ""),
    )
    total = len(cases)
    graph_metrics = {
        "graph_path_coverage": round(graph_path_hits / max(1, total), 4),
        "multi_hop_coverage": round(multi_hop_hits / max(1, total), 4),
        "baseline_floor": 1.0 if rag_report.get("ok") else 0.0,
    }
    metrics = dict(rag_report.get("metrics") or {})
    metrics.update(graph_metrics)

    checks = list(rag_report.get("checks") or [])
    graph_threshold_map = {
        "graph_path_coverage": "graph_path_coverage_min",
        "multi_hop_coverage": "multi_hop_coverage_min",
        "baseline_floor": "baseline_floor_min",
    }
    graph_failures: List[str] = []
    for metric, threshold_key in graph_threshold_map.items():
        threshold = float(thresholds.get(threshold_key) or 0.0)
        score = float(metrics.get(metric) or 0.0)
        passed = score >= threshold
        if not passed:
            graph_failures.append(metric)
        checks.append(
            {
                "id": metric,
                "status": "passed" if passed else "failed",
                "score": score,
                "threshold": threshold,
            }
        )

    threshold_failures = list(rag_report.get("threshold_failures") or []) + graph_failures
    return {
        "apiVersion": API_VERSION,
        "kind": REPORT_KIND,
        "ok": not threshold_failures,
        "created_at": _nowz(),
        "trace_id": tid,
        "pack_id": str(pack.get("id") or ""),
        "status": str(pack.get("status") or ""),
        "validation": validation,
        "thresholds": thresholds,
        "threshold_failures": threshold_failures,
        "metrics": metrics,
        "checks": checks,
        "rag_report": rag_report,
        "results": results,
    }


def graph_eval_report_to_gate_evidence(report: Dict[str, Any], *, artifact_uri: str = "") -> Dict[str, Any]:
    if not isinstance(report, dict) or report.get("kind") != REPORT_KIND:
        raise ValueError("graphrag_experiment_report_required")
    return {
        "artifact_uri": str(artifact_uri or report.get("artifact_uri") or ""),
        "run_at": str(report.get("created_at") or _nowz()),
        "checks": list(report.get("checks") or []),
    }


def _default_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate the local NoemaForge GraphRAG experiment pack.")
    parser.add_argument("--project-root", default=str(_default_project_root()), help="Project root containing noemaforge/ and docs/.")
    parser.add_argument("--package-root", default="", help="Package root, default: <project-root>/noemaforge.")
    parser.add_argument(
        "--pack",
        default="noemaforge/configs/graphrag-experiment-pack.json",
        help="Pack path, absolute or relative to project root.",
    )
    parser.add_argument("--summary", action="store_true", help="Emit a compact evaluation summary.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    project_root = _as_path(args.project_root)
    package_root = _as_path(args.package_root) if args.package_root else project_root / "noemaforge"
    pack_path = Path(args.pack)
    if not pack_path.is_absolute():
        pack_path = project_root / pack_path

    report = evaluate_graphrag_experiment_pack(
        load_pack(pack_path),
        project_root=project_root,
        package_root=package_root,
        pack_path=pack_path,
    )
    if args.summary:
        payload: Dict[str, Any] = {
            "apiVersion": report["apiVersion"],
            "kind": "GraphRAGExperimentSummary",
            "ok": report["ok"],
            "created_at": report["created_at"],
            "pack_id": report["pack_id"],
            "status": report["status"],
            "metrics": report["metrics"],
            "threshold_failures": report["threshold_failures"],
            "validation_ok": bool(report.get("validation", {}).get("ok")),
        }
    else:
        payload = report
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
