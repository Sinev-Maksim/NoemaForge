#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/tinyml_node_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Validate offline TinyML node contracts before MCU inference deployment consideration.
Inputs: noemaforge/configs/tinyml-node-policy.json plus local project/package roots.
Outputs: JSON-compatible TinyMLNodeReport artifacts.
Side effects: None unless run as a CLI, which writes JSON to stdout.
Tests: noemaforge/tests/test_tinyml_node_runtime.py
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
from typing import Any, Dict, Iterable, List, Optional, Sequence


SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import production_ai_contracts as pac


API_VERSION = "noemaforge.tinyml-node/v1"
POLICY_KIND = "TinyMLNodePolicy"
REPORT_KIND = "TinyMLNodeReport"

VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
VALID_RUNTIMES = {"tflm", "mock"}
VALID_DECISION_MODES = {"advisory_only", "fallback_only"}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")
SHA256_RE = re.compile(r"^[A-Fa-f0-9]{64}$")
REGISTRY_REF_RE = re.compile(r"^[a-z-]+:[A-Za-z0-9_.:-]+:[A-Za-z0-9_.:-]+$")


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


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


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


def load_policy(policy_path: Path | str) -> Dict[str, Any]:
    return json.loads(Path(policy_path).read_text(encoding="utf-8"))


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
    if str(policy.get("mode") or "") != "offline_validation":
        failures.append("policy_mode_not_offline_validation")

    for key in [
        "require_golden_vectors",
        "require_latency_budget",
        "require_ram_arena_budget",
        "require_model_size_gate",
        "require_model_hash",
        "require_signed_model_manifest",
        "require_edge_rules_fallback",
        "forbid_direct_control_decisions",
    ]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    if _as_int(policy.get("min_golden_vectors"), 0) <= 0:
        failures.append("policy_min_golden_vectors_invalid")
    runtimes = set(_as_string_list(policy.get("allowed_runtimes")))
    modes = set(_as_string_list(policy.get("allowed_decision_modes")))
    if not runtimes:
        failures.append("policy_allowed_runtimes_empty")
    if not modes:
        failures.append("policy_allowed_decision_modes_empty")
    failures.extend(f"policy_invalid_runtime:{item}" for item in sorted(runtimes - VALID_RUNTIMES))
    failures.extend(f"policy_invalid_decision_mode:{item}" for item in sorted(modes - VALID_DECISION_MODES))
    return failures


def _load_golden_vectors(path: Path) -> Dict[str, Any]:
    vectors: List[Dict[str, Any]] = []
    failures: List[str] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception as exc:
        return {"vectors": [], "failures": [f"golden_vectors_load_failed:{exc}"]}
    for index, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except Exception as exc:
            failures.append(f"golden_vector_json_invalid:{index}:{exc}")
            continue
        if not str(item.get("case_id") or "").strip():
            failures.append(f"golden_vector_case_id_missing:{index}")
        if "input" not in item:
            failures.append(f"golden_vector_input_missing:{index}")
        if "expected_output" not in item:
            failures.append(f"golden_vector_expected_output_missing:{index}")
        vectors.append(item)
    return {"vectors": vectors, "failures": failures}


def _load_arena_report(path: Path) -> Dict[str, Any]:
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"report": {}, "failures": [f"static_arena_report_load_failed:{exc}"]}
    failures: List[str] = []
    if report.get("kind") != "StaticArenaReport":
        failures.append("static_arena_report_kind_invalid")
    if _as_int(report.get("arena_bytes"), -1) <= 0:
        failures.append("static_arena_report_arena_bytes_invalid")
    if _as_int(report.get("peak_bytes"), -1) <= 0:
        failures.append("static_arena_report_peak_bytes_invalid")
    if _as_int(report.get("peak_bytes"), 0) > _as_int(report.get("arena_bytes"), 0):
        failures.append("static_arena_report_peak_exceeds_arena")
    return {"report": report, "failures": failures}


