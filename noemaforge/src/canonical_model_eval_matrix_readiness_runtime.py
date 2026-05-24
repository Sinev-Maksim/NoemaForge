#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/canonical_model_eval_matrix_readiness_runtime.py
Zone: release/package
Version: 0.31.21.alpha
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate the offline readiness contract for the canonical CPU/GPU model evaluation matrix.
Inputs: canonical model eval matrix readiness policy, examples, registry refs and canonical docs.
Outputs: JSON validation reports and summaries.
Side effects: None; this validator never executes target model evaluation commands.
Tests: noemaforge/tests/test_canonical_model_eval_matrix_readiness_runtime.py, QA and performance tests.
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


API_VERSION = "noemaforge.canonical-model-eval-matrix-readiness/v1"
POLICY_KIND = "CanonicalModelEvalMatrixReadinessPolicy"
EXAMPLE_KIND = "CanonicalModelEvalMatrixReadinessExampleSet"
REPORT_KIND = "CanonicalModelEvalMatrixReadinessValidationReport"
POLICY_ID = "canonical-model-eval-matrix-readiness-core"
VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
SAFE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
ALLOWED_RUNTIME_DEVICES = {"cpu", "gpu"}
REQUIRED_DIMENSION_IDS = {
    "canonical-model-inventory",
    "cpu-scorecard-run",
    "gpu-scorecard-run",
    "role-coverage",
    "eval-suite-coverage",
    "health-filter-coverage",
    "scorecard-separation",
    "evidence-archive",
}
REQUIRED_SAFETY_CONTROLS = {
    "no_auto_live_execution",
    "target_machine_required",
    "cpu_gpu_scorecards_separate",
    "canonical_model_list_required",
    "full_matrix_required_before_completion",
    "evidence_archive_required",
    "failed_or_excluded_models_not_selected",
    "local_validator_has_no_subprocess",
}
REQUIRED_OUTPUTS = {
    "matrix_readiness_summary",
    "blocked_completion_notice",
    "runtime_device_dimensions",
    "canonical_model_matrix_manifest",
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
    "noemaforge/docs/wiki/first-start/model-selection-modes-0.31.13.alpha-patched1.md",
}

SRC_DIR = Path(__file__).resolve().parent
PACKAGE_ROOT = SRC_DIR.parent
PROJECT_ROOT = PACKAGE_ROOT.parent
DEFAULT_POLICY = PACKAGE_ROOT / "configs" / "canonical-model-eval-matrix-readiness-policy.json"


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


