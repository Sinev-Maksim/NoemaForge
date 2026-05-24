#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/systemd_gdm_nvidia_live_validation_readiness_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-21
Modified: 2026-05-21
Purpose: Validate the offline readiness contract for target systemd, GDM and NVIDIA live validation evidence.
Inputs: Systemd/GDM/NVIDIA live-validation readiness policy, examples, registry refs and canonical docs.
Outputs: JSON validation reports and summaries.
Side effects: None; this validator never runs systemd, GDM, NVIDIA, journal, loginctl or archive commands.
Tests: noemaforge/tests/test_systemd_gdm_nvidia_live_validation_readiness_runtime.py, QA and performance tests.
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


API_VERSION = "noemaforge.systemd-gdm-nvidia-live-validation-readiness/v1"
POLICY_KIND = "SystemdGdmNvidiaLiveValidationReadinessPolicy"
EXAMPLE_KIND = "SystemdGdmNvidiaLiveValidationReadinessExampleSet"
REPORT_KIND = "SystemdGdmNvidiaLiveValidationReadinessValidationReport"
POLICY_ID = "systemd-gdm-nvidia-live-validation-readiness-core"
VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
SAFE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
PRIMARY_BLOCKED_TODO = "Run live systemd/GDM/NVIDIA validation on NoemaForge."
SECONDARY_BLOCKED_TODO = "Confirm NoemaForge NVIDIA/GDM recovery path after reboot."
REQUIRED_CHECK_IDS = {
    "target-boot-baseline",
    "operator-approval",
    "display-manager-gdm",
    "nvidia-driver-device",
    "secure-boot-kernel",
    "post-reboot-recovery-check",
    "evidence-archive",
}
REQUIRED_SAFETY_CONTROLS = {
    "no_auto_live_execution",
    "target_machine_required",
    "operator_approval_required",
    "read_only_checks_preferred",
    "display_manager_required",
    "nvidia_driver_required",
    "archive_required",
    "local_validator_has_no_subprocess",
}
REQUIRED_OUTPUTS = {
    "systemd_gdm_nvidia_live_validation_summary",
    "blocked_completion_notice",
    "target_systemd_gdm_nvidia_command_manifest",
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
FORBIDDEN_LOCAL_OR_REMOTE_TOKENS = (
    "--upload",
    "curl ",
    "scp ",
    "rsync ",
    "http://",
    "https://",
    "rm -",
    "reboot",
    "poweroff",
)

SRC_DIR = Path(__file__).resolve().parent
PACKAGE_ROOT = SRC_DIR.parent
PROJECT_ROOT = PACKAGE_ROOT.parent
DEFAULT_POLICY = PACKAGE_ROOT / "configs" / "systemd-gdm-nvidia-live-validation-readiness-policy.json"


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


def _require_items(cid: str, owner: str, required: Sequence[str], actual: Sequence[str], failures: List[str]) -> None:
    for item in required:
        if item not in actual:
            failures.append(f"check_{owner}_missing:{cid}:{item}")


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
    for token in FORBIDDEN_LOCAL_OR_REMOTE_TOKENS:
        if token in joined:
            failures.append(f"check_forbidden_token:{cid}:{token.strip()}")
    if cid == "evidence-archive" and check.get("requires_operator_approval") is not True:
        failures.append(f"check_operator_approval_required:{cid}")
    if cid == "target-boot-baseline":
        _require_items(
            cid,
            "target_boot_baseline_evidence",
            ["boot_id", "system_running_state", "failed_units", "target_timestamp"],
            evidence,
            failures,
        )
        _require_items(
            cid,
            "target_boot_baseline_gate",
            ["boot_id_recorded", "system_state_recorded", "failed_units_recorded", "evidence_file_archived"],
            gates,
            failures,
        )
    if cid == "operator-approval":
        _require_items(
            cid,
            "operator_approval_evidence",
            ["operator_approval_record", "approved_scope", "approved_target_host"],
            evidence,
            failures,
        )
        _require_items(
            cid,
            "operator_approval_gate",
            ["operator_approval_recorded", "scope_limited_to_systemd_gdm_nvidia_validation", "evidence_file_archived"],
            gates,
            failures,
        )
    if cid == "display-manager-gdm":
        _require_items(
            cid,
            "display_manager_gdm_command",
            [
                "systemctl is-active display-manager.service || true",
                "systemctl is-active gdm.service || true",
                "systemctl status display-manager.service --no-pager -l || true",
            ],
            commands,
            failures,
        )
        _require_items(
            cid,
            "display_manager_gdm_evidence",
            ["display_manager_state", "gdm_state", "graphical_target_state", "display_manager_status_excerpt"],
            evidence,
            failures,
        )
        _require_items(
            cid,
            "display_manager_gdm_gate",
            [
                "display_manager_active_or_blocker_recorded",
                "gdm_active_or_alias_recorded",
                "graphical_target_state_recorded",
                "evidence_file_archived",
            ],
            gates,
            failures,
        )
    if cid == "nvidia-driver-device":
        _require_items(
            cid,
            "nvidia_driver_device_command",
            [
                "nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader || true",
                "nvidia-smi -L || true",
                "lsmod | grep -E '^nvidia' || true",
            ],
            commands,
            failures,
        )
        _require_items(
            cid,
            "nvidia_driver_device_evidence",
            ["gpu_name", "driver_version", "memory_total", "nvidia_smi_exit_code", "nvidia_module_state"],
            evidence,
            failures,
        )
        _require_items(
            cid,
            "nvidia_driver_device_gate",
            ["nvidia_smi_ok_or_blocker_recorded", "module_state_recorded", "evidence_file_archived"],
            gates,
            failures,
        )
    if cid == "secure-boot-kernel":
        _require_items(
            cid,
            "secure_boot_kernel_command",
            [
                "mokutil --sb-state || true",
                "uname -a",
                "journalctl -k -b --no-pager | grep -Ei 'nvidia|nouveau|secure boot' || true",
            ],
            commands,
            failures,
        )
        _require_items(
            cid,
            "secure_boot_kernel_evidence",
            ["secure_boot_state", "kernel_release", "kernel_driver_log_excerpt", "nouveau_conflict_state"],
            evidence,
            failures,
        )
        _require_items(
            cid,
            "secure_boot_kernel_gate",
            ["secure_boot_state_recorded", "kernel_release_recorded", "driver_log_reviewed", "evidence_file_archived"],
            gates,
            failures,
        )
    if cid == "post-reboot-recovery-check":
        _require_items(
            cid,
            "post_reboot_recovery_check_command",
            [
                "test ! -e /run/nologin",
                "systemctl is-active graphical.target || true",
                "loginctl seat-status seat0 || true",
            ],
            commands,
            failures,
        )
        _require_items(
            cid,
            "post_reboot_recovery_check_evidence",
            ["nologin_absent_state", "graphical_target_state", "seat0_status_excerpt"],
            evidence,
            failures,
        )
        _require_items(
            cid,
            "post_reboot_recovery_check_gate",
            ["nologin_absence_recorded", "graphical_target_ready_or_blocker_recorded", "seat_state_recorded", "evidence_file_archived"],
            gates,
            failures,
        )
    if cid == "evidence-archive":
        _require_items(
            cid,
            "evidence_archive_command",
            [
                "sudo noemaforge forensics --include-systemd-gdm-nvidia",
                "sha256sum <systemd-gdm-nvidia-live-validation-bundle>",
            ],
            commands,
            failures,
        )
        _require_items(
            cid,
            "evidence_archive_evidence",
            ["forensics_bundle_path", "bundle_sha256", "validation_transcript", "redaction_manifest"],
            evidence,
            failures,
        )
        _require_items(
            cid,
            "evidence_archive_gate",
            ["bundle_exists", "bundle_sha256_recorded", "secrets_redacted", "canonical_docs_updated_after_review", "evidence_file_archived"],
            gates,
            failures,
        )
    if cid != "operator-approval" and "evidence_file_archived" not in gates:
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
    if policy.get("activation_state") != "patched10_systemd_gdm_nvidia_live_validation_readiness":
        failures.append("policy_activation_state_invalid")
    if policy.get("completion_state") != "blocked_until_target_systemd_gdm_nvidia_live_validation_evidence":
        failures.append("policy_completion_state_invalid")
    for key in ["require_registry_attachment", "require_docs_and_changelog_refs", "require_no_live_execution"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    blocked = _as_string_list(policy.get("blocked_todo_refs"))
    if PRIMARY_BLOCKED_TODO not in blocked:
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
    refs = _as_string_list(payload.get("refs")) + _as_string_list(_policy(payload).get("required_refs"))
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
    scenarios = example.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        failures.append("example_scenarios_missing")
        scenarios = []
    expected_checks = set()
    expected_outputs = set()
    for scenario in scenarios:
        if not isinstance(scenario, dict):
            failures.append("example_scenario_not_object")
            continue
        if scenario.get("blocked_completion") is not True:
            failures.append(f"example_scenario_not_blocked:{scenario.get('id')}")
        expected_checks.update(_as_string_list(scenario.get("expected_check_ids")))
        expected_outputs.update(_as_string_list(scenario.get("expected_outputs")))
    for cid in REQUIRED_CHECK_IDS - expected_checks:
        failures.append(f"example_check_missing:{cid}")
    for output in REQUIRED_OUTPUTS - expected_outputs:
        failures.append(f"example_output_missing:{output}")
    return {"failures": failures, "scenarios": len(scenarios)}


def _evidence_requirements(payload: Dict[str, Any]) -> List[str]:
    evidence: List[str] = []
    for check in _policy(payload).get("required_checks", []):
        if isinstance(check, dict):
            evidence.extend(_as_string_list(check.get("evidence")))
    return sorted(set(evidence))


def _target_commands(payload: Dict[str, Any]) -> List[str]:
    commands: List[str] = []
    for check in _policy(payload).get("required_checks", []):
        if isinstance(check, dict):
            commands.extend(_as_string_list(check.get("commands")))
    return sorted(set(commands))


def validate_systemd_gdm_nvidia_live_validation_readiness_policy(
    payload: Dict[str, Any],
    *,
    project_root: Path = PROJECT_ROOT,
    package_root: Path = PACKAGE_ROOT,
    example_path: Path | None = None,
) -> Dict[str, Any]:
    if example_path is None:
        example_path = project_root / "prelaunch" / "governance" / "systemd_gdm_nvidia_live_validation_readiness.example.json"
    failures = _policy_failures(payload)
    refs = _ref_failures(payload, project_root=project_root, package_root=package_root)
    example = _example_failures(payload, example_path)
    failures.extend(refs["failures"])
    failures.extend(example["failures"])
    evidence = _evidence_requirements(payload)
    commands = _target_commands(payload)
    return {
        "apiVersion": API_VERSION,
        "kind": REPORT_KIND,
        "created_at": _nowz(),
        "ok": not failures,
        "id": payload.get("id"),
        "version": payload.get("version"),
        "completion_state": _policy(payload).get("completion_state"),
        "failures": failures,
        "metrics": {
            "required_checks": len(_policy(payload).get("required_checks", [])),
            "target_commands": len(commands),
            "evidence_requirements": len(evidence),
            "resolved_refs": len(refs["resolved_refs"]),
            "missing_refs": len(refs["missing_refs"]),
            "example_scenarios": example["scenarios"],
        },
        "systemd_gdm_nvidia_live_validation_summary": {
            "completion_blocked": _policy(payload).get("completion_state") == "blocked_until_target_systemd_gdm_nvidia_live_validation_evidence",
            "target_machine_required": True,
            "operator_approval_required": True,
            "safe_local_validator_only": True,
            "target_command_count": len(commands),
            "evidence_requirement_count": len(evidence),
        },
        "target_systemd_gdm_nvidia_command_manifest": commands,
        "evidence_requirements": evidence,
        "resolved_refs": refs["resolved_refs"],
        "missing_refs": refs["missing_refs"],
    }


def gate_evidence(report: Dict[str, Any], *, artifact_uri: str) -> Dict[str, Any]:
    return {
        "apiVersion": API_VERSION,
        "kind": "SystemdGdmNvidiaLiveValidationReadinessGateEvidence",
        "created_at": _nowz(),
        "gate": "systemd_gdm_nvidia_live_validation_readiness",
        "status": "passed" if report.get("ok") else "failed",
        "artifact_uri": artifact_uri,
        "metrics": dict(report.get("metrics") or {}),
        "failures": list(report.get("failures") or []),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate systemd/GDM/NVIDIA live-validation readiness policy.")
    parser.add_argument("--policy", default=str(DEFAULT_POLICY))
    parser.add_argument("--example", default="")
    parser.add_argument("--summary", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    example_path = Path(args.example) if args.example else None
    report = validate_systemd_gdm_nvidia_live_validation_readiness_policy(load_policy(args.policy), example_path=example_path)
    payload = {
        "ok": report["ok"],
        "completion_state": report["completion_state"],
        "metrics": report["metrics"],
        "failures": report["failures"],
    } if args.summary else report
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
