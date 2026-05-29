#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/post_reboot_service_health_readiness_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-21
Modified: 2026-05-21
Purpose: Validate the offline readiness contract for post-reboot service health evidence.
Inputs: Post-reboot service health readiness policy, examples, registry refs and canonical docs.
Outputs: JSON validation reports and summaries.
Side effects: None; this validator never runs systemd, socket, gateway, ToolProxy or LLM commands.
Tests: noemaforge/tests/test_post_reboot_service_health_readiness_runtime.py, QA and performance tests.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Sequence


API_VERSION = "noemaforge.post-reboot-service-health-readiness/v1"
POLICY_KIND = "PostRebootServiceHealthReadinessPolicy"
EXAMPLE_KIND = "PostRebootServiceHealthReadinessExampleSet"
REPORT_KIND = "PostRebootServiceHealthReadinessValidationReport"
POLICY_ID = "post-reboot-service-health-readiness-core"
VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
SAFE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
REQUIRED_CHECK_IDS = {
    "post-reboot-baseline",
    "gateway-service-health",
    "main-backend-service-health",
    "toolproxy-service-health",
    "socket-api-smoke",
    "service-health-archive",
}
REQUIRED_SERVICE_TOKENS = {
    "gateway-service-health": "noemaforge-llm-gateway.service",
    "main-backend-service-health": "noemaforge-llama@main.service",
    "toolproxy-service-health": "noemaforge-toolproxy.service",
}
REQUIRED_SAFETY_CONTROLS = {
    "no_auto_live_execution",
    "target_machine_required",
    "operator_approval_required",
    "post_reboot_evidence_required",
    "main_backend_manual_start_required",
    "gateway_health_required",
    "toolproxy_health_required",
    "socket_evidence_required",
    "archive_required",
    "local_validator_has_no_subprocess",
}
REQUIRED_OUTPUTS = {
    "post_reboot_service_health_summary",
    "blocked_completion_notice",
    "target_health_command_manifest",
    "evidence_requirements",
    "registry_attachment",
    "docs_changelog_trace",
}
REQUIRED_DOC_REFS = {
    "noemaforge/docs/README.md",
    "noemaforge/docs/TODO.md",
    "noemaforge/docs/reference/PROJECT_CONTEXT.md",
    "noemaforge/docs/backlog/ROADMAP_AND_TODO.md",
    "noemaforge/docs/history/CHANGELOG.md",
    "noemaforge/docs/wiki/operations/recovery-stability-trixie.md",
}
PRIMARY_BLOCKED_TODO = "Confirm post-reboot health of `noemaforge-llama@main`, gateway, and ToolProxy on NoemaForge."

SRC_DIR = Path(__file__).resolve().parent
PACKAGE_ROOT = SRC_DIR.parent
PROJECT_ROOT = PACKAGE_ROOT.parent
DEFAULT_POLICY = PACKAGE_ROOT / "configs" / "post-reboot-service-health-readiness-policy.json"


def _nowz() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _display_path(path: Path) -> str:
    return path.as_posix()


def _as_string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


def _policy(payload: Dict[str, Any]) -> Dict[str, Any]:
    value = payload.get("policy")
    return value if isinstance(value, dict) else {}


def _is_safe_relative_ref(ref: str) -> bool:
    text = str(ref or "").strip().replace("\\", "/")
    if not text or text.startswith("/") or text.startswith("~"):
        return False
    return not any(part in {"", ".", ".."} for part in PurePosixPath(text).parts)


def _resolve_ref(ref: str, *, project_root: Path = PROJECT_ROOT, package_root: Path = PACKAGE_ROOT) -> Dict[str, Any]:
    normalized = ref.replace("\\", "/")
    candidates = [project_root / normalized, package_root / normalized]
    if normalized.startswith("noemaforge/"):
        candidates.append(project_root / normalized)
    else:
        candidates.append(project_root / "noemaforge" / normalized)
    checked: List[str] = []
    for candidate in candidates:
        checked.append(_display_path(candidate))
        if candidate.exists():
            return {"ok": True, "ref": ref, "path": _display_path(candidate.resolve()), "checked": checked}
    return {"ok": False, "ref": ref, "path": "", "checked": checked}


