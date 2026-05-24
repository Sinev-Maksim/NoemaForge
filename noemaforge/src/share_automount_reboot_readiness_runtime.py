#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/share_automount_reboot_readiness_runtime.py
Zone: release/package
Version: 0.31.21.alpha
Created: 2026-05-21
Modified: 2026-05-21
Purpose: Validate the offline readiness contract for share automount reboot evidence.
Inputs: Share automount reboot readiness policy, examples, registry refs and canonical docs.
Outputs: JSON validation reports and summaries.
Side effects: None; this validator never runs reboot, mount, systemd or forensics commands.
Tests: noemaforge/tests/test_share_automount_reboot_readiness_runtime.py, QA and performance tests.
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


API_VERSION = "noemaforge.share-automount-reboot-readiness/v1"
POLICY_KIND = "ShareAutomountRebootReadinessPolicy"
EXAMPLE_KIND = "ShareAutomountRebootReadinessExampleSet"
REPORT_KIND = "ShareAutomountRebootReadinessValidationReport"
POLICY_ID = "share-automount-reboot-readiness-core"
VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
SAFE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
REQUIRED_CHECK_IDS = {
    "share-mount-baseline",
    "operator-approved-reboot-plan",
    "post-reboot-emergency-guard",
    "post-reboot-share-access",
    "share-reboot-evidence-archive",
}
REQUIRED_SAFETY_CONTROLS = {
    "no_auto_reboot_execution",
    "target_machine_required",
    "operator_approval_required",
    "nofail_automount_required",
    "emergency_mode_absence_required",
    "post_reboot_share_access_required",
    "forensics_archive_required",
    "local_validator_has_no_subprocess",
}
REQUIRED_OUTPUTS = {
    "share_reboot_readiness_summary",
    "blocked_completion_notice",
    "target_reboot_command_manifest",
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
    "noemaforge/docs/wiki/first-start/full-composite-real-launch-0.31.13.alpha-patched1.md",
}

SRC_DIR = Path(__file__).resolve().parent
PACKAGE_ROOT = SRC_DIR.parent
PROJECT_ROOT = PACKAGE_ROOT.parent
DEFAULT_POLICY = PACKAGE_ROOT / "configs" / "share-automount-reboot-readiness-policy.json"


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
    if cid == "operator-approved-reboot-plan" and check.get("requires_operator_approval") is not True:
        failures.append("check_operator_approval_required:operator-approved-reboot-plan")
    if cid == "share-mount-baseline":
        for token in ["/mnt/noemaforge-share", "nofail", "x-systemd.automount"]:
            if token not in joined:
                failures.append(f"check_share_baseline_token_missing:{token}")
    if cid == "post-reboot-emergency-guard":
        for gate in ["boot_id_changed_after_reboot", "emergency_target_inactive", "rescue_target_inactive"]:
            if gate not in gates:
                failures.append(f"check_emergency_guard_gate_missing:{gate}")
    if cid == "post-reboot-share-access":
        if "/mnt/noemaforge-share" not in joined:
            failures.append("check_post_reboot_share_path_missing")
        if "share_path_reachable_after_reboot" not in gates:
            failures.append("check_share_reachable_gate_missing")
    if cid != "share-reboot-evidence-archive" and "evidence_file_archived" not in gates:
        failures.append(f"check_archive_gate_missing:{cid}")
    if cid == "share-reboot-evidence-archive" and "bundle_sha256_recorded" not in gates:
        failures.append("check_archive_bundle_sha_missing")
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
    if policy.get("activation_state") != "patched10_share_automount_reboot_readiness":
        failures.append("policy_activation_state_invalid")
    if policy.get("completion_state") != "blocked_until_target_share_reboot_evidence":
        failures.append("policy_completion_state_invalid")
    for key in ["require_registry_attachment", "require_docs_and_changelog_refs", "require_no_live_execution"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    blocked_refs = _as_string_list(policy.get("blocked_todo_refs"))
    if "Confirm share automount lines do not re-enter emergency mode after reboot." not in blocked_refs:
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


def validate_share_automount_reboot_readiness_policy(
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
    example_path = project_root / "prelaunch" / "governance" / "share_automount_reboot_readiness.example.json"
    example_report = _example_failures(payload, example_path)
    failures = _policy_failures(payload) + ref_report["failures"] + example_report["failures"]
    command_manifest = [
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
        "share_reboot_readiness_summary": {
            "completion_blocked": True,
            "blocked_until": "target_share_reboot_evidence",
            "safe_local_validator_only": True,
            "target_machine_required": True,
            "target_command_count": command_count,
            "required_check_count": len(checks),
            "required_evidence_count": evidence_count,
        },
        "blocked_completion_notice": "Share automount reboot confirmation remains open until target fstab/unit, reboot, emergency guard, share access and archive evidence are captured and reviewed.",
        "target_reboot_command_manifest": command_manifest,
        "evidence_requirements": sorted({evidence for item in command_manifest for evidence in item["evidence"]}),
        "resolved_refs": ref_report["resolved_refs"],
        "missing_refs": ref_report["missing_refs"],
        "example_scenarios": example_report["scenarios"],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate NoemaForge share automount reboot readiness policy.")
    parser.add_argument("--policy", default=str(DEFAULT_POLICY))
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(argv)
    report = validate_share_automount_reboot_readiness_policy(load_policy(args.policy))
    if args.summary:
        report = {
            "apiVersion": API_VERSION,
            "kind": "ShareAutomountRebootReadinessSummary",
            "id": POLICY_ID,
            "ok": report["ok"],
            "failures": report["failures"],
            "metrics": report["share_reboot_readiness_summary"],
        }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
