#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/media_backend_selection_readiness_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-21
Modified: 2026-05-21
Purpose: Validate the offline readiness contract for explicit live-media backend selection.
Inputs: Media backend selection readiness policy, examples, registry refs and canonical docs.
Outputs: JSON validation reports and summaries.
Side effects: None; this validator never starts media backends, captures devices or downloads model weights.
Tests: noemaforge/tests/test_media_backend_selection_readiness_runtime.py, QA and performance tests.
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


API_VERSION = "noemaforge.media-backend-selection-readiness/v1"
POLICY_KIND = "MediaBackendSelectionReadinessPolicy"
EXAMPLE_KIND = "MediaBackendSelectionReadinessExampleSet"
REPORT_KIND = "MediaBackendSelectionReadinessValidationReport"
POLICY_ID = "media-backend-selection-readiness-core"
VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
SAFE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
REQUIRED_BACKEND_SLOTS = {
    "vlm",
    "stt",
    "tts",
    "music_generation",
    "image_generation",
    "video_generation",
    "segmentation_masks",
}
PRIVACY_GATED_SLOTS = {"stt", "segmentation_masks"}
REQUIRED_CHECK_IDS = {
    "backend-selection-record",
    "adapter-contract-surface",
    "privacy-consent-boundary",
    "telemetry-selftest-boundary",
    "target-live-media-smoke",
}
REQUIRED_SAFETY_CONTROLS = {
    "explicit_backend_selection_required",
    "target_machine_validation_required",
    "operator_approval_required",
    "no_auto_backend_start",
    "no_weight_download",
    "privacy_gate_required",
    "telemetry_required",
    "plan_only_fallback_required",
    "local_validator_has_no_subprocess",
}
REQUIRED_OUTPUTS = {
    "media_backend_selection_summary",
    "blocked_completion_notice",
    "backend_slot_manifest",
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
    "noemaforge/docs/wiki/multimodal/multimodal-vault-readiness-0.32.1.md",
}
PRIMARY_TODO = "Add final live-media backend adapters after explicit backend selection."

SRC_DIR = Path(__file__).resolve().parent
PACKAGE_ROOT = SRC_DIR.parent
PROJECT_ROOT = PACKAGE_ROOT.parent
DEFAULT_POLICY = PACKAGE_ROOT / "configs" / "media-backend-selection-readiness-policy.json"


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


