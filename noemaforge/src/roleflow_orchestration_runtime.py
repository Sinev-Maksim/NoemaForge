#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/roleflow_orchestration_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate RoleFlow orchestration graphs for role switches, guards, approvals, rollback and batons.
Inputs: noemaforge/configs/roleflow-orchestration-policy.json, role kernel policy, role catalog and examples.
Outputs: JSON-compatible RoleFlowValidationReport artifacts.
Side effects: None unless run as a CLI, which writes JSON to stdout.
Tests: noemaforge/tests/test_roleflow_orchestration_runtime.py
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
from typing import Any, Dict, List, Optional, Sequence, Set


SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import unified_registry_runtime as urr


API_VERSION = "noemaforge.roleflow/v1"
POLICY_KIND = "RoleFlowPolicy"
SET_KIND = "RoleFlowSet"
FLOW_KIND = "RoleFlow"
REPORT_KIND = "RoleFlowValidationReport"

VALID_POLICY_STATUSES = {"draft", "shadow", "stable", "retired"}
VALID_FLOW_STATUSES = {"draft", "ready", "blocked", "retired"}
REQUIRED_NODE_KINDS = {"role_switch", "branch", "guard", "approval", "rollback", "baton"}
REQUIRED_EDGE_KINDS = {"next", "branch", "guard", "approval", "rollback"}
REQUIRED_FEATURES = {
    "role_switching",
    "branching",
    "guard_edges",
    "approval_edges",
    "rollback_edges",
    "baton_payloads",
}
REQUIRED_BATON_FIELDS = {"id", "role_key", "payload", "handoff_reason", "resume_policy"}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,180}$")


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
            return {"ok": True, "ref": ref, "resolved_under": base_name, "path": _display_path(path), "checked": checked}
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


def _policy_dict(payload: Dict[str, Any]) -> Dict[str, Any]:
    return payload.get("policy") if isinstance(payload.get("policy"), dict) else payload


def _registry_ref(entry: Dict[str, Any]) -> str:
    return f"{entry.get('kind')}:{entry.get('id')}:{entry.get('version')}"


def _node_list(graph: Dict[str, Any]) -> List[Dict[str, Any]]:
    nodes = graph.get("nodes") if isinstance(graph.get("nodes"), list) else []
    return [item for item in nodes if isinstance(item, dict)]


def _edge_list(graph: Dict[str, Any]) -> List[Dict[str, Any]]:
    edges = graph.get("edges") if isinstance(graph.get("edges"), list) else []
    return [item for item in edges if isinstance(item, dict)]


def _baton_list(graph: Dict[str, Any]) -> List[Dict[str, Any]]:
    batons = graph.get("batons") if isinstance(graph.get("batons"), list) else []
    return [item for item in batons if isinstance(item, dict)]


def _role_kernel_role_keys(role_kernel_payload: Dict[str, Any]) -> Set[str]:
    policy = role_kernel_payload.get("policy") if isinstance(role_kernel_payload.get("policy"), dict) else {}
    roles = policy.get("default_roles") if isinstance(policy.get("default_roles"), list) else []
    return {str(item.get("role_key") or "") for item in roles if isinstance(item, dict) and str(item.get("role_key") or "")}


