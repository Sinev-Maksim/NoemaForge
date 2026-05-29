#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/dashboard_launcher_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate local dashboard launcher contracts.
Inputs: noemaforge/configs/dashboard-launcher-policy.json and dashboard launcher examples.
Outputs: JSON-compatible DashboardLauncherValidationReport artifacts.
Side effects: None unless run as a CLI, which writes JSON to stdout.
Tests: noemaforge/tests/test_dashboard_launcher_runtime.py
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


API_VERSION = "noemaforge.dashboard-launcher/v1"
POLICY_KIND = "DashboardLauncherPolicy"
SET_KIND = "DashboardLauncherExampleSet"
REPORT_KIND = "DashboardLauncherValidationReport"

VALID_POLICY_STATUSES = {"draft", "shadow", "stable", "retired"}
REQUIRED_COMMANDS = {
    "path",
    "state",
    "serve",
    "start",
    "stop",
    "status",
    "autostart-enable",
    "autostart-disable",
    "autostart-status",
}
REQUIRED_REF_KEYS = {"cli", "launcher", "dashboard_ui", "state_runtime", "gui_runtime"}
REQUIRED_CONTROLS = {
    "writes_dashboard_state",
    "serves_static_ui",
    "localhost_only",
    "operator_writable_state_required",
    "no_llm_autostart",
    "no_media_autostart",
    "background_pidfile_required",
    "status_command_required",
    "user_systemd_autostart_required",
    "autostart_dry_run_required",
    "no_root_required_for_user_autostart",
}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,220}$")
LLM_AUTOSTART_PATTERNS = [
    r"\bsystemctl\s+start\s+noemaforge-llama",
    r"\bnoemaforge\s+safe-start\b",
    r"\bllama-server\b",
]
MEDIA_AUTOSTART_PATTERNS = [
    r"\bffmpeg\b",
    r"\barecord\b",
    r"\bvoice\.capture\b",
]


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


def load_text(path: Path | str) -> str:
    return Path(path).read_text(encoding="utf-8")


def _policy_dict(payload: Dict[str, Any]) -> Dict[str, Any]:
    return payload.get("policy") if isinstance(payload.get("policy"), dict) else payload


def _registry_ref(entry: Dict[str, Any]) -> str:
    return f"{entry.get('kind')}:{entry.get('id')}:{entry.get('version')}"


def _patterns_found(text: str, patterns: Sequence[str]) -> List[str]:
    return [pattern for pattern in patterns if re.search(pattern, text)]


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
    if str(policy.get("activation_state") or "") != "local_dashboard_launcher":
        failures.append("policy_activation_state_invalid")
    for key in ["require_trace_id", "require_registry_attachment", "require_docs_and_changelog_refs"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    if not str(policy.get("required_pipeline_ref") or "").startswith("pipeline:"):
        failures.append("policy_required_pipeline_ref_invalid")
    if not REQUIRED_COMMANDS.issubset(set(_as_string_list(policy.get("required_cli_commands")))):
        failures.append("policy_required_cli_commands_missing")
    refs = policy.get("required_refs") if isinstance(policy.get("required_refs"), dict) else {}
    for key in REQUIRED_REF_KEYS:
        if not str(refs.get(key) or "").strip():
            failures.append(f"policy_required_ref_missing:{key}")
    controls = policy.get("launcher_controls") if isinstance(policy.get("launcher_controls"), dict) else {}
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
            "configs/dashboard-launcher-policy.json",
            "contracts/dashboard_launcher.schema.json",
            "src/dashboard_launcher_runtime.py",
            "tests/test_dashboard_launcher_runtime.py",
            "tests/test_dashboard_launcher_qa.py",
            "tests/test_dashboard_launcher_performance.py",
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
        "configs/dashboard-launcher-policy.json",
        "contracts/dashboard_launcher.schema.json",
        "src/dashboard_launcher_runtime.py",
        "prelaunch/governance/dashboard_launcher.example.json",
    ]:
        if ref not in pipeline_refs:
            failures.append(f"registry_pipeline_ref_missing:{ref}")
    return {"failures": failures, "registry_report": report, "entries": entries, "pipeline_eval_refs": pipeline_eval_refs}


