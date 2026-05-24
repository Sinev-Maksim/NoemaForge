#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/setup_front_door_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate the root setup.sh front-door contract for setup flags and progress phases.
Inputs: Setup Front Door policy, setup.sh, installer wrapper, registry and offline examples.
Outputs: JSON-compatible SetupFrontDoorValidationReport artifacts.
Side effects: None; CLI writes JSON to stdout.
Tests: noemaforge/tests/test_setup_front_door_runtime.py
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


API_VERSION = "noemaforge.setup-front-door/v1"
POLICY_KIND = "SetupFrontDoorPolicy"
SET_KIND = "SetupFrontDoorExampleSet"
REPORT_KIND = "SetupFrontDoorValidationReport"

VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,220}$")
REQUIRED_MODES = {"vm", "host", "docker-dev"}
REQUIRED_FLAGS = {"--mode", "--install-root", "--data-root", "--model-profile", "--with-share", "--offline-after-setup"}
REQUIRED_PHASE_MARKERS = {
    "seed_copy",
    "host_preflight",
    "vault_scan",
    "inbox_normalize",
    "candidate_staging",
    "role_staffing",
    "epoch_apply",
    "reboot_pending",
}
REQUIRED_WRAPPER_MARKERS = {"bootstrap", "firstboot_orchestrator", "progress_output"}
REQUIRED_CONTROLS = {
    "root_setup_exists",
    "required_modes_supported",
    "required_flags_supported",
    "bootstrap_firstboot_progress_wrapped",
    "phase_progress_output_required",
    "non_dry_run_requires_root",
    "installer_one_way_delegation",
    "no_live_host_required",
}
REQUIRED_REGISTRY_REFS = [
    "configs/setup-front-door-policy.json",
    "contracts/setup_front_door.schema.json",
    "src/setup_front_door_runtime.py",
    "setup.sh",
    "install_noemaforge_0.32.1_mvp.sh",
    "src/firstboot_orchestrator.py",
    "src/firstboot_status.py",
    "src/firstboot_eval.py",
    "tests/test_setup_front_door_runtime.py",
    "tests/test_setup_front_door_qa.py",
    "tests/test_setup_front_door_performance.py",
    "prelaunch/governance/setup_front_door.example.json",
]
REQUIRED_PIPELINE_REFS = [
    "configs/setup-front-door-policy.json",
    "contracts/setup_front_door.schema.json",
    "src/setup_front_door_runtime.py",
    "prelaunch/governance/setup_front_door.example.json",
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


def analyze_setup_front_door(setup_text: str, installer_text: str = "") -> Dict[str, Any]:
    modes = sorted(mode for mode in REQUIRED_MODES | {"macos-dev"} if mode in setup_text)
    flags = sorted(flag for flag in REQUIRED_FLAGS if flag in setup_text)
    phases = sorted(marker for marker in REQUIRED_PHASE_MARKERS if marker in setup_text)
    wrappers = sorted(marker for marker in REQUIRED_WRAPPER_MARKERS if marker in setup_text)
    failures: List[str] = []
    missing_modes = sorted(REQUIRED_MODES - set(modes))
    missing_flags = sorted(REQUIRED_FLAGS - set(flags))
    missing_phases = sorted(REQUIRED_PHASE_MARKERS - set(phases))
    missing_wrappers = sorted(REQUIRED_WRAPPER_MARKERS - set(wrappers))
    if missing_modes:
        failures.append(f"required_modes_missing:{','.join(missing_modes)}")
    if missing_flags:
        failures.append(f"required_flags_missing:{','.join(missing_flags)}")
    if missing_phases:
        failures.append(f"phase_markers_missing:{','.join(missing_phases)}")
    if missing_wrappers:
        failures.append(f"wrapper_markers_missing:{','.join(missing_wrappers)}")
    if "non-dry-run install requires sudo/root" not in setup_text:
        failures.append("root_guard_missing")
    if "NOEMAFORGE_SETUP_DEPTH" not in setup_text:
        failures.append("recursion_guard_missing")
    if re.search(r"^[ \t]*(exec|bash|sh)[ \t]+(?!-n[ \t]+).*setup\.sh", installer_text, re.MULTILINE):
        failures.append("installer_calls_setup_back")
    return {
        "apiVersion": API_VERSION,
        "kind": "SetupFrontDoorAnalysis",
        "ok": not failures,
        "failures": failures,
        "modes": modes,
        "flags": flags,
        "phase_markers": phases,
        "wrapper_markers": wrappers,
        "metrics": {
            "required_modes": len(set(modes) & REQUIRED_MODES),
            "required_flags": len(flags),
            "phase_markers": len(phases),
            "wrapper_markers": len(wrappers),
        },
    }


def evaluate_setup_contract(contract: Dict[str, Any]) -> Dict[str, Any]:
    setup_text = "\n".join(
        _as_string_list(contract.get("modes"))
        + _as_string_list(contract.get("flags"))
        + _as_string_list(contract.get("wrapper_markers"))
        + _as_string_list(contract.get("phase_markers"))
        + ["non-dry-run install requires sudo/root", "NOEMAFORGE_SETUP_DEPTH"]
    )
    installer_text = "exec setup.sh" if bool(contract.get("installer_calls_setup_back")) else ""
    return analyze_setup_front_door(setup_text, installer_text)


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
    if str(policy.get("activation_state") or "") != "root_setup_wraps_bootstrap_firstboot_progress":
        failures.append("policy_activation_state_invalid")
    if not str(policy.get("required_pipeline_ref") or "").startswith("pipeline:"):
        failures.append("policy_required_pipeline_ref_invalid")
    for key in ["setup_script_ref", "installer_ref", "firstboot_orchestrator_ref"]:
        if not _is_safe_relative_ref(str(policy.get(key) or "")):
            failures.append(f"policy_{key}_invalid")
    for key in ["require_trace_id", "require_registry_attachment", "require_docs_and_changelog_refs", "require_no_live_dependency"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    modes = set(_as_string_list(policy.get("required_modes")))
    for item in REQUIRED_MODES:
        if item not in modes:
            failures.append(f"policy_required_mode_missing:{item}")
    flags = set(_as_string_list(policy.get("required_flags")))
    for item in REQUIRED_FLAGS:
        if item not in flags:
            failures.append(f"policy_required_flag_missing:{item}")
    phases = set(_as_string_list(policy.get("required_phase_markers")))
    for item in REQUIRED_PHASE_MARKERS:
        if item not in phases:
            failures.append(f"policy_required_phase_missing:{item}")
    wrappers = set(_as_string_list(policy.get("required_wrapper_markers")))
    for item in REQUIRED_WRAPPER_MARKERS:
        if item not in wrappers:
            failures.append(f"policy_required_wrapper_missing:{item}")
    controls = policy.get("controls") if isinstance(policy.get("controls"), dict) else {}
    for key in REQUIRED_CONTROLS:
        if controls.get(key) is not True:
            failures.append(f"policy_control_{key}_not_true")
    for key in ["required_boundary_refs", "required_runtime_refs", "required_example_sets"]:
        if not _as_string_list(policy.get(key)):
            failures.append(f"policy_{key}_empty")
    return failures


def _setup_failures(policy: Dict[str, Any], *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    setup_resolved = _resolve_ref(str(policy.get("setup_script_ref") or ""), project_root=project_root, package_root=package_root)
    installer_resolved = _resolve_ref(str(policy.get("installer_ref") or ""), project_root=project_root, package_root=package_root)
    failures: List[str] = []
    if not setup_resolved.get("ok"):
        failures.append(f"setup_script_missing:{policy.get('setup_script_ref')}")
    if not installer_resolved.get("ok"):
        failures.append(f"installer_missing:{policy.get('installer_ref')}")
    setup_text = Path(setup_resolved["path"]).read_text(encoding="utf-8") if setup_resolved.get("ok") else ""
    installer_text = Path(installer_resolved["path"]).read_text(encoding="utf-8") if installer_resolved.get("ok") else ""
    analysis = analyze_setup_front_door(setup_text, installer_text)
    failures.extend(analysis["failures"])
    return {"failures": failures, "setup": setup_resolved, "installer": installer_resolved, "analysis": analysis}


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
        report = evaluate_setup_contract(scenario.get("setup_contract") if isinstance(scenario.get("setup_contract"), dict) else {})
        local_failures.extend(report["failures"])
        if scenario.get("expected", {}).get("ok") is not True or not report["ok"]:
            local_failures.append("scenario_expected_ok_mismatch")
        scenario_reports.append({"id": sid, "ok": not local_failures, "failures": local_failures, "analysis": report})
        if local_failures:
            failures.extend([f"scenario:{sid}:{item}" for item in local_failures])
        else:
            passing_scenarios += 1
    return {"failures": failures, "scenario_reports": scenario_reports, "scenarios": len(scenarios), "passing_scenarios": passing_scenarios}


def validate_setup_front_door_policy(
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
    runtime_refs = _resolve_refs(_as_string_list(policy.get("required_runtime_refs")), project_root=project, package_root=package, owner="runtime_refs")
    failures.extend(runtime_refs["failures"])
    setup_report = _setup_failures(policy, project_root=project, package_root=package)
    failures.extend(setup_report["failures"])
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
    analysis_metrics = setup_report.get("analysis", {}).get("metrics", {})
    metrics = {
        "refs": len(_as_string_list(payload.get("refs"))),
        "resolved_refs": len(ref_report["resolved_refs"]),
        "runtime_refs": len(runtime_refs["resolved_refs"]),
        "required_modes": int(analysis_metrics.get("required_modes") or 0),
        "required_flags": int(analysis_metrics.get("required_flags") or 0),
        "phase_markers": int(analysis_metrics.get("phase_markers") or 0),
        "wrapper_markers": int(analysis_metrics.get("wrapper_markers") or 0),
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
        "runtime_refs": runtime_refs,
        "setup": setup_report,
        "registry": registry_report,
        "docs": docs_report,
        "examples": example_reports,
    }


def build_summary(report: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "apiVersion": API_VERSION,
        "kind": "SetupFrontDoorValidationSummary",
        "ok": bool(report.get("ok")),
        "id": report.get("id"),
        "version": report.get("version"),
        "metrics": report.get("metrics", {}),
        "failures": report.get("failures", []),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate NoemaForge setup front-door contract")
    parser.add_argument("--policy", default=str(SRC_DIR.parent / "configs" / "setup-front-door-policy.json"))
    parser.add_argument("--project-root", default=str(SRC_DIR.parent.parent))
    parser.add_argument("--package-root", default=str(SRC_DIR.parent))
    parser.add_argument("--registry", default="")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = validate_setup_front_door_policy(
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
