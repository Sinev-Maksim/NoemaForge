#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/role_review_state_machine_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate the Admin/Surgeon/Scary review-flow state machine contract.
Inputs: Role review state-machine policy, role kernel, roleflow policy, docs and examples.
Outputs: JSON-compatible RoleReviewStateMachineValidationReport artifacts.
Side effects: None; CLI writes JSON to stdout.
Tests: noemaforge/tests/test_role_review_state_machine_runtime.py
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
from typing import Any, Dict, List, Sequence, Set, Tuple


SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import unified_registry_runtime as urr


API_VERSION = "noemaforge.role-review-state-machine/v1"
POLICY_KIND = "RoleReviewStateMachinePolicy"
SET_KIND = "RoleReviewStateMachineExampleSet"
REPORT_KIND = "RoleReviewStateMachineValidationReport"

VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,220}$")
REQUIRED_CONTROLS = {
    "explicit_state_machine",
    "scary_first_risk_gate",
    "surgeon_repair_only_after_admin_approval",
    "admin_final_apply_approval",
    "rollback_terminal_state",
    "blocked_terminal_state",
    "durable_baton_per_handoff",
    "no_auto_apply_without_admin",
    "no_live_host_required",
}
REQUIRED_OUTPUTS = {
    "state_transition_log",
    "scary_verdict",
    "surgeon_repair_plan",
    "admin_approval",
    "rollback_record",
    "terminal_state",
}
REQUIRED_REGISTRY_REFS = [
    "configs/role-review-state-machine-policy.json",
    "contracts/role_review_state_machine.schema.json",
    "configs/role-kernel-policy.json",
    "configs/roleflow-orchestration-policy.json",
    "src/role_review_state_machine_runtime.py",
    "tests/test_role_review_state_machine_runtime.py",
    "tests/test_role_review_state_machine_qa.py",
    "tests/test_role_review_state_machine_performance.py",
]
REQUIRED_PIPELINE_REFS = [
    "configs/role-review-state-machine-policy.json",
    "contracts/role_review_state_machine.schema.json",
    "src/role_review_state_machine_runtime.py",
    "prelaunch/governance/role_review_state_machine.example.json",
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


def _policy_state_ids(policy: Dict[str, Any]) -> Set[str]:
    states = policy.get("states") if isinstance(policy.get("states"), list) else []
    return {str(item.get("id") or "") for item in states if isinstance(item, dict) and str(item.get("id") or "")}


def _transition_key(item: Dict[str, Any]) -> Tuple[str, str, str]:
    return (str(item.get("from") or ""), str(item.get("to") or ""), str(item.get("kind") or ""))


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
    if str(policy.get("activation_state") or "") != "explicit_admin_surgeon_scary_state_machine":
        failures.append("policy_activation_state_invalid")
    if not str(policy.get("required_pipeline_ref") or "").startswith("pipeline:"):
        failures.append("policy_required_pipeline_ref_invalid")
    for key in ["require_trace_id", "require_registry_attachment", "require_docs_and_changelog_refs", "require_no_live_dependency"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    for key in ["role_kernel_policy_ref", "roleflow_policy_ref"]:
        if not _is_safe_relative_ref(str(policy.get(key) or "")):
            failures.append(f"policy_{key}_invalid")
    for key in [
        "required_roles",
        "required_state_kinds",
        "required_terminal_states",
        "states",
        "mandatory_transitions",
        "blocked_transition_claims",
        "required_boundary_refs",
        "scan_refs",
        "required_example_sets",
    ]:
        if not isinstance(policy.get(key), list) or not policy.get(key):
            failures.append(f"policy_{key}_empty")
    controls = policy.get("controls") if isinstance(policy.get("controls"), dict) else {}
    for key in REQUIRED_CONTROLS:
        if controls.get(key) is not True:
            failures.append(f"policy_control_{key}_not_true")
    outputs = set(_as_string_list(policy.get("required_outputs")))
    for output in REQUIRED_OUTPUTS:
        if output not in outputs:
            failures.append(f"policy_required_output_missing:{output}")
    required_roles = set(_as_string_list(policy.get("required_roles")))
    required_kinds = set(_as_string_list(policy.get("required_state_kinds")))
    states = policy.get("states") if isinstance(policy.get("states"), list) else []
    for state in states:
        if not isinstance(state, dict):
            failures.append("policy_state_invalid")
            continue
        sid = str(state.get("id") or "")
        if not SAFE_ID_RE.match(sid):
            failures.append(f"policy_state_id_invalid:{sid}")
        if str(state.get("role_key") or "") not in required_roles:
            failures.append(f"policy_state_role_not_required:{sid}:{state.get('role_key')}")
        if str(state.get("kind") or "") not in required_kinds:
            failures.append(f"policy_state_kind_not_required:{sid}:{state.get('kind')}")
    terminal_ids = _policy_state_ids(policy)
    for terminal in _as_string_list(policy.get("required_terminal_states")):
        if terminal not in terminal_ids:
            failures.append(f"policy_terminal_state_missing:{terminal}")
    baton = policy.get("baton_requirements") if isinstance(policy.get("baton_requirements"), dict) else {}
    if baton.get("durable") is not True:
        failures.append("policy_baton_durable_not_required")
    if baton.get("sleep_wake") is not True:
        failures.append("policy_baton_sleep_wake_not_required")
    for field in ["id", "from_state", "to_state", "role_key", "payload", "handoff_reason", "resume_policy"]:
        if field not in _as_string_list(baton.get("required_fields")):
            failures.append(f"policy_baton_field_missing:{field}")
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


def _role_dependency_failures(payload: Dict[str, Any], *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    policy = _policy_dict(payload)
    failures: List[str] = []
    required_roles = set(_as_string_list(policy.get("required_roles")))
    role_kernel_ref = _resolve_ref(str(policy.get("role_kernel_policy_ref") or ""), project_root=project_root, package_root=package_root)
    roleflow_ref = _resolve_ref(str(policy.get("roleflow_policy_ref") or ""), project_root=project_root, package_root=package_root)
    if not role_kernel_ref.get("ok"):
        failures.append(f"role_kernel_policy_ref_missing:{policy.get('role_kernel_policy_ref')}")
        kernel_roles: Set[str] = set()
    else:
        kernel = load_policy(role_kernel_ref["path"])
        kpolicy = _policy_dict(kernel)
        defaults = kpolicy.get("default_roles") if isinstance(kpolicy.get("default_roles"), list) else []
        kernel_roles = {str(item.get("role_key") or "") for item in defaults if isinstance(item, dict)}
    for role in required_roles:
        if role not in kernel_roles:
            failures.append(f"role_kernel_default_role_missing:{role}")
    if not roleflow_ref.get("ok"):
        failures.append(f"roleflow_policy_ref_missing:{policy.get('roleflow_policy_ref')}")
    else:
        roleflow = load_policy(roleflow_ref["path"])
        rpolicy = _policy_dict(roleflow)
        approval_roles = set(_as_string_list(rpolicy.get("approval_roles")))
        for role in required_roles:
            if role not in approval_roles:
                failures.append(f"roleflow_approval_role_missing:{role}")
        features = set(_as_string_list(rpolicy.get("required_flow_features")))
        for feature in ["guard_edges", "approval_edges", "rollback_edges", "baton_payloads"]:
            if feature not in features:
                failures.append(f"roleflow_feature_missing:{feature}")
        node_kinds = set(_as_string_list(rpolicy.get("allowed_node_kinds")))
        for kind in ["guard", "approval", "rollback", "baton"]:
            if kind not in node_kinds:
                failures.append(f"roleflow_node_kind_missing:{kind}")
    return {"failures": failures, "role_kernel": role_kernel_ref, "roleflow": roleflow_ref}


def _docs_failures(payload: Dict[str, Any], *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    policy = _policy_dict(payload)
    phrase = str(policy.get("boundary_phrase") or "")
    blocked_claims = _as_string_list(policy.get("blocked_transition_claims"))
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
                item_failures.append(f"blocked_transition_claim:{claim}")
        if item_failures:
            failures.extend([f"doc_scan:{ref}:{failure}" for failure in item_failures])
        scan_reports.append({"ref": ref, "ok": not item_failures, "failures": item_failures})
    return {"failures": failures, "boundary_reports": boundary_reports, "scan_reports": scan_reports}


def _state_machine_failures(machine: Dict[str, Any], *, policy: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    states = machine.get("states") if isinstance(machine.get("states"), list) else []
    transitions = machine.get("transitions") if isinstance(machine.get("transitions"), list) else []
    batons = machine.get("batons") if isinstance(machine.get("batons"), list) else []
    state_by_id = {str(item.get("id") or ""): item for item in states if isinstance(item, dict)}
    if str(machine.get("start_state") or "") != "admin_intake":
        failures.append("machine_start_state_not_admin_intake")
    for state in policy.get("states", []):
        if isinstance(state, dict) and str(state.get("id") or "") not in state_by_id:
            failures.append(f"machine_state_missing:{state.get('id')}")
    required_roles = set(_as_string_list(policy.get("required_roles")))
    required_kinds = set(_as_string_list(policy.get("required_state_kinds")))
    for sid, state in state_by_id.items():
        if str(state.get("role_key") or "") not in required_roles:
            failures.append(f"machine_state_role_invalid:{sid}:{state.get('role_key')}")
        if str(state.get("kind") or "") not in required_kinds:
            failures.append(f"machine_state_kind_invalid:{sid}:{state.get('kind')}")
    for terminal in _as_string_list(policy.get("required_terminal_states")):
        if state_by_id.get(terminal, {}).get("kind") != "terminal":
            failures.append(f"machine_terminal_state_invalid:{terminal}")
    transition_by_key = {_transition_key(item): item for item in transitions if isinstance(item, dict)}
    for transition in transitions:
        if not isinstance(transition, dict):
            failures.append("machine_transition_invalid")
            continue
        if str(transition.get("from") or "") not in state_by_id:
            failures.append(f"machine_transition_from_missing:{transition.get('from')}")
        if str(transition.get("to") or "") not in state_by_id:
            failures.append(f"machine_transition_to_missing:{transition.get('to')}")
        kind = str(transition.get("kind") or "")
        if kind.startswith("guard") and not str(transition.get("condition") or ""):
            failures.append(f"machine_guard_condition_missing:{transition.get('from')}->{transition.get('to')}")
        if kind == "approval" and str(transition.get("approver_role") or "") != "operator.admin/administrator":
            failures.append(f"machine_admin_approval_missing:{transition.get('from')}->{transition.get('to')}")
        if kind == "rollback" and not str(transition.get("rollback_target") or ""):
            failures.append(f"machine_rollback_target_missing:{transition.get('from')}->{transition.get('to')}")
    for required in policy.get("mandatory_transitions", []):
        if not isinstance(required, dict):
            failures.append("policy_mandatory_transition_invalid")
            continue
        key = _transition_key(required)
        actual = transition_by_key.get(key)
        if not actual:
            failures.append(f"machine_mandatory_transition_missing:{key[0]}->{key[1]}:{key[2]}")
            continue
        if required.get("condition_required") is True and not str(actual.get("condition") or ""):
            failures.append(f"machine_required_condition_missing:{key[0]}->{key[1]}")
        expected_approver = str(required.get("approver_role") or "")
        if expected_approver and str(actual.get("approver_role") or "") != expected_approver:
            failures.append(f"machine_required_approver_missing:{key[0]}->{key[1]}:{expected_approver}")
        expected_rollback = str(required.get("rollback_target") or "")
        if expected_rollback and str(actual.get("rollback_target") or "") != expected_rollback:
            failures.append(f"machine_required_rollback_target_missing:{key[0]}->{key[1]}:{expected_rollback}")
    baton_req = policy.get("baton_requirements") if isinstance(policy.get("baton_requirements"), dict) else {}
    required_baton_fields = _as_string_list(baton_req.get("required_fields"))
    if not batons:
        failures.append("machine_baton_missing")
    for baton in batons:
        if not isinstance(baton, dict):
            failures.append("machine_baton_invalid")
            continue
        for field in required_baton_fields:
            if baton.get(field) in ("", None):
                failures.append(f"machine_baton_field_missing:{field}")
        if baton_req.get("durable") is True and baton.get("durable") is not True:
            failures.append(f"machine_baton_not_durable:{baton.get('id')}")
        if baton_req.get("sleep_wake") is True and baton.get("sleep_wake") is not True:
            failures.append(f"machine_baton_not_sleep_wake:{baton.get('id')}")
        if (baton.get("from_state"), baton.get("to_state")) != ("admin_decision", "surgeon_repair_plan"):
            failures.append(f"machine_baton_not_admin_to_surgeon:{baton.get('id')}")
    return failures


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
    blocked_claims = _as_string_list(policy.get("blocked_transition_claims"))
    for scenario in scenarios:
        sid = str(scenario.get("id") or "")
        local_failures: List[str] = []
        if not SAFE_ID_RE.match(sid):
            local_failures.append("scenario_id_invalid")
        if not str(scenario.get("trace_id") or "").startswith("trace:"):
            local_failures.append("scenario_trace_id_missing")
        machine = scenario.get("state_machine") if isinstance(scenario.get("state_machine"), dict) else {}
        local_failures.extend(_state_machine_failures(machine, policy=policy))
        trace = _as_string_list(scenario.get("accepted_trace"))
        if trace[:3] != ["admin_intake", "scary_risk_review", "admin_decision"]:
            local_failures.append("scenario_trace_does_not_start_admin_scary_admin")
        if "surgeon_repair_plan" not in trace or "admin_apply_approval" not in trace:
            local_failures.append("scenario_trace_missing_surgeon_or_final_admin")
        if trace and trace[-1] not in _as_string_list(policy.get("required_terminal_states")):
            local_failures.append(f"scenario_trace_terminal_invalid:{trace[-1]}")
        rejected = scenario.get("rejected_transitions") if isinstance(scenario.get("rejected_transitions"), list) else []
        if not rejected:
            local_failures.append("scenario_rejected_transitions_empty")
        for transition in rejected:
            if not isinstance(transition, dict):
                local_failures.append("scenario_rejected_transition_invalid")
                continue
            claim = str(transition.get("claim") or "")
            if not any(_contains(claim, blocked) for blocked in blocked_claims):
                local_failures.append(f"scenario_rejected_claim_not_blocked:{claim}")
            if not str(transition.get("reason") or ""):
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


def validate_role_review_state_machine_policy(
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
    role_report = _role_dependency_failures(payload, project_root=project, package_root=package)
    failures.extend(role_report["failures"])
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
        "required_roles": len(_as_string_list(policy.get("required_roles"))),
        "states": len(policy.get("states") if isinstance(policy.get("states"), list) else []),
        "mandatory_transitions": len(policy.get("mandatory_transitions") if isinstance(policy.get("mandatory_transitions"), list) else []),
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
        "roles": role_report,
        "docs": docs_report,
        "examples": example_reports,
    }


def role_review_state_machine_report_to_gate_evidence(report: Dict[str, Any], *, artifact_uri: str = "") -> Dict[str, Any]:
    status = "pass" if report.get("ok") else "fail"
    return {
        "artifact_uri": artifact_uri,
        "run_at": report.get("validated_at") or _nowz(),
        "checks": [
            {"id": "pipeline_eval", "status": status, "score": 1.0 if status == "pass" else 0.0, "threshold": 1.0},
            {"id": "rollback_plan", "status": "pass", "score": 1.0, "threshold": 1.0},
        ],
        "details": {"id": report.get("id"), "version": report.get("version"), "metrics": report.get("metrics", {}), "failures": report.get("failures", [])},
    }


def build_summary(report: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "apiVersion": API_VERSION,
        "kind": "RoleReviewStateMachineValidationSummary",
        "ok": bool(report.get("ok")),
        "id": report.get("id"),
        "version": report.get("version"),
        "metrics": report.get("metrics", {}),
        "failures": report.get("failures", []),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate NoemaForge Admin/Surgeon/Scary state-machine contract")
    parser.add_argument("--policy", default=str(SRC_DIR.parent / "configs" / "role-review-state-machine-policy.json"))
    parser.add_argument("--project-root", default=str(SRC_DIR.parent.parent))
    parser.add_argument("--package-root", default=str(SRC_DIR.parent))
    parser.add_argument("--registry", default="")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = validate_role_review_state_machine_policy(
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