def load_policy(path: Path | str = DEFAULT_POLICY) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def load_example(path: Path | str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def _check_failures(check: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    cid = str(check.get("id") or "")
    commands = _as_string_list(check.get("commands"))
    evidence = _as_string_list(check.get("evidence"))
    gates = _as_string_list(check.get("completion_gates"))
    joined = " ".join(commands + evidence + gates)
    if not SAFE_ID_RE.match(cid):
        failures.append(f"check_id_invalid:{cid}")
    if not str(check.get("title") or "").strip():
        failures.append(f"check_title_missing:{cid}")
    if check.get("target_evidence_required") is not True:
        failures.append(f"check_target_evidence_required_not_true:{cid}")
    if not commands:
        failures.append(f"check_commands_empty:{cid}")
    if not evidence:
        failures.append(f"check_evidence_empty:{cid}")
    if not gates:
        failures.append(f"check_completion_gates_empty:{cid}")
    if cid in {"main-backend-service-health", "socket-api-smoke"} and check.get("requires_operator_approval") is not True:
        failures.append(f"check_operator_approval_required:{cid}")
    if cid in REQUIRED_SERVICE_TOKENS:
        token = REQUIRED_SERVICE_TOKENS[cid]
        if token not in joined:
            failures.append(f"check_service_token_missing:{cid}:{token}")
        if "systemctl" not in joined:
            failures.append(f"check_systemctl_probe_missing:{cid}")
        if "service_state_recorded" not in gates:
            failures.append(f"check_service_state_gate_missing:{cid}")
    if cid == "post-reboot-baseline":
        for gate in ["boot_id_recorded", "system_state_recorded", "failed_units_recorded"]:
            if gate not in gates:
                failures.append(f"check_post_reboot_baseline_gate_missing:{gate}")
    if cid == "main-backend-service-health" and "manual_start_approval_recorded" not in gates:
        failures.append("check_main_backend_manual_approval_gate_missing")
    if cid == "socket-api-smoke":
        for token in ["gateway_health_json", "toolproxy_status_json", "socket_state"]:
            if token not in joined:
                failures.append(f"check_socket_api_token_missing:{token}")
        if "operator_approval_recorded" not in gates:
            failures.append("check_socket_api_operator_gate_missing")
    if cid == "service-health-archive":
        for gate in ["bundle_exists", "bundle_sha256_recorded", "secrets_redacted", "canonical_docs_updated_after_review"]:
            if gate not in gates:
                failures.append(f"check_archive_gate_missing:{gate}")
    elif "evidence_file_archived" not in gates:
        failures.append(f"check_archive_gate_missing:{cid}")
    return failures


def _policy_failures(payload: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    policy = _policy(payload)
    if payload.get("apiVersion") != API_VERSION:
        failures.append("policy_api_version_invalid")
    if payload.get("kind") != POLICY_KIND:
        failures.append("policy_kind_invalid")
    if payload.get("id") != POLICY_ID:
        failures.append("policy_id_invalid")
    if str(payload.get("status") or "") not in VALID_STATUSES:
        failures.append("policy_status_invalid")
    if policy.get("mode") != "offline_contract":
        failures.append("policy_mode_not_offline_contract")
    if policy.get("activation_state") != "patched10_post_reboot_service_health_readiness":
        failures.append("policy_activation_state_invalid")
    if policy.get("completion_state") != "blocked_until_target_post_reboot_service_health_evidence":
        failures.append("policy_completion_state_invalid")
    for key in ["require_registry_attachment", "require_docs_and_changelog_refs", "require_no_live_execution"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    if PRIMARY_BLOCKED_TODO not in _as_string_list(policy.get("blocked_todo_refs")):
        failures.append("policy_primary_blocked_todo_missing")
    controls = policy.get("required_safety_controls") if isinstance(policy.get("required_safety_controls"), dict) else {}
    for control in REQUIRED_SAFETY_CONTROLS:
        if controls.get(control) is not True:
            failures.append(f"policy_safety_control_missing:{control}")
    checks = policy.get("required_checks")
    if not isinstance(checks, list):
        failures.append("policy_required_checks_not_list")
        checks = []
    seen_checks = set()
    for raw in checks:
        if not isinstance(raw, dict):
            failures.append("policy_required_check_not_object")
            continue
        cid = str(raw.get("id") or "")
        if cid in seen_checks:
            failures.append(f"policy_duplicate_check:{cid}")
        seen_checks.add(cid)
        failures.extend(_check_failures(raw))
    for cid in sorted(REQUIRED_CHECK_IDS - seen_checks):
        failures.append(f"policy_required_check_missing:{cid}")
    outputs = set(_as_string_list(policy.get("required_outputs")))
    for output in sorted(REQUIRED_OUTPUTS - outputs):
        failures.append(f"policy_required_output_missing:{output}")
    refs = set(_as_string_list(policy.get("required_refs"))) | set(_as_string_list(payload.get("refs")))
    for ref in REQUIRED_DOC_REFS - refs:
        failures.append(f"policy_doc_ref_missing:{ref}")
    return failures


def _ref_failures(payload: Dict[str, Any], *, project_root: Path = PROJECT_ROOT, package_root: Path = PACKAGE_ROOT) -> Dict[str, Any]:
    policy = _policy(payload)
    refs = _as_string_list(payload.get("refs")) + _as_string_list(policy.get("required_refs"))
    failures: List[str] = []
    resolved: List[Dict[str, Any]] = []
    missing: List[Dict[str, Any]] = []
    unsafe: List[str] = []
    for ref in sorted(set(refs)):
        if not _is_safe_relative_ref(ref):
            unsafe.append(ref)
            failures.append(f"unsafe_ref:{ref}")
            continue
        result = _resolve_ref(ref, project_root=project_root, package_root=package_root)
        if result["ok"]:
            resolved.append(result)
        else:
            missing.append(result)
            failures.append(f"missing_ref:{ref}")
    return {"failures": failures, "resolved_refs": resolved, "missing_refs": missing, "unsafe_refs": unsafe}


def _example_failures(payload: Dict[str, Any], example_path: Path) -> Dict[str, Any]:
    failures: List[str] = []
    if not example_path.exists():
        return {"failures": [f"example_missing:{_display_path(example_path)}"], "scenarios": 0}
    example = load_example(example_path)
    if example.get("apiVersion") != API_VERSION:
        failures.append("example_api_version_invalid")
    if example.get("kind") != EXAMPLE_KIND:
        failures.append("example_kind_invalid")
    scenarios = example.get("scenarios") if isinstance(example.get("scenarios"), list) else []
    policy = _policy(payload)
    check_ids = {str(item.get("id")) for item in policy.get("required_checks", []) if isinstance(item, dict)}
    outputs = set(_as_string_list(policy.get("required_outputs")))
    for scenario in scenarios:
        if not isinstance(scenario, dict):
            failures.append("example_scenario_not_object")
            continue
        sid = str(scenario.get("id") or "unknown")
        if scenario.get("blocked_completion") is not True:
            failures.append(f"example_blocked_completion_not_true:{sid}")
        for cid in sorted(set(_as_string_list(scenario.get("expected_check_ids"))) - check_ids):
            failures.append(f"example_check_missing_from_policy:{sid}:{cid}")
        for output in sorted(set(_as_string_list(scenario.get("expected_outputs"))) - outputs):
            failures.append(f"example_output_missing_from_policy:{sid}:{output}")
    if not scenarios:
        failures.append("example_scenarios_empty")
    return {"failures": failures, "scenarios": len(scenarios)}


def validate_post_reboot_service_health_readiness_policy(
    payload: Dict[str, Any],
    *,
    project_root: Path = PROJECT_ROOT,
    package_root: Path = PACKAGE_ROOT,
    example_path: Path | None = None,
) -> Dict[str, Any]:
    failures: List[str] = []
    failures.extend(_policy_failures(payload))
    refs = _ref_failures(payload, project_root=project_root, package_root=package_root)
    failures.extend(refs["failures"])
    example_path = example_path or project_root / "prelaunch" / "governance" / "post_reboot_service_health_readiness.example.json"
    examples = _example_failures(payload, example_path)
    failures.extend(examples["failures"])
    policy = _policy(payload)
    checks = [check for check in policy.get("required_checks", []) if isinstance(check, dict)]
    command_manifest = [
        {
            "id": str(check.get("id") or ""),
            "commands": _as_string_list(check.get("commands")),
            "evidence": _as_string_list(check.get("evidence")),
            "completion_gates": _as_string_list(check.get("completion_gates")),
            "requires_operator_approval": bool(check.get("requires_operator_approval")),
        }
        for check in checks
    ]
    evidence_requirements = sorted({item for check in checks for item in _as_string_list(check.get("evidence"))})
    command_count = sum(len(item["commands"]) for item in command_manifest)
    return {
        "apiVersion": API_VERSION,
        "kind": REPORT_KIND,
        "created_at": _nowz(),
        "ok": not failures,
        "id": payload.get("id"),
        "version": payload.get("version"),
        "completion_state": policy.get("completion_state"),
        "failures": failures,
        "metrics": {
            "required_checks": len(checks),
            "target_commands": command_count,
            "evidence_requirements": len(evidence_requirements),
            "resolved_refs": len(refs["resolved_refs"]),
            "missing_refs": len(refs["missing_refs"]),
            "example_scenarios": examples["scenarios"],
        },
        "post_reboot_service_health_summary": {
            "completion_blocked": True,
            "target_machine_required": True,
            "safe_local_validator_only": True,
            "target_command_count": command_count,
            "blocked_todo_refs": _as_string_list(policy.get("blocked_todo_refs")),
        },
        "target_health_command_manifest": command_manifest,
        "evidence_requirements": evidence_requirements,
        "refs": refs,
        "examples": examples,
        "blocked_completion_notice": (
            "Post-reboot service health remains open until NoemaForge target evidence "
            "for gateway, ToolProxy, noemaforge-llama@main, socket/API smoke and archive review is captured."
        ),
    }


def gate_evidence(report: Dict[str, Any], *, artifact_uri: str) -> Dict[str, Any]:
    return {
        "apiVersion": "noemaforge.release-evidence/v1",
        "kind": "ReleaseEvidence",
        "gate": "post_reboot_service_health_readiness",
        "artifact_uri": artifact_uri,
        "status": "passed" if report.get("ok") else "failed",
        "checks": [
            {"id": "target_machine_blocker_recorded", "status": "passed" if report.get("completion_state") == "blocked_until_target_post_reboot_service_health_evidence" else "failed"},
            {"id": "gateway_service_evidence_required", "status": "passed" if "gateway_service_state" in report.get("evidence_requirements", []) else "failed"},
            {"id": "toolproxy_service_evidence_required", "status": "passed" if "toolproxy_service_state" in report.get("evidence_requirements", []) else "failed"},
            {"id": "main_backend_service_evidence_required", "status": "passed" if "main_backend_service_state" in report.get("evidence_requirements", []) else "failed"},
            {"id": "local_validator_has_no_live_execution", "status": "passed"},
        ],
        "metrics": report.get("metrics", {}),
        "failures": report.get("failures", []),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate post-reboot service health readiness policy.")
    parser.add_argument("--policy", default=str(DEFAULT_POLICY))
    parser.add_argument("--project-root", default=str(PROJECT_ROOT))
    parser.add_argument("--package-root", default=str(PACKAGE_ROOT))
    parser.add_argument("--example", default="")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(argv)
    report = validate_post_reboot_service_health_readiness_policy(
        load_policy(args.policy),
        project_root=Path(args.project_root),
        package_root=Path(args.package_root),
        example_path=Path(args.example) if args.example else None,
    )
    if args.summary:
        print(json.dumps({"ok": report["ok"], "failures": report["failures"], "metrics": report["metrics"], "completion_state": report["completion_state"]}, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