def _slot_failures(slot: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    sid = str(slot.get("id") or "")
    if not SAFE_ID_RE.match(sid):
        failures.append(f"slot_id_invalid:{sid}")
    if not str(slot.get("title") or "").strip():
        failures.append(f"slot_title_missing:{sid}")
    if not _as_string_list(slot.get("artifact_classes")):
        failures.append(f"slot_artifact_classes_empty:{sid}")
    if slot.get("explicit_selection_required") is not True:
        failures.append(f"slot_explicit_selection_not_true:{sid}")
    if slot.get("target_smoke_required") is not True:
        failures.append(f"slot_target_smoke_not_true:{sid}")
    if sid in PRIVACY_GATED_SLOTS and slot.get("privacy_gate_required") is not True:
        failures.append(f"slot_privacy_gate_missing:{sid}")
    if str(slot.get("telemetry_profile") or "") != "media_adapter_telemetry":
        failures.append(f"slot_telemetry_profile_invalid:{sid}")
    return failures


def _check_failures(check: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    cid = str(check.get("id") or "")
    evidence = _as_string_list(check.get("evidence"))
    gates = _as_string_list(check.get("completion_gates"))
    joined = " ".join(evidence + gates)
    if not SAFE_ID_RE.match(cid):
        failures.append(f"check_id_invalid:{cid}")
    if check.get("target_evidence_required") is not True:
        failures.append(f"check_target_evidence_required_not_true:{cid}")
    if not evidence:
        failures.append(f"check_evidence_empty:{cid}")
    if not gates:
        failures.append(f"check_completion_gates_empty:{cid}")
    if cid in {"backend-selection-record", "privacy-consent-boundary", "target-live-media-smoke"} and check.get("requires_operator_approval") is not True:
        failures.append(f"check_operator_approval_required:{cid}")
    if cid == "backend-selection-record":
        for token in ["operator_selection_record", "selected_backend_id", "plan_only_fallback"]:
            if token not in evidence:
                failures.append(f"check_backend_selection_evidence_missing:{token}")
    if cid == "adapter-contract-surface":
        for token in ["input_schema", "output_manifest_schema", "artifact_manifest"]:
            if token not in evidence:
                failures.append(f"check_adapter_contract_evidence_missing:{token}")
    if cid == "privacy-consent-boundary":
        for gate in ["capture_default_off", "operator_consent_recorded", "no_autostart_recorded"]:
            if gate not in gates:
                failures.append(f"check_privacy_gate_missing:{gate}")
    if cid == "telemetry-selftest-boundary":
        for token in ["media_adapter_telemetry_report", "plan_only_selftest_report", "resource_metrics"]:
            if token not in joined:
                failures.append(f"check_telemetry_token_missing:{token}")
    if cid == "target-live-media-smoke":
        for gate in ["target_smoke_transcript_archived", "artifact_sha256_recorded", "operator_review_recorded"]:
            if gate not in gates:
                failures.append(f"check_live_smoke_gate_missing:{gate}")
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
    if policy.get("activation_state") != "media_backend_selection_readiness":
        failures.append("policy_activation_state_invalid")
    if policy.get("completion_state") != "blocked_until_explicit_media_backend_selection":
        failures.append("policy_completion_state_invalid")
    for key in ["require_registry_attachment", "require_docs_and_changelog_refs", "require_no_live_execution"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    if PRIMARY_TODO not in _as_string_list(policy.get("blocked_todo_refs")):
        failures.append("policy_primary_blocked_todo_missing")
    controls = policy.get("required_safety_controls") if isinstance(policy.get("required_safety_controls"), dict) else {}
    for control in REQUIRED_SAFETY_CONTROLS:
        if controls.get(control) is not True:
            failures.append(f"policy_safety_control_missing:{control}")
    slots = policy.get("required_backend_slots")
    if not isinstance(slots, list):
        failures.append("policy_backend_slots_not_list")
        slots = []
    seen_slots = set()
    for raw in slots:
        if not isinstance(raw, dict):
            failures.append("policy_backend_slot_not_object")
            continue
        sid = str(raw.get("id") or "")
        if sid in seen_slots:
            failures.append(f"policy_duplicate_slot:{sid}")
        seen_slots.add(sid)
        failures.extend(_slot_failures(raw))
    for sid in sorted(REQUIRED_BACKEND_SLOTS - seen_slots):
        failures.append(f"policy_backend_slot_missing:{sid}")
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
    slot_ids = {str(item.get("id")) for item in policy.get("required_backend_slots", []) if isinstance(item, dict)}
    check_ids = {str(item.get("id")) for item in policy.get("required_checks", []) if isinstance(item, dict)}
    outputs = set(_as_string_list(policy.get("required_outputs")))
    for scenario in scenarios:
        if not isinstance(scenario, dict):
            failures.append("example_scenario_not_object")
            continue
        sid = str(scenario.get("id") or "unknown")
        if scenario.get("blocked_completion") is not True:
            failures.append(f"example_blocked_completion_not_true:{sid}")
        for slot in sorted(set(_as_string_list(scenario.get("expected_backend_slots"))) - slot_ids):
            failures.append(f"example_slot_missing_from_policy:{sid}:{slot}")
        for cid in sorted(set(_as_string_list(scenario.get("expected_check_ids"))) - check_ids):
            failures.append(f"example_check_missing_from_policy:{sid}:{cid}")
        for output in sorted(set(_as_string_list(scenario.get("expected_outputs"))) - outputs):
            failures.append(f"example_output_missing_from_policy:{sid}:{output}")
    if not scenarios:
        failures.append("example_scenarios_empty")
    return {"failures": failures, "scenarios": len(scenarios)}


def validate_media_backend_selection_readiness_policy(
    payload: Dict[str, Any],
    *,
    project_root: Path = PROJECT_ROOT,
    package_root: Path = PACKAGE_ROOT,
) -> Dict[str, Any]:
    policy = _policy(payload)
    slots = [item for item in policy.get("required_backend_slots", []) if isinstance(item, dict)]
    checks = [item for item in policy.get("required_checks", []) if isinstance(item, dict)]
    evidence_count = sum(len(_as_string_list(item.get("evidence"))) for item in checks)
    ref_report = _ref_failures(payload, project_root=project_root, package_root=package_root)
    example_path = project_root / "prelaunch" / "governance" / "media_backend_selection_readiness.example.json"
    example_report = _example_failures(payload, example_path)
    failures = _policy_failures(payload) + ref_report["failures"] + example_report["failures"]
    backend_manifest = [
        {
            "id": str(item.get("id") or ""),
            "artifact_classes": _as_string_list(item.get("artifact_classes")),
            "explicit_selection_required": bool(item.get("explicit_selection_required")),
            "target_smoke_required": bool(item.get("target_smoke_required")),
            "privacy_gate_required": bool(item.get("privacy_gate_required")),
            "telemetry_profile": str(item.get("telemetry_profile") or ""),
        }
        for item in slots
    ]
    check_manifest = [
        {
            "id": str(item.get("id") or ""),
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
        "media_backend_selection_summary": {
            "completion_blocked": True,
            "blocked_until": "explicit_media_backend_selection",
            "safe_local_validator_only": True,
            "target_machine_required": True,
            "backend_slot_count": len(slots),
            "required_check_count": len(checks),
            "required_evidence_count": evidence_count,
        },
        "blocked_completion_notice": "Final live-media backend adapters remain open until explicit backend choices, operator approvals, target smoke transcripts and artifact hashes are captured and reviewed.",
        "backend_slot_manifest": backend_manifest,
        "evidence_requirements": sorted({evidence for item in check_manifest for evidence in item["evidence"]}),
        "target_check_manifest": check_manifest,
        "resolved_refs": ref_report["resolved_refs"],
        "missing_refs": ref_report["missing_refs"],
        "example_scenarios": example_report["scenarios"],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate NoemaForge media backend selection readiness policy.")
    parser.add_argument("--policy", default=str(DEFAULT_POLICY))
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(argv)
    report = validate_media_backend_selection_readiness_policy(load_policy(args.policy))
    if args.summary:
        report = {
            "apiVersion": API_VERSION,
            "kind": "MediaBackendSelectionReadinessSummary",
            "id": POLICY_ID,
            "ok": report["ok"],
            "failures": report["failures"],
            "metrics": report["media_backend_selection_summary"],
        }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
