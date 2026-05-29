#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/target_live_validation_readiness_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate the offline readiness contract for target-machine live NVIDIA/GDM/LLM evidence.
Inputs: target live validation readiness policy, examples, registry refs and canonical docs.
Outputs: JSON validation reports and summaries.
Side effects: None; this validator never executes live target commands.
Tests: noemaforge/tests/test_target_live_validation_readiness_runtime.py, QA and performance tests.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Sequence


API_VERSION = "noemaforge.target-live-validation-readiness/v1"
POLICY_KIND = "TargetLiveValidationReadinessPolicy"
EXAMPLE_KIND = "TargetLiveValidationReadinessExampleSet"
REPORT_KIND = "TargetLiveValidationReadinessValidationReport"
POLICY_ID = "target-live-validation-readiness-core"
VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
SAFE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
LLM_START_RE = re.compile(r"\bsystemctl\s+start\s+noemaforge-llama@", re.IGNORECASE)
REQUIRED_CHECK_IDS = {
    "trixie-preflight",
    "display-manager-gdm",
    "nvidia-gpu",
    "gateway-socket",
    "main-llm-manual-smoke",
    "toolproxy-live-llm-smoke",
    "gui-rescue-recovery",
    "evidence-archive",
}
REQUIRED_SAFETY_CONTROLS = {
    "no_auto_live_execution",
    "target_machine_required",
    "operator_approval_required_for_llm_start",
    "heavy_llm_manual_only",
    "evidence_archive_required",
    "redact_secrets",
    "local_validator_has_no_subprocess",
}
REQUIRED_OUTPUTS = {
    "readiness_summary",
    "blocked_completion_notice",
    "target_command_manifest",
    "evidence_requirements",
    "manual_llm_approval_gate",
    "registry_attachment",
    "docs_changelog_trace",
}
REQUIRED_DOC_REFS = {
    "noemaforge/docs/README.md",
    "noemaforge/docs/TODO.md",
    "noemaforge/docs/reference/PROJECT_CONTEXT.md",
    "noemaforge/docs/backlog/ROADMAP_AND_TODO.md",
    "noemaforge/docs/history/CHANGELOG.md",
    "noemaforge/docs/wiki/first-start/full-composite-real-launch-0.32.1.md",
}

SRC_DIR = Path(__file__).resolve().parent
PACKAGE_ROOT = SRC_DIR.parent
PROJECT_ROOT = PACKAGE_ROOT.parent
DEFAULT_POLICY = PACKAGE_ROOT / "configs" / "target-live-validation-readiness-policy.json"


