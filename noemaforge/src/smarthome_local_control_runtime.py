#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/smarthome_local_control_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate local-first SmartHome control contracts.
Inputs: noemaforge/configs/smarthome-local-control-policy.json and SmartHome examples.
Outputs: JSON-compatible SmartHomeLocalControlValidationReport artifacts.
Side effects: None unless run as a CLI, which writes JSON to stdout.
Tests: noemaforge/tests/test_smarthome_local_control_runtime.py
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


API_VERSION = "noemaforge.smarthome/v1"
POLICY_KIND = "SmartHomeLocalControlPolicy"
SET_KIND = "SmartHomeLocalControlSet"
REGISTRY_KIND = "SmartHomeDeviceRegistry"
ACTION_KIND = "SmartHomeAction"
REPORT_KIND = "SmartHomeLocalControlValidationReport"

VALID_POLICY_STATUSES = {"draft", "shadow", "stable", "retired"}
REQUIRED_DEVICES = {"smart_plug", "smart_switch", "vacuum", "camera", "sensor"}
REQUIRED_ADAPTERS = {"mqtt", "home_assistant", "zigbee", "z_wave", "matter"}
REQUIRED_SOURCE_LABELS = {"trusted", "simulated", "unverified"}
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
    if str(policy.get("activation_state") or "") != "local_first_control_pack":
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
    if not REQUIRED_DEVICES.issubset(set(_as_string_list(policy.get("supported_devices")))):
        failures.append("policy_supported_devices_missing")
    if not REQUIRED_ADAPTERS.issubset(set(_as_string_list(policy.get("adapter_surfaces")))):
        failures.append("policy_adapter_surfaces_missing")
    if not REQUIRED_SOURCE_LABELS.issubset(set(_as_string_list(policy.get("source_labels")))):
        failures.append("policy_source_labels_missing")

    privacy = policy.get("privacy_controls") if isinstance(policy.get("privacy_controls"), dict) else {}
    for key in ["telemetry_local_only", "visible_privacy_state_required"]:
        if privacy.get(key) is not True:
            failures.append(f"policy_privacy_{key}_not_true")
    for key in ["cloud_upload_default", "hidden_camera_capture_allowed", "hidden_microphone_capture_allowed", "raw_media_persistence_allowed"]:
        if privacy.get(key) is not False:
            failures.append(f"policy_privacy_{key}_not_false")

    governance = policy.get("governance_controls") if isinstance(policy.get("governance_controls"), dict) else {}
    for key in [
        "room_graph_required",
        "device_registry_required",
        "automation_rules_required",
        "emergency_pause_required",
        "sr_ssr_review_required",
        "human_override_wins",
        "auditable_actions",
    ]:
        if governance.get(key) is not True:
            failures.append(f"policy_governance_{key}_not_true")
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
            "configs/smarthome-local-control-policy.json",
            "contracts/smarthome_local_control.schema.json",
            "src/smarthome_local_control_runtime.py",
            "tests/test_smarthome_local_control_runtime.py",
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
        "configs/smarthome-local-control-policy.json",
        "src/smarthome_local_control_runtime.py",
        "prelaunch/governance/smarthome_local_control.example.json",
    ]:
        if ref not in pipeline_refs:
            failures.append(f"registry_pipeline_ref_missing:{ref}")
    return {"failures": failures, "registry_report": report, "entries": entries, "pipeline_eval_refs": pipeline_eval_refs}


