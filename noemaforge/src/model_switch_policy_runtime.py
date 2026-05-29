#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/model_switch_policy_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-21
Modified: 2026-05-21
Purpose: Validate role-driven model switch policy and fallback decisions.
Inputs: Model switch policy, schema, example inventory and local registry refs.
Outputs: JSON-compatible ModelSwitchPolicyValidationReport artifacts.
Side effects: None; CLI writes JSON to stdout.
Tests: noemaforge/tests/test_model_switch_policy_runtime.py, QA and performance tests.
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
from typing import Any, Dict, List, Optional, Sequence


API_VERSION = "noemaforge.model-switch-policy/v1"
POLICY_KIND = "ModelSwitchPolicy"
EXAMPLE_KIND = "ModelSwitchPolicyExampleSet"
REPORT_KIND = "ModelSwitchPolicyValidationReport"
POLICY_ID = "model-switch-policy-core"
PRIMARY_TODO = "Add model switch policy: role -> preferred local/remote model -> fallback."

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = PACKAGE_ROOT.parent
DEFAULT_POLICY = PACKAGE_ROOT / "configs" / "model-switch-policy.json"
DEFAULT_EXAMPLE = PROJECT_ROOT / "prelaunch" / "governance" / "model_switch_policy.example.json"

VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
HEALTHY_STATES = {"pass", "ok", "healthy"}
AVAILABLE_STATES = {"available", "ready", "staged"}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,220}$")
MODEL_ID_RE = re.compile(r"^(local|remote):[A-Za-z0-9_.:/-]{1,180}$")