def _policy_failures(payload: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    policy = _policy_dict(payload)
    if payload.get("apiVersion") != API_VERSION:
        failures.append("policy_api_version_invalid")
    if payload.get("kind") != POLICY_KIND:
        failures.append("policy_kind_invalid")
    if not SAFE_ID_RE.match(str(payload.get("id") or "")):
        failures.append("policy_id_invalid")
    if str(payload.get("status") or "") not in VALID_POLICY_STATUSES:
        failures.append("policy_status_invalid")
    if str(policy.get("mode") or "") != "offline_contract":
        failures.append("policy_mode_not_offline_contract")
    if str(policy.get("activation_state") or "") != "protected_orchestration":
        failures.append("policy_activation_state_invalid")
    for key in [
        "require_trace_id",
        "require_registry_attachment",
        "require_policy_schema_runtime_tests",
        "require_docs_and_changelog_refs",
    ]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    if not str(policy.get("required_pipeline_ref") or "").startswith("pipeline:"):
        failures.append("policy_required_pipeline_ref_invalid")
    for key in ["role_kernel_policy_ref", "role_catalog_ref"]:
        if not _is_safe_relative_ref(str(policy.get(key) or "")):
            failures.append(f"policy_{key}_invalid")

    if not REQUIRED_NODE_KINDS.issubset(set(_as_string_list(policy.get("allowed_node_kinds")))):
        failures.append("policy_required_node_kinds_missing")
    if not REQUIRED_EDGE_KINDS.issubset(set(_as_string_list(policy.get("edge_kinds")))):
        failures.append("policy_required_edge_kinds_missing")
    if not REQUIRED_FEATURES.issubset(set(_as_string_list(policy.get("required_flow_features")))):
        failures.append("policy_required_flow_features_missing")

    guard_requirements = policy.get("guard_requirements") if isinstance(policy.get("guard_requirements"), dict) else {}
    for key in [
        "guard_edges_require_condition",
        "branch_edges_require_condition",
        "approval_edges_require_approver_role",
        "rollback_edges_require_target",
    ]:
        if guard_requirements.get(key) is not True:
            failures.append(f"policy_{key}_not_true")

    baton_requirements = policy.get("baton_requirements") if isinstance(policy.get("baton_requirements"), dict) else {}
    if baton_requirements.get("durable") is not True:
        failures.append("policy_baton_durable_not_required")
    if baton_requirements.get("sleep_wake") is not True:
        failures.append("policy_baton_sleep_wake_not_required")
    if not REQUIRED_BATON_FIELDS.issubset(set(_as_string_list(baton_requirements.get("required_fields")))):
        failures.append("policy_baton_required_fields_missing")

    approval_roles = _as_string_list(policy.get("approval_roles"))
    if not approval_roles:
        failures.append("policy_approval_roles_empty")
    for role_key in approval_roles:
        if not SAFE_ID_RE.match(role_key):
            failures.append(f"policy_approval_role_invalid:{role_key}")
    if not _as_string_list(policy.get("required_example_sets")):
        failures.append("policy_required_example_sets_empty")
    return failures


def _registry_failures(payload: Dict[str, Any], *, project_root: Path, package_root: Path, registry_path: Path) -> Dict[str, Any]:
    policy = _policy_dict(payload)
    registry = urr.load_registry(registry_path)
    report = urr.validate_unified_registry(registry, project_root=project_root, package_root=package_root, registry_path=registry_path)
    failures = [f"registry_invalid:{item}" for item in report.get("failures", [])]
    entries = {
        _registry_ref(entry): entry
        for entry in report.get("normalized_registry", {}).get("entries", [])
        if isinstance(entry, dict)
    }
    raw_entries = {
        _registry_ref(entry): entry
        for entry in registry.get("entries", [])
        if isinstance(entry, dict)
    }
    eval_ref = f"eval-pack:{payload.get('id')}:{payload.get('version')}"
    eval_entry = entries.get(eval_ref)
    if not eval_entry:
        failures.append(f"registry_eval_pack_missing:{eval_ref}")
    else:
        entry_refs = set(_as_string_list(eval_entry.get("refs")))
        for ref in [
            "configs/roleflow-orchestration-policy.json",
            "contracts/roleflow_orchestration.schema.json",
            "src/roleflow_orchestration_runtime.py",
        ]:
            if ref not in entry_refs:
                failures.append(f"registry_eval_pack_ref_missing:{eval_ref}:{ref}")

    pipeline_ref = str(policy.get("required_pipeline_ref") or "")
    pipeline = raw_entries.get(pipeline_ref) or entries.get(pipeline_ref)
    if not pipeline:
        failures.append(f"registry_pipeline_missing:{pipeline_ref}")
        pipeline_eval_refs: List[str] = []
        pipeline_refs: List[str] = []
    else:
        pipeline_eval_refs = _as_string_list(pipeline.get("eval_pack_refs"))
        pipeline_refs = _as_string_list(pipeline.get("refs"))
    if eval_ref not in pipeline_eval_refs:
        failures.append(f"registry_pipeline_eval_pack_missing:{eval_ref}")
    for ref in [
        "configs/roleflow-orchestration-policy.json",
        "src/roleflow_orchestration_runtime.py",
        "prelaunch/governance/roleflow_orchestration.example.json",
    ]:
        if ref not in pipeline_refs:
            failures.append(f"registry_pipeline_ref_missing:{ref}")
    return {"failures": failures, "registry_report": report, "entries": entries, "pipeline_eval_refs": pipeline_eval_refs}


def _catalog_failures(policy: Dict[str, Any], *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    failures: List[str] = []
    role_kernel_ref = str(policy.get("role_kernel_policy_ref") or "")
    role_catalog_ref = str(policy.get("role_catalog_ref") or "")
    role_kernel_resolved = _resolve_ref(role_kernel_ref, project_root=project_root, package_root=package_root)
    role_catalog_resolved = _resolve_ref(role_catalog_ref, project_root=project_root, package_root=package_root)
    role_kernel_keys: Set[str] = set()
    if not role_kernel_resolved["ok"]:
        failures.append(f"role_kernel_policy_missing:{role_kernel_ref}")
    else:
        role_kernel_payload = json.loads(Path(role_kernel_resolved["path"]).read_text(encoding="utf-8"))
        if role_kernel_payload.get("apiVersion") != "noemaforge.role-kernel/v1":
            failures.append(f"role_kernel_policy_api_version_invalid:{role_kernel_ref}")
        if role_kernel_payload.get("kind") != "RoleKernelPolicy":
            failures.append(f"role_kernel_policy_kind_invalid:{role_kernel_ref}")
        role_kernel_keys = _role_kernel_role_keys(role_kernel_payload)
        if not role_kernel_keys:
            failures.append(f"role_kernel_policy_default_roles_empty:{role_kernel_ref}")
    if not role_catalog_resolved["ok"]:
        failures.append(f"role_catalog_missing:{role_catalog_ref}")
        role_text = ""
    else:
        role_text = Path(role_catalog_resolved["path"]).read_text(encoding="utf-8")

    for role_key in _as_string_list(policy.get("approval_roles")):
        if role_kernel_keys and role_key not in role_kernel_keys:
            failures.append(f"approval_role_not_default_kernel_role:{role_key}")
        if role_text and f"{role_key}:" not in role_text:
            failures.append(f"role_catalog_role_missing:{role_key}")
    return {"failures": failures, "role_kernel_keys": role_kernel_keys}


def _flow_failures(flow: Dict[str, Any], policy_payload: Dict[str, Any], *, kernel_role_keys: Set[str]) -> List[str]:
    policy = _policy_dict(policy_payload)
    failures: List[str] = []
    flow_id = str(flow.get("id") or "<missing>")
    allowed_node_kinds = set(_as_string_list(policy.get("allowed_node_kinds")))
    allowed_edge_kinds = set(_as_string_list(policy.get("edge_kinds")))
    approval_roles = set(_as_string_list(policy.get("approval_roles")))
    guard_requirements = policy.get("guard_requirements") if isinstance(policy.get("guard_requirements"), dict) else {}
    baton_requirements = policy.get("baton_requirements") if isinstance(policy.get("baton_requirements"), dict) else {}
    baton_required_fields = set(_as_string_list(baton_requirements.get("required_fields")))

    if flow.get("apiVersion") != API_VERSION:
        failures.append(f"flow_api_version_invalid:{flow_id}")
    if flow.get("kind") != FLOW_KIND:
        failures.append(f"flow_kind_invalid:{flow_id}")
    if not SAFE_ID_RE.match(flow_id):
        failures.append(f"flow_id_invalid:{flow_id}")
    if policy.get("require_trace_id") is True and not SAFE_ID_RE.match(str(flow.get("trace_id") or "")):
        failures.append(f"flow_trace_id_invalid:{flow_id}")
    if str(flow.get("status") or "") not in VALID_FLOW_STATUSES:
        failures.append(f"flow_status_invalid:{flow_id}:{flow.get('status')}")

    graph = flow.get("orchestration_graph") if isinstance(flow.get("orchestration_graph"), dict) else {}
    if not graph:
        failures.append(f"flow_graph_missing:{flow_id}")
    nodes = _node_list(graph)
    edges = _edge_list(graph)
    batons = _baton_list(graph)
    if not nodes:
        failures.append(f"flow_nodes_empty:{flow_id}")
    if not edges:
        failures.append(f"flow_edges_empty:{flow_id}")

    node_ids: Set[str] = set()
    node_kinds: Set[str] = set()
    role_switch_roles: Set[str] = set()
    for node in nodes:
        node_id = str(node.get("id") or "")
        node_kind = str(node.get("kind") or "")
        role_key = str(node.get("role_key") or "")
        if not SAFE_ID_RE.match(node_id):
            failures.append(f"flow_node_id_invalid:{flow_id}:{node_id}")
        if node_id in node_ids:
            failures.append(f"flow_node_id_duplicate:{flow_id}:{node_id}")
        node_ids.add(node_id)
        node_kinds.add(node_kind)
        if node_kind not in allowed_node_kinds:
            failures.append(f"flow_node_kind_invalid:{flow_id}:{node_id}:{node_kind}")
        if role_key:
            if not SAFE_ID_RE.match(role_key):
                failures.append(f"flow_node_role_invalid:{flow_id}:{node_id}:{role_key}")
            if kernel_role_keys and role_key not in kernel_role_keys:
                failures.append(f"flow_node_role_not_kernel_default:{flow_id}:{node_id}:{role_key}")
        if node_kind == "role_switch" and role_key:
            role_switch_roles.add(role_key)
    if str(graph.get("start_node") or "") not in node_ids:
        failures.append(f"flow_start_node_invalid:{flow_id}:{graph.get('start_node')}")
    if not REQUIRED_NODE_KINDS.issubset(node_kinds):
        failures.append(f"flow_required_node_kinds_missing:{flow_id}")
    if len(role_switch_roles) < 2:
        failures.append(f"flow_role_switching_missing:{flow_id}")

    edge_ids: Set[str] = set()
    edge_kinds: Set[str] = set()
    for edge in edges:
        edge_id = str(edge.get("id") or "")
        edge_kind = str(edge.get("kind") or "")
        source = str(edge.get("from") or "")
        target = str(edge.get("to") or "")
        if not SAFE_ID_RE.match(edge_id):
            failures.append(f"flow_edge_id_invalid:{flow_id}:{edge_id}")
        if edge_id in edge_ids:
            failures.append(f"flow_edge_id_duplicate:{flow_id}:{edge_id}")
        edge_ids.add(edge_id)
        edge_kinds.add(edge_kind)
        if edge_kind not in allowed_edge_kinds:
            failures.append(f"flow_edge_kind_invalid:{flow_id}:{edge_id}:{edge_kind}")
        if source not in node_ids:
            failures.append(f"flow_edge_source_missing:{flow_id}:{edge_id}:{source}")
        if target not in node_ids:
            failures.append(f"flow_edge_target_missing:{flow_id}:{edge_id}:{target}")
        if edge_kind == "guard" and guard_requirements.get("guard_edges_require_condition") is True and not str(edge.get("condition") or "").strip():
            failures.append(f"flow_guard_edge_condition_missing:{flow_id}:{edge_id}")
        if edge_kind == "branch" and guard_requirements.get("branch_edges_require_condition") is True and not str(edge.get("condition") or "").strip():
            failures.append(f"flow_branch_edge_condition_missing:{flow_id}:{edge_id}")
        if edge_kind == "approval":
            approver = str(edge.get("approver_role") or "")
            if guard_requirements.get("approval_edges_require_approver_role") is True and approver not in approval_roles:
                failures.append(f"flow_approval_edge_approver_invalid:{flow_id}:{edge_id}:{approver}")
        if edge_kind == "rollback":
            rollback_target = str(edge.get("rollback_target") or "")
            if guard_requirements.get("rollback_edges_require_target") is True and rollback_target not in node_ids:
                failures.append(f"flow_rollback_edge_target_invalid:{flow_id}:{edge_id}:{rollback_target}")
    if not REQUIRED_EDGE_KINDS.issubset(edge_kinds):
        failures.append(f"flow_required_edge_kinds_missing:{flow_id}")

    baton_ids: Set[str] = set()
    for baton in batons:
        baton_id = str(baton.get("id") or "")
        role_key = str(baton.get("role_key") or "")
        if not SAFE_ID_RE.match(baton_id):
            failures.append(f"flow_baton_id_invalid:{flow_id}:{baton_id}")
        baton_ids.add(baton_id)
        if role_key not in kernel_role_keys:
            failures.append(f"flow_baton_role_not_kernel_default:{flow_id}:{baton_id}:{role_key}")
        if baton_requirements.get("durable") is True and baton.get("durable") is not True:
            failures.append(f"flow_baton_not_durable:{flow_id}:{baton_id}")
        if baton_requirements.get("sleep_wake") is True and baton.get("sleep_wake") is not True:
            failures.append(f"flow_baton_not_sleep_wake:{flow_id}:{baton_id}")
        missing_fields = sorted(field for field in baton_required_fields if field not in baton)
        if missing_fields:
            failures.append(f"flow_baton_required_fields_missing:{flow_id}:{baton_id}:{','.join(missing_fields)}")
        if not isinstance(baton.get("payload"), dict) or not baton.get("payload"):
            failures.append(f"flow_baton_payload_invalid:{flow_id}:{baton_id}")
    baton_node_ids = {str(node.get("baton_id") or "") for node in nodes if str(node.get("kind") or "") == "baton"}
    if not baton_node_ids or not baton_node_ids.issubset(baton_ids):
        failures.append(f"flow_baton_node_unresolved:{flow_id}")
    return failures


def validate_roleflow_policy(
    payload: Dict[str, Any],
    *,
    project_root: Path | str,
    package_root: Path | str,
    policy_path: Optional[Path | str] = None,
    registry_path: Optional[Path | str] = None,
) -> Dict[str, Any]:
    project = _as_path(project_root)
    package = _as_path(package_root)
    if not project.exists():
        raise FileNotFoundError(project)
    if not package.exists():
        raise FileNotFoundError(package)
    registry = _as_path(registry_path) if registry_path else package / "configs" / "unified-registry.json"

    policy = _policy_dict(payload)
    failures: List[str] = []
    failures.extend(_policy_failures(payload))
    catalog_result = _catalog_failures(policy, project_root=project, package_root=package)
    failures.extend(catalog_result["failures"])
    registry_result = _registry_failures(payload, project_root=project, package_root=package, registry_path=registry)
    failures.extend(registry_result["failures"])

    all_resolved_refs: List[Dict[str, Any]] = []
    all_missing_refs: List[Dict[str, Any]] = []
    all_unsafe_refs: List[Dict[str, Any]] = []
    flow_results: List[Dict[str, Any]] = []

    refs_to_resolve = _as_string_list(payload.get("refs"))
    refs_to_resolve.extend([str(policy.get("role_kernel_policy_ref") or ""), str(policy.get("role_catalog_ref") or "")])
    refs_result = _resolve_refs(sorted(set(refs_to_resolve)), project_root=project, package_root=package, owner=str(payload.get("id") or "policy"))
    failures.extend(refs_result["failures"])
    all_resolved_refs.extend(refs_result["resolved_refs"])
    all_missing_refs.extend(refs_result["missing_refs"])
    all_unsafe_refs.extend(refs_result["unsafe_refs"])

    example_ref_results = _resolve_refs(_as_string_list(policy.get("required_example_sets")), project_root=project, package_root=package, owner="required_example_sets")
    failures.extend(example_ref_results["failures"])
    all_resolved_refs.extend(example_ref_results["resolved_refs"])
    all_missing_refs.extend(example_ref_results["missing_refs"])
    all_unsafe_refs.extend(example_ref_results["unsafe_refs"])

    kernel_role_keys = catalog_result["role_kernel_keys"]
    for item in example_ref_results["resolved_refs"]:
        example_set = load_example_set(Path(item["path"]))
        if example_set.get("apiVersion") != API_VERSION:
            failures.append(f"example_set_api_version_invalid:{item['ref']}")
        if example_set.get("kind") != SET_KIND:
            failures.append(f"example_set_kind_invalid:{item['ref']}")
        flows = example_set.get("flows") if isinstance(example_set.get("flows"), list) else []
        if not flows:
            failures.append(f"example_set_flows_empty:{item['ref']}")
        for flow in flows:
            if not isinstance(flow, dict):
                failures.append(f"flow_not_object:{item['ref']}")
                continue
            flow_id = str(flow.get("id") or "<missing>")
            flow_failures = _flow_failures(flow, payload, kernel_role_keys=kernel_role_keys)
            flow_ref_result = _resolve_refs(_as_string_list(flow.get("refs")), project_root=project, package_root=package, owner=flow_id)
            flow_failures.extend(flow_ref_result["failures"])
            failures.extend(flow_failures)
            all_resolved_refs.extend(flow_ref_result["resolved_refs"])
            all_missing_refs.extend(flow_ref_result["missing_refs"])
            all_unsafe_refs.extend(flow_ref_result["unsafe_refs"])
            graph = flow.get("orchestration_graph") if isinstance(flow.get("orchestration_graph"), dict) else {}
            flow_results.append(
                {
                    "id": flow_id,
                    "ok": not flow_failures,
                    "nodes": len(_node_list(graph)),
                    "edges": len(_edge_list(graph)),
                    "batons": len(_baton_list(graph)),
                    "failures": sorted(set(flow_failures)),
                }
            )

    checks = [
        {"id": "role_switching", "status": "passed" if not any("role_switching" in item for item in failures) else "failed"},
        {"id": "branching", "status": "passed" if not any("branch" in item for item in failures) else "failed"},
        {"id": "guard_edges", "status": "passed" if not any("guard_edge" in item for item in failures) else "failed"},
        {"id": "approval_edges", "status": "passed" if not any("approval_edge" in item for item in failures) else "failed"},
        {"id": "rollback_edges", "status": "passed" if not any("rollback_edge" in item for item in failures) else "failed"},
        {"id": "baton_payloads", "status": "passed" if not any("baton" in item for item in failures) else "failed"},
        {"id": "refs_resolved", "status": "passed" if not all_missing_refs and not all_unsafe_refs else "failed"},
    ]
    metrics = {
        "flows": len(flow_results),
        "passing_flows": sum(1 for item in flow_results if item["ok"]),
        "kernel_roles": len(kernel_role_keys),
        "allowed_node_kinds": len(set(_as_string_list(policy.get("allowed_node_kinds")))),
        "edge_kinds": len(set(_as_string_list(policy.get("edge_kinds")))),
        "approval_roles": len(set(_as_string_list(policy.get("approval_roles")))),
        "registry_entries": len(registry_result["entries"]),
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
        "registry_path": _display_path(registry),
        "project_root": _display_path(project),
        "package_root": _display_path(package),
        "failures": sorted(set(failures)),
        "metrics": metrics,
        "checks": checks,
        "flow_results": sorted(flow_results, key=lambda item: item["id"]),
        "resolved_refs": sorted(all_resolved_refs, key=lambda item: (item["owner"], item["ref"])),
        "missing_refs": sorted(all_missing_refs, key=lambda item: (item["owner"], item["ref"])),
        "unsafe_refs": sorted(all_unsafe_refs, key=lambda item: (item["owner"], item["ref"])),
    }


def roleflow_report_to_gate_evidence(report: Dict[str, Any], *, artifact_uri: str = "") -> Dict[str, Any]:
    if not isinstance(report, dict) or report.get("kind") != REPORT_KIND:
        raise ValueError("roleflow_report_required")
    status = "passed" if report.get("ok") else "failed"
    return {
        "artifact_uri": str(artifact_uri or report.get("artifact_uri") or ""),
        "run_at": str(report.get("created_at") or _nowz()),
        "checks": [
            {"id": "pipeline_eval", "status": status, "score": 1.0 if status == "passed" else 0.0, "threshold": 1.0},
            {"id": "rollback_plan", "status": status, "score": 1.0 if status == "passed" else 0.0, "threshold": 1.0},
            {"id": "safety_eval", "status": status, "score": 1.0 if status == "passed" else 0.0, "threshold": 1.0},
        ],
    }


def _default_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate NoemaForge RoleFlow orchestration contracts.")
    parser.add_argument("--project-root", default=str(_default_project_root()), help="Project root containing noemaforge/ and docs/.")
    parser.add_argument("--package-root", default="", help="Package root, default: <project-root>/noemaforge.")
    parser.add_argument(
        "--policy",
        default="noemaforge/configs/roleflow-orchestration-policy.json",
        help="Policy path, absolute or relative to project root.",
    )
    parser.add_argument("--registry", default="", help="Optional Unified Registry path.")
    parser.add_argument("--summary", action="store_true", help="Emit a compact validation summary.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    project_root = _as_path(args.project_root)
    package_root = _as_path(args.package_root) if args.package_root else project_root / "noemaforge"
    policy_path = Path(args.policy)
    if not policy_path.is_absolute():
        policy_path = project_root / policy_path
    registry_path = Path(args.registry) if args.registry else package_root / "configs" / "unified-registry.json"
    if not registry_path.is_absolute():
        registry_path = project_root / registry_path

    report = validate_roleflow_policy(
        load_policy(policy_path),
        project_root=project_root,
        package_root=package_root,
        policy_path=policy_path,
        registry_path=registry_path,
    )
    if args.summary:
        payload: Dict[str, Any] = {
            "apiVersion": report["apiVersion"],
            "kind": "RoleFlowValidationSummary",
            "ok": report["ok"],
            "created_at": report["created_at"],
            "policy_path": report["policy_path"],
            "registry_path": report["registry_path"],
            "metrics": report["metrics"],
            "failures": report["failures"],
        }
    else:
        payload = report
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