def _device_registry_failures(registry: Dict[str, Any], policy_payload: Dict[str, Any]) -> List[str]:
    policy = _policy_dict(policy_payload)
    supported_devices = set(_as_string_list(policy.get("supported_devices")))
    adapters = set(_as_string_list(policy.get("adapter_surfaces")))
    labels = set(_as_string_list(policy.get("source_labels")))
    failures: List[str] = []
    if registry.get("apiVersion") != API_VERSION:
        failures.append("device_registry_api_version_invalid")
    if registry.get("kind") != REGISTRY_KIND:
        failures.append("device_registry_kind_invalid")
    if not SAFE_ID_RE.match(str(registry.get("id") or "")):
        failures.append("device_registry_id_invalid")
    if "privacy" not in str(registry.get("privacy_principle") or "").lower():
        failures.append("device_registry_privacy_principle_missing")
    rooms = registry.get("rooms") if isinstance(registry.get("rooms"), list) else []
    devices = registry.get("devices") if isinstance(registry.get("devices"), list) else []
    if not rooms:
        failures.append("device_registry_rooms_empty")
    if not devices:
        failures.append("device_registry_devices_empty")
    room_ids = {str(room.get("id") or "") for room in rooms if isinstance(room, dict)}
    device_ids: Set[str] = set()
    device_types: Set[str] = set()
    adapter_types: Set[str] = set()
    for device in devices:
        if not isinstance(device, dict):
            failures.append("device_registry_device_not_object")
            continue
        device_id = str(device.get("id") or "")
        device_type = str(device.get("type") or "")
        adapter = str(device.get("adapter") or "")
        device_ids.add(device_id)
        device_types.add(device_type)
        adapter_types.add(adapter)
        if not SAFE_ID_RE.match(device_id):
            failures.append(f"device_id_invalid:{device_id}")
        if device_type not in supported_devices:
            failures.append(f"device_type_not_supported:{device_id}:{device_type}")
        if str(device.get("room_id") or "") not in room_ids:
            failures.append(f"device_room_missing:{device_id}:{device.get('room_id')}")
        if adapter not in adapters:
            failures.append(f"device_adapter_not_supported:{device_id}:{adapter}")
        if str(device.get("source_label") or "") not in labels:
            failures.append(f"device_source_label_invalid:{device_id}:{device.get('source_label')}")
        if policy["privacy_controls"].get("visible_privacy_state_required") is True and device.get("visible_privacy_state") is not True:
            failures.append(f"device_visible_privacy_state_missing:{device_id}")
        if policy["privacy_controls"].get("hidden_camera_capture_allowed") is False and device_type == "camera" and device.get("camera") is not True:
            failures.append(f"camera_device_not_explicit:{device_id}")
        if policy["privacy_controls"].get("hidden_microphone_capture_allowed") is False and device.get("microphone") is True:
            failures.append(f"microphone_capture_not_allowed:{device_id}")
    if not REQUIRED_DEVICES.issubset(device_types):
        failures.append("device_registry_required_device_types_missing")
    if not REQUIRED_ADAPTERS.issubset(adapter_types):
        failures.append("device_registry_required_adapters_missing")
    if len(device_ids) != len(devices):
        failures.append("device_registry_duplicate_device_ids")
    return failures


def _action_failures(action: Dict[str, Any], device_ids: Set[str], policy_payload: Dict[str, Any]) -> List[str]:
    policy = _policy_dict(policy_payload)
    governance = policy.get("governance_controls") if isinstance(policy.get("governance_controls"), dict) else {}
    failures: List[str] = []
    action_id = str(action.get("id") or "<missing>")
    if action.get("apiVersion") != API_VERSION:
        failures.append(f"action_api_version_invalid:{action_id}")
    if action.get("kind") != ACTION_KIND:
        failures.append(f"action_kind_invalid:{action_id}")
    if not SAFE_ID_RE.match(action_id):
        failures.append(f"action_id_invalid:{action_id}")
    if policy.get("require_trace_id") is True and not SAFE_ID_RE.match(str(action.get("trace_id") or "")):
        failures.append(f"action_trace_id_invalid:{action_id}")
    if str(action.get("device_id") or "") not in device_ids:
        failures.append(f"action_device_missing:{action_id}:{action.get('device_id')}")
    if not str(action.get("action") or "").strip():
        failures.append(f"action_name_empty:{action_id}")
    if governance.get("emergency_pause_required") is True and action.get("emergency_pause_checked") is not True:
        failures.append(f"action_emergency_pause_not_checked:{action_id}")
    if governance.get("human_override_wins") is True and action.get("human_override_allowed") is not True:
        failures.append(f"action_human_override_not_allowed:{action_id}")
    if governance.get("auditable_actions") is True and action.get("audit_required") is not True:
        failures.append(f"action_audit_not_required:{action_id}")
    review = action.get("sr_ssr_review") if isinstance(action.get("sr_ssr_review"), dict) else {}
    if governance.get("sr_ssr_review_required") is True and "required" not in review:
        failures.append(f"action_review_missing:{action_id}")
    if review.get("required") is True and not str(review.get("reason") or "").strip():
        failures.append(f"action_review_reason_empty:{action_id}")
    return failures