def _node_failures(node: Dict[str, Any], policy: Dict[str, Any], *, project_root: Path, package_root: Path) -> List[str]:
    failures: List[str] = []
    node_id = str(node.get("id") or "").strip()
    owner = node_id or "<missing>"
    if not SAFE_ID_RE.match(node_id):
        failures.append(f"node_id_invalid:{owner}")
    if str(node.get("state") or "") not in VALID_STATUSES:
        failures.append(f"node_state_invalid:{owner}:{node.get('state')}")
    runtime = str(node.get("runtime") or "")
    if runtime not in set(_as_string_list(policy.get("allowed_runtimes"))) or runtime not in VALID_RUNTIMES:
        failures.append(f"node_runtime_not_allowed:{owner}:{runtime}")
    decision_mode = str(node.get("decision_mode") or "")
    if decision_mode not in set(_as_string_list(policy.get("allowed_decision_modes"))) or decision_mode not in VALID_DECISION_MODES:
        failures.append(f"node_decision_mode_not_allowed:{owner}:{decision_mode}")
    if not REGISTRY_REF_RE.match(str(node.get("model_ref") or "")):
        failures.append(f"node_model_ref_invalid:{owner}")
    if not SHA256_RE.match(str(node.get("model_hash") or "")):
        failures.append(f"node_model_hash_invalid:{owner}")

    if _as_float(node.get("observed_latency_ms"), -1.0) > _as_float(node.get("latency_budget_ms"), 0.0):
        failures.append(f"node_latency_budget_exceeded:{owner}")
    if _as_int(node.get("observed_ram_arena_bytes"), -1) > _as_int(node.get("ram_arena_budget_bytes"), 0):
        failures.append(f"node_ram_arena_budget_exceeded:{owner}")
    if _as_int(node.get("observed_model_size_bytes"), -1) > _as_int(node.get("model_size_budget_bytes"), 0):
        failures.append(f"node_model_size_budget_exceeded:{owner}")
    for key in ["latency_budget_ms", "ram_arena_budget_bytes", "model_size_budget_bytes"]:
        if _as_float(node.get(key), 0.0) <= 0:
            failures.append(f"node_{key}_invalid:{owner}")
    if policy.get("forbid_direct_control_decisions") is True and node.get("direct_control_decisions") is not False:
        failures.append(f"node_direct_control_decision_enabled:{owner}")
    if policy.get("require_edge_rules_fallback") is True and node.get("fallback_rules_required") is not True:
        failures.append(f"node_fallback_rules_not_required:{owner}")

    for ref_key in ["signed_model_manifest_ref", "edge_rules_ref", "golden_vectors_ref", "static_arena_report_ref"]:
        ref = str(node.get(ref_key) or "")
        if not _is_safe_relative_ref(ref):
            failures.append(f"node_{ref_key}_unsafe:{owner}:{ref}")

    golden_ref = str(node.get("golden_vectors_ref") or "")
    golden_resolved = _resolve_ref(golden_ref, project_root=project_root, package_root=package_root) if _is_safe_relative_ref(golden_ref) else {"ok": False}
    if golden_resolved.get("ok"):
        golden = _load_golden_vectors(Path(str(golden_resolved["path"])))
        failures.extend(f"node_{item}:{owner}" for item in golden["failures"])
        if len(golden["vectors"]) < _as_int(policy.get("min_golden_vectors"), 1):
            failures.append(f"node_golden_vectors_below_min:{owner}:{len(golden['vectors'])}")
    else:
        failures.append(f"node_golden_vectors_missing:{owner}:{golden_ref}")

    arena_ref = str(node.get("static_arena_report_ref") or "")
    arena_resolved = _resolve_ref(arena_ref, project_root=project_root, package_root=package_root) if _is_safe_relative_ref(arena_ref) else {"ok": False}
    if arena_resolved.get("ok"):
        arena = _load_arena_report(Path(str(arena_resolved["path"])))
        failures.extend(f"node_{item}:{owner}" for item in arena["failures"])
        if _as_int(arena["report"].get("arena_bytes"), 0) > _as_int(node.get("ram_arena_budget_bytes"), 0):
            failures.append(f"node_static_arena_report_exceeds_budget:{owner}")
    else:
        failures.append(f"node_static_arena_report_missing:{owner}:{arena_ref}")
    return failures


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


