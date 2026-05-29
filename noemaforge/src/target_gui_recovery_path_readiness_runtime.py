#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/target_gui_recovery_path_readiness_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-21
Modified: 2026-05-21
Purpose: Validate the offline readiness contract for target GUI recovery path evidence.
Inputs: Target GUI recovery path readiness policy, examples, registry refs and canonical docs.
Outputs: JSON validation reports and summaries.
Side effects: None; this validator never runs sudo, pause, gui-rescue, systemd or archive commands.
Tests: noemaforge/tests/test_target_gui_recovery_path_readiness_runtime.py, QA and performance tests.
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


API_VERSION = "noemaforge.target-gui-recovery-path-readiness/v1"
POLICY_KIND = "TargetGuiRecoveryPathReadinessPolicy"
EXAMPLE_KIND = "TargetGuiRecoveryPathReadinessExampleSet"
REPORT_KIND = "TargetGuiRecoveryPathReadinessValidationReport"
POLICY_ID = "target-gui-recovery-path-readiness-core"
VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
SAFE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
PRIMARY_BLOCKED_TODO = "Confirm GUI recovery path on target hardware: `sudo noemaforge pause --wait` then `sudo noemaforge gui-rescue --wait`."
REQUIRED_CHECK_IDS = {
    "display-baseline",
    "pause-command-capture",
    "gui-rescue-command-capture",
    "recovery-state-verification",
    "gui-recovery-archive",
    "operator-inspection-followup",
}
REQUIRED_SAFETY_CONTROLS = {
    "no_auto_live_execution",
    "target_machine_required",
    "operator_approval_required",
    "pause_before_rescue_required",
    "display_state_required",
    "nologin_guard_required",
    "archive_required",
    "local_validator_has_no_subprocess",
}
REQUIRED_OUTPUTS = {
    "target_gui_recovery_summary",
    "blocked_completion_notice",
    "target_gui_recovery_command_manifest",
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
FORBIDDEN_LOCAL_OR_REMOTE_TOKENS = (
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
DEFAULT_POLICY = PACKAGE_ROOT / "configs" / "target-gui-recovery-path-readiness-policy.json"


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
    for token in FORBIDDEN_LOCAL_OR_REMOTE_TOKENS:
        if token in joined:
            failures.append(f"check_forbidden_token:{cid}:{token.strip()}")
    if cid in {"pause-command-capture", "gui-rescue-command-capture"} and check.get("requires_operator_approval") is not True:
        failures.append(f"check_operator_approval_required:{cid}")
    if cid == "display-baseline":
        for item in ["display_manager_state", "gdm_state", "graphical_target_state", "login_seat_state"]:
            if item not in evidence:
                failures.append(f"check_display_baseline_evidence_missing:{item}")
        for gate in ["display_manager_recorded", "graphical_target_recorded", "evidence_file_archived"]:
            if gate not in gates:
                failures.append(f"check_display_baseline_gate_missing:{gate}")
    if cid == "pause-command-capture":
        if "sudo noemaforge pause --wait" not in commands:
            failures.append("check_pause_command_missing")
        for gate in ["operator_approval_recorded", "pause_command_completed", "evidence_file_archived"]:
            if gate not in gates:
                failures.append(f"check_pause_gate_missing:{gate}")
    if cid == "gui-rescue-command-capture":
        if "sudo noemaforge gui-rescue --wait" not in commands:
            failures.append("check_gui_rescue_command_missing")
        for gate in ["operator_approval_recorded", "pause_precedes_rescue", "gui_rescue_command_completed", "evidence_file_archived"]:
            if gate not in gates:
                failures.append(f"check_gui_rescue_gate_missing:{gate}")
    if cid == "recovery-state-verification":
        for item in ["post_rescue_display_manager_state", "post_rescue_gdm_state", "post_rescue_graphical_target_state", "post_rescue_nologin_state"]:
            if item not in evidence:
                failures.append(f"check_recovery_state_evidence_missing:{item}")
        for gate in ["display_recovered", "run_nologin_absent", "operator_can_reach_login_or_desktop", "evidence_file_archived"]:
            if gate not in gates:
                failures.append(f"check_recovery_state_gate_missing:{gate}")
    if cid == "gui-recovery-archive":
        for item in ["forensics_bundle_path", "bundle_sha256", "gui_recovery_transcript", "redaction_manifest"]:
            if item not in evidence:
                failures.append(f"check_archive_evidence_missing:{item}")
        for gate in ["bundle_exists", "bundle_sha256_recorded", "secrets_redacted", "canonical_docs_updated_after_review"]:
            if gate not in gates:
                failures.append(f"check_archive_gate_missing:{gate}")
    if cid == "operator-inspection-followup":
        for item in ["inspector_name_or_role", "findings_summary", "followup_decision", "linked_todo_or_fix_id"]:
            if item not in evidence:
                failures.append(f"check_inspection_evidence_missing:{item}")
        for gate in ["target_gui_path_inspected", "blocker_or_fix_recorded", "docs_update_decision_recorded"]:
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
    if policy.get("activation_state") != "patched10_target_gui_recovery_path_readiness":
        failures.append("policy_activation_state_invalid")
    if policy.get("completion_state") != "blocked_until_target_gui_recovery_path_evidence":
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


def validate_target_gui_recovery_path_readiness_policy(
    payload: Dict[str, Any],
    *,
    project_root: Path = PROJECT_ROOT,
    package_root: Path = PACKAGE_ROOT,
    example_path: Path | None = None,
) -> Dict[str, Any]:
    if example_path is None:
        example_path = project_root / "prelaunch" / "governance" / "target_gui_recovery_path_readiness.example.json"
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
        "target_gui_recovery_summary": {
            "completion_blocked": _policy(payload).get("completion_state") == "blocked_until_target_gui_recovery_path_evidence",
            "target_machine_required": True,
            "safe_local_validator_only": True,
            "target_command_count": len(commands),
            "evidence_requirement_count": len(evidence),
        },
        "target_gui_recovery_command_manifest": commands,
        "evidence_requirements": evidence,
        "resolved_refs": refs["resolved_refs"],
        "missing_refs": refs["missing_refs"],
    }


def gate_evidence(report: Dict[str, Any], *, artifact_uri: str) -> Dict[str, Any]:
    return {
        "apiVersion": API_VERSION,
        "kind": "TargetGuiRecoveryPathReadinessGateEvidence",
        "created_at": _nowz(),
        "gate": "target_gui_recovery_path_readiness",
        "status": "passed" if report.get("ok") else "failed",
        "artifact_uri": artifact_uri,
        "metrics": dict(report.get("metrics") or {}),
        "failures": list(report.get("failures") or []),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate target GUI recovery path readiness policy.")
    parser.add_argument("--policy", default=str(DEFAULT_POLICY))
    parser.add_argument("--example", default="")
    parser.add_argument("--summary", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    example_path = Path(args.example) if args.example else None
    report = validate_target_gui_recovery_path_readiness_policy(load_policy(args.policy), example_path=example_path)
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