def _nowz() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _display_path(path: Path) -> str:
    return str(path).replace(os.sep, "/")


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
    parts = PurePosixPath(text).parts
    return not any(part in {"", ".", ".."} for part in parts)


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
    if not SAFE_ID_RE.match(cid):
        failures.append(f"check_id_invalid:{cid}")
    if not str(check.get("title") or "").strip():
        failures.append(f"check_title_missing:{cid}")
    if check.get("live_target_required") is not True:
        failures.append(f"check_live_target_required_not_true:{cid}")
    commands = _as_string_list(check.get("commands"))
    evidence = _as_string_list(check.get("evidence"))
    gates = _as_string_list(check.get("completion_gates"))
    if not commands:
        failures.append(f"check_commands_empty:{cid}")
    if not evidence:
        failures.append(f"check_evidence_empty:{cid}")
    if not gates:
        failures.append(f"check_completion_gates_empty:{cid}")
    for command in commands:
        if LLM_START_RE.search(command) and check.get("requires_operator_approval") is not True:
            failures.append(f"check_llm_start_without_operator_approval:{cid}")
    if cid in {"main-llm-manual-smoke", "toolproxy-live-llm-smoke", "gui-rescue-recovery"} and check.get("requires_operator_approval") is not True:
        failures.append(f"check_operator_approval_required:{cid}")
    if "evidence_file_archived" not in gates and cid != "evidence-archive":
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
    if policy.get("activation_state") != "nvidia_gdm_llm_live_evidence_readiness":
        failures.append("policy_activation_state_invalid")
    if policy.get("completion_state") != "blocked_until_target_machine_evidence":
        failures.append("policy_completion_state_invalid")
    for key in ["require_registry_attachment", "require_docs_and_changelog_refs", "require_no_live_execution"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    blocked_refs = _as_string_list(policy.get("blocked_todo_refs"))
    if "Real NoemaForge live validation of NVIDIA/GDM/LLM services." not in blocked_refs:
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


def _example_failures(payload: Dict[str, Any], example_path: Path, *, project_root: Path = PROJECT_ROOT, package_root: Path = PACKAGE_ROOT) -> Dict[str, Any]:
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
        expected_checks = set(_as_string_list(scenario.get("expected_check_ids")))
        expected_outputs = set(_as_string_list(scenario.get("expected_outputs")))
        for cid in sorted(expected_checks - check_ids):
            failures.append(f"example_check_missing_from_policy:{sid}:{cid}")
        for output in sorted(expected_outputs - outputs):
            failures.append(f"example_output_missing_from_policy:{sid}:{output}")
    if not scenarios:
        failures.append("example_scenarios_empty")
    return {"failures": failures, "scenarios": len(scenarios)}


def validate_target_live_validation_readiness_policy(
    payload: Dict[str, Any],
    *,
    project_root: Path = PROJECT_ROOT,
    package_root: Path = PACKAGE_ROOT,
) -> Dict[str, Any]:
    policy = _policy(payload)
    checks = [item for item in policy.get("required_checks", []) if isinstance(item, dict)]
    command_count = sum(len(_as_string_list(item.get("commands"))) for item in checks)
    evidence_count = sum(len(_as_string_list(item.get("evidence"))) for item in checks)
    ref_report = _ref_failures(payload, project_root=project_root, package_root=package_root)
    example_path = project_root / "prelaunch" / "governance" / "target_live_validation_readiness.example.json"
    example_report = _example_failures(payload, example_path, project_root=project_root, package_root=package_root)
    failures = _policy_failures(payload) + ref_report["failures"] + example_report["failures"]
    normalized_checks = [
        {
            "id": str(item.get("id") or ""),
            "commands": _as_string_list(item.get("commands")),
            "evidence": _as_string_list(item.get("evidence")),
            "completion_gates": _as_string_list(item.get("completion_gates")),
            "requires_operator_approval": bool(item.get("requires_operator_approval")),
        }
        for item in checks
    ]
    return {
        "apiVersion": API_VERSION,
        "kind": REPORT_KIND,
        "id": POLICY_ID,
        "version": str(payload.get("version") or ""),
        "generated_at": _nowz(),
        "ok": not failures,
        "failures": failures,
        "readiness_summary": {
            "completion_blocked": True,
            "blocked_until": "target_machine_evidence",
            "safe_local_validator_only": True,
            "target_command_count": command_count,
            "required_evidence_count": evidence_count,
            "required_check_count": len(checks),
        },
        "blocked_completion_notice": "Live NVIDIA/GDM/LLM validation remains open until target-machine evidence is captured and archived.",
        "target_command_manifest": normalized_checks,
        "evidence_requirements": sorted({evidence for item in normalized_checks for evidence in item["evidence"]}),
        "resolved_refs": ref_report["resolved_refs"],
        "missing_refs": ref_report["missing_refs"],
        "example_scenarios": example_report["scenarios"],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate NoemaForge target live validation readiness policy.")
    parser.add_argument("--policy", default=str(DEFAULT_POLICY))
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(argv)
    report = validate_target_live_validation_readiness_policy(load_policy(args.policy))
    if args.summary:
        report = {
            "apiVersion": API_VERSION,
            "kind": "TargetLiveValidationReadinessSummary",
            "id": POLICY_ID,
            "ok": report["ok"],
            "failures": report["failures"],
            "metrics": report["readiness_summary"],
        }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