def validate_tinyml_node_policy(
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
    nodes = payload.get("nodes") if isinstance(payload.get("nodes"), list) else []
    failures: List[str] = []
    failures.extend(_policy_failures(payload))
    if not nodes:
        failures.append("nodes_empty")

    all_resolved_refs: List[Dict[str, Any]] = []
    all_missing_refs: List[Dict[str, Any]] = []
    all_unsafe_refs: List[Dict[str, Any]] = []
    node_results: List[Dict[str, Any]] = []

    policy_refs = _resolve_refs(_as_string_list(payload.get("refs")), project_root=project, package_root=package, owner=str(payload.get("id") or "policy"))
    failures.extend(policy_refs["failures"])
    all_resolved_refs.extend(policy_refs["resolved_refs"])
    all_missing_refs.extend(policy_refs["missing_refs"])
    all_unsafe_refs.extend(policy_refs["unsafe_refs"])

    for node in nodes:
        if not isinstance(node, dict):
            failures.append("node_not_object")
            continue
        node_id = str(node.get("id") or "<missing>")
        node_failures = _node_failures(node, policy, project_root=project, package_root=package)
        refs = _as_string_list(node.get("refs"))
        for ref_key in ["signed_model_manifest_ref", "edge_rules_ref", "golden_vectors_ref", "static_arena_report_ref"]:
            ref = str(node.get(ref_key) or "")
            if ref and ref not in refs:
                refs.append(ref)
        refs_result = _resolve_refs(refs, project_root=project, package_root=package, owner=node_id)
        node_failures.extend(refs_result["failures"])
        failures.extend(node_failures)
        all_resolved_refs.extend(refs_result["resolved_refs"])
        all_missing_refs.extend(refs_result["missing_refs"])
        all_unsafe_refs.extend(refs_result["unsafe_refs"])
        node_results.append(
            {
                "id": node_id,
                "ok": not node_failures,
                "runtime": str(node.get("runtime") or ""),
                "decision_mode": str(node.get("decision_mode") or ""),
                "latency_ms": _as_float(node.get("observed_latency_ms"), 0.0),
                "ram_arena_bytes": _as_int(node.get("observed_ram_arena_bytes"), 0),
                "model_size_bytes": _as_int(node.get("observed_model_size_bytes"), 0),
                "direct_control_decisions": node.get("direct_control_decisions") is True,
                "failures": sorted(set(node_failures)),
            }
        )

    checks = [
        {"id": "golden_vectors", "status": "passed" if not any("golden" in item for item in failures) else "failed"},
        {"id": "latency_budget", "status": "passed" if not any("latency" in item for item in failures) else "failed"},
        {"id": "ram_arena_budget", "status": "passed" if not any("arena" in item for item in failures) else "failed"},
        {"id": "model_size_gate", "status": "passed" if not any("model_size" in item for item in failures) else "failed"},
        {"id": "model_hash", "status": "passed" if not any("model_hash" in item for item in failures) else "failed"},
        {"id": "fallback_rules", "status": "passed" if not any("fallback" in item for item in failures) else "failed"},
        {"id": "refs_resolved", "status": "passed" if not all_missing_refs and not all_unsafe_refs else "failed"},
    ]
    metrics = {
        "nodes": len(node_results),
        "passing_nodes": sum(1 for item in node_results if item["ok"]),
        "direct_control_decision_nodes": sum(1 for item in node_results if item["direct_control_decisions"]),
        "max_observed_latency_ms": max((item["latency_ms"] for item in node_results), default=0.0),
        "max_observed_ram_arena_bytes": max((item["ram_arena_bytes"] for item in node_results), default=0),
        "max_observed_model_size_bytes": max((item["model_size_bytes"] for item in node_results), default=0),
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
        "node_results": sorted(node_results, key=lambda item: item["id"]),
        "resolved_refs": sorted(all_resolved_refs, key=lambda item: (item["owner"], item["ref"])),
        "missing_refs": sorted(all_missing_refs, key=lambda item: (item["owner"], item["ref"])),
        "unsafe_refs": sorted(all_unsafe_refs, key=lambda item: (item["owner"], item["ref"])),
    }


def tinyml_node_report_to_gate_evidence(report: Dict[str, Any], *, artifact_uri: str = "") -> Dict[str, Any]:
    if not isinstance(report, dict) or report.get("kind") != REPORT_KIND:
        raise ValueError("tinyml_node_report_required")
    status = "passed" if report.get("ok") else "failed"
    return {
        "artifact_uri": str(artifact_uri or report.get("artifact_uri") or ""),
        "run_at": str(report.get("created_at") or _nowz()),
        "checks": [
            {"id": "model_eval", "status": status, "score": 1.0 if status == "passed" else 0.0, "threshold": 1.0},
            {"id": "safety_eval", "status": status, "score": 1.0 if status == "passed" else 0.0, "threshold": 1.0},
        ],
    }


def _default_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate NoemaForge offline TinyML node contracts.")
    parser.add_argument("--project-root", default=str(_default_project_root()), help="Project root containing noemaforge/ and docs/.")
    parser.add_argument("--package-root", default="", help="Package root, default: <project-root>/noemaforge.")
    parser.add_argument(
        "--policy",
        default="noemaforge/configs/tinyml-node-policy.json",
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

    report = validate_tinyml_node_policy(
        load_policy(policy_path),
        project_root=project_root,
        package_root=package_root,
        policy_path=policy_path,
    )
    if args.summary:
        payload: Dict[str, Any] = {
            "apiVersion": report["apiVersion"],
            "kind": "TinyMLNodeSummary",
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
