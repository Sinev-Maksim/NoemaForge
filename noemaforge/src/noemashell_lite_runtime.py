#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/noemashell_lite_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate NoemaShell Lite as the primary operator shell contract.
Inputs: noemaforge/configs/noemashell-lite-policy.json and NoemaShell Lite examples.
Outputs: JSON-compatible NoemaShellLiteValidationReport artifacts.
Side effects: None unless run as a CLI, which writes JSON to stdout.
Tests: noemaforge/tests/test_noemashell_lite_runtime.py
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


API_VERSION = "noemaforge.noemashell/v1"
POLICY_KIND = "NoemaShellLitePolicy"
SET_KIND = "NoemaShellLiteSessionSet"
SESSION_KIND = "NoemaShellLiteSession"
REPORT_KIND = "NoemaShellLiteValidationReport"

VALID_POLICY_STATUSES = {"draft", "shadow", "stable", "retired"}
VALID_SESSION_STATUSES = {"draft", "ready", "blocked", "retired"}
REQUIRED_SURFACES = {"active_worker", "approvals", "artifacts", "resource_budgets", "safe_mode", "recovery"}
REQUIRED_CONTROLS = {"pause", "resume", "stop", "approve", "reject", "recover", "open_artifact", "switch_role"}
REQUIRED_LAUNCH_MODES = {"normal_window", "minimal_graphical_session", "local_app_mode"}
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


def _role_kernel_role_keys(role_kernel_payload: Dict[str, Any]) -> Set[str]:
    policy = role_kernel_payload.get("policy") if isinstance(role_kernel_payload.get("policy"), dict) else {}
    roles = policy.get("default_roles") if isinstance(policy.get("default_roles"), list) else []
    return {str(item.get("role_key") or "") for item in roles if isinstance(item, dict) and str(item.get("role_key") or "")}


def _roleflow_ids(roleflow_set: Dict[str, Any]) -> Set[str]:
    flows = roleflow_set.get("flows") if isinstance(roleflow_set.get("flows"), list) else []
    return {str(item.get("id") or "") for item in flows if isinstance(item, dict) and str(item.get("id") or "")}


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
    if str(policy.get("activation_state") or "") != "primary_operator_shell":
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
    for key in ["role_kernel_policy_ref", "roleflow_policy_ref", "gui_shell_policy_ref"]:
        if not _is_safe_relative_ref(str(policy.get(key) or "")):
            failures.append(f"policy_{key}_invalid")
    if not REQUIRED_LAUNCH_MODES.issubset(set(_as_string_list(policy.get("launch_modes")))):
        failures.append("policy_launch_modes_missing")
    if not REQUIRED_SURFACES.issubset(set(_as_string_list(policy.get("primary_surfaces")))):
        failures.append("policy_primary_surfaces_missing")
    if not REQUIRED_CONTROLS.issubset(set(_as_string_list(policy.get("operator_controls")))):
        failures.append("policy_operator_controls_missing")

    safety = policy.get("safety_defaults") if isinstance(policy.get("safety_defaults"), dict) else {}
    for key in [
        "no_hidden_privileged_action",
        "no_heavy_backend_autostart",
        "explicit_approval_required",
        "visible_reason_required",
        "no_destructive_action_without_policy",
    ]:
        if safety.get(key) is not True:
            failures.append(f"policy_safety_{key}_not_true")

    profiles = policy.get("resource_budget_profiles") if isinstance(policy.get("resource_budget_profiles"), list) else []
    if not profiles:
        failures.append("policy_resource_budget_profiles_empty")
    profile_ids: Set[str] = set()
    for profile in profiles:
        if not isinstance(profile, dict):
            failures.append("policy_resource_budget_profile_not_object")
            continue
        profile_id = str(profile.get("id") or "")
        if not SAFE_ID_RE.match(profile_id):
            failures.append(f"policy_resource_budget_profile_id_invalid:{profile_id}")
        if profile_id in profile_ids:
            failures.append(f"policy_resource_budget_profile_duplicate:{profile_id}")
        profile_ids.add(profile_id)
        if profile.get("max_active_heavy_workers") != 1:
            failures.append(f"policy_profile_max_heavy_invalid:{profile_id}")
        if profile.get("heavy_backend_autostart") is not False:
            failures.append(f"policy_profile_heavy_autostart_allowed:{profile_id}")
        if profile.get("requires_operator_confirmation") is not True:
            failures.append(f"policy_profile_confirmation_not_required:{profile_id}")
    if not _as_string_list(policy.get("required_example_sets")):
        failures.append("policy_required_example_sets_empty")
    return failures


