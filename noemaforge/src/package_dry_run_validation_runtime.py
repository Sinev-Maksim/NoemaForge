#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/package_dry_run_validation_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate install/uninstall dry-run package validation contracts.
Inputs: noemaforge/configs/package-dry-run-validation-policy.json and package dry-run examples.
Outputs: JSON-compatible PackageDryRunValidationReport artifacts.
Side effects: None unless run as a CLI, which writes JSON to stdout.
Tests: noemaforge/tests/test_package_dry_run_validation_runtime.py
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
from typing import Any, Dict, List, Optional, Sequence, Set


SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import unified_registry_runtime as urr


API_VERSION = "noemaforge.package-dry-run/v1"
POLICY_KIND = "PackageDryRunValidationPolicy"
SET_KIND = "PackageDryRunValidationExampleSet"
REPORT_KIND = "PackageDryRunValidationReport"

VALID_POLICY_STATUSES = {"draft", "shadow", "stable", "retired"}
REQUIRED_SETUP_FLAGS = {"--dry-run", "--selftest", "--install-root", "--data-root", "--model-profile"}
REQUIRED_UNINSTALL_FLAGS = {"--dry-run", "--selftest"}
REQUIRED_CONTROLS = {
    "setup_dry_run_exits_before_installer_exec",
    "setup_non_dry_run_requires_root",
    "setup_recursion_guard_required",
    "setup_selftest_checks_install_and_uninstall_syntax",
    "setup_dry_run_no_rm_rf",
    "uninstall_dry_run_required",
    "uninstall_reports_no_destructive_actions",
    "uninstall_dry_run_no_rm_rf",
}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,220}$")


def _nowz() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _as_path(value: Path | str) -> Path:
    return Path(value).resolve()


def _display_path(path: Path) -> str:
    return str(path).replace(os.sep, "/")


def _as_string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


def _is_safe_relative_ref(ref: str) -> bool:
    text = str(ref or "").strip().replace("\\", "/")
    if not text or text.startswith("/") or text.startswith("~"):
        return False
    parts = PurePosixPath(text).parts
    return not any(part in {"", ".", ".."} for part in parts)


