#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/live_testbench_suite_readiness_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-21
Modified: 2026-05-21
Purpose: Validate the offline readiness contract for the target live testbench suite.
Inputs: Live testbench readiness policy, example evidence, registry refs and canonical docs.
Outputs: JSON validation reports and summaries.
Side effects: None; this validator never runs testbench, live suites, GPU probes, wiki-patch or archive commands.
Tests: noemaforge/tests/test_live_testbench_suite_readiness_runtime.py, QA and performance tests.
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


API_VERSION = "noemaforge.live-testbench-suite-readiness/v1"
POLICY_KIND = "LiveTestbenchSuiteReadinessPolicy"
EXAMPLE_KIND = "LiveTestbenchSuiteReadinessExampleSet"
REPORT_KIND = "LiveTestbenchSuiteReadinessValidationReport"
POLICY_ID = "live-testbench-suite-readiness-core"
BLOCKED_STATE = "blocked_until_target_live_testbench_suite_evidence"
PRIMARY_BLOCKED_TODO = "Run live testbench suite on NoemaForge: `noemaforge testbench run --suite live --include-live`."
VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
SAFE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
REQUIRED_CHECK_IDS = {
    "target-baseline",
    "operator-approval",
    "live-suite-catalog",
    "live-suite-run",
    "telemetry-artifacts",
    "baseline-compare-and-archive",
}
REQUIRED_SAFETY_CONTROLS = {
    "no_auto_live_execution",
    "target_machine_required",
    "operator_approval_required",
    "live_suite_requires_include_live",
    "resource_telemetry_required",
    "baseline_compare_required",
    "archive_required",
    "local_validator_has_no_subprocess",
}
REQUIRED_OUTPUTS = {
    "live_testbench_suite_summary",
    "blocked_completion_notice",
    "target_live_testbench_command_manifest",
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
    "noemaforge/docs/wiki/metrics/testbench-and-regression-metrics.md",
    "noemaforge/docs/wiki/pipelines/self-improvement-pipelines.md",
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
)
REQUIRED_COMMANDS: Mapping[str, Sequence[str]] = {
    "target-baseline": (
        "cat /proc/sys/kernel/random/boot_id",
        "noemaforge status --json",
        "noemaforge testbench catalog --json",
    ),
    "live-suite-catalog": (
        "noemaforge testbench catalog --json",
    ),
    "live-suite-run": (
        "noemaforge testbench run --suite live --include-live --json",
    ),
    "telemetry-artifacts": (
        "test -s <live-testbench-out>/selftest-report.json",
        "find <live-testbench-out>/cases -name result.json -print",
    ),
    "baseline-compare-and-archive": (
        "noemaforge testbench baseline --suite live --json",
        "noemaforge testbench report --json",
        "noemaforge wiki-patch create --report <live-testbench-out>/selftest-report.json --json",
        "sha256sum <live-testbench-archive>",
    ),
}
REQUIRED_EVIDENCE: Mapping[str, Sequence[str]] = {
    "target-baseline": (
        "boot_id",
        "target_timestamp",
        "target_host",
        "noemaforge_status_json",
        "testbench_catalog_json",
    ),
    "operator-approval": (
        "operator_approval_record",
        "approved_scope",
        "approved_target_host",
        "approval_timestamp",
    ),
    "live-suite-catalog": (
        "live_suite_case_ids",
        "include_live_flag_recorded",
        "live_case_count",
        "suite_catalog_digest",
    ),
    "live-suite-run": (
        "live_testbench_command",
        "live_testbench_exit_code",
        "live_testbench_stdout_json",
        "live_testbench_stderr_excerpt",
        "selftest_report_path",
    ),
    "telemetry-artifacts": (
        "case_result_paths",
        "duration_sec_metrics",
        "max_rss_kib_metrics",
        "disk_io_metrics",
        "gpu_ecc_metrics_or_na",
    ),
    "baseline-compare-and-archive": (
        "baseline_compare_json",
        "wiki_patch_manifest",
        "archive_path",
        "archive_sha256",
        "redaction_manifest",
        "review_followup_record",
    ),
}
REQUIRED_GATES: Mapping[str, Sequence[str]] = {
    "target-baseline": (
        "boot_id_recorded",
        "status_json_archived",
        "catalog_json_archived",
    ),
    "operator-approval": (
        "operator_approval_recorded",
        "scope_limited_to_live_testbench_suite",
        "evidence_file_archived",
    ),
    "live-suite-catalog": (
        "live_suite_cases_recorded",
        "include_live_flag_recorded",
        "catalog_digest_recorded",
    ),
    "live-suite-run": (
        "operator_approval_recorded",
        "include_live_flag_used",
        "suite_exit_code_recorded",
        "selftest_report_archived",
    ),
    "telemetry-artifacts": (
        "case_results_archived",
        "resource_metrics_recorded",
        "gpu_ecc_metrics_recorded_or_marked_na",
    ),
    "baseline-compare-and-archive": (
        "baseline_compare_recorded",
        "wiki_patch_manifest_recorded",
        "archive_sha256_recorded",
        "review_followup_recorded",
    ),
}

