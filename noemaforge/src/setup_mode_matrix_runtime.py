#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/setup_mode_matrix_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate setup mode semantics for Linux host, macOS dev, VM and docker-dev paths.
Inputs: Setup mode policy, setup mode matrix, root setup.sh, registry, docs and examples.
Outputs: JSON-compatible SetupModeMatrixValidationReport artifacts.
Side effects: None; CLI writes JSON to stdout.
Tests: noemaforge/tests/test_setup_mode_matrix_runtime.py
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


API_VERSION = "noemaforge.setup-modes/v1"
POLICY_KIND = "SetupModeMatrixPolicy"
MATRIX_KIND = "SetupModeMatrix"
SET_KIND = "SetupModeMatrixExampleSet"
REPORT_KIND = "SetupModeMatrixValidationReport"
REQUIRED_MODES = ["vm", "host", "macos-dev", "docker-dev"]
VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,220}$")
REGISTRY_REFS = [
    "configs/setup-mode-matrix-policy.json",
    "configs/setup-modes.json",
    "contracts/setup_mode_matrix.schema.json",
    "src/setup_mode_matrix_runtime.py",
    "setup.sh",
    "tests/test_setup_mode_matrix_runtime.py",
    "tests/test_setup_mode_matrix_qa.py",
    "tests/test_setup_mode_matrix_performance.py",
    "prelaunch/governance/setup_mode_matrix.example.json",
    "docs/README.md",
    "docs/TODO.md",
    "docs/onboarding/SETUP_MODES.md",
    "docs/backlog/ROADMAP_AND_TODO.md",
    "docs/history/CHANGELOG.md",
    "docs/reference/PROJECT_CONTEXT.md",
]
PIPELINE_REFS = [
    "configs/setup-mode-matrix-policy.json",
    "configs/setup-modes.json",
    "src/setup_mode_matrix_runtime.py",
    "prelaunch/governance/setup_mode_matrix.example.json",
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
    for ref in refs:
        if not _is_safe_relative_ref(ref):
            failures.append(f"unsafe_ref:{owner}:{ref}")
            continue
        resolved = _resolve_ref(ref, project_root=project_root, package_root=package_root)
        if resolved["ok"]:
            resolved_refs.append(resolved)
        else:
            failures.append(f"missing_ref:{owner}:{ref}")
    return {"failures": failures, "resolved_refs": resolved_refs}


def load_policy(path: Path | str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_mode_matrix(path: Path | str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_example_set(path: Path | str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validate_mode_matrix(matrix: Dict[str, Any]) -> Dict[str, Any]:
    failures: List[str] = []
    if matrix.get("apiVersion") != API_VERSION:
        failures.append("matrix_api_version_invalid")
    if matrix.get("kind") != MATRIX_KIND:
        failures.append("matrix_kind_invalid")
    modes = matrix.get("modes") if isinstance(matrix.get("modes"), dict) else {}
    for mode in REQUIRED_MODES:
        rec = modes.get(mode) if isinstance(modes.get(mode), dict) else {}
        if not rec:
            failures.append(f"mode_missing:{mode}")
            continue
        if not str(rec.get("operator_command") or "").startswith(("./setup.sh", "sudo ./setup.sh")):
            failures.append(f"mode_operator_command_invalid:{mode}")
        if mode == "host":
            if rec.get("production_runtime_path") is not True or rec.get("requires_root_for_apply") is not True or rec.get("writes_privileged_system_files") is not True:
                failures.append("host_mode_not_native_privileged_runtime")
            if "Native services" not in str(rec.get("purpose") or rec.get("label") or "") and "native services" not in str(rec.get("purpose") or ""):
                failures.append("host_mode_native_services_missing")
        if mode == "macos-dev":
            if rec.get("requires_root_for_apply") is not False or rec.get("writes_privileged_system_files") is not False or rec.get("dry_run_default") is not True:
                failures.append("macos_dev_not_non_privileged")
        if mode == "vm":
            if rec.get("recommended_first_success") is not True or rec.get("dry_run_default") is not True:
                failures.append("vm_mode_not_recommended_dry_run")
        if mode == "docker-dev":
            if rec.get("production_runtime_path") is not False or "development" not in str(rec.get("purpose") or "").lower():
                failures.append("docker_dev_not_marked_dev_only")
    return {"apiVersion": API_VERSION, "kind": "SetupModeMatrixReport", "ok": not failures, "failures": failures, "modes": sorted(modes)}


def analyze_setup_script(setup_text: str) -> Dict[str, Any]:
    failures: List[str] = []
    for mode in REQUIRED_MODES:
        if mode not in setup_text:
            failures.append(f"setup_mode_missing:{mode}")
    checks = {
        "host_native_services": "Linux host mode: native services + local paths" in setup_text,
        "macos_non_privileged": "macOS dev mode: validates repo and writes no privileged system files" in setup_text,
        "vm_recommended": "VM mode: Ubuntu/Debian VM recommended no-risk onboarding path" in setup_text,
        "docker_dev_only": "Docker/dev mode: development/test only, not the full production NoemaForge path" in setup_text,
        "vm_default": 'MODE="vm"' in setup_text,
        "vm_dry_run_without_apply": "[[ \"$APPLY_VM\" == 1 ]] || DRY_RUN=1" in setup_text,
        "macos_forces_dry_run": "macos-dev)" in setup_text and "DRY_RUN=1" in setup_text,
        "root_guard": "non-dry-run install requires sudo/root" in setup_text,
    }
    for key, ok in checks.items():
        if not ok:
            failures.append(f"setup_check_failed:{key}")
    return {"apiVersion": API_VERSION, "kind": "SetupModeScriptAnalysis", "ok": not failures, "failures": failures, "checks": checks}


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
    if str(policy.get("activation_state") or "") != "explicit_setup_mode_matrix":
        failures.append("policy_activation_state_invalid")
    if not str(policy.get("required_pipeline_ref") or "").startswith("pipeline:"):
        failures.append("policy_required_pipeline_ref_invalid")
    for key in ["mode_matrix_ref", "setup_script_ref"]:
        if not _is_safe_relative_ref(str(policy.get(key) or "")):
            failures.append(f"policy_{key}_invalid")
    for key in ["require_registry_attachment", "require_docs_and_changelog_refs", "require_no_live_dependency"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    if _as_string_list(policy.get("required_modes")) != REQUIRED_MODES:
        failures.append("policy_required_modes_invalid")
    mode_requirements = policy.get("mode_requirements") if isinstance(policy.get("mode_requirements"), dict) else {}
    for mode in REQUIRED_MODES:
        if not _as_string_list(mode_requirements.get(mode)):
            failures.append(f"policy_mode_requirements_missing:{mode}")
    for key in ["required_boundary_refs", "required_example_sets"]:
        if not _as_string_list(policy.get(key)):
            failures.append(f"policy_{key}_empty")
    return failures


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
        for ref in REGISTRY_REFS:
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
            failures.append(f"registry_pipeline_eval_pack_ref_missing:{pipeline_ref}:{eval_ref}")
        for ref in PIPELINE_REFS:
            if ref not in pipeline_refs:
                failures.append(f"registry_pipeline_ref_missing:{pipeline_ref}:{ref}")
    return {"failures": failures, "registry_report": report, "eval_ref": eval_ref, "pipeline_eval_refs": pipeline_eval_refs}


def evaluate_example_set(example_set: Dict[str, Any]) -> Dict[str, Any]:
    failures: List[str] = []
    if example_set.get("apiVersion") != API_VERSION:
        failures.append("example_api_version_invalid")
    if example_set.get("kind") != SET_KIND:
        failures.append("example_kind_invalid")
    scenarios = example_set.get("scenarios") if isinstance(example_set.get("scenarios"), list) else []
    seen = set()
    for scenario in scenarios:
        mode = str(scenario.get("start_mode") or "")
        seen.add(mode)
        command = str(scenario.get("command") or "")
        expected = set(_as_string_list(scenario.get("expected")))
        if mode not in REQUIRED_MODES:
            failures.append(f"example_mode_invalid:{mode}")
        if f"--mode {mode}" not in command:
            failures.append(f"example_command_mode_missing:{mode}")
        if not expected:
            failures.append(f"example_expected_empty:{mode}")
    for mode in REQUIRED_MODES:
        if mode not in seen:
            failures.append(f"example_mode_missing:{mode}")
    return {"ok": not failures, "failures": failures, "scenarios": len(scenarios)}


def validate_setup_mode_matrix_policy(
    payload: Dict[str, Any],
    *,
    project_root: Path,
    package_root: Path,
    registry_path: Path | None = None,
) -> Dict[str, Any]:
    registry_path = registry_path or package_root / "configs" / "unified-registry.json"
    policy = _policy_dict(payload)
    failures = _policy_failures(payload)
    refs = _resolve_refs(payload.get("refs", []), project_root=project_root, package_root=package_root, owner=str(payload.get("id") or "policy"))
    failures.extend(refs["failures"])

    matrix_res = _resolve_ref(str(policy.get("mode_matrix_ref") or ""), project_root=project_root, package_root=package_root)
    if matrix_res["ok"]:
        matrix_report = validate_mode_matrix(load_mode_matrix(matrix_res["path"]))
        failures.extend(matrix_report["failures"])
    else:
        matrix_report = {"ok": False, "failures": ["matrix_ref_missing"], "modes": []}
        failures.append("matrix_ref_missing")

    setup_res = _resolve_ref(str(policy.get("setup_script_ref") or ""), project_root=project_root, package_root=package_root)
    if setup_res["ok"]:
        setup_report = analyze_setup_script(Path(setup_res["path"]).read_text(encoding="utf-8"))
        failures.extend(setup_report["failures"])
    else:
        setup_report = {"ok": False, "failures": ["setup_ref_missing"], "checks": {}}
        failures.append("setup_ref_missing")

    registry = _registry_failures(payload, project_root=project_root, package_root=package_root, registry_path=registry_path)
    failures.extend(registry["failures"])

    boundary = str(policy.get("boundary_phrase") or "")
    boundary_hits = []
    for ref in _as_string_list(policy.get("required_boundary_refs")):
        resolved = _resolve_ref(ref, project_root=project_root, package_root=package_root)
        if not resolved["ok"]:
            failures.append(f"boundary_ref_missing:{ref}")
            continue
        if _contains(Path(resolved["path"]).read_text(encoding="utf-8"), boundary):
            boundary_hits.append(ref)
        else:
            failures.append(f"boundary_phrase_missing:{ref}")

    example_reports = []
    for ref in _as_string_list(policy.get("required_example_sets")):
        resolved = _resolve_ref(ref, project_root=project_root, package_root=package_root)
        if not resolved["ok"]:
            failures.append(f"example_ref_missing:{ref}")
            continue
        report = evaluate_example_set(load_example_set(resolved["path"]))
        example_reports.append({"ref": ref, **report})
        failures.extend([f"example_invalid:{ref}:{item}" for item in report["failures"]])

    return {
        "apiVersion": API_VERSION,
        "kind": REPORT_KIND,
        "created_at": _nowz(),
        "ok": not failures,
        "failures": failures,
        "policy_id": payload.get("id"),
        "matrix": matrix_report,
        "setup": setup_report,
        "registry": {"eval_ref": registry["eval_ref"], "pipeline_eval_refs": registry["pipeline_eval_refs"]},
        "examples": example_reports,
        "resolved_refs": refs["resolved_refs"],
        "metrics": {
            "refs": len(payload.get("refs", [])) if isinstance(payload.get("refs"), list) else 0,
            "resolved_refs": len(refs["resolved_refs"]),
            "modes": len(matrix_report.get("modes", [])),
            "boundary_refs": len(boundary_hits),
            "examples": len(example_reports),
            "registry_entries": len(registry["registry_report"].get("normalized_registry", {}).get("entries", [])),
        },
    }


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Validate NoemaForge setup mode matrix policy")
    package_root = Path(__file__).resolve().parent.parent
    project_root = package_root.parent
    ap.add_argument("--policy", default=str(package_root / "configs" / "setup-mode-matrix-policy.json"))
    ap.add_argument("--project-root", default=str(project_root))
    ap.add_argument("--package-root", default=str(package_root))
    ap.add_argument("--registry", default="")
    ap.add_argument("--summary", action="store_true")
    args = ap.parse_args(argv)
    pkg = Path(args.package_root).resolve()
    proj = Path(args.project_root).resolve()
    registry = Path(args.registry).resolve() if args.registry else pkg / "configs" / "unified-registry.json"
    report = validate_setup_mode_matrix_policy(load_policy(args.policy), project_root=proj, package_root=pkg, registry_path=registry)
    if args.summary:
        print(json.dumps({"ok": report["ok"], "failures": report["failures"], "metrics": report["metrics"]}, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
