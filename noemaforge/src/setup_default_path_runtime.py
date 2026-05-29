#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/setup_default_path_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate the offline setup default-path contract for one blessed install story.
Inputs: Setup Default Path policy, root setup.sh, onboarding docs, registry and offline examples.
Outputs: JSON-compatible SetupDefaultPathValidationReport artifacts.
Side effects: None; CLI writes JSON to stdout.
Tests: noemaforge/tests/test_setup_default_path_runtime.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Sequence


SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import unified_registry_runtime as urr


API_VERSION = "noemaforge.setup-default-path/v1"
POLICY_KIND = "SetupDefaultPathPolicy"
SET_KIND = "SetupDefaultPathExampleSet"
REPORT_KIND = "SetupDefaultPathValidationReport"

VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,220}$")
REQUIRED_STEPS = {"release_unpack_or_git_clone", "root_setup_sh", "vm_mode_first", "explicit_host_install", "reboot_then_use"}
REQUIRED_MODES = {"vm", "host", "docker-dev", "macos-dev"}
REQUIRED_CONTROLS = {
    "root_setup_front_door_required",
    "vm_mode_default_required",
    "vm_dry_run_selftest_required",
    "windows_helpers_optional_only",
    "host_install_explicit_only",
    "quickstart_vm_required",
    "setup_modes_required",
    "no_live_host_required",
}
REQUIRED_REGISTRY_REFS = [
    "configs/setup-default-path-policy.json",
    "contracts/setup_default_path.schema.json",
    "src/setup_default_path_runtime.py",
    "setup.sh",
    "docs/onboarding/QUICKSTART_VM.md",
    "docs/onboarding/SETUP_MODES.md",
    "docs/operations/OPERATOR_GUIDE.md",
    "tests/test_setup_default_path_runtime.py",
    "tests/test_setup_default_path_qa.py",
    "tests/test_setup_default_path_performance.py",
    "prelaunch/governance/setup_default_path.example.json",
]
REQUIRED_PIPELINE_REFS = [
    "configs/setup-default-path-policy.json",
    "contracts/setup_default_path.schema.json",
    "src/setup_default_path_runtime.py",
    "prelaunch/governance/setup_default_path.example.json",
]


def _nowz() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _display_path(path: Path) -> str:
    return str(path).replace(os.sep, "/")


def _as_string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


def _policy_dict(payload: Dict[str, Any]) -> Dict[str, Any]:
    return payload.get("policy") if isinstance(payload.get("policy"), dict) else payload


def _registry_ref(entry: Dict[str, Any]) -> str:
    return f"{entry.get('kind')}:{entry.get('id')}:{entry.get('version')}"


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def _contains(text: str, needle: str) -> bool:
    return _norm(needle) in _norm(text)


def _is_safe_relative_ref(ref: str) -> bool:
    text = str(ref or "").strip().replace("\\", "/")
    if not text or text.startswith("/") or text.startswith("~"):
        return False
    parts = PurePosixPath(text).parts
    return not any(part in {"", ".", ".."} for part in parts)