def _dimension_failures(dimension: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    did = str(dimension.get("id") or "")
    if not SAFE_ID_RE.match(did):
        failures.append(f"dimension_id_invalid:{did}")
    if not str(dimension.get("title") or "").strip():
        failures.append(f"dimension_title_missing:{did}")
    runtime_devices = set(_as_string_list(dimension.get("runtime_devices")))
    if not runtime_devices:
        failures.append(f"dimension_runtime_devices_empty:{did}")
    for runtime_device in sorted(runtime_devices):
        if runtime_device not in ALLOWED_RUNTIME_DEVICES:
            failures.append(f"dimension_runtime_device_invalid:{did}:{runtime_device}")
    if dimension.get("target_evidence_required") is not True:
        failures.append(f"dimension_target_evidence_required_not_true:{did}")
    source_refs = _as_string_list(dimension.get("source_refs"))
    evidence = _as_string_list(dimension.get("evidence"))
    gates = _as_string_list(dimension.get("completion_gates"))
    if not source_refs:
        failures.append(f"dimension_source_refs_empty:{did}")
    if not evidence:
        failures.append(f"dimension_evidence_empty:{did}")
    if not gates:
        failures.append(f"dimension_completion_gates_empty:{did}")
    if did == "cpu-scorecard-run" and runtime_devices != {"cpu"}:
        failures.append("dimension_cpu_scorecard_runtime_device_invalid")
    if did == "gpu-scorecard-run" and runtime_devices != {"gpu"}:
        failures.append("dimension_gpu_scorecard_runtime_device_invalid")
    if did in {
        "canonical-model-inventory",
        "role-coverage",
        "eval-suite-coverage",
        "health-filter-coverage",
        "scorecard-separation",
        "evidence-archive",
    } and runtime_devices != {"cpu", "gpu"}:
        failures.append(f"dimension_requires_cpu_gpu:{did}")
    if did != "evidence-archive" and "evidence_file_archived" not in gates:
        failures.append(f"dimension_archive_gate_missing:{did}")
    if did == "evidence-archive" and "bundle_sha256_recorded" not in gates:
        failures.append("dimension_archive_bundle_sha_missing")
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
    if policy.get("activation_state") != "canonical_model_eval_matrix_readiness":
        failures.append("policy_activation_state_invalid")
    if policy.get("completion_state") != "blocked_until_canonical_model_matrix_evidence":
        failures.append("policy_completion_state_invalid")
    for key in ["require_registry_attachment", "require_docs_and_changelog_refs", "require_no_live_execution"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    blocked_refs = _as_string_list(policy.get("blocked_todo_refs"))
    if "Full CPU/GPU evaluation matrix on the canonical model list." not in blocked_refs:
        failures.append("policy_primary_blocked_todo_missing")
    controls = policy.get("required_safety_controls") if isinstance(policy.get("required_safety_controls"), dict) else {}
    for control in REQUIRED_SAFETY_CONTROLS:
        if controls.get(control) is not True:
            failures.append(f"policy_safety_control_missing:{control}")
    dimensions = policy.get("required_dimensions")
    if not isinstance(dimensions, list):
        failures.append("policy_required_dimensions_not_list")
        dimensions = []
    seen_dimensions = set()
    for raw in dimensions:
        if not isinstance(raw, dict):
            failures.append("policy_required_dimension_not_object")
            continue
        did = str(raw.get("id") or "")
        if did in seen_dimensions:
            failures.append(f"policy_duplicate_dimension:{did}")
        seen_dimensions.add(did)
        failures.extend(_dimension_failures(raw))
    for did in sorted(REQUIRED_DIMENSION_IDS - seen_dimensions):
        failures.append(f"policy_required_dimension_missing:{did}")
    outputs = set(_as_string_list(policy.get("required_outputs")))
    for output in sorted(REQUIRED_OUTPUTS - outputs):
        failures.append(f"policy_required_output_missing:{output}")
    refs = set(_as_string_list(policy.get("required_refs"))) | set(_as_string_list(payload.get("refs")))
    for ref in REQUIRED_DOC_REFS - refs:
        failures.append(f"policy_doc_ref_missing:{ref}")
    return failures


def _ref_failures(payload: Dict[str, Any], *, project_root: Path = PROJECT_ROOT, package_root: Path = PACKAGE_ROOT) -> Dict[str, Any]:
    policy = _policy(payload)
    dimension_refs: List[str] = []
    for raw in policy.get("required_dimensions", []):
        if isinstance(raw, dict):
            dimension_refs.extend(_as_string_list(raw.get("source_refs")))
    refs = _as_string_list(payload.get("refs")) + _as_string_list(policy.get("required_refs")) + dimension_refs
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
    dimension_ids = {str(item.get("id")) for item in policy.get("required_dimensions", []) if isinstance(item, dict)}
    outputs = set(_as_string_list(policy.get("required_outputs")))
    for scenario in scenarios:
        if not isinstance(scenario, dict):
            failures.append("example_scenario_not_object")
            continue
        sid = str(scenario.get("id") or "unknown")
        if scenario.get("blocked_completion") is not True:
            failures.append(f"example_blocked_completion_not_true:{sid}")
        expected_dimensions = set(_as_string_list(scenario.get("expected_dimension_ids")))
        expected_outputs = set(_as_string_list(scenario.get("expected_outputs")))
        for did in sorted(expected_dimensions - dimension_ids):
            failures.append(f"example_dimension_missing_from_policy:{sid}:{did}")
        for output in sorted(expected_outputs - outputs):
            failures.append(f"example_output_missing_from_policy:{sid}:{output}")
    if not scenarios:
        failures.append("example_scenarios_empty")
    return {"failures": failures, "scenarios": len(scenarios)}


def validate_canonical_model_eval_matrix_readiness_policy(
    payload: Dict[str, Any],
    *,
    project_root: Path = PROJECT_ROOT,
    package_root: Path = PACKAGE_ROOT,
) -> Dict[str, Any]:
    policy = _policy(payload)
    dimensions = [item for item in policy.get("required_dimensions", []) if isinstance(item, dict)]
    evidence_count = sum(len(_as_string_list(item.get("evidence"))) for item in dimensions)
    runtime_devices = sorted({device for item in dimensions for device in _as_string_list(item.get("runtime_devices"))})
    ref_report = _ref_failures(payload, project_root=project_root, package_root=package_root)
    example_path = project_root / "prelaunch" / "governance" / "canonical_model_eval_matrix_readiness.example.json"
    example_report = _example_failures(payload, example_path)
    failures = _policy_failures(payload) + ref_report["failures"] + example_report["failures"]
    manifest = [
        {
            "id": str(item.get("id") or ""),
            "runtime_devices": _as_string_list(item.get("runtime_devices")),
            "source_refs": _as_string_list(item.get("source_refs")),
            "evidence": _as_string_list(item.get("evidence")),
            "completion_gates": _as_string_list(item.get("completion_gates")),
            "target_evidence_required": bool(item.get("target_evidence_required")),
        }
        for item in dimensions
    ]
    return {
        "apiVersion": API_VERSION,
        "kind": REPORT_KIND,
        "id": POLICY_ID,
        "version": str(payload.get("version") or ""),
        "generated_at": _nowz(),
        "ok": not failures,
        "failures": failures,
        "matrix_readiness_summary": {
            "completion_blocked": True,
            "blocked_until": "canonical_model_matrix_evidence",
            "safe_local_validator_only": True,
            "required_dimension_count": len(dimensions),
            "runtime_devices": runtime_devices,
            "runtime_device_count": len(runtime_devices),
            "required_evidence_count": evidence_count,
        },
        "blocked_completion_notice": "The full CPU/GPU canonical model evaluation matrix remains open until target-machine CPU and GPU evidence is captured, separated and archived.",
        "runtime_device_dimensions": {
            device: sorted(item["id"] for item in manifest if device in item["runtime_devices"]) for device in runtime_devices
        },
        "canonical_model_matrix_manifest": manifest,
        "evidence_requirements": sorted({evidence for item in manifest for evidence in item["evidence"]}),
        "resolved_refs": ref_report["resolved_refs"],
        "missing_refs": ref_report["missing_refs"],
        "example_scenarios": example_report["scenarios"],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate NoemaForge canonical model evaluation matrix readiness policy.")
    parser.add_argument("--policy", default=str(DEFAULT_POLICY))
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(argv)
    report = validate_canonical_model_eval_matrix_readiness_policy(load_policy(args.policy))
    if args.summary:
        report = {
            "apiVersion": API_VERSION,
            "kind": "CanonicalModelEvalMatrixReadinessSummary",
            "id": POLICY_ID,
            "ok": report["ok"],
            "failures": report["failures"],
            "metrics": report["matrix_readiness_summary"],
        }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
