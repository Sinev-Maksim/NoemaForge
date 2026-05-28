#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/final_gui_scenario_replay_readiness_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-21
Modified: 2026-05-21
Purpose: Validate the offline readiness contract for final Admin GUI scenario replay evidence.
Inputs: Final GUI scenario replay readiness policy, example evidence, registry refs and canonical docs.
Outputs: JSON validation reports and summaries.
Side effects: None; this validator never runs Admin GUI, pipeline, Dev Team, model-evolution, browser or archive commands.
Tests: noemaforge/tests/test_final_gui_scenario_replay_readiness_runtime.py, QA and performance tests.
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


API_VERSION = "noemaforge.final-gui-scenario-replay-readiness/v1"
POLICY_KIND = "FinalGuiScenarioReplayReadinessPolicy"
EXAMPLE_KIND = "FinalGuiScenarioReplayReadinessExampleSet"
REPORT_KIND = "FinalGuiScenarioReplayReadinessValidationReport"
POLICY_ID = "final-gui-scenario-replay-readiness-core"
BLOCKED_STATE = "blocked_until_target_final_gui_scenario_replay_evidence"
PRIMARY_BLOCKED_TODO = (
    "Run `0.32.1` on the target machine from GUI start through Admin greeting, routed pipeline launch, "
    "Dev Team action and model-evolution action."
)
SECONDARY_BLOCKED_TODO = "On NoemaForge, replay the final GUI scenario and capture transcript before bumping to `0.32.1`."
REQUIRED_SHOWCASE_ID = "polished_admin_gui_guided_scenario"
VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
SAFE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
REQUIRED_CHECK_IDS = {
    "target-baseline",
    "operator-approval",
    "admin-gui-start",
    "admin-greeting",
    "routed-pipeline-launch",
    "dev-team-action",
    "model-evolution-action",
    "transcript-and-archive",
}
REQUIRED_SAFETY_CONTROLS = {
    "no_auto_gui_execution",
    "target_machine_required",
    "operator_approval_required",
    "public_showcase_selection_required",
    "transcript_required",
    "artifact_hashes_required",
    "archive_required",
    "local_validator_has_no_subprocess",
}
REQUIRED_OUTPUTS = {
    "final_gui_scenario_replay_summary",
    "blocked_completion_notice",
    "target_gui_scenario_command_manifest",
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
    "noemaforge/docs/wiki/gui/admin-console-and-admin-routing-0.32.1.md",
    "noemaforge/docs/wiki/evolution/model-evolution-control-plane-0.32.1.md",
    "noemaforge/docs/wiki/gui/persona-portraits-and-dashboard-0.32.1.md",
}
FORBIDDEN_COMMAND_TOKENS = (
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
    "browser ",
)
REQUIRED_COMMANDS: Mapping[str, Sequence[str]] = {
    "target-baseline": (
        "cat /proc/sys/kernel/random/boot_id",
        "date --iso-8601=seconds",
        "hostnamectl --static || hostname",
        "noemaforge status --json",
        "noemaforge public-showcase scenario --id polished_admin_gui_guided_scenario --json",
    ),
    "operator-approval": (
        "printf '%s\\n' '<operator records approval before final Admin GUI replay>'",
    ),
    "admin-gui-start": (
        "noemaforge admin-gui start --target --scenario polished_admin_gui_guided_scenario --json",
        "noemaforge admin-gui health --json",
    ),
    "admin-greeting": (
        "noemaforge admin-gui transcript --capture admin-greeting --json",
    ),
    "routed-pipeline-launch": (
        "noemaforge admin-gui route --scenario polished_admin_gui_guided_scenario --step routed-pipeline-launch --json",
        "noemaforge pipeline status --last --json",
    ),
    "dev-team-action": (
        "noemaforge admin-gui route --scenario polished_admin_gui_guided_scenario --step dev-team-action --json",
        "noemaforge dev-team status --last --json",
    ),
    "model-evolution-action": (
        "noemaforge admin-gui route --scenario polished_admin_gui_guided_scenario --step model-evolution-action --json",
        "noemaforge model-evolution status --last --json",
    ),
    "transcript-and-archive": (
        "noemaforge admin-gui transcript --scenario polished_admin_gui_guided_scenario --json",
        "noemaforge admin-gui artifact-manifest --scenario polished_admin_gui_guided_scenario --json",
        "sha256sum <final-gui-scenario-archive>",
    ),
}
REQUIRED_EVIDENCE: Mapping[str, Sequence[str]] = {
    "target-baseline": (
        "boot_id",
        "target_timestamp",
        "target_host",
        "noemaforge_status_json",
        "version_under_test",
        "public_showcase_scenario_json",
        "selected_showcase",
        "scenario_id",
    ),
    "operator-approval": (
        "operator_approval_record",
        "approved_scope",
        "approved_target_host",
        "approval_timestamp",
    ),
    "admin-gui-start": (
        "admin_gui_start_json",
        "admin_gui_health_json",
        "admin_gui_pid_or_session",
        "gui_screenshot_refs",
    ),
    "admin-greeting": (
        "admin_greeting_transcript",
        "admin_greeting_response_json",
        "greeting_language_observed",
    ),
    "routed-pipeline-launch": (
        "routed_pipeline_request",
        "routed_pipeline_response_json",
        "pipeline_artifact_manifest",
        "pipeline_route_name",
    ),
    "dev-team-action": (
        "dev_team_request",
        "dev_team_response_json",
        "dev_team_artifact_manifest",
        "dev_team_route_name",
    ),
    "model-evolution-action": (
        "model_evolution_request",
        "model_evolution_response_json",
        "model_evolution_artifact_manifest",
        "rollback_plan_ref",
    ),
    "transcript-and-archive": (
        "full_transcript_path",
        "artifact_hash_manifest",
        "archive_path",
        "archive_sha256",
        "redaction_manifest",
        "review_followup_record",
        "version_bump_guard_record",
    ),
}
REQUIRED_GATES: Mapping[str, Sequence[str]] = {
    "target-baseline": (
        "boot_id_recorded",
        "status_json_archived",
        "version_under_test_recorded",
        "public_showcase_scenario_recorded",
        "selected_showcase_matches_policy",
    ),
    "operator-approval": (
        "operator_approval_recorded",
        "scope_limited_to_final_gui_scenario_replay",
        "evidence_file_archived",
    ),
    "admin-gui-start": (
        "admin_gui_started_on_target",
        "admin_gui_health_recorded",
        "initial_screenshot_archived",
    ),
    "admin-greeting": (
        "admin_greeting_transcript_recorded",
        "admin_greeting_response_archived",
        "language_observation_recorded",
    ),
    "routed-pipeline-launch": (
        "routed_pipeline_request_recorded",
        "pipeline_response_archived",
        "pipeline_artifact_manifest_archived",
    ),
    "dev-team-action": (
        "dev_team_request_recorded",
        "dev_team_response_archived",
        "dev_team_artifact_manifest_archived",
    ),
    "model-evolution-action": (
        "model_evolution_request_recorded",
        "model_evolution_response_archived",
        "model_evolution_artifact_manifest_archived",
        "rollback_plan_recorded",
    ),
    "transcript-and-archive": (
        "full_transcript_archived",
        "artifact_hash_manifest_recorded",
        "archive_sha256_recorded",
        "redaction_manifest_recorded",
        "review_followup_recorded",
        "version_bump_guard_recorded",
    ),
}