def _resolve_ref(ref: str, *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    local = str(ref or "").strip().replace("\\", "/")
    candidates = [("project", project_root / local), ("package", package_root / local)]
    if not local.startswith("noemaforge/"):
        candidates.append(("project_noemaforge", project_root / "noemaforge" / local))
    checked: List[str] = []
    for owner, path in candidates:
        checked.append(_display_path(path))
        if path.exists():
            return {"ok": True, "ref": ref, "resolved_under": owner, "path": _display_path(path), "checked": checked}
    return {"ok": False, "ref": ref, "resolved_under": "", "path": "", "checked": checked}


def _resolve_refs(refs: Sequence[str], *, project_root: Path, package_root: Path, owner: str) -> Dict[str, Any]:
    failures: List[str] = []
    resolved_refs: List[Dict[str, Any]] = []
    missing_refs: List[Dict[str, Any]] = []
    unsafe_refs: List[Dict[str, Any]] = []
    for ref in refs:
        if not _is_safe_relative_ref(ref):
            unsafe_refs.append({"owner": owner, "ref": ref})
            failures.append(f"unsafe_ref:{owner}:{ref}")
            continue
        resolved = _resolve_ref(ref, project_root=project_root, package_root=package_root)
        resolved["owner"] = owner
        if resolved["ok"]:
            resolved_refs.append(resolved)
        else:
            missing_refs.append(resolved)
            failures.append(f"missing_ref:{owner}:{ref}")
    return {"failures": failures, "resolved_refs": resolved_refs, "missing_refs": missing_refs, "unsafe_refs": unsafe_refs}


def load_policy(policy_path: Path | str) -> Dict[str, Any]:
    return json.loads(Path(policy_path).read_text(encoding="utf-8"))


def load_example_set(example_path: Path | str) -> Dict[str, Any]:
    return json.loads(Path(example_path).read_text(encoding="utf-8"))


def evaluate_setup_candidate(candidate: Dict[str, Any]) -> Dict[str, Any]:
    steps = set(_as_string_list(candidate.get("steps")))
    modes = set(_as_string_list(candidate.get("modes")))
    first_command = str(candidate.get("first_command") or "")
    host_command = str(candidate.get("host_command") or "")
    failures: List[str] = []
    if not REQUIRED_STEPS.issubset(steps):
        failures.append("canonical_steps_missing")
    if not REQUIRED_MODES.issubset(modes):
        failures.append("required_modes_missing")
    if "./setup.sh" not in first_command or "--mode vm" not in first_command or "--dry-run" not in first_command or "--selftest" not in first_command:
        failures.append("vm_first_command_invalid")
    if "sudo ./setup.sh" not in host_command or "--mode host" not in host_command:
        failures.append("host_command_not_explicit")
    if bool(candidate.get("requires_windows")):
        failures.append("canonical_path_requires_windows")
    if str(candidate.get("windows_helpers") or "") != "optional_side_tools":
        failures.append("windows_helpers_not_optional")
    return {
        "apiVersion": API_VERSION,
        "kind": "SetupDefaultPathCandidateReport",
        "ok": not failures,
        "failures": failures,
        "metrics": {
            "steps": len(steps),
            "modes": len(modes),
            "requires_windows": 1 if bool(candidate.get("requires_windows")) else 0,
        },
    }


def _policy_failures(payload: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    policy = _policy_dict(payload)
    if payload.get("apiVersion") != API_VERSION:
        failures.append("policy_api_version_invalid")
    if payload.get("kind") != POLICY_KIND:
        failures.append("policy_kind_invalid")
    if not SAFE_ID_RE.match(str(payload.get("id") or "")):
        failures.append("policy_id_invalid")
    if str(payload.get("status") or "") not in VALID_STATUSES:
        failures.append("policy_status_invalid")
    if str(policy.get("mode") or "") != "offline_contract":
        failures.append("policy_mode_not_offline_contract")
    if str(policy.get("activation_state") or "") != "single_blessed_install_story":
        failures.append("policy_activation_state_invalid")
    if not str(policy.get("required_pipeline_ref") or "").startswith("pipeline:"):
        failures.append("policy_required_pipeline_ref_invalid")
    for key in ["setup_script_ref", "quickstart_ref", "setup_modes_ref"]:
        if not _is_safe_relative_ref(str(policy.get(key) or "")):
            failures.append(f"policy_{key}_invalid")
    for key in ["require_trace_id", "require_registry_attachment", "require_docs_and_changelog_refs", "require_no_live_dependency"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    steps = set(_as_string_list(policy.get("canonical_steps")))
    for item in REQUIRED_STEPS:
        if item not in steps:
            failures.append(f"policy_canonical_step_missing:{item}")
    modes = set(_as_string_list(policy.get("required_modes")))
    for item in REQUIRED_MODES:
        if item not in modes:
            failures.append(f"policy_required_mode_missing:{item}")
    forbidden = set(_as_string_list(policy.get("forbidden_canonical_dependencies")))
    for item in ["powershell", ".ps1", ".cmd", "windows-only"]:
        if item not in forbidden:
            failures.append(f"policy_forbidden_dependency_missing:{item}")
    controls = policy.get("controls") if isinstance(policy.get("controls"), dict) else {}
    for key in REQUIRED_CONTROLS:
        if controls.get(key) is not True:
            failures.append(f"policy_control_{key}_not_true")
    for key in ["required_boundary_refs", "required_onboarding_refs", "required_example_sets"]:
        if not _as_string_list(policy.get(key)):
            failures.append(f"policy_{key}_empty")
    return failures


def _setup_script_failures(policy: Dict[str, Any], *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    ref = str(policy.get("setup_script_ref") or "")
    resolved = _resolve_ref(ref, project_root=project_root, package_root=package_root)
    failures: List[str] = []
    if not resolved.get("ok"):
        return {"failures": [f"setup_script_missing:{ref}"], "resolved": resolved, "checks": {}}
    text = Path(resolved["path"]).read_text(encoding="utf-8")
    checks = {
        "mode_default_vm": 'MODE="vm"' in text,
        "vm_dry_run_selftest": "./setup.sh --mode vm --dry-run --selftest" in text,
        "explicit_host_install": "sudo ./setup.sh --mode host" in text,
        "root_required_for_install": "non-dry-run install requires sudo/root" in text,
        "supported_modes": all(mode in text for mode in REQUIRED_MODES),
        "recursion_guard": "NOEMAFORGE_SETUP_DEPTH" in text,
    }
    for key, ok in checks.items():
        if not ok:
            failures.append(f"setup_check_failed:{key}")
    canonical_block = text[text.find("Recommended first public MWP path:"):text.find("Notes:")]
    if any(token in canonical_block.lower() for token in ["powershell", ".ps1", ".cmd", "windows-only"]):
        failures.append("setup_canonical_path_mentions_windows_dependency")
    return {"failures": failures, "resolved": resolved, "checks": checks}


def _onboarding_failures(policy: Dict[str, Any], *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    failures: List[str] = []
    reports: List[Dict[str, Any]] = []
    required_phrase = str(policy.get("boundary_phrase") or "")
    for ref in _as_string_list(policy.get("required_onboarding_refs")):
        resolved = _resolve_ref(ref, project_root=project_root, package_root=package_root)
        has_vm_first = False
        has_boundary = False
        if not resolved.get("ok"):
            failures.append(f"onboarding_ref_missing:{ref}")
        else:
            text = Path(resolved["path"]).read_text(encoding="utf-8")
            has_vm_first = "./setup.sh --mode vm --dry-run --selftest" in text or ref == "setup.sh"
            has_boundary = _contains(text, required_phrase) or ref == "setup.sh"
            if not has_vm_first:
                failures.append(f"onboarding_vm_first_missing:{ref}")
            if ref in {"docs/onboarding/QUICKSTART_VM.md", "docs/onboarding/SETUP_MODES.md"} and not has_boundary:
                failures.append(f"onboarding_boundary_missing:{ref}")
        reports.append({"ref": ref, "ok": bool(resolved.get("ok")) and has_vm_first, "has_boundary": has_boundary, "resolved": resolved})
    return {"failures": failures, "onboarding_reports": reports}


def _registry_failures(payload: Dict[str, Any], *, project_root: Path, package_root: Path, registry_path: Path) -> Dict[str, Any]:
    policy = _policy_dict(payload)
    registry = urr.load_registry(registry_path)
    report = urr.validate_unified_registry(registry, project_root=project_root, package_root=package_root, registry_path=registry_path)
    failures = [f"registry_invalid:{item}" for item in report.get("failures", [])]
    entries = {_registry_ref(entry): entry for entry in report.get("normalized_registry", {}).get("entries", []) if isinstance(entry, dict)}
    raw_entries = {_registry_ref(entry): entry for entry in registry.get("entries", []) if isinstance(entry, dict)}
    eval_ref = f"eval-pack:{payload.get('id')}:{payload.get('version')}"
    eval_entry = entries.get(eval_ref)
    if not eval_entry:
        failures.append(f"registry_eval_pack_missing:{eval_ref}")
    else:
        refs = set(_as_string_list(eval_entry.get("refs")))
        for ref in REQUIRED_REGISTRY_REFS:
            if ref not in refs:
                failures.append(f"registry_eval_pack_ref_missing:{eval_ref}:{ref}")
    pipeline_ref = str(policy.get("required_pipeline_ref") or "")
    pipeline = raw_entries.get(pipeline_ref) or entries.get(pipeline_ref)
    pipeline_eval_refs: List[str] = []
    pipeline_refs: List[str] = []
    if not pipeline:
        failures.append(f"registry_pipeline_missing:{pipeline_ref}")
    else:
        pipeline_eval_refs = _as_string_list(pipeline.get("eval_pack_refs"))
        pipeline_refs = _as_string_list(pipeline.get("refs"))
    if eval_ref not in pipeline_eval_refs:
        failures.append(f"registry_pipeline_eval_pack_missing:{eval_ref}")
    for ref in REQUIRED_PIPELINE_REFS:
        if ref not in pipeline_refs:
            failures.append(f"registry_pipeline_ref_missing:{ref}")
    return {"failures": failures, "registry_report": report, "pipeline_eval_refs": pipeline_eval_refs, "pipeline_refs": pipeline_refs}


def _docs_failures(payload: Dict[str, Any], *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    policy = _policy_dict(payload)
    boundary = str(policy.get("boundary_phrase") or "")
    failures: List[str] = []
    boundary_reports: List[Dict[str, Any]] = []
    for ref in _as_string_list(policy.get("required_boundary_refs")):
        resolved = _resolve_ref(ref, project_root=project_root, package_root=package_root)
        has_phrase = False
        if resolved.get("ok"):
            has_phrase = _contains(Path(resolved["path"]).read_text(encoding="utf-8"), boundary)
        else:
            failures.append(f"boundary_ref_missing:{ref}")
        if resolved.get("ok") and not has_phrase:
            failures.append(f"boundary_phrase_missing:{ref}")
        boundary_reports.append({"ref": ref, "ok": bool(resolved.get("ok")) and has_phrase, "has_phrase": has_phrase, "resolved": resolved})
    return {"failures": failures, "boundary_reports": boundary_reports}


def _example_failures(example_set: Dict[str, Any]) -> Dict[str, Any]:
    failures: List[str] = []
    scenario_reports: List[Dict[str, Any]] = []
    passing_scenarios = 0
    if example_set.get("apiVersion") != API_VERSION:
        failures.append("example_api_version_invalid")
    if example_set.get("kind") != SET_KIND:
        failures.append("example_kind_invalid")
    scenarios = example_set.get("scenarios") if isinstance(example_set.get("scenarios"), list) else []
    if not scenarios:
        failures.append("example_scenarios_empty")
    for scenario in scenarios:
        sid = str(scenario.get("id") or "scenario")
        local_failures: List[str] = []
        if not str(scenario.get("trace_id") or "").startswith("trace:"):
            local_failures.append("scenario_trace_id_invalid")
        report = evaluate_setup_candidate(scenario.get("candidate") if isinstance(scenario.get("candidate"), dict) else {})
        local_failures.extend(report["failures"])
        expected = scenario.get("expected") if isinstance(scenario.get("expected"), dict) else {}
        if expected.get("ok") is not True or not report["ok"]:
            local_failures.append("scenario_expected_ok_mismatch")
        scenario_reports.append({"id": sid, "ok": not local_failures, "failures": local_failures, "candidate_report": report})
        if local_failures:
            failures.extend([f"scenario:{sid}:{item}" for item in local_failures])
        else:
            passing_scenarios += 1
    return {"failures": failures, "scenario_reports": scenario_reports, "scenarios": len(scenarios), "passing_scenarios": passing_scenarios}


def validate_setup_default_path_policy(
    payload: Dict[str, Any],
    *,
    project_root: Path | str,
    package_root: Path | str,
    policy_path: Path | str | None = None,
    registry_path: Path | str | None = None,
) -> Dict[str, Any]:
    project = Path(project_root).resolve()
    package = Path(package_root).resolve()
    registry = Path(registry_path).resolve() if registry_path else package / "configs" / "unified-registry.json"
    policy = _policy_dict(payload)
    failures: List[str] = []
    failures.extend(_policy_failures(payload))
    ref_report = _resolve_refs(_as_string_list(payload.get("refs")), project_root=project, package_root=package, owner=str(payload.get("id") or "policy"))
    failures.extend(ref_report["failures"])
    setup_report = _setup_script_failures(policy, project_root=project, package_root=package)
    failures.extend(setup_report["failures"])
    onboarding_report = _onboarding_failures(policy, project_root=project, package_root=package)
    failures.extend(onboarding_report["failures"])
    registry_report = _registry_failures(payload, project_root=project, package_root=package, registry_path=registry)
    failures.extend(registry_report["failures"])
    docs_report = _docs_failures(payload, project_root=project, package_root=package)
    failures.extend(docs_report["failures"])
    example_reports: List[Dict[str, Any]] = []
    for ref in _as_string_list(policy.get("required_example_sets")):
        resolved = _resolve_ref(ref, project_root=project, package_root=package)
        if not resolved.get("ok"):
            failures.append(f"example_ref_missing:{ref}")
            continue
        example_report = _example_failures(load_example_set(resolved["path"]))
        failures.extend(example_report["failures"])
        example_reports.append({"ref": ref, **example_report})
    metrics = {
        "refs": len(_as_string_list(payload.get("refs"))),
        "resolved_refs": len(ref_report["resolved_refs"]),
        "canonical_steps": len(_as_string_list(policy.get("canonical_steps"))),
        "required_modes": len(_as_string_list(policy.get("required_modes"))),
        "onboarding_refs": len(onboarding_report["onboarding_reports"]),
        "boundary_refs": len(docs_report["boundary_reports"]),
        "scenarios": sum(int(item.get("scenarios") or 0) for item in example_reports),
        "passing_scenarios": sum(int(item.get("passing_scenarios") or 0) for item in example_reports),
        "registry_entries": len(registry_report.get("registry_report", {}).get("normalized_registry", {}).get("entries", [])),
        "checked_controls": len(REQUIRED_CONTROLS),
    }
    return {
        "apiVersion": API_VERSION,
        "kind": REPORT_KIND,
        "id": str(payload.get("id") or ""),
        "version": str(payload.get("version") or ""),
        "ok": not failures,
        "validated_at": _nowz(),
        "policy_path": _display_path(Path(policy_path).resolve()) if policy_path else "",
        "failures": failures,
        "metrics": metrics,
        "refs": ref_report,
        "setup": setup_report,
        "onboarding": onboarding_report,
        "registry": registry_report,
        "docs": docs_report,
        "examples": example_reports,
    }


def build_summary(report: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "apiVersion": API_VERSION,
        "kind": "SetupDefaultPathValidationSummary",
        "ok": bool(report.get("ok")),
        "id": report.get("id"),
        "version": report.get("version"),
        "metrics": report.get("metrics", {}),
        "failures": report.get("failures", []),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate NoemaForge setup default-path contract")
    parser.add_argument("--policy", default=str(SRC_DIR.parent / "configs" / "setup-default-path-policy.json"))
    parser.add_argument("--project-root", default=str(SRC_DIR.parent.parent))
    parser.add_argument("--package-root", default=str(SRC_DIR.parent))
    parser.add_argument("--registry", default="")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = validate_setup_default_path_policy(
        load_policy(args.policy),
        project_root=Path(args.project_root),
        package_root=Path(args.package_root),
        policy_path=Path(args.policy),
        registry_path=Path(args.registry) if args.registry else None,
    )
    print(json.dumps(build_summary(report) if args.summary else report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
