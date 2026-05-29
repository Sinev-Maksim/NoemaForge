#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/post_reboot_gpu_gdm_gateway_toolproxy_readiness_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-21
Modified: 2026-05-21
Purpose: Validate the offline readiness contract for post-reboot GPU, GDM, gateway and ToolProxy target evidence.
Inputs: Post-reboot composite readiness policy, example evidence, registry refs and canonical docs.
Outputs: JSON validation reports and summaries.
Side effects: None; this validator never runs systemd, NVIDIA, gateway, ToolProxy, LLM, journal or archive commands.
Tests: noemaforge/tests/test_post_reboot_gpu_gdm_gateway_toolproxy_readiness_runtime.py, QA and performance tests.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Mapping, Sequence


API_VERSION = "noemaforge.post-reboot-gpu-gdm-gateway-toolproxy-readiness/v1"
POLICY_KIND = "PostRebootGpuGdmGatewayToolproxyReadinessPolicy"
EXAMPLE_KIND = "PostRebootGpuGdmGatewayToolproxyReadinessExampleSet"
REPORT_KIND = "PostRebootGpuGdmGatewayToolproxyReadinessValidationReport"
POLICY_ID = "post-reboot-gpu-gdm-gateway-toolproxy-readiness-core"
VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
SAFE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
PRIMARY_BLOCKED_TODO = "Run live NoemaForge post-reboot GPU/GDM/gateway/ToolProxy validation."
BLOCKED_STATE = "blocked_until_target_post_reboot_gpu_gdm_gateway_toolproxy_evidence"
REQUIRED_CHECK_IDS = {
    "target-boot-baseline",
    "operator-approval",
    "gpu-gdm-baseline",
    "gateway-toolproxy-services",
    "socket-live-smokes",
    "archive-and-redaction",
}
REQUIRED_SAFETY_CONTROLS = {
    "no_auto_live_execution",
    "target_machine_required",
    "operator_approval_required",
    "post_reboot_baseline_required",
    "gpu_gdm_required",
    "gateway_toolproxy_required",
    "archive_required",
    "local_validator_has_no_subprocess",
}
REQUIRED_OUTPUTS = {
    "post_reboot_gpu_gdm_gateway_toolproxy_summary",
    "blocked_completion_notice",
    "target_post_reboot_validation_command_manifest",
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
    "sudo reboot",
    "poweroff",
    "shutdown -",
)
REQUIRED_COMMANDS: Mapping[str, Sequence[str]] = {
    "target-boot-baseline": (
        "cat /proc/sys/kernel/random/boot_id",
        "systemctl is-system-running || true",
        "systemctl --failed --no-legend || true",
    ),
    "gpu-gdm-baseline": (
        "systemctl is-active display-manager.service || true",
        "systemctl is-active gdm.service || true",
        "nvidia-smi --query-gpu=name,driver_version,memory.total,ecc.mode.current --format=csv,noheader",
        "ls -l /dev/nvidia* 2>/dev/null || true",
    ),
    "gateway-toolproxy-services": (
        "systemctl is-active noemaforge-llm-gateway.service || true",
        "systemctl is-active noemaforge-toolproxy.service || true",
        "noemaforge status --json",
    ),
    "socket-live-smokes": (
        "test -S /run/noemaforge/llm/gateway.sock",
        "test -S /run/noemaforge/toolproxy.sock",
        "noemaforge smoke --json",
        "noemaforge toolproxy smoke --capability llm.chat --json",
    ),
    "archive-and-redaction": (
        "sudo noemaforge forensics --include-gpu-gdm-gateway-toolproxy",
        "sha256sum <gpu-gdm-gateway-toolproxy-bundle>",
    ),
}
REQUIRED_EVIDENCE: Mapping[str, Sequence[str]] = {
    "target-boot-baseline": (
        "boot_id",
        "target_timestamp",
        "system_running_state",
        "failed_units",
        "target_host",
    ),
    "operator-approval": (
        "operator_approval_record",
        "approved_scope",
        "approved_target_host",
        "approval_timestamp",
    ),
    "gpu-gdm-baseline": (
        "display_manager_state",
        "gdm_state",
        "graphical_target_state",
        "nvidia_smi_csv",
        "nvidia_device_nodes",
    ),
    "gateway-toolproxy-services": (
        "gateway_service_state",
        "toolproxy_service_state",
        "noemaforge_status_json",
        "gateway_status_excerpt",
        "toolproxy_status_excerpt",
    ),
    "socket-live-smokes": (
        "gateway_socket_path",
        "toolproxy_socket_path",
        "gateway_smoke_transcript",
        "toolproxy_smoke_json",
        "llm_chat_capability_result",
    ),
    "archive-and-redaction": (
        "forensics_bundle_path",
        "bundle_sha256",
        "redaction_manifest",
        "secret_scan_summary",
        "review_followup_record",
    ),
}
REQUIRED_GATES: Mapping[str, Sequence[str]] = {
    "target-boot-baseline": (
        "boot_id_recorded",
        "system_state_recorded",
        "failed_units_recorded",
        "evidence_file_archived",
    ),
    "operator-approval": (
        "operator_approval_recorded",
        "scope_limited_to_post_reboot_gpu_gdm_gateway_toolproxy_validation",
        "evidence_file_archived",
    ),
    "gpu-gdm-baseline": (
        "display_manager_recorded",
        "gdm_state_recorded",
        "nvidia_signal_recorded",
        "evidence_file_archived",
    ),
    "gateway-toolproxy-services": (
        "gateway_state_recorded",
        "toolproxy_state_recorded",
        "status_json_archived",
        "evidence_file_archived",
    ),
    "socket-live-smokes": (
        "operator_approval_recorded",
        "gateway_socket_recorded",
        "toolproxy_socket_recorded",
        "gateway_smoke_recorded",
        "toolproxy_smoke_recorded",
        "evidence_file_archived",
    ),
    "archive-and-redaction": (
        "forensics_bundle_created",
        "bundle_sha256_recorded",
        "redaction_manifest_recorded",
        "review_followup_recorded",
    ),
}