def _static_launcher_failures(payload: Dict[str, Any], *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    refs = _policy_dict(payload).get("required_refs") or {}
    resolved = {key: _resolve_ref(str(ref), project_root=project_root, package_root=package_root) for key, ref in refs.items()}
    failures: List[str] = []
    for key, item in resolved.items():
        if not item.get("ok"):
            failures.append(f"launcher_required_ref_unresolved:{key}:{refs.get(key)}")
    launcher_text = load_text(resolved["launcher"]["path"]) if resolved.get("launcher", {}).get("ok") else ""
    cli_text = load_text(resolved["cli"]["path"]) if resolved.get("cli", {}).get("ok") else ""
    ui_text = load_text(resolved["dashboard_ui"]["path"]) if resolved.get("dashboard_ui", {}).get("ok") else ""

    action_match = re.search(r'case\s+"\$action"\s+in\s+([A-Za-z0-9_|-]+)\)', launcher_text)
    action_words = set((action_match.group(1).split("|") if action_match else []))
    launcher_commands = REQUIRED_COMMANDS.intersection(action_words)
    script_checks = {
        "commands": sorted(launcher_commands),
        "uses_dashboard_state_runtime": "dashboard-state" in launcher_text and "pipeline_runtime.py" in launcher_text and "--out" in launcher_text,
        "uses_admin_gui_server": "admin_gui_server.py" in launcher_text,
        "uses_operator_state_home": "XDG_STATE_HOME" in launcher_text and "$HOME/.local/state" in launcher_text,
        "uses_pidfile": "dashboard.pid" in launcher_text,
        "status_branch": "NoemaForge dashboard running" in launcher_text and "NoemaForge dashboard not running" in launcher_text,
        "localhost_url": "127.0.0.1" in launcher_text,
        "user_systemd_autostart": "systemd/user" in launcher_text and "noemaforge-dashboard.timer" in launcher_text,
        "user_autostart_enable": "systemctl --user enable" in launcher_text and "autostart-enable" in launcher_text,
        "user_autostart_disable": "systemctl --user disable" in launcher_text and "autostart-disable" in launcher_text,
        "user_autostart_status": "autostart-status" in launcher_text and "systemctl --user is-enabled" in launcher_text,
        "autostart_dry_run": "--dry-run" in launcher_text and "autostart dry-run" in launcher_text,
        "user_autostart_no_sudo": "sudo" not in launcher_text,
        "llm_autostart_patterns": _patterns_found(launcher_text, LLM_AUTOSTART_PATTERNS),
        "media_autostart_patterns": _patterns_found(launcher_text, MEDIA_AUTOSTART_PATTERNS),
        "cli_dispatch": "cmd_dashboard" in cli_text and "noemaforge-dashboard.sh" in cli_text,
        "ui_has_app_shell": "<html" in ui_text.lower() and "script" in ui_text.lower(),
    }
    missing_commands = sorted(REQUIRED_COMMANDS.difference(launcher_commands))
    for command in missing_commands:
        failures.append(f"launcher_command_missing:{command}")
    if not script_checks["uses_dashboard_state_runtime"]:
        failures.append("launcher_dashboard_state_runtime_missing")
    if not script_checks["uses_admin_gui_server"]:
        failures.append("launcher_admin_gui_server_missing")
    if not script_checks["uses_operator_state_home"]:
        failures.append("launcher_operator_writable_state_missing")
    if not script_checks["uses_pidfile"]:
        failures.append("launcher_pidfile_missing")
    if not script_checks["status_branch"]:
        failures.append("launcher_status_branch_missing")
    if not script_checks["localhost_url"]:
        failures.append("launcher_localhost_url_missing")
    if not script_checks["user_systemd_autostart"]:
        failures.append("launcher_user_systemd_autostart_missing")
    if not script_checks["user_autostart_enable"]:
        failures.append("launcher_user_autostart_enable_missing")
    if not script_checks["user_autostart_disable"]:
        failures.append("launcher_user_autostart_disable_missing")
    if not script_checks["user_autostart_status"]:
        failures.append("launcher_user_autostart_status_missing")
    if not script_checks["autostart_dry_run"]:
        failures.append("launcher_autostart_dry_run_missing")
    if not script_checks["user_autostart_no_sudo"]:
        failures.append("launcher_user_autostart_requires_sudo")
    if script_checks["llm_autostart_patterns"]:
        failures.append("launcher_llm_autostart_pattern_present")
    if script_checks["media_autostart_patterns"]:
        failures.append("launcher_media_autostart_pattern_present")
    if not script_checks["cli_dispatch"]:
        failures.append("cli_dashboard_dispatch_missing")
    if not script_checks["ui_has_app_shell"]:
        failures.append("dashboard_ui_shell_missing")
    return {"failures": failures, "script_checks": script_checks, "resolved_required_refs": resolved}


def _scenario_failures(scenario: Dict[str, Any], policy_payload: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    scenario_id = str(scenario.get("id") or "<missing>")
    if not SAFE_ID_RE.match(scenario_id):
        failures.append(f"scenario_id_invalid:{scenario_id}")
    if _policy_dict(policy_payload).get("require_trace_id") is True and not SAFE_ID_RE.match(str(scenario.get("trace_id") or "")):
        failures.append(f"scenario_trace_id_invalid:{scenario_id}")
    commands = set(_as_string_list(scenario.get("commands")))
    if not commands:
        failures.append(f"scenario_commands_missing:{scenario_id}")
    if not commands.issubset(REQUIRED_COMMANDS):
        failures.append(f"scenario_commands_invalid:{scenario_id}")
    expected = scenario.get("expected") if isinstance(scenario.get("expected"), dict) else {}
    if expected.get("starts_llm") is not False:
        failures.append(f"scenario_starts_llm_not_false:{scenario_id}")
    if expected.get("starts_media_backend") is not False:
        failures.append(f"scenario_starts_media_backend_not_false:{scenario_id}")
    if expected.get("requires_root") is not False:
        failures.append(f"scenario_requires_root_not_false:{scenario_id}")
    if "state" in commands and expected.get("writes_dashboard_state") is not True:
        failures.append(f"scenario_state_write_missing:{scenario_id}")
    if "serve" in commands and expected.get("serves_static_ui") is not True:
        failures.append(f"scenario_static_serve_missing:{scenario_id}")
    if {"start", "status", "stop"}.intersection(commands) and expected.get("background_pidfile") is not True:
        failures.append(f"scenario_pidfile_missing:{scenario_id}")
    if {"autostart-enable", "autostart-disable", "autostart-status"}.intersection(commands):
        if expected.get("user_systemd_timer") is not True:
            failures.append(f"scenario_user_systemd_timer_missing:{scenario_id}")
        if expected.get("dry_run_available") is not True:
            failures.append(f"scenario_autostart_dry_run_missing:{scenario_id}")
    return failures


def validate_dashboard_launcher_policy(
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
    static_result = _static_launcher_failures(payload, project_root=project, package_root=package)
    failures.extend(static_result["failures"])

    all_resolved_refs: List[Dict[str, Any]] = []
    all_missing_refs: List[Dict[str, Any]] = []
    all_unsafe_refs: List[Dict[str, Any]] = []
    scenario_results: List[Dict[str, Any]] = []

    refs_to_resolve = sorted(set(_as_string_list(payload.get("refs")) + _as_string_list((policy.get("required_refs") or {}).values())))
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
            scenario_results.append({"id": scenario_id, "ok": not scenario_failures, "commands": len(_as_string_list(scenario.get("commands"))), "failures": sorted(set(scenario_failures))})

    checks = [
        {"id": "cli_commands", "status": "passed" if not any("command_missing" in item for item in failures) else "failed"},
        {"id": "state_writer", "status": "passed" if not any("dashboard_state_runtime" in item for item in failures) else "failed"},
        {"id": "static_ui_server", "status": "passed" if not any("admin_gui_server" in item or "ui_shell" in item for item in failures) else "failed"},
        {"id": "operator_writable_state", "status": "passed" if not any("operator_writable" in item for item in failures) else "failed"},
        {"id": "user_dashboard_autostart", "status": "passed" if not any("autostart" in item or "user_systemd" in item for item in failures) else "failed"},
        {"id": "no_llm_or_media_autostart", "status": "passed" if not any("autostart_pattern" in item for item in failures) else "failed"},
        {"id": "registry_attachment", "status": "passed" if not any("registry_" in item for item in failures) else "failed"},
        {"id": "refs_resolved", "status": "passed" if not all_missing_refs and not all_unsafe_refs else "failed"},
    ]
    metrics = {
        "scenarios": len(scenario_results),
        "passing_scenarios": sum(1 for item in scenario_results if item["ok"]),
        "required_cli_commands": len(_as_string_list(policy.get("required_cli_commands"))),
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
        "script_checks": static_result["script_checks"],
        "scenario_results": sorted(scenario_results, key=lambda item: item["id"]),
        "resolved_refs": sorted(all_resolved_refs, key=lambda item: (item["owner"], item["ref"])),
        "missing_refs": sorted(all_missing_refs, key=lambda item: (item["owner"], item["ref"])),
        "unsafe_refs": sorted(all_unsafe_refs, key=lambda item: (item["owner"], item["ref"])),
    }


def dashboard_launcher_report_to_gate_evidence(report: Dict[str, Any], *, artifact_uri: str = "") -> Dict[str, Any]:
    if not isinstance(report, dict) or report.get("kind") != REPORT_KIND:
        raise ValueError("dashboard_launcher_report_required")
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
    parser = argparse.ArgumentParser(description="Validate NoemaForge local dashboard launcher contracts.")
    parser.add_argument("--project-root", default=str(_default_project_root()), help="Project root containing noemaforge/ and docs/.")
    parser.add_argument("--package-root", default="", help="Package root, default: <project-root>/noemaforge.")
    parser.add_argument(
        "--policy",
        default="noemaforge/configs/dashboard-launcher-policy.json",
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

    report = validate_dashboard_launcher_policy(
        load_policy(policy_path),
        project_root=project_root,
        package_root=package_root,
        policy_path=policy_path,
        registry_path=registry_path,
    )
    if args.summary:
        payload: Dict[str, Any] = {
            "apiVersion": report["apiVersion"],
            "kind": "DashboardLauncherValidationSummary",
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