REQUIRED_ROLE_FIELDS = [
    "role",
    "preferred_local_models",
    "preferred_remote_models",
    "fallback_models",
    "allow_remote",
    "default_when_unavailable",
]
REQUIRED_CANDIDATE_FIELDS = ["model_id", "backend", "status", "health", "approved"]
REQUIRED_CONTROLS = [
    "local_first",
    "remote_requires_explicit_approval",
    "remote_disabled_by_default",
    "failed_or_unhealthy_models_blocked",
    "silent_fallback_blocked",
    "na_when_no_candidate",
]
EXPECTED_CANDIDATE_ORDER = [
    "preferred_local_models",
    "preferred_remote_models_when_approved",
    "fallback_models",
    "default_when_unavailable",
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
    missing_refs: List[Dict[str, Any]] = []
    unsafe_refs: List[Dict[str, Any]] = []
    for ref in refs:
        if not _is_safe_relative_ref(ref):
            failures.append(f"unsafe_ref:{owner}:{ref}")
            unsafe_refs.append({"owner": owner, "ref": ref})
            continue
        resolved = _resolve_ref(ref, project_root=project_root, package_root=package_root)
        resolved["owner"] = owner
        if resolved["ok"]:
            resolved_refs.append(resolved)
        else:
            failures.append(f"missing_ref:{owner}:{ref}")
            missing_refs.append(resolved)
    return {"failures": failures, "resolved_refs": resolved_refs, "missing_refs": missing_refs, "unsafe_refs": unsafe_refs}


def load_policy(policy_path: Path | str = DEFAULT_POLICY) -> Dict[str, Any]:
    return json.loads(Path(policy_path).read_text(encoding="utf-8"))


def load_example(example_path: Path | str = DEFAULT_EXAMPLE) -> Dict[str, Any]:
    return json.loads(Path(example_path).read_text(encoding="utf-8"))


def _role_index(policy_payload: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    policy = _policy_dict(policy_payload)
    roles = policy.get("roles") if isinstance(policy.get("roles"), list) else []
    return {str(item.get("role") or "").strip(): item for item in roles if isinstance(item, dict)}


def _inventory_index(inventory: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {str(item.get("model_id") or "").strip(): item for item in inventory if isinstance(item, dict)}


def _candidate_is_usable(candidate: Optional[Dict[str, Any]], *, remote_approved: bool) -> tuple[bool, str]:
    if not candidate:
        return False, "missing"
    model_id = str(candidate.get("model_id") or "")
    backend = str(candidate.get("backend") or "")
    if backend not in {"local", "remote"}:
        return False, "invalid_backend"
    if backend == "remote" and not remote_approved:
        return False, "remote_requires_approval"
    if not model_id.startswith(f"{backend}:"):
        return False, "model_backend_mismatch"
    if str(candidate.get("status") or "") not in AVAILABLE_STATES:
        return False, "status_not_available"
    if str(candidate.get("health") or "") not in HEALTHY_STATES:
        return False, "health_not_pass"
    if candidate.get("approved") is not True:
        return False, "not_approved"
    return True, "usable"


def resolve_model_switch(
    policy_payload: Dict[str, Any],
    role: str,
    inventory: Sequence[Dict[str, Any]],
    *,
    remote_approved: bool = False,
) -> Dict[str, Any]:
    role_name = str(role or "").strip()
    roles = _role_index(policy_payload)
    role_config = roles.get(role_name)
    checked: List[Dict[str, str]] = []
    if not role_config:
        return {
            "role": role_name,
            "decision": "role_unmapped",
            "selected_model_id": "N/A",
            "selected_source": "default_when_unavailable",
            "remote_approved": bool(remote_approved),
            "checked_candidates": checked,
        }

    inventory_by_id = _inventory_index(inventory)
    groups = [
        ("preferred_local_models", _as_string_list(role_config.get("preferred_local_models"))),
        ("preferred_remote_models", _as_string_list(role_config.get("preferred_remote_models"))),
        ("fallback_models", _as_string_list(role_config.get("fallback_models"))),
    ]
    for source, model_ids in groups:
        if source == "preferred_remote_models" and not bool(role_config.get("allow_remote")):
            for model_id in model_ids:
                checked.append({"model_id": model_id, "source": source, "status": "remote_not_allowed_for_role"})
            continue
        for model_id in model_ids:
            candidate = inventory_by_id.get(model_id)
            usable, reason = _candidate_is_usable(candidate, remote_approved=remote_approved)
            checked.append({"model_id": model_id, "source": source, "status": reason})
            if usable:
                return {
                    "role": role_name,
                    "decision": "selected",
                    "selected_model_id": model_id,
                    "selected_source": source,
                    "remote_approved": bool(remote_approved),
                    "checked_candidates": checked,
                }

    return {
        "role": role_name,
        "decision": "no_candidate",
        "selected_model_id": str(role_config.get("default_when_unavailable") or "N/A"),
        "selected_source": "default_when_unavailable",
        "remote_approved": bool(remote_approved),
        "checked_candidates": checked,
    }


def _policy_failures(payload: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    policy = _policy_dict(payload)
    if payload.get("apiVersion") != API_VERSION:
        failures.append("policy_api_version_invalid")
    if payload.get("kind") != POLICY_KIND:
        failures.append("policy_kind_invalid")
    if payload.get("id") != POLICY_ID:
        failures.append("policy_id_invalid")
    if str(payload.get("status") or "") not in VALID_STATUSES:
        failures.append("policy_status_invalid")
    if str(policy.get("mode") or "") != "offline_contract":
        failures.append("policy_mode_not_offline_contract")
    if str(policy.get("activation_state") or "") != "role_preferred_model_switch_with_fallback":
        failures.append("policy_activation_state_invalid")
    if str(policy.get("required_pipeline_ref") or "") != "pipeline:firstboot-model-selection:0.32.1":
        failures.append("policy_required_pipeline_ref_invalid")
    if PRIMARY_TODO not in _as_string_list(policy.get("closed_todo_refs")):
        failures.append("policy_closed_todo_ref_missing")
    for key in ["require_registry_attachment", "require_docs_and_changelog_refs", "require_no_live_backend_dependency"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    controls = policy.get("controls") if isinstance(policy.get("controls"), dict) else {}
    for key in REQUIRED_CONTROLS:
        if controls.get(key) is not True:
            failures.append(f"control_{key}_not_true")
    if int(controls.get("max_active_heavy_workers") or 0) > 1:
        failures.append("control_max_active_heavy_workers_gt_one")
    if str(controls.get("applies_on") or "") != "next_persona_or_model_switch_or_backend_restart":
        failures.append("control_applies_on_invalid")
    if _as_string_list(policy.get("required_role_fields")) != REQUIRED_ROLE_FIELDS:
        failures.append("policy_required_role_fields_invalid")
    if _as_string_list(policy.get("required_candidate_fields")) != REQUIRED_CANDIDATE_FIELDS:
        failures.append("policy_required_candidate_fields_invalid")
    if _as_string_list(policy.get("candidate_order")) != EXPECTED_CANDIDATE_ORDER:
        failures.append("policy_candidate_order_invalid")
    roles = policy.get("roles") if isinstance(policy.get("roles"), list) else []
    if len(roles) < 4:
        failures.append("policy_roles_too_few")
    seen_roles: set[str] = set()
    for index, role_config in enumerate(roles):
        if not isinstance(role_config, dict):
            failures.append(f"role_not_object:{index}")
            continue
        role_name = str(role_config.get("role") or "")
        if not SAFE_ID_RE.match(role_name):
            failures.append(f"role_invalid:{index}")
        if role_name in seen_roles:
            failures.append(f"role_duplicate:{role_name}")
        seen_roles.add(role_name)
        for field in REQUIRED_ROLE_FIELDS:
            if field not in role_config:
                failures.append(f"role_field_missing:{role_name}:{field}")
        for model_id in _as_string_list(role_config.get("preferred_local_models")):
            if not model_id.startswith("local:") or not MODEL_ID_RE.match(model_id):
                failures.append(f"role_local_model_invalid:{role_name}:{model_id}")
        remote_ids = _as_string_list(role_config.get("preferred_remote_models"))
        for model_id in remote_ids:
            if not model_id.startswith("remote:") or not MODEL_ID_RE.match(model_id):
                failures.append(f"role_remote_model_invalid:{role_name}:{model_id}")
        if remote_ids and role_config.get("allow_remote") is not True:
            failures.append(f"role_remote_pref_without_allow_remote:{role_name}")
        if str(role_config.get("default_when_unavailable") or "") != "N/A":
            failures.append(f"role_default_not_na:{role_name}")
    if not {"administrator", "surgeon", "scary"}.issubset(seen_roles):
        failures.append("policy_core_roles_missing")
    if not _as_string_list(policy.get("required_outputs")):
        failures.append("policy_required_outputs_empty")
    if not _as_string_list(policy.get("required_refs")):
        failures.append("policy_required_refs_empty")
    return failures


def _example_failures(policy_payload: Dict[str, Any], example: Dict[str, Any]) -> Dict[str, Any]:
    failures: List[str] = []
    decisions: List[Dict[str, Any]] = []
    if example.get("apiVersion") != API_VERSION:
        failures.append("example_api_version_invalid")
    if example.get("kind") != EXAMPLE_KIND:
        failures.append("example_kind_invalid")
    inventory = example.get("model_inventory") if isinstance(example.get("model_inventory"), list) else []
    cases = example.get("cases") if isinstance(example.get("cases"), list) else []
    if not inventory:
        failures.append("example_inventory_empty")
    if not cases:
        failures.append("example_cases_empty")
    for item in inventory:
        if not isinstance(item, dict):
            failures.append("example_inventory_item_not_object")
            continue
        for field in REQUIRED_CANDIDATE_FIELDS:
            if field not in item:
                failures.append(f"example_candidate_field_missing:{field}")
        model_id = str(item.get("model_id") or "")
        if not MODEL_ID_RE.match(model_id):
            failures.append(f"example_candidate_model_id_invalid:{model_id}")
    for case in cases:
        if not isinstance(case, dict):
            failures.append("example_case_not_object")
            continue
        decision = resolve_model_switch(
            policy_payload,
            str(case.get("role") or ""),
            inventory,
            remote_approved=bool(case.get("remote_approved")),
        )
        decisions.append(decision)
        if decision["selected_model_id"] != str(case.get("expected_model_id") or ""):
            failures.append(f"example_expected_model_mismatch:{case.get('role')}")
        if decision["decision"] != str(case.get("expected_decision") or ""):
            failures.append(f"example_expected_decision_mismatch:{case.get('role')}")
    return {"failures": failures, "decisions": decisions}


def validate_model_switch_policy(
    policy_payload: Dict[str, Any],
    *,
    project_root: Path | str = PROJECT_ROOT,
    package_root: Path | str = PACKAGE_ROOT,
    example_path: Path | str = DEFAULT_EXAMPLE,
) -> Dict[str, Any]:
    project = Path(project_root).resolve()
    package = Path(package_root).resolve()
    failures: List[str] = []
    failures.extend(_policy_failures(policy_payload))

    policy = _policy_dict(policy_payload)
    refs = _as_string_list(policy_payload.get("refs")) + _as_string_list(policy.get("required_refs"))
    ref_report = _resolve_refs(refs, project_root=project, package_root=package, owner=POLICY_ID)
    failures.extend(ref_report["failures"])

    example = load_example(example_path)
    example_report = _example_failures(policy_payload, example)
    failures.extend(example_report["failures"])

    roles = _role_index(policy_payload)
    remote_enabled_roles = [name for name, item in sorted(roles.items()) if item.get("allow_remote") is True]
    return {
        "apiVersion": API_VERSION,
        "kind": REPORT_KIND,
        "ok": not failures,
        "created_at": _nowz(),
        "id": POLICY_ID,
        "failures": sorted(failures),
        "model_switch_policy_summary": {
            "role_count": len(roles),
            "remote_enabled_role_count": len(remote_enabled_roles),
            "local_first": policy.get("controls", {}).get("local_first") is True,
            "remote_requires_explicit_approval": policy.get("controls", {}).get("remote_requires_explicit_approval") is True,
            "silent_fallback_blocked": policy.get("controls", {}).get("silent_fallback_blocked") is True,
            "na_when_no_candidate": policy.get("controls", {}).get("na_when_no_candidate") is True,
            "example_case_count": len(example.get("cases") or []),
        },
        "role_resolution_matrix": example_report["decisions"],
        "resolved_refs": ref_report["resolved_refs"],
        "missing_refs": ref_report["missing_refs"],
        "unsafe_refs": ref_report["unsafe_refs"],
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate NoemaForge role-driven model switch policy.")
    parser.add_argument("--policy", default=str(DEFAULT_POLICY), help="Policy JSON path.")
    parser.add_argument("--example", default=str(DEFAULT_EXAMPLE), help="Example set JSON path.")
    parser.add_argument("--summary", action="store_true", help="Emit compact summary.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    report = validate_model_switch_policy(load_policy(args.policy), example_path=args.example)
    payload: Dict[str, Any]
    if args.summary:
        payload = {
            "apiVersion": API_VERSION,
            "kind": "ModelSwitchPolicySummary",
            "id": POLICY_ID,
            "ok": report["ok"],
            "failures": report["failures"],
            "metrics": report["model_switch_policy_summary"],
        }
    else:
        payload = report
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