SRC_DIR = Path(__file__).resolve().parent
PACKAGE_ROOT = SRC_DIR.parent
PROJECT_ROOT = PACKAGE_ROOT.parent
DEFAULT_POLICY = PACKAGE_ROOT / "configs" / "post-reboot-gpu-gdm-gateway-toolproxy-readiness-policy.json"


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
    if cid in {"operator-approval", "socket-live-smokes", "archive-and-redaction"}:
        if check.get("requires_operator_approval") is not True:
            failures.append(f"check_operator_approval_required:{cid}")
    _require_items(cid, "command", REQUIRED_COMMANDS.get(cid, ()), commands, failures)
    _require_items(cid, "evidence", REQUIRED_EVIDENCE.get(cid, ()), evidence, failures)
    _require_items(cid, "gate", REQUIRED_GATES.get(cid, ()), gates, failures)
    return failures


def _refs_report(refs: Iterable[str]) -> Dict[str, Any]:
    resolved = []
    missing = []
    unsafe = []
    for ref in refs:
        if not _is_safe_relative_ref(ref):
            unsafe.append(ref)
            continue
        item = _resolve_ref(ref)
        if item["ok"]:
            resolved.append(item)
        else:
            missing.append(item)
    return {"resolved": resolved, "missing": missing, "unsafe": unsafe}