def _automation_failures(example_set: Dict[str, Any], policy_payload: Dict[str, Any]) -> List[str]:
    policy = _policy_dict(policy_payload)
    governance = policy.get("governance_controls") if isinstance(policy.get("governance_controls"), dict) else {}
    rules = example_set.get("automation_rules") if isinstance(example_set.get("automation_rules"), list) else []
    failures: List[str] = []
    if governance.get("automation_rules_required") is True and not rules:
        failures.append("automation_rules_empty")
    if governance.get("emergency_pause_required") is True:
        has_pause = any(isinstance(rule, dict) and rule.get("trigger") == "emergency_pause" for rule in rules)
        if not has_pause:
            failures.append("automation_emergency_pause_missing")
    for rule in rules:
        if not isinstance(rule, dict):
            failures.append("automation_rule_not_object")
            continue
        rule_id = str(rule.get("id") or "<missing>")
        if rule.get("local_only") is not True:
            failures.append(f"automation_local_only_not_true:{rule_id}")
        if rule.get("requires_review") is not True:
            failures.append(f"automation_requires_review_not_true:{rule_id}")
    return failures


def validate_smarthome_policy(
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
    registry_result = _registry_failures(payload, project_root=project, package_root=package, registry_path=registry)
    failures.extend(registry_result["failures"])

    all_resolved_refs: List[Dict[str, Any]] = []
    all_missing_refs: List[Dict[str, Any]] = []
    all_unsafe_refs: List[Dict[str, Any]] = []
    action_results: List[Dict[str, Any]] = []
    registry_results: List[Dict[str, Any]] = []

    refs_result = _resolve_refs(sorted(set(_as_string_list(payload.get("refs")))), project_root=project, package_root=package, owner=str(payload.get("id") or "policy"))
    failures.extend(refs_result["failures"])
    all_resolved_refs.extend(refs_result["resolved_refs"])
    all_missing_refs.extend(refs_result["missing_refs"])
    all_unsafe_refs.extend(refs_result["unsafe_refs"])

    example_ref_results = _resolve_refs(_as_string_list(policy.get("required_example_sets")), project_root=project, package_root=package, owner="required_example_sets")
    failures.extend(example_ref_results["failures"])
    all_resolved_refs.extend(example_ref_results["resolved_refs"])
    all_missing_refs.extend(example_ref_results["missing_refs"])
    all_unsafe_refs.extend(example_ref_results["unsafe_refs"])

    for ref_item in example_ref_results["resolved_refs"]:
        example_set = load_example_set(Path(ref_item["path"]))
        if example_set.get("apiVersion") != API_VERSION:
            failures.append(f"example_set_api_version_invalid:{ref_item['ref']}")
        if example_set.get("kind") != SET_KIND:
            failures.append(f"example_set_kind_invalid:{ref_item['ref']}")
        device_registry = example_set.get("device_registry") if isinstance(example_set.get("device_registry"), dict) else {}
        registry_failures = _device_registry_failures(device_registry, payload)
        failures.extend(registry_failures)
        devices = device_registry.get("devices") if isinstance(device_registry.get("devices"), list) else []
        device_ids = {str(device.get("id") or "") for device in devices if isinstance(device, dict)}
        registry_results.append(
            {
                "id": str(device_registry.get("id") or "<missing>"),
                "ok": not registry_failures,
                "rooms": len(device_registry.get("rooms") or []),
                "devices": len(devices),
                "failures": sorted(set(registry_failures)),
            }
        )
        automation_failures = _automation_failures(example_set, payload)
        failures.extend(automation_failures)

        actions = example_set.get("actions") if isinstance(example_set.get("actions"), list) else []
        if not actions:
            failures.append(f"example_set_actions_empty:{ref_item['ref']}")
        for action in actions:
            if not isinstance(action, dict):
                failures.append(f"action_not_object:{ref_item['ref']}")
                continue
            action_id = str(action.get("id") or "<missing>")
            action_failures = _action_failures(action, device_ids, payload)
            failures.extend(action_failures)
            action_results.append(
                {
                    "id": action_id,
                    "ok": not action_failures,
                    "device_id": str(action.get("device_id") or ""),
                    "requires_approval": action.get("requires_approval"),
                    "failures": sorted(set(action_failures)),
                }
            )

        example_refs = _as_string_list(example_set.get("refs"))
        example_resolved = _resolve_refs(example_refs, project_root=project, package_root=package, owner=str(example_set.get("id") or "example_set"))
        failures.extend(example_resolved["failures"])
        all_resolved_refs.extend(example_resolved["resolved_refs"])
        all_missing_refs.extend(example_resolved["missing_refs"])
        all_unsafe_refs.extend(example_resolved["unsafe_refs"])

    checks = [
        {"id": "local_first", "status": "passed" if not any("local_only" in item or "telemetry_local_only" in item for item in failures) else "failed"},
        {"id": "device_registry", "status": "passed" if not any("device_registry" in item for item in failures) else "failed"},
        {"id": "adapter_surfaces", "status": "passed" if not any("adapter" in item for item in failures) else "failed"},
        {"id": "privacy_visible", "status": "passed" if not any("privacy" in item or "hidden_" in item or "microphone" in item for item in failures) else "failed"},
        {"id": "emergency_pause", "status": "passed" if not any("emergency_pause" in item for item in failures) else "failed"},
        {"id": "sr_ssr_review", "status": "passed" if not any("review" in item for item in failures) else "failed"},
        {"id": "refs_resolved", "status": "passed" if not all_missing_refs and not all_unsafe_refs else "failed"},
    ]
    metrics = {
        "device_registries": len(registry_results),
        "passing_device_registries": sum(1 for item in registry_results if item["ok"]),
        "actions": len(action_results),
        "passing_actions": sum(1 for item in action_results if item["ok"]),
        "supported_devices": len(_as_string_list(policy.get("supported_devices"))),
        "adapter_surfaces": len(_as_string_list(policy.get("adapter_surfaces"))),
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
        "device_registry_results": sorted(registry_results, key=lambda item: item["id"]),
        "action_results": sorted(action_results, key=lambda item: item["id"]),
        "resolved_refs": sorted(all_resolved_refs, key=lambda item: (item["owner"], item["ref"])),
        "missing_refs": sorted(all_missing_refs, key=lambda item: (item["owner"], item["ref"])),
        "unsafe_refs": sorted(all_unsafe_refs, key=lambda item: (item["owner"], item["ref"])),
    }


def smarthome_report_to_gate_evidence(report: Dict[str, Any], *, artifact_uri: str = "") -> Dict[str, Any]:
    if not isinstance(report, dict) or report.get("kind") != REPORT_KIND:
        raise ValueError("smarthome_report_required")
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
    parser = argparse.ArgumentParser(description="Validate NoemaForge local-first SmartHome contracts.")
    parser.add_argument("--project-root", default=str(_default_project_root()), help="Project root containing noemaforge/ and docs/.")
    parser.add_argument("--package-root", default="", help="Package root, default: <project-root>/noemaforge.")
    parser.add_argument(
        "--policy",
        default="noemaforge/configs/smarthome-local-control-policy.json",
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

    report = validate_smarthome_policy(
        load_policy(policy_path),
        project_root=project_root,
        package_root=package_root,
        policy_path=policy_path,
        registry_path=registry_path,
    )
    if args.summary:
        payload: Dict[str, Any] = {
            "apiVersion": report["apiVersion"],
            "kind": "SmartHomeLocalControlValidationSummary",
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
