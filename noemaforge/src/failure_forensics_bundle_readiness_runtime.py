#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/failure_forensics_bundle_readiness_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-21
Modified: 2026-05-21
Purpose: Validate the offline readiness contract for target failure forensics bundle evidence.
Inputs: Failure forensics bundle readiness policy, examples, registry refs and canonical docs.
Outputs: JSON validation reports and summaries.
Side effects: None; this validator never runs sudo, forensics, journal, systemd, upload or archive commands.
Tests: noemaforge/tests/test_failure_forensics_bundle_readiness_runtime.py, QA and performance tests.
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


API_VERSION = "noemaforge.failure-forensics-bundle-readiness/v1"
POLICY_KIND = "FailureForensicsBundleReadinessPolicy"
EXAMPLE_KIND = "FailureForensicsBundleReadinessExampleSet"
REPORT_KIND = "FailureForensicsBundleReadinessValidationReport"
POLICY_ID = "failure-forensics-bundle-readiness-core"
VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
SAFE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
PRIMARY_BLOCKED_TODO = "Run `sudo noemaforge forensics` after any launcher/runtime failure and inspect the bundle."
REQUIRED_CHECK_IDS = {
    "failure-trigger-baseline",
    "forensics-command-capture",
    "bundle-integrity",
    "redaction-inspection",
    "runtime-log-coverage",
    "inspection-followup",
}
REQUIRED_SAFETY_CONTROLS = {
    "no_auto_live_execution",
    "target_machine_required",
    "failure_context_required",
    "operator_approval_required",
    "archive_required",
    "redaction_required",
    "inspection_required",
    "local_validator_has_no_subprocess",
}
REQUIRED_OUTPUTS = {
    "failure_forensics_summary",
    "blocked_completion_notice",
    "target_forensics_command_manifest",
    "evidence_requirements",
    "inspection_followup_manifest",
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
FORBIDDEN_REMOTE_OR_MUTATING_TOKENS = (
    "--upload",
    "curl ",
    "scp ",
    "rsync ",
    "http://",
    "https://",
    "rm -",
)

SRC_DIR = Path(__file__).resolve().parent
PACKAGE_ROOT = SRC_DIR.parent
PROJECT_ROOT = PACKAGE_ROOT.parent
DEFAULT_POLICY = PACKAGE_ROOT / "configs" / "failure-forensics-bundle-readiness-policy.json"


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
    for token in FORBIDDEN_REMOTE_OR_MUTATING_TOKENS:
        if token in joined:
            failures.append(f"check_forbidden_remote_or_mutating_token:{cid}:{token.strip()}")
    if cid == "failure-trigger-baseline":
        for item in ["failure_timestamp", "failure_surface", "operator_failure_note"]:
            if item not in evidence:
                failures.append(f"check_failure_trigger_evidence_missing:{item}")
        for gate in ["failure_context_recorded", "target_host_recorded", "evidence_file_archived"]:
            if gate not in gates:
                failures.append(f"check_failure_trigger_gate_missing:{gate}")
    if cid == "forensics-command-capture":
        if check.get("requires_operator_approval") is not True:
            failures.append("check_operator_approval_required:forensics-command-capture")
        for command in ["sudo noemaforge forensics --dry-run", "sudo noemaforge forensics"]:
            if command not in commands:
                failures.append(f"check_forensics_command_missing:{command}")
        for gate in ["operator_approval_recorded", "dry_run_reviewed", "bundle_path_recorded", "evidence_file_archived"]:
            if gate not in gates:
                failures.append(f"check_forensics_command_gate_missing:{gate}")
    if cid == "bundle-integrity":
        for item in ["forensics_bundle_path", "bundle_sha256", "bundle_file_list", "bundle_size_bytes"]:
            if item not in evidence:
                failures.append(f"check_bundle_integrity_evidence_missing:{item}")
        for gate in ["bundle_exists", "bundle_sha256_recorded", "file_list_reviewed", "evidence_file_archived"]:
            if gate not in gates:
                failures.append(f"check_bundle_integrity_gate_missing:{gate}")
    if cid == "redaction-inspection":
        for item in ["redaction_manifest", "secret_scan_summary", "excluded_sensitive_paths"]:
            if item not in evidence:
                failures.append(f"check_redaction_evidence_missing:{item}")
        for gate in ["secrets_redacted", "model_weights_excluded", "vault_contents_excluded", "browser_profiles_excluded", "token_paths_excluded"]:
            if gate not in gates:
                failures.append(f"check_redaction_gate_missing:{gate}")
    if cid == "runtime-log-coverage":
        for item in ["failed_service_status", "journal_excerpt", "launcher_error_context", "firstboot_status", "admin_gui_log_tail"]:
            if item not in evidence:
                failures.append(f"check_runtime_log_evidence_missing:{item}")
        for gate in ["failure_context_recorded", "service_log_recorded", "journal_excerpt_recorded", "evidence_file_archived"]:
            if gate not in gates:
                failures.append(f"check_runtime_log_gate_missing:{gate}")
    if cid == "inspection-followup":
        for item in ["inspector_name_or_role", "findings_summary", "remediation_plan", "docs_update_decision"]:
            if item not in evidence:
                failures.append(f"check_inspection_evidence_missing:{item}")
        for gate in ["bundle_inspected", "blocker_or_fix_recorded", "canonical_docs_updated_after_review"]:
            if gate not in gates:
                failures.append(f"check_inspection_gate_missing:{gate}")
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
    if policy.get("activation_state") != "patched10_failure_forensics_bundle_readiness":
        failures.append("policy_activation_state_invalid")
    if policy.get("completion_state") != "blocked_until_target_failure_forensics_bundle_evidence":
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


def validate_failure_forensics_bundle_readiness_policy(
    payload: Dict[str, Any],
    *,
    project_root: Path = PROJECT_ROOT,
    package_root: Path = PACKAGE_ROOT,
    example_path: Path | None = None,
) -> Dict[str, Any]:
    if example_path is None:
        example_path = project_root / "prelaunch" / "governance" / "failure_forensics_bundle_readiness.example.json"
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
        "failure_forensics_summary": {
            "completion_blocked": _policy(payload).get("completion_state") == "blocked_until_target_failure_forensics_bundle_evidence",
            "target_machine_required": True,
            "safe_local_validator_only": True,
            "target_command_count": len(commands),
            "evidence_requirement_count": len(evidence),
        },
        "target_forensics_command_manifest": commands,
        "evidence_requirements": evidence,
        "resolved_refs": refs["resolved_refs"],
        "missing_refs": refs["missing_refs"],
    }


def gate_evidence(report: Dict[str, Any], *, artifact_uri: str) -> Dict[str, Any]:
    return {
        "apiVersion": API_VERSION,
        "kind": "FailureForensicsBundleReadinessGateEvidence",
        "created_at": _nowz(),
        "gate": "failure_forensics_bundle_readiness",
        "status": "passed" if report.get("ok") else "failed",
        "artifact_uri": artifact_uri,
        "metrics": dict(report.get("metrics") or {}),
        "failures": list(report.get("failures") or []),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate target failure forensics bundle readiness policy.")
    parser.add_argument("--policy", default=str(DEFAULT_POLICY))
    parser.add_argument("--example", default="")
    parser.add_argument("--summary", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    example_path = Path(args.example) if args.example else None
    report = validate_failure_forensics_bundle_readiness_policy(load_policy(args.policy), example_path=example_path)
    if args.summary:
        payload = {
            "ok": report["ok"],
            "completion_state": report["completion_state"],
            "metrics": report["metrics"],
            "failures": report["failures"],
        }
    else:
        payload = report
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