def _policy_failures(payload: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    policy = _policy(payload)
    if payload.get("apiVersion") != API_VERSION:
        failures.append("apiVersion_invalid")
    if payload.get("kind") != POLICY_KIND:
        failures.append("kind_invalid")
    if policy.get("id") != POLICY_ID:
        failures.append("policy_id_invalid")
    if policy.get("status") not in VALID_STATUSES:
        failures.append("policy_status_invalid")
    if policy.get("completion_state") != BLOCKED_STATE:
        failures.append("policy_completion_state_invalid")
    if policy.get("local_validator_only") is not True:
        failures.append("policy_local_validator_only_not_true")
    if policy.get("target_machine_required") is not True:
        failures.append("policy_target_machine_required_not_true")
    if policy.get("operator_approval_required") is not True:
        failures.append("policy_operator_approval_required_not_true")
    if policy.get("blocked_todo") != PRIMARY_BLOCKED_TODO:
        failures.append("policy_blocked_todo_invalid")

    checks = policy.get("required_checks")
    if not isinstance(checks, list):
        failures.append("required_checks_not_list")
        checks = []
    check_ids = {str(check.get("id") or "") for check in checks if isinstance(check, dict)}
    for cid in sorted(REQUIRED_CHECK_IDS - check_ids):
        failures.append(f"required_check_missing:{cid}")
    for cid in sorted(check_ids - REQUIRED_CHECK_IDS):
        failures.append(f"required_check_unknown:{cid}")
    for check in checks:
        if isinstance(check, dict):
            failures.extend(_check_failures(check))
        else:
            failures.append("required_check_not_object")

    controls = set(_as_string_list(policy.get("safety_controls")))
    outputs = set(_as_string_list(policy.get("output_artifacts")))
    doc_refs = set(_as_string_list(policy.get("docs_refs")))
    for item in sorted(REQUIRED_SAFETY_CONTROLS - controls):
        failures.append(f"safety_control_missing:{item}")
    for item in sorted(REQUIRED_OUTPUTS - outputs):
        failures.append(f"output_artifact_missing:{item}")
    for item in sorted(REQUIRED_DOC_REFS - doc_refs):
        failures.append(f"doc_ref_missing:{item}")

    refs = _as_string_list(policy.get("registry_refs")) + _as_string_list(policy.get("docs_refs")) + _as_string_list(policy.get("example_refs"))
    refs_report = _refs_report(refs)
    for ref in refs_report["unsafe"]:
        failures.append(f"ref_unsafe:{ref}")
    for item in refs_report["missing"]:
        failures.append(f"ref_missing:{item['ref']}")
    return failures


def _collect_target_commands(policy: Dict[str, Any]) -> List[str]:
    commands: List[str] = []
    for check in policy.get("required_checks", []):
        if isinstance(check, dict):
            commands.extend(_as_string_list(check.get("commands")))
    return commands


def _collect_evidence(policy: Dict[str, Any]) -> List[str]:
    evidence: List[str] = []
    for check in policy.get("required_checks", []):
        if isinstance(check, dict):
            evidence.extend(_as_string_list(check.get("evidence")))
    return sorted(set(evidence))


def validate_post_reboot_gpu_gdm_gateway_toolproxy_readiness_policy(payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
    payload = load_policy() if payload is None else payload
    policy = _policy(payload)
    failures = _policy_failures(payload)
    refs = _as_string_list(policy.get("registry_refs")) + _as_string_list(policy.get("docs_refs")) + _as_string_list(policy.get("example_refs"))
    refs_report = _refs_report(refs)
    commands = _collect_target_commands(policy)
    evidence = _collect_evidence(policy)
    summary = {
        "policy_id": policy.get("id"),
        "completion_state": policy.get("completion_state"),
        "completion_blocked": policy.get("completion_state") == BLOCKED_STATE,
        "target_machine_required": policy.get("target_machine_required") is True,
        "operator_approval_required": policy.get("operator_approval_required") is True,
        "safe_local_validator_only": policy.get("local_validator_only") is True,
        "required_check_count": len(policy.get("required_checks", [])) if isinstance(policy.get("required_checks"), list) else 0,
        "target_command_count": len(commands),
        "evidence_requirement_count": len(evidence),
    }
    metrics = {
        "required_checks": summary["required_check_count"],
        "target_commands": len(commands),
        "evidence_requirements": len(evidence),
        "resolved_refs": len(refs_report["resolved"]),
        "missing_refs": len(refs_report["missing"]),
        "failures": len(failures),
    }
    return {
        "apiVersion": API_VERSION,
        "kind": REPORT_KIND,
        "generated_at": _nowz(),
        "ok": not failures,
        "failures": failures,
        "post_reboot_gpu_gdm_gateway_toolproxy_summary": summary,
        "target_post_reboot_validation_command_manifest": commands,
        "evidence_requirements": evidence,
        "registry_attachment": refs_report,
        "docs_changelog_trace": sorted(REQUIRED_DOC_REFS),
        "blocked_completion_notice": (
            "Local contract validation passed, but the roadmap item remains open until reviewed "
            "target-machine post-reboot GPU/GDM/gateway/ToolProxy evidence exists."
        ),
        "metrics": metrics,
    }


def validate_example(payload: Dict[str, Any] | None = None, path: Path | str | None = None) -> Dict[str, Any]:
    if payload is None:
        if path is None:
            path = PACKAGE_ROOT.parent / "prelaunch" / "governance" / "post_reboot_gpu_gdm_gateway_toolproxy_readiness.example.json"
        payload = load_example(path)
    failures: List[str] = []
    if payload.get("apiVersion") != API_VERSION:
        failures.append("example_apiVersion_invalid")
    if payload.get("kind") != EXAMPLE_KIND:
        failures.append("example_kind_invalid")
    examples = payload.get("examples")
    if not isinstance(examples, list) or not examples:
        failures.append("examples_missing")
        examples = []
    for example in examples:
        if not isinstance(example, dict):
            failures.append("example_not_object")
            continue
        if example.get("completion_state") != BLOCKED_STATE:
            failures.append(f"example_completion_state_invalid:{example.get('id')}")
        evidence = set(_as_string_list(example.get("evidence")))
        for item in {"boot_id", "nvidia_smi_csv", "gateway_smoke_transcript", "toolproxy_smoke_json", "bundle_sha256"}:
            if item not in evidence:
                failures.append(f"example_evidence_missing:{example.get('id')}:{item}")
    return {"ok": not failures, "failures": failures, "example_count": len(examples)}


def gate_evidence(report: Dict[str, Any], *, artifact_uri: str) -> Dict[str, Any]:
    status = "passed" if report.get("ok") else "failed"
    return {
        "gate": "post_reboot_gpu_gdm_gateway_toolproxy_readiness",
        "status": status,
        "artifact_uri": artifact_uri,
        "policy_id": POLICY_ID,
        "completion_state": BLOCKED_STATE,
        "metrics": report.get("metrics", {}),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate post-reboot GPU/GDM/gateway/ToolProxy readiness policy.")
    parser.add_argument("--policy", default=str(DEFAULT_POLICY), help="Path to readiness policy JSON.")
    parser.add_argument("--example", help="Optional example evidence JSON to validate.")
    parser.add_argument("--gate-artifact", default="", help="Optional artifact URI for a gate evidence envelope.")
    parser.add_argument("--json", action="store_true", help="Print JSON report.")
    args = parser.parse_args(argv)

    report = validate_post_reboot_gpu_gdm_gateway_toolproxy_readiness_policy(load_policy(args.policy))
    if args.example:
        report["example_validation"] = validate_example(path=args.example)
        if not report["example_validation"]["ok"]:
            report["ok"] = False
            report["failures"].extend(report["example_validation"]["failures"])
    if args.gate_artifact:
        report["gate_evidence"] = gate_evidence(report, artifact_uri=args.gate_artifact)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print("OK" if report["ok"] else "FAIL")
        for failure in report["failures"]:
            print(f"- {failure}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