SRC_DIR = Path(__file__).resolve().parent
PACKAGE_ROOT = SRC_DIR.parent
PROJECT_ROOT = PACKAGE_ROOT.parent
DEFAULT_POLICY = PACKAGE_ROOT / "configs" / "final-gui-scenario-replay-readiness-policy.json"


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
    if cid in {"operator-approval", "admin-gui-start", "transcript-and-archive"}:
        if check.get("requires_operator_approval") is not True:
            failures.append(f"check_operator_approval_required:{cid}")
    for token in FORBIDDEN_COMMAND_TOKENS:
        if token in joined:
            failures.append(f"check_forbidden_token:{cid}:{token.strip()}")
    _require_items(cid, "command", REQUIRED_COMMANDS.get(cid, ()), commands, failures)
    _require_items(cid, "evidence", REQUIRED_EVIDENCE.get(cid, ()), evidence, failures)
    _require_items(cid, "gate", REQUIRED_GATES.get(cid, ()), gates, failures)
    if cid == "target-baseline" and REQUIRED_SHOWCASE_ID not in joined:
        failures.append(f"check_required_showcase_missing:{cid}:{REQUIRED_SHOWCASE_ID}")
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
    if policy.get("blocked_todo") != PRIMARY_BLOCKED_TODO:
        failures.append("policy_blocked_todo_invalid")
    if policy.get("secondary_blocked_todo") != SECONDARY_BLOCKED_TODO:
        failures.append("policy_secondary_blocked_todo_invalid")
    if policy.get("required_showcase_id") != REQUIRED_SHOWCASE_ID:
        failures.append("policy_required_showcase_id_invalid")
    if policy.get("local_validator_only") is not True:
        failures.append("policy_local_validator_only_not_true")
    if policy.get("target_machine_required") is not True:
        failures.append("policy_target_machine_required_not_true")
    if policy.get("operator_approval_required") is not True:
        failures.append("policy_operator_approval_required_not_true")

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


