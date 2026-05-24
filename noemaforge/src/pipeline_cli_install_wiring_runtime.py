#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/pipeline_cli_install_wiring_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-21
Modified: 2026-05-21
Purpose: Validate offline installer wiring for the public pipeline CLI entrypoint.
Inputs: Pipeline CLI install wiring policy, setup script, installer and packaged CLI.
Outputs: JSON-compatible PipelineCliInstallWiringValidationReport artifacts.
Side effects: None; CLI writes JSON to stdout.
Tests: noemaforge/tests/test_pipeline_cli_install_wiring_runtime.py, QA and performance tests.
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
from typing import Any, Dict, List, Optional, Sequence


API_VERSION = "noemaforge.pipeline-cli-install-wiring/v1"
POLICY_KIND = "PipelineCliInstallWiringPolicy"
EXAMPLE_KIND = "PipelineCliInstallWiringExampleSet"
REPORT_KIND = "PipelineCliInstallWiringValidationReport"
POLICY_ID = "pipeline-cli-install-wiring-core"
PRIMARY_TODO = "Wire pipeline CLI into installed /usr/local/bin/noemaforge during installer/apply step."

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = PACKAGE_ROOT.parent
DEFAULT_POLICY = PACKAGE_ROOT / "configs" / "pipeline-cli-install-wiring-policy.json"
DEFAULT_EXAMPLE = PROJECT_ROOT / "prelaunch" / "governance" / "pipeline_cli_install_wiring.example.json"

VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
REQUIRED_SCRIPT_IDS = ["root_setup", "promoted_installer", "package_cli"]
MINIMUM_PIPELINE_COMMANDS = [
    "catalog",
    "run",
    "approve",
    "advance",
    "pause",
    "resume",
    "fail",
    "artifact",
    "worktree",
    "template-import",
    "template-append",
    "compact",
    "metrics",
    "executor-step",
    "validate",
]
SUMMARY_FIELDS = [
    "public_symlink_count",
    "pipeline_command_count",
    "setup_selftest_cli",
    "dry_run_link_plan",
    "canonical_self_guard",
    "pipeline_runtime_dispatch",
]
REQUIRED_CONTROLS = [
    "copy_payload_before_symlink",
    "public_cli_symlink_required",
    "dry_run_prints_link_without_writing",
    "setup_selftest_checks_cli",
    "cli_self_resolves_to_canonical_root",
    "no_public_wrapper_as_canonical_self",
    "pipeline_runtime_dispatch_required",
    "no_live_install_execution",
    "docs_changelog_trace_required",
]
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,220}$")


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
            failures.append(f"unsafe_ref:{owner}:{ref}")
            unsafe_refs.append({"owner": owner, "ref": ref})
            continue
        resolved = _resolve_ref(ref, project_root=project_root, package_root=package_root)
        resolved["owner"] = owner
        if resolved["ok"]:
            resolved_refs.append(resolved)
        else:
            failures.append(f"missing_ref:{owner}:{ref}")
            missing_refs.append(resolved)
    return {"failures": failures, "resolved_refs": resolved_refs, "missing_refs": missing_refs, "unsafe_refs": unsafe_refs}


def load_policy(policy_path: Path | str = DEFAULT_POLICY) -> Dict[str, Any]:
    return json.loads(Path(policy_path).read_text(encoding="utf-8"))


def load_example(example_path: Path | str = DEFAULT_EXAMPLE) -> Dict[str, Any]:
    return json.loads(Path(example_path).read_text(encoding="utf-8"))