def _dependency_failures(policy: Dict[str, Any], *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    failures: List[str] = []
    role_kernel_keys: Set[str] = set()
    roleflow_ids: Set[str] = set()
    for key, api_version, kind in [
        ("role_kernel_policy_ref", "noemaforge.role-kernel/v1", "RoleKernelPolicy"),
        ("roleflow_policy_ref", "noemaforge.roleflow/v1", "RoleFlowPolicy"),
    ]:
        ref = str(policy.get(key) or "")
        resolved = _resolve_ref(ref, project_root=project_root, package_root=package_root)
        if not resolved["ok"]:
            failures.append(f"{key}_missing:{ref}")
            continue
        payload = json.loads(Path(resolved["path"]).read_text(encoding="utf-8"))
        if payload.get("apiVersion") != api_version:
            failures.append(f"{key}_api_version_invalid:{ref}")
        if payload.get("kind") != kind:
            failures.append(f"{key}_kind_invalid:{ref}")
        if key == "role_kernel_policy_ref":
            role_kernel_keys = _role_kernel_role_keys(payload)

    gui_ref = str(policy.get("gui_shell_policy_ref") or "")
    gui_resolved = _resolve_ref(gui_ref, project_root=project_root, package_root=package_root)
    if not gui_resolved["ok"]:
        failures.append(f"gui_shell_policy_missing:{gui_ref}")
    else:
        gui_policy = json.loads(Path(gui_resolved["path"]).read_text(encoding="utf-8"))
        if gui_policy.get("apiVersion") != "noemaforge.gui/v1" or gui_policy.get("kind") != "GuiShellPolicy":
            failures.append(f"gui_shell_policy_invalid:{gui_ref}")
        if gui_policy.get("stateful") is not True:
            failures.append(f"gui_shell_policy_not_stateful:{gui_ref}")
        rules = _as_string_list(gui_policy.get("gui_rules"))
        for required in ["no hidden privileged action", "persist messages", "restore state after refresh"]:
            if required not in rules:
                failures.append(f"gui_shell_policy_rule_missing:{required}")

    roleflow_example = _resolve_ref("prelaunch/governance/roleflow_orchestration.example.json", project_root=project_root, package_root=package_root)
    if roleflow_example["ok"]:
        roleflow_ids = _roleflow_ids(json.loads(Path(roleflow_example["path"]).read_text(encoding="utf-8")))
    else:
        failures.append("roleflow_example_missing:prelaunch/governance/roleflow_orchestration.example.json")
    if not role_kernel_keys:
        failures.append("role_kernel_default_roles_empty")
    if not roleflow_ids:
        failures.append("roleflow_ids_empty")
    return {"failures": failures, "role_kernel_keys": role_kernel_keys, "roleflow_ids": roleflow_ids}


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
        for ref in ["configs/noemashell-lite-policy.json", "contracts/noemashell_lite.schema.json", "src/noemashell_lite_runtime.py"]:
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
    for ref in ["configs/noemashell-lite-policy.json", "src/noemashell_lite_runtime.py", "prelaunch/governance/noemashell_lite.example.json"]:
        if ref not in pipeline_refs:
            failures.append(f"registry_pipeline_ref_missing:{ref}")
    return {"failures": failures, "registry_report": report, "entries": entries, "pipeline_eval_refs": pipeline_eval_refs}


def _session_failures(session: Dict[str, Any], policy_payload: Dict[str, Any], *, role_keys: Set[str], roleflow_ids: Set[str]) -> List[str]:
    policy = _policy_dict(policy_payload)
    failures: List[str] = []
    session_id = str(session.get("id") or "<missing>")
    profile_ids = {str(item.get("id") or "") for item in policy.get("resource_budget_profiles", []) if isinstance(item, dict)}
    controls_required = set(_as_string_list(policy.get("operator_controls")))
    launch_modes = set(_as_string_list(policy.get("launch_modes")))

    if session.get("apiVersion") != API_VERSION:
        failures.append(f"session_api_version_invalid:{session_id}")
    if session.get("kind") != SESSION_KIND:
        failures.append(f"session_kind_invalid:{session_id}")
    if not SAFE_ID_RE.match(session_id):
        failures.append(f"session_id_invalid:{session_id}")
    if policy.get("require_trace_id") is True and not SAFE_ID_RE.match(str(session.get("trace_id") or "")):
        failures.append(f"session_trace_id_invalid:{session_id}")
    if str(session.get("status") or "") not in VALID_SESSION_STATUSES:
        failures.append(f"session_status_invalid:{session_id}:{session.get('status')}")
    if str(session.get("launch_mode") or "") not in launch_modes:
        failures.append(f"session_launch_mode_invalid:{session_id}:{session.get('launch_mode')}")

    surfaces = session.get("surfaces") if isinstance(session.get("surfaces"), dict) else {}
    if not REQUIRED_SURFACES.issubset(set(surfaces)):
        failures.append(f"session_surfaces_missing:{session_id}")
    active_worker = surfaces.get("active_worker") if isinstance(surfaces.get("active_worker"), dict) else {}
    role_key = str(active_worker.get("role_key") or "")
    if role_key not in role_keys:
        failures.append(f"session_active_worker_role_invalid:{session_id}:{role_key}")
    if str(active_worker.get("worker_slot") or "") not in {"awake", "sleeping"}:
        failures.append(f"session_active_worker_slot_invalid:{session_id}:{active_worker.get('worker_slot')}")
    if str(active_worker.get("flow_ref") or "") not in roleflow_ids:
        failures.append(f"session_active_worker_flow_invalid:{session_id}:{active_worker.get('flow_ref')}")
    if not SAFE_ID_RE.match(str(active_worker.get("baton_id") or "")):
        failures.append(f"session_active_worker_baton_invalid:{session_id}:{active_worker.get('baton_id')}")

    approvals = surfaces.get("approvals") if isinstance(surfaces.get("approvals"), list) else []
    if not approvals:
        failures.append(f"session_approvals_empty:{session_id}")
    for approval in approvals:
        if not isinstance(approval, dict):
            failures.append(f"session_approval_not_object:{session_id}")
            continue
        approval_id = str(approval.get("id") or "")
        if not SAFE_ID_RE.match(approval_id):
            failures.append(f"session_approval_id_invalid:{session_id}:{approval_id}")
        if str(approval.get("approver_role") or "") not in role_keys:
            failures.append(f"session_approval_role_invalid:{session_id}:{approval_id}:{approval.get('approver_role')}")
        if not str(approval.get("visible_reason") or "").strip():
            failures.append(f"session_approval_visible_reason_missing:{session_id}:{approval_id}")
        if not SAFE_ID_RE.match(str(approval.get("trace_id") or "")):
            failures.append(f"session_approval_trace_id_invalid:{session_id}:{approval_id}")

    artifacts = surfaces.get("artifacts") if isinstance(surfaces.get("artifacts"), list) else []
    if not artifacts:
        failures.append(f"session_artifacts_empty:{session_id}")
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            failures.append(f"session_artifact_not_object:{session_id}")
            continue
        artifact_id = str(artifact.get("id") or "")
        if not SAFE_ID_RE.match(artifact_id):
            failures.append(f"session_artifact_id_invalid:{session_id}:{artifact_id}")
        path = str(artifact.get("path") or "")
        if not _is_safe_relative_ref(path):
            failures.append(f"session_artifact_path_invalid:{session_id}:{artifact_id}:{path}")
        for key in ["type", "provenance", "retention"]:
            if not str(artifact.get(key) or "").strip():
                failures.append(f"session_artifact_{key}_missing:{session_id}:{artifact_id}")

    budgets = surfaces.get("resource_budgets") if isinstance(surfaces.get("resource_budgets"), dict) else {}
    profile_id = str(budgets.get("profile_id") or "")
    if profile_id not in profile_ids:
        failures.append(f"session_budget_profile_invalid:{session_id}:{profile_id}")
    if budgets.get("max_active_heavy_workers") != 1:
        failures.append(f"session_budget_max_heavy_invalid:{session_id}:{budgets.get('max_active_heavy_workers')}")
    if budgets.get("heavy_backend_autostart") is not False:
        failures.append(f"session_budget_heavy_autostart_allowed:{session_id}")
    if budgets.get("requires_operator_confirmation") is not True:
        failures.append(f"session_budget_confirmation_not_required:{session_id}")
    if not str(budgets.get("visible_reason") or "").strip():
        failures.append(f"session_budget_visible_reason_missing:{session_id}")

    for surface_key in ["safe_mode", "recovery"]:
        surface = surfaces.get(surface_key) if isinstance(surfaces.get(surface_key), dict) else {}
        if surface.get("enabled") is not True:
            failures.append(f"session_{surface_key}_not_enabled:{session_id}")
        if not str(surface.get("entry_command") or "").startswith("noemaforge "):
            failures.append(f"session_{surface_key}_entry_command_invalid:{session_id}:{surface.get('entry_command')}")
        if not str(surface.get("visible_reason") or "").strip():
            failures.append(f"session_{surface_key}_visible_reason_missing:{session_id}")

    controls = set(_as_string_list(session.get("operator_controls")))
    if not controls_required.issubset(controls):
        failures.append(f"session_operator_controls_missing:{session_id}")
    privileged_actions = session.get("privileged_actions") if isinstance(session.get("privileged_actions"), list) else []
    for action in privileged_actions:
        if not isinstance(action, dict):
            failures.append(f"session_privileged_action_not_object:{session_id}")
            continue
        action_id = str(action.get("id") or "")
        if not SAFE_ID_RE.match(action_id):
            failures.append(f"session_privileged_action_id_invalid:{session_id}:{action_id}")
        if action.get("requires_approval") is not True:
            failures.append(f"session_privileged_action_approval_missing:{session_id}:{action_id}")
        if not str(action.get("visible_reason") or "").strip():
            failures.append(f"session_privileged_action_visible_reason_missing:{session_id}:{action_id}")
    return failures


def validate_noemashell_policy(
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
    dependency_result = _dependency_failures(policy, project_root=project, package_root=package)
    failures.extend(dependency_result["failures"])
    registry_result = _registry_failures(payload, project_root=project, package_root=package, registry_path=registry)
    failures.extend(registry_result["failures"])

    all_resolved_refs: List[Dict[str, Any]] = []
    all_missing_refs: List[Dict[str, Any]] = []
    all_unsafe_refs: List[Dict[str, Any]] = []
    session_results: List[Dict[str, Any]] = []

    refs_to_resolve = _as_string_list(payload.get("refs"))
    refs_to_resolve.extend(
        [
            str(policy.get("role_kernel_policy_ref") or ""),
            str(policy.get("roleflow_policy_ref") or ""),
            str(policy.get("gui_shell_policy_ref") or ""),
        ]
    )
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

    role_keys = dependency_result["role_kernel_keys"]
    roleflow_ids = dependency_result["roleflow_ids"]
    for item in example_ref_results["resolved_refs"]:
        example_set = load_example_set(Path(item["path"]))
        if example_set.get("apiVersion") != API_VERSION:
            failures.append(f"example_set_api_version_invalid:{item['ref']}")
        if example_set.get("kind") != SET_KIND:
            failures.append(f"example_set_kind_invalid:{item['ref']}")
        sessions = example_set.get("sessions") if isinstance(example_set.get("sessions"), list) else []
        if not sessions:
            failures.append(f"example_set_sessions_empty:{item['ref']}")
        for session in sessions:
            if not isinstance(session, dict):
                failures.append(f"session_not_object:{item['ref']}")
                continue
            session_id = str(session.get("id") or "<missing>")
            session_failures = _session_failures(session, payload, role_keys=role_keys, roleflow_ids=roleflow_ids)
            session_ref_result = _resolve_refs(_as_string_list(session.get("refs")), project_root=project, package_root=package, owner=session_id)
            session_failures.extend(session_ref_result["failures"])
            failures.extend(session_failures)
            all_resolved_refs.extend(session_ref_result["resolved_refs"])
            all_missing_refs.extend(session_ref_result["missing_refs"])
            all_unsafe_refs.extend(session_ref_result["unsafe_refs"])
            surfaces = session.get("surfaces") if isinstance(session.get("surfaces"), dict) else {}
            session_results.append(
                {
                    "id": session_id,
                    "ok": not session_failures,
                    "surfaces": len(set(surfaces)),
                    "approvals": len(surfaces.get("approvals", [])) if isinstance(surfaces.get("approvals"), list) else 0,
                    "artifacts": len(surfaces.get("artifacts", [])) if isinstance(surfaces.get("artifacts"), list) else 0,
                    "failures": sorted(set(session_failures)),
                }
            )

    checks = [
        {"id": "active_worker", "status": "passed" if not any("active_worker" in item for item in failures) else "failed"},
        {"id": "approvals", "status": "passed" if not any("approval" in item for item in failures) else "failed"},
        {"id": "artifacts", "status": "passed" if not any("artifact" in item for item in failures) else "failed"},
        {"id": "resource_budgets", "status": "passed" if not any("budget" in item or "profile" in item for item in failures) else "failed"},
        {"id": "safe_mode", "status": "passed" if not any("safe_mode" in item for item in failures) else "failed"},
        {"id": "recovery", "status": "passed" if not any("recovery" in item for item in failures) else "failed"},
        {"id": "refs_resolved", "status": "passed" if not all_missing_refs and not all_unsafe_refs else "failed"},
    ]
    metrics = {
        "sessions": len(session_results),
        "passing_sessions": sum(1 for item in session_results if item["ok"]),
        "required_surfaces": len(REQUIRED_SURFACES),
        "operator_controls": len(set(_as_string_list(policy.get("operator_controls")))),
        "budget_profiles": len(policy.get("resource_budget_profiles", [])) if isinstance(policy.get("resource_budget_profiles"), list) else 0,
        "role_kernel_roles": len(role_keys),
        "roleflow_ids": len(roleflow_ids),
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
        "session_results": sorted(session_results, key=lambda item: item["id"]),
        "resolved_refs": sorted(all_resolved_refs, key=lambda item: (item["owner"], item["ref"])),
        "missing_refs": sorted(all_missing_refs, key=lambda item: (item["owner"], item["ref"])),
        "unsafe_refs": sorted(all_unsafe_refs, key=lambda item: (item["owner"], item["ref"])),
    }


def noemashell_report_to_gate_evidence(report: Dict[str, Any], *, artifact_uri: str = "") -> Dict[str, Any]:
    if not isinstance(report, dict) or report.get("kind") != REPORT_KIND:
        raise ValueError("noemashell_report_required")
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
    parser = argparse.ArgumentParser(description="Validate NoemaShell Lite operator-shell contracts.")
    parser.add_argument("--project-root", default=str(_default_project_root()), help="Project root containing noemaforge/ and docs/.")
    parser.add_argument("--package-root", default="", help="Package root, default: <project-root>/noemaforge.")
    parser.add_argument(
        "--policy",
        default="noemaforge/configs/noemashell-lite-policy.json",
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

    report = validate_noemashell_policy(
        load_policy(policy_path),
        project_root=project_root,
        package_root=package_root,
        policy_path=policy_path,
        registry_path=registry_path,
    )
    if args.summary:
        payload: Dict[str, Any] = {
            "apiVersion": report["apiVersion"],
            "kind": "NoemaShellLiteValidationSummary",
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