def validate_final_gui_scenario_replay_readiness_policy(payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
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
        "required_showcase_id": policy.get("required_showcase_id"),
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
        "final_gui_scenario_replay_summary": summary,
        "target_gui_scenario_command_manifest": commands,
        "evidence_requirements": evidence,
        "registry_attachment": refs_report,
        "docs_changelog_trace": sorted(REQUIRED_DOC_REFS),
        "blocked_completion_notice": (
            "Local contract validation passed, but the final GUI scenario replay TODO remains open until "
            "reviewed NoemaForge target-machine transcript and artifact evidence exists."
        ),
        "metrics": metrics,
    }


def validate_example(payload: Dict[str, Any] | None = None, path: Path | str | None = None) -> Dict[str, Any]:
    if payload is None:
        if path is None:
            path = PACKAGE_ROOT.parent / "prelaunch" / "governance" / "final_gui_scenario_replay_readiness.example.json"
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
        if example.get("scenario_id") != REQUIRED_SHOWCASE_ID:
            failures.append(f"example_required_showcase_invalid:{example.get('id')}")
        evidence = set(_as_string_list(example.get("evidence")))
        for item in {
            "admin_greeting_transcript",
            "routed_pipeline_response_json",
            "dev_team_response_json",
            "model_evolution_response_json",
            "full_transcript_path",
            "archive_sha256",
            "version_bump_guard_record",
        }:
            if item not in evidence:
                failures.append(f"example_evidence_missing:{example.get('id')}:{item}")
    return {"ok": not failures, "failures": failures, "example_count": len(examples)}


def gate_evidence(report: Dict[str, Any], *, artifact_uri: str) -> Dict[str, Any]:
    return {
        "gate": "final_gui_scenario_replay_readiness",
        "status": "passed" if report.get("ok") else "failed",
        "artifact_uri": artifact_uri,
        "policy_id": POLICY_ID,
        "completion_state": BLOCKED_STATE,
        "metrics": report.get("metrics", {}),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate final GUI scenario replay readiness policy.")
    parser.add_argument("--policy", default=str(DEFAULT_POLICY), help="Path to readiness policy JSON.")
    parser.add_argument("--example", help="Optional example evidence JSON to validate.")
    parser.add_argument("--gate-artifact", default="", help="Optional artifact URI for a gate evidence envelope.")
    parser.add_argument("--json", action="store_true", help="Print JSON report.")
    args = parser.parse_args(argv)

    report = validate_final_gui_scenario_replay_readiness_policy(load_policy(args.policy))
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