def _resolve_ref(ref: str, *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    candidates = [
        ("project", project_root / ref),
        ("package", package_root / ref),
    ]
    if not str(ref).startswith("noemaforge/"):
        candidates.append(("project_noemaforge", project_root / "noemaforge" / ref))

    checked: List[str] = []
    for base_name, path in candidates:
        checked.append(_display_path(path))
        if path.exists():
            return {"ok": True, "ref": ref, "resolved_under": base_name, "path": _display_path(path), "checked": checked}
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


def load_script_text(script_path: Path | str) -> str:
    return Path(script_path).read_text(encoding="utf-8")


def _policy_dict(payload: Dict[str, Any]) -> Dict[str, Any]:
    return payload.get("policy") if isinstance(payload.get("policy"), dict) else payload


def _registry_ref(entry: Dict[str, Any]) -> str:
    return f"{entry.get('kind')}:{entry.get('id')}:{entry.get('version')}"


def _line_of(text: str, needle: str) -> int:
    for index, line in enumerate(text.splitlines(), start=1):
        if needle in line:
            return index
    return -1


def _dangerous_tokens(text: str) -> Set[str]:
    tokens: Set[str] = set()
    patterns = {
        "rm_rf": r"\brm\s+-rf\b",
        "systemctl_disable": r"\bsystemctl\s+(disable|stop|restart|daemon-reload)\b",
        "unlink_recursive": r"\bfind\b.*\b-delete\b",
    }
    for name, pattern in patterns.items():
        if re.search(pattern, text):
            tokens.add(name)
    return tokens


def _policy_failures(payload: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    policy = _policy_dict(payload)
    if payload.get("apiVersion") != API_VERSION:
        failures.append("policy_api_version_invalid")
    if payload.get("kind") != POLICY_KIND:
        failures.append("policy_kind_invalid")
    if not SAFE_ID_RE.match(str(payload.get("id") or "")):
        failures.append("policy_id_invalid")
    if str(payload.get("status") or "") not in VALID_POLICY_STATUSES:
        failures.append("policy_status_invalid")
    if str(policy.get("mode") or "") != "offline_contract":
        failures.append("policy_mode_not_offline_contract")
    if str(policy.get("activation_state") or "") != "install_uninstall_dry_run_tests":
        failures.append("policy_activation_state_invalid")
    for key in ["require_trace_id", "require_registry_attachment", "require_docs_and_changelog_refs"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    if not str(policy.get("required_pipeline_ref") or "").startswith("pipeline:"):
        failures.append("policy_required_pipeline_ref_invalid")
    scripts = policy.get("required_scripts") if isinstance(policy.get("required_scripts"), dict) else {}
    for key in ["setup", "installer", "uninstall"]:
        if not str(scripts.get(key) or "").strip():
            failures.append(f"policy_required_script_missing:{key}")
    if not REQUIRED_SETUP_FLAGS.issubset(set(_as_string_list(policy.get("required_setup_flags")))):
        failures.append("policy_required_setup_flags_missing")
    if not REQUIRED_UNINSTALL_FLAGS.issubset(set(_as_string_list(policy.get("required_uninstall_flags")))):
        failures.append("policy_required_uninstall_flags_missing")
    controls = policy.get("dry_run_controls") if isinstance(policy.get("dry_run_controls"), dict) else {}
    for key in REQUIRED_CONTROLS:
        if controls.get(key) is not True:
            failures.append(f"policy_control_{key}_not_true")
    if not _as_string_list(policy.get("required_example_sets")):
        failures.append("policy_required_example_sets_empty")
    return failures


def _registry_failures(payload: Dict[str, Any], *, project_root: Path, package_root: Path, registry_path: Path) -> Dict[str, Any]:
    policy = _policy_dict(payload)
    registry = urr.load_registry(registry_path)
    report = urr.validate_unified_registry(registry, project_root=project_root, package_root=package_root, registry_path=registry_path)
    failures = [f"registry_invalid:{item}" for item in report.get("failures", [])]
    entries = {
        _registry_ref(entry): entry
        for entry in report.get("normalized_registry", {}).get("entries", [])
        if isinstance(entry, dict)
    }
    raw_entries = {
        _registry_ref(entry): entry
        for entry in registry.get("entries", [])
        if isinstance(entry, dict)
    }
    eval_ref = f"eval-pack:{payload.get('id')}:{payload.get('version')}"
    eval_entry = entries.get(eval_ref)
    if not eval_entry:
        failures.append(f"registry_eval_pack_missing:{eval_ref}")
    else:
        entry_refs = set(_as_string_list(eval_entry.get("refs")))
        for ref in [
            "configs/package-dry-run-validation-policy.json",
            "contracts/package_dry_run_validation.schema.json",
            "src/package_dry_run_validation_runtime.py",
            "tests/test_package_dry_run_validation_runtime.py",
            "tests/test_package_dry_run_validation_qa.py",
            "tests/test_package_dry_run_validation_performance.py",
            "tests/test_version_03200_qa.py",
            "tests/test_version_03200_performance.py",
        ]:
            if ref not in entry_refs:
                failures.append(f"registry_eval_pack_ref_missing:{eval_ref}:{ref}")

    pipeline_ref = str(policy.get("required_pipeline_ref") or "")
    pipeline = raw_entries.get(pipeline_ref) or entries.get(pipeline_ref)
    if not pipeline:
        failures.append(f"registry_pipeline_missing:{pipeline_ref}")
        pipeline_eval_refs: List[str] = []
        pipeline_refs: List[str] = []
    else:
        pipeline_eval_refs = _as_string_list(pipeline.get("eval_pack_refs"))
        pipeline_refs = _as_string_list(pipeline.get("refs"))
    if eval_ref not in pipeline_eval_refs:
        failures.append(f"registry_pipeline_eval_pack_missing:{eval_ref}")
    for ref in [
        "configs/package-dry-run-validation-policy.json",
        "contracts/package_dry_run_validation.schema.json",
        "src/package_dry_run_validation_runtime.py",
        "prelaunch/governance/package_dry_run_validation.example.json",
    ]:
        if ref not in pipeline_refs:
            failures.append(f"registry_pipeline_ref_missing:{ref}")
    return {"failures": failures, "registry_report": report, "entries": entries, "pipeline_eval_refs": pipeline_eval_refs}


def _script_map(policy_payload: Dict[str, Any], *, project_root: Path, package_root: Path) -> Dict[str, str]:
    scripts = _policy_dict(policy_payload).get("required_scripts") or {}
    mapping: Dict[str, str] = {}
    for key, ref in scripts.items():
        resolved = _resolve_ref(str(ref), project_root=project_root, package_root=package_root)
        if resolved.get("ok"):
            mapping[str(key)] = str(resolved["path"])
    return mapping


def _static_script_failures(payload: Dict[str, Any], *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    policy = _policy_dict(payload)
    controls = policy.get("dry_run_controls") if isinstance(policy.get("dry_run_controls"), dict) else {}
    mapping = _script_map(payload, project_root=project_root, package_root=package_root)
    failures: List[str] = []
    details: Dict[str, Any] = {"scripts": mapping, "script_checks": {}}

    setup_text = load_script_text(mapping["setup"]) if "setup" in mapping else ""
    uninstall_text = load_script_text(mapping["uninstall"]) if "uninstall" in mapping else ""
    installer_ref = str((policy.get("required_scripts") or {}).get("installer") or "")
    uninstall_ref = str((policy.get("required_scripts") or {}).get("uninstall") or "")

    setup_checks = {
        "required_flags": sorted([flag for flag in REQUIRED_SETUP_FLAGS if flag in setup_text]),
        "dry_run_if_line": _line_of(setup_text, 'if [[ "$DRY_RUN" == 1 ]]'),
        "installer_exec_line": _line_of(setup_text, 'exec "$PKG_DIR/install_noemaforge_0.32.2_mvp.sh"'),
        "root_guard": "non-dry-run install requires sudo/root" in setup_text,
        "recursion_guard": "NOEMAFORGE_SETUP_DEPTH" in setup_text,
        "syntax_checks_installer": f'bash -n "$PKG_DIR/{installer_ref}"' in setup_text,
        "syntax_checks_uninstall": f'bash -n "$PKG_DIR/{uninstall_ref}"' in setup_text,
        "dangerous_tokens": sorted(_dangerous_tokens(setup_text)),
    }
    details["script_checks"]["setup"] = setup_checks
    missing_setup_flags = sorted(REQUIRED_SETUP_FLAGS.difference(set(setup_checks["required_flags"])))
    for flag in missing_setup_flags:
        failures.append(f"setup_flag_missing:{flag}")
    if controls.get("setup_dry_run_exits_before_installer_exec") is True:
        if setup_checks["dry_run_if_line"] < 0 or setup_checks["installer_exec_line"] < 0 or setup_checks["dry_run_if_line"] > setup_checks["installer_exec_line"]:
            failures.append("setup_dry_run_does_not_exit_before_installer_exec")
    if controls.get("setup_non_dry_run_requires_root") is True and not setup_checks["root_guard"]:
        failures.append("setup_root_guard_missing")
    if controls.get("setup_recursion_guard_required") is True and not setup_checks["recursion_guard"]:
        failures.append("setup_recursion_guard_missing")
    if controls.get("setup_selftest_checks_install_and_uninstall_syntax") is True:
        if not setup_checks["syntax_checks_installer"]:
            failures.append("setup_selftest_installer_syntax_check_missing")
        if not setup_checks["syntax_checks_uninstall"]:
            failures.append("setup_selftest_uninstall_syntax_check_missing")
    if controls.get("setup_dry_run_no_rm_rf") is True and "rm_rf" in setup_checks["dangerous_tokens"]:
        failures.append("setup_rm_rf_present_in_dry_run_surface")

    uninstall_checks = {
        "required_flags": sorted([flag for flag in REQUIRED_UNINSTALL_FLAGS if flag in uninstall_text]),
        "dry_run_complete": "dry-run complete" in uninstall_text,
        "no_destructive_actions_report": "destructive_actions: none" in uninstall_text,
        "selftest_syntax": 'bash -n "$0"' in uninstall_text,
        "dangerous_tokens": sorted(_dangerous_tokens(uninstall_text)),
    }
    details["script_checks"]["uninstall"] = uninstall_checks
    missing_uninstall_flags = sorted(REQUIRED_UNINSTALL_FLAGS.difference(set(uninstall_checks["required_flags"])))
    for flag in missing_uninstall_flags:
        failures.append(f"uninstall_flag_missing:{flag}")
    if controls.get("uninstall_dry_run_required") is True and not uninstall_checks["dry_run_complete"]:
        failures.append("uninstall_dry_run_completion_missing")
    if controls.get("uninstall_reports_no_destructive_actions") is True and not uninstall_checks["no_destructive_actions_report"]:
        failures.append("uninstall_no_destructive_actions_report_missing")
    if controls.get("uninstall_dry_run_no_rm_rf") is True and "rm_rf" in uninstall_checks["dangerous_tokens"]:
        failures.append("uninstall_rm_rf_present_in_dry_run_surface")
    return {"failures": failures, "details": details}


def _scenario_failures(scenario: Dict[str, Any], policy_payload: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    scenario_id = str(scenario.get("id") or "<missing>")
    if not SAFE_ID_RE.match(scenario_id):
        failures.append(f"scenario_id_invalid:{scenario_id}")
    if _policy_dict(policy_payload).get("require_trace_id") is True and not SAFE_ID_RE.match(str(scenario.get("trace_id") or "")):
        failures.append(f"scenario_trace_id_invalid:{scenario_id}")
    command = _as_string_list(scenario.get("command"))
    if not command:
        failures.append(f"scenario_command_missing:{scenario_id}")
    expected = scenario.get("expected") if isinstance(scenario.get("expected"), dict) else {}
    for key in ["no_root_required", "plans_only", "dry_run_exits_before_installer_exec"]:
        if expected.get(key) is not True:
            failures.append(f"scenario_expected_{key}_not_true:{scenario_id}")
    if expected.get("destructive_actions_allowed") is not False:
        failures.append(f"scenario_allows_destructive_actions:{scenario_id}")
    if "--dry-run" not in command and "--plan" not in command:
        failures.append(f"scenario_command_dry_run_missing:{scenario_id}")
    if "--selftest" not in command:
        failures.append(f"scenario_command_selftest_missing:{scenario_id}")
    if not _as_string_list(expected.get("syntax_checks")):
        failures.append(f"scenario_syntax_checks_missing:{scenario_id}")
    return failures


def validate_package_dry_run_policy(
    payload: Dict[str, Any],
    *,
    project_root: Path | str,
    package_root: Path | str,
    policy_path: Optional[Path | str] = None,
    registry_path: Optional[Path | str] = None,
) -> Dict[str, Any]:
    project = _as_path(project_root)
    package = _as_path(package_root)
    if not project.exists():
        raise FileNotFoundError(project)
    if not package.exists():
        raise FileNotFoundError(package)
    registry = _as_path(registry_path) if registry_path else package / "configs" / "unified-registry.json"

    policy = _policy_dict(payload)
    failures: List[str] = []
    failures.extend(_policy_failures(payload))
    registry_result = _registry_failures(payload, project_root=project, package_root=package, registry_path=registry)
    failures.extend(registry_result["failures"])
    static_result = _static_script_failures(payload, project_root=project, package_root=package)
    failures.extend(static_result["failures"])

    all_resolved_refs: List[Dict[str, Any]] = []
    all_missing_refs: List[Dict[str, Any]] = []
    all_unsafe_refs: List[Dict[str, Any]] = []
    scenario_results: List[Dict[str, Any]] = []

    refs_to_resolve = sorted(set(_as_string_list(payload.get("refs")) + _as_string_list((policy.get("required_scripts") or {}).values())))
    refs_result = _resolve_refs(refs_to_resolve, project_root=project, package_root=package, owner=str(payload.get("id") or "policy"))
    failures.extend(refs_result["failures"])
    all_resolved_refs.extend(refs_result["resolved_refs"])
    all_missing_refs.extend(refs_result["missing_refs"])
    all_unsafe_refs.extend(refs_result["unsafe_refs"])

    example_ref_results = _resolve_refs(_as_string_list(policy.get("required_example_sets")), project_root=project, package_root=package, owner="required_example_sets")
    failures.extend(example_ref_results["failures"])
    all_resolved_refs.extend(example_ref_results["resolved_refs"])
    all_missing_refs.extend(example_ref_results["missing_refs"])
    all_unsafe_refs.extend(example_ref_results["unsafe_refs"])

    for ref_item in example_ref_results["resolved_refs"]:
        example_set = load_example_set(Path(ref_item["path"]))
        if example_set.get("apiVersion") != API_VERSION:
            failures.append(f"example_set_api_version_invalid:{ref_item['ref']}")
        if example_set.get("kind") != SET_KIND:
            failures.append(f"example_set_kind_invalid:{ref_item['ref']}")
        scenarios = example_set.get("scenarios") if isinstance(example_set.get("scenarios"), list) else []
        if not scenarios:
            failures.append(f"example_set_scenarios_empty:{ref_item['ref']}")
        for scenario in scenarios:
            if not isinstance(scenario, dict):
                failures.append(f"scenario_not_object:{ref_item['ref']}")
                continue
            scenario_id = str(scenario.get("id") or "<missing>")
            scenario_failures = _scenario_failures(scenario, payload)
            failures.extend(scenario_failures)
            scenario_ref_result = _resolve_refs(_as_string_list(scenario.get("refs")), project_root=project, package_root=package, owner=scenario_id)
            failures.extend(scenario_ref_result["failures"])
            all_resolved_refs.extend(scenario_ref_result["resolved_refs"])
            all_missing_refs.extend(scenario_ref_result["missing_refs"])
            all_unsafe_refs.extend(scenario_ref_result["unsafe_refs"])
            scenario_results.append({"id": scenario_id, "ok": not scenario_failures, "failures": sorted(set(scenario_failures))})

    checks = [
        {"id": "setup_dry_run_flags", "status": "passed" if not any("setup_flag_missing" in item for item in failures) else "failed"},
        {"id": "uninstall_dry_run_flags", "status": "passed" if not any("uninstall_flag_missing" in item for item in failures) else "failed"},
        {"id": "dry_run_before_apply", "status": "passed" if not any("dry_run_does_not_exit" in item for item in failures) else "failed"},
        {"id": "syntax_selftest", "status": "passed" if not any("syntax_check_missing" in item for item in failures) else "failed"},
        {"id": "no_destructive_dry_run", "status": "passed" if not any("rm_rf_present" in item or "destructive" in item for item in failures) else "failed"},
        {"id": "registry_attachment", "status": "passed" if not any("registry_" in item for item in failures) else "failed"},
        {"id": "refs_resolved", "status": "passed" if not all_missing_refs and not all_unsafe_refs else "failed"},
    ]
    metrics = {
        "scenarios": len(scenario_results),
        "passing_scenarios": sum(1 for item in scenario_results if item["ok"]),
        "required_setup_flags": len(_as_string_list(policy.get("required_setup_flags"))),
        "required_uninstall_flags": len(_as_string_list(policy.get("required_uninstall_flags"))),
        "registry_entries": len(registry_result["entries"]),
        "refs": len(all_resolved_refs) + len(all_missing_refs) + len(all_unsafe_refs),
        "resolved_refs": len(all_resolved_refs),
        "missing_refs": len(all_missing_refs),
        "unsafe_refs": len(all_unsafe_refs),
    }
    return {
        "apiVersion": API_VERSION,
        "kind": REPORT_KIND,
        "ok": not failures,
        "created_at": _nowz(),
        "policy_path": str(policy_path or ""),
        "registry_path": _display_path(registry),
        "project_root": _display_path(project),
        "package_root": _display_path(package),
        "failures": sorted(set(failures)),
        "metrics": metrics,
        "checks": checks,
        "script_checks": static_result["details"].get("script_checks", {}),
        "scenario_results": sorted(scenario_results, key=lambda item: item["id"]),
        "resolved_refs": sorted(all_resolved_refs, key=lambda item: (item["owner"], item["ref"])),
        "missing_refs": sorted(all_missing_refs, key=lambda item: (item["owner"], item["ref"])),
        "unsafe_refs": sorted(all_unsafe_refs, key=lambda item: (item["owner"], item["ref"])),
    }


def package_dry_run_report_to_gate_evidence(report: Dict[str, Any], *, artifact_uri: str = "") -> Dict[str, Any]:
    if not isinstance(report, dict) or report.get("kind") != REPORT_KIND:
        raise ValueError("package_dry_run_report_required")
    status = "passed" if report.get("ok") else "failed"
    return {
        "artifact_uri": str(artifact_uri or report.get("artifact_uri") or ""),
        "run_at": str(report.get("created_at") or _nowz()),
        "checks": [
            {"id": "pipeline_eval", "status": status, "score": 1.0 if status == "passed" else 0.0, "threshold": 1.0},
            {"id": "rollback_plan", "status": status, "score": 1.0 if status == "passed" else 0.0, "threshold": 1.0},
            {"id": "safety_eval", "status": status, "score": 1.0 if status == "passed" else 0.0, "threshold": 1.0},
        ],
    }


def _default_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate NoemaForge install/uninstall dry-run contracts.")
    parser.add_argument("--project-root", default=str(_default_project_root()), help="Project root containing noemaforge/ and docs/.")
    parser.add_argument("--package-root", default="", help="Package root, default: <project-root>/noemaforge.")
    parser.add_argument(
        "--policy",
        default="noemaforge/configs/package-dry-run-validation-policy.json",
        help="Policy path, absolute or relative to project root.",
    )
    parser.add_argument("--registry", default="", help="Optional Unified Registry path.")
    parser.add_argument("--summary", action="store_true", help="Emit a compact validation summary.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    project_root = _as_path(args.project_root)
    package_root = _as_path(args.package_root) if args.package_root else project_root / "noemaforge"
    policy_path = Path(args.policy)
    if not policy_path.is_absolute():
        policy_path = project_root / policy_path
    registry_path = Path(args.registry) if args.registry else package_root / "configs" / "unified-registry.json"
    if not registry_path.is_absolute():
        registry_path = project_root / registry_path

    report = validate_package_dry_run_policy(
        load_policy(policy_path),
        project_root=project_root,
        package_root=package_root,
        policy_path=policy_path,
        registry_path=registry_path,
    )
    if args.summary:
        payload: Dict[str, Any] = {
            "apiVersion": report["apiVersion"],
            "kind": "PackageDryRunValidationSummary",
            "ok": report["ok"],
            "created_at": report["created_at"],
            "policy_path": report["policy_path"],
            "registry_path": report["registry_path"],
            "metrics": report["metrics"],
            "failures": report["failures"],
        }
    else:
        payload = report
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