SRC_DIR = Path(__file__).resolve().parent
PACKAGE_ROOT = SRC_DIR.parent
PROJECT_ROOT = PACKAGE_ROOT.parent
DEFAULT_POLICY = PACKAGE_ROOT / "configs" / "live-testbench-suite-readiness-policy.json"


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
    if cid in {"operator-approval", "live-suite-run", "baseline-compare-and-archive"}:
        if check.get("requires_operator_approval") is not True:
            failures.append(f"check_operator_approval_required:{cid}")
    for token in FORBIDDEN_COMMAND_TOKENS:
        if token in joined:
            failures.append(f"check_forbidden_token:{cid}:{token.strip()}")
    _require_items(cid, "command", REQUIRED_COMMANDS.get(cid, ()), commands, failures)
    _require_items(cid, "evidence", REQUIRED_EVIDENCE.get(cid, ()), evidence, failures)
    _require_items(cid, "gate", REQUIRED_GATES.get(cid, ()), gates, failures)
    if cid == "live-suite-run" and "--include-live" not in joined:
        failures.append("check_include_live_flag_missing:live-suite-run")
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


def validate_live_testbench_suite_readiness_policy(payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
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
        "live_testbench_suite_summary": summary,
        "target_live_testbench_command_manifest": commands,
        "evidence_requirements": evidence,
        "registry_attachment": refs_report,
        "docs_changelog_trace": sorted(REQUIRED_DOC_REFS),
        "blocked_completion_notice": (
            "Local contract validation passed, but the live testbench TODO remains open until "
            "reviewed NoemaForge target-machine suite evidence exists."
        ),
        "metrics": metrics,
    }


def validate_example(payload: Dict[str, Any] | None = None, path: Path | str | None = None) -> Dict[str, Any]:
    if payload is None:
        if path is None:
            path = PACKAGE_ROOT.parent / "prelaunch" / "governance" / "live_testbench_suite_readiness.example.json"
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
        for item in {
            "live_testbench_stdout_json",
            "selftest_report_path",
            "duration_sec_metrics",
            "baseline_compare_json",
            "archive_sha256",
        }:
            if item not in evidence:
                failures.append(f"example_evidence_missing:{example.get('id')}:{item}")
    return {"ok": not failures, "failures": failures, "example_count": len(examples)}


def gate_evidence(report: Dict[str, Any], *, artifact_uri: str) -> Dict[str, Any]:
    return {
        "gate": "live_testbench_suite_readiness",
        "status": "passed" if report.get("ok") else "failed",
        "artifact_uri": artifact_uri,
        "policy_id": POLICY_ID,
        "completion_state": BLOCKED_STATE,
        "metrics": report.get("metrics", {}),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate live testbench suite readiness policy.")
    parser.add_argument("--policy", default=str(DEFAULT_POLICY), help="Path to readiness policy JSON.")
    parser.add_argument("--example", help="Optional example evidence JSON to validate.")
    parser.add_argument("--gate-artifact", default="", help="Optional artifact URI for a gate evidence envelope.")
    parser.add_argument("--json", action="store_true", help="Print JSON report.")
    args = parser.parse_args(argv)

    report = validate_live_testbench_suite_readiness_policy(load_policy(args.policy))
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