def _scripts_by_id(policy: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    scripts = policy.get("required_scripts") if isinstance(policy.get("required_scripts"), list) else []
    return {str(item.get("id") or ""): item for item in scripts if isinstance(item, dict)}


def _resolved_script_texts(
    policy: Dict[str, Any],
    *,
    project_root: Path,
    package_root: Path,
) -> Dict[str, Any]:
    failures: List[str] = []
    scripts: Dict[str, Dict[str, Any]] = {}
    for script_id, item in _scripts_by_id(policy).items():
        ref = str(item.get("ref") or "").strip()
        resolved = _resolve_ref(ref, project_root=project_root, package_root=package_root)
        if not resolved["ok"]:
            failures.append(f"script_ref_missing:{script_id}:{ref}")
            scripts[script_id] = {"ref": ref, "path": "", "text": ""}
            continue
        path = Path(resolved["path"])
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = path.read_text(encoding="utf-8", errors="replace")
        scripts[script_id] = {"ref": ref, "path": resolved["path"], "text": text}
    return {"failures": failures, "scripts": scripts}


def _policy_failures(payload: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    policy = _policy_dict(payload)
    if payload.get("apiVersion") != API_VERSION:
        failures.append("policy_api_version_invalid")
    if payload.get("kind") != POLICY_KIND:
        failures.append("policy_kind_invalid")
    if payload.get("id") != POLICY_ID:
        failures.append("policy_id_invalid")
    if str(payload.get("status") or "") not in VALID_STATUSES:
        failures.append("policy_status_invalid")
    if str(policy.get("mode") or "") != "offline_contract":
        failures.append("policy_mode_not_offline_contract")
    if str(policy.get("activation_state") or "") != "pipeline_cli_installer_wiring_contract":
        failures.append("policy_activation_state_invalid")
    if str(policy.get("required_pipeline_ref") or "") != "pipeline:firstboot-model-selection:0.32.1":
        failures.append("policy_required_pipeline_ref_invalid")
    if PRIMARY_TODO not in _as_string_list(policy.get("closed_todo_refs")):
        failures.append("policy_closed_todo_ref_missing")
    if str(policy.get("required_public_entrypoint") or "") != "/usr/local/bin/noemaforge":
        failures.append("policy_public_entrypoint_invalid")
    if str(policy.get("canonical_cli_target") or "") != "/opt/noemaforge/bin/noemaforge":
        failures.append("policy_canonical_cli_target_invalid")
    script_ids = list(_scripts_by_id(policy).keys())
    for script_id in REQUIRED_SCRIPT_IDS:
        if script_id not in script_ids:
            failures.append(f"policy_required_script_missing:{script_id}")
    for item in policy.get("required_install_symlinks", []):
        if not isinstance(item, dict):
            failures.append("policy_required_symlink_not_object")
            continue
        public_path = str(item.get("public_path") or "")
        target_path = str(item.get("target_path") or "")
        if not public_path.startswith("/") or not target_path.startswith("/"):
            failures.append(f"policy_symlink_path_invalid:{public_path}")
    symlinks = policy.get("required_install_symlinks") if isinstance(policy.get("required_install_symlinks"), list) else []
    if not any(
        isinstance(item, dict)
        and item.get("public_path") == "/usr/local/bin/noemaforge"
        and item.get("target_path") == "/opt/noemaforge/bin/noemaforge"
        for item in symlinks
    ):
        failures.append("policy_primary_public_symlink_missing")
    commands = _as_string_list(policy.get("required_pipeline_commands"))
    for command in MINIMUM_PIPELINE_COMMANDS:
        if command not in commands:
            failures.append(f"policy_pipeline_command_missing:{command}")
    controls = policy.get("controls") if isinstance(policy.get("controls"), dict) else {}
    for key in REQUIRED_CONTROLS:
        if controls.get(key) is not True:
            failures.append(f"control_{key}_not_true")
    if policy.get("require_registry_attachment") is not True:
        failures.append("policy_require_registry_attachment_not_true")
    if policy.get("require_docs_and_changelog_refs") is not True:
        failures.append("policy_require_docs_and_changelog_refs_not_true")
    if _as_string_list(policy.get("summary_fields")) != SUMMARY_FIELDS:
        failures.append("policy_summary_fields_invalid")
    if not _as_string_list(policy.get("required_outputs")):
        failures.append("policy_required_outputs_empty")
    if not _as_string_list(policy.get("required_refs")):
        failures.append("policy_required_refs_empty")
    return failures


def _example_failures(example: Dict[str, Any], *, policy: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    if example.get("apiVersion") != API_VERSION:
        failures.append("example_api_version_invalid")
    if example.get("kind") != EXAMPLE_KIND:
        failures.append("example_kind_invalid")
    plan = example.get("install_plan") if isinstance(example.get("install_plan"), dict) else {}
    if plan.get("public_entrypoint") != policy.get("required_public_entrypoint"):
        failures.append("example_public_entrypoint_mismatch")
    if plan.get("canonical_target") != policy.get("canonical_cli_target"):
        failures.append("example_canonical_target_mismatch")
    surface = example.get("pipeline_surface") if isinstance(example.get("pipeline_surface"), dict) else {}
    commands = _as_string_list(surface.get("commands"))
    for command in _as_string_list(policy.get("required_pipeline_commands")):
        if command not in commands:
            failures.append(f"example_pipeline_command_missing:{command}")
    expected = example.get("expected_summary") if isinstance(example.get("expected_summary"), dict) else {}
    if expected.get("public_symlink_count") != len(policy.get("required_install_symlinks", [])):
        failures.append("example_public_symlink_count_mismatch")
    if expected.get("pipeline_command_count") != len(_as_string_list(policy.get("required_pipeline_commands"))):
        failures.append("example_pipeline_command_count_mismatch")
    for key in ["setup_selftest_cli", "dry_run_link_plan", "canonical_self_guard", "pipeline_runtime_dispatch"]:
        if expected.get(key) is not True:
            failures.append(f"example_expected_{key}_not_true")
    return failures


def _installer_payload_copy_ok(installer_text: str) -> bool:
    return (
        'mkdir -p "$(target /opt/noemaforge)"' in installer_text
        and 'rsync -a "$PKG_DIR/noemaforge/" "$(target /opt/noemaforge)/"' in installer_text
        and 'cp -a "$PKG_DIR/noemaforge/." "$(target /opt/noemaforge)/"' in installer_text
    )


def _installer_symlink_failures(installer_text: str, symlinks: Sequence[Dict[str, Any]]) -> List[str]:
    failures: List[str] = []
    for item in symlinks:
        public_path = str(item.get("public_path") or "").strip()
        target_path = str(item.get("target_path") or "").strip()
        pattern = r"(?m)^\s*install_symlink\s+" + re.escape(target_path) + r"\s+" + re.escape(public_path) + r"\s*$"
        if not re.search(pattern, installer_text):
            failures.append(f"installer_symlink_missing:{public_path}")
    return failures


def _installer_dry_run_link_ok(installer_text: str) -> bool:
    return (
        "install_symlink()" in installer_text
        and '[[ "$DRY_RUN" == 1 ]]' in installer_text
        and 'echo "link $dst -> $src"' in installer_text
        and "return 0" in installer_text
    )


def _setup_selftest_cli_ok(setup_text: str) -> bool:
    return 'bash -n "$PKG_DIR/noemaforge/bin/noemaforge"' in setup_text


def _cli_canonical_self_guard_ok(cli_text: str) -> bool:
    required_tokens = [
        'NOEMAFORGE_SELF_CANDIDATE="$ROOT/bin/noemaforge"',
        "/usr/local/bin/noemaforge",
        "/usr/local/sbin/noemaforge",
        "/usr/bin/noemaforge",
        "/bin/noemaforge",
        "canonical NoemaForge CLI resolved to public wrapper path",
    ]
    return all(token in cli_text for token in required_tokens)


def _pipeline_runtime_dispatch_ok(cli_text: str) -> bool:
    return (
        "cmd_pipeline()" in cli_text
        and 'NOEMAFORGE_ROOT="$ROOT" /usr/bin/python3 "$ROOT/src/pipeline_runtime.py" "$@"' in cli_text
        and 'pipeline|pipelines) cmd_pipeline "$@" ;;' in cli_text
    )


def _pipeline_command_failures(cli_text: str, commands: Sequence[str]) -> List[str]:
    failures: List[str] = []
    if "noemaforge pipeline" not in cli_text:
        failures.append("cli_pipeline_help_missing")
    for command in commands:
        if command not in cli_text:
            failures.append(f"cli_pipeline_command_missing:{command}")
    return failures


def analyze_pipeline_cli_install_wiring(
    policy_payload: Dict[str, Any],
    *,
    project_root: Path | str = PROJECT_ROOT,
    package_root: Path | str = PACKAGE_ROOT,
) -> Dict[str, Any]:
    project = Path(project_root).resolve()
    package = Path(package_root).resolve()
    policy = _policy_dict(policy_payload)
    failures: List[str] = []
    script_report = _resolved_script_texts(policy, project_root=project, package_root=package)
    failures.extend(script_report["failures"])
    scripts = script_report["scripts"]
    setup_text = scripts.get("root_setup", {}).get("text", "")
    installer_text = scripts.get("promoted_installer", {}).get("text", "")
    cli_text = scripts.get("package_cli", {}).get("text", "")
    symlinks = policy.get("required_install_symlinks") if isinstance(policy.get("required_install_symlinks"), list) else []
    commands = _as_string_list(policy.get("required_pipeline_commands"))

    payload_copy = _installer_payload_copy_ok(installer_text)
    if not payload_copy:
        failures.append("installer_payload_copy_missing")
    symlink_failures = _installer_symlink_failures(installer_text, symlinks)
    failures.extend(symlink_failures)
    dry_run_link_plan = _installer_dry_run_link_ok(installer_text)
    if not dry_run_link_plan:
        failures.append("installer_dry_run_link_plan_missing")
    setup_selftest_cli = _setup_selftest_cli_ok(setup_text)
    if not setup_selftest_cli:
        failures.append("setup_cli_selftest_missing")
    canonical_self_guard = _cli_canonical_self_guard_ok(cli_text)
    if not canonical_self_guard:
        failures.append("cli_canonical_self_guard_missing")
    pipeline_runtime_dispatch = _pipeline_runtime_dispatch_ok(cli_text)
    if not pipeline_runtime_dispatch:
        failures.append("cli_pipeline_runtime_dispatch_missing")
    command_failures = _pipeline_command_failures(cli_text, commands)
    failures.extend(command_failures)

    return {
        "failures": failures,
        "summary": {
            "public_symlink_count": len(symlinks) - len(symlink_failures),
            "pipeline_command_count": len(commands) - len([item for item in command_failures if item.startswith("cli_pipeline_command_missing:")]),
            "setup_selftest_cli": setup_selftest_cli,
            "dry_run_link_plan": dry_run_link_plan,
            "canonical_self_guard": canonical_self_guard,
            "pipeline_runtime_dispatch": pipeline_runtime_dispatch,
            "payload_copy_before_symlink": payload_copy,
        },
        "script_paths": {script_id: item.get("path", "") for script_id, item in scripts.items()},
    }


def validate_pipeline_cli_install_wiring_policy(
    policy_payload: Dict[str, Any],
    *,
    project_root: Path | str = PROJECT_ROOT,
    package_root: Path | str = PACKAGE_ROOT,
    example_path: Path | str = DEFAULT_EXAMPLE,
) -> Dict[str, Any]:
    project = Path(project_root).resolve()
    package = Path(package_root).resolve()
    failures: List[str] = []
    failures.extend(_policy_failures(policy_payload))
    policy = _policy_dict(policy_payload)

    refs = _as_string_list(policy_payload.get("refs")) + _as_string_list(policy.get("required_refs"))
    ref_report = _resolve_refs(refs, project_root=project, package_root=package, owner=POLICY_ID)
    failures.extend(ref_report["failures"])

    failures.extend(_example_failures(load_example(example_path), policy=policy))
    analysis = analyze_pipeline_cli_install_wiring(policy_payload, project_root=project, package_root=package)
    failures.extend(analysis["failures"])

    return {
        "apiVersion": API_VERSION,
        "kind": REPORT_KIND,
        "ok": not failures,
        "created_at": _nowz(),
        "id": POLICY_ID,
        "failures": sorted(set(failures)),
        "pipeline_cli_install_wiring_summary": analysis["summary"],
        "script_paths": analysis["script_paths"],
        "resolved_refs": ref_report["resolved_refs"],
        "missing_refs": ref_report["missing_refs"],
        "unsafe_refs": ref_report["unsafe_refs"],
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate NoemaForge pipeline CLI install wiring.")
    parser.add_argument("--policy", default=str(DEFAULT_POLICY), help="Policy JSON path.")
    parser.add_argument("--example", default=str(DEFAULT_EXAMPLE), help="Example install wiring path.")
    parser.add_argument("--summary", action="store_true", help="Emit compact summary.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    report = validate_pipeline_cli_install_wiring_policy(load_policy(args.policy), example_path=args.example)
    payload: Dict[str, Any]
    if args.summary:
        payload = {
            "apiVersion": API_VERSION,
            "kind": "PipelineCliInstallWiringSummary",
            "id": POLICY_ID,
            "ok": report["ok"],
            "failures": report["failures"],
            "summary": report["pipeline_cli_install_wiring_summary"],
        }
    else:
        payload = report
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
