#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/production_gui_installer_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate the production GUI installer readiness contract without touching a live host.
Inputs: Production GUI installer policy, setup/installer scripts, systemd units, registry and examples.
Outputs: JSON-compatible ProductionGuiInstallerValidationReport artifacts.
Side effects: None; CLI writes JSON to stdout.
Tests: noemaforge/tests/test_production_gui_installer_runtime.py
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


API_VERSION = "noemaforge.production-gui-installer/v1"
POLICY_KIND = "ProductionGuiInstallerPolicy"
EXAMPLE_KIND = "ProductionGuiInstallerExampleSet"
REPORT_KIND = "ProductionGuiInstallerValidationReport"
POLICY_ID = "production-gui-installer-core"
SELECTED_TODO = "Production-grade GUI installer."
VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,220}$")
SRC_DIR = Path(__file__).resolve().parent

REQUIRED_OUTPUTS = {
    "dry_run_first",
    "root_guarded_install",
    "timer_driven_gui_autostart",
    "runtime_only_gui",
    "stateful_admin_gui_available",
    "recovery_helpers_installed",
}
BLOCKED_SIDE_EFFECTS = {
    "no_live_host_required_for_validation",
    "no_heavy_llm_autostart",
    "no_direct_graphical_target_service_enable",
    "no_hidden_network_dependency",
}
REGISTRY_REFS = [
    "configs/production-gui-installer-policy.json",
    "contracts/production_gui_installer.schema.json",
    "configs/alpha-feature-coverage.json",
    "src/production_gui_installer_runtime.py",
    "tests/test_production_gui_installer_runtime.py",
    "tests/test_production_gui_installer_qa.py",
    "tests/test_production_gui_installer_performance.py",
    "prelaunch/governance/production_gui_installer.example.json",
    "docs/README.md",
    "docs/TODO.md",
    "docs/reference/PROJECT_CONTEXT.md",
    "docs/backlog/ROADMAP_AND_TODO.md",
    "docs/history/CHANGELOG.md",
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


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def _contains(text: str, needle: str) -> bool:
    return _norm(needle) in _norm(text)


def _is_safe_relative_ref(ref: str) -> bool:
    text = str(ref or "").strip().replace("\\", "/")
    if not text or text.startswith("/") or text.startswith("~"):
        return False
    return not any(part in {"", ".", ".."} for part in PurePosixPath(text).parts)


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


def load_json(path: Path | str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_policy(path: Path | str) -> Dict[str, Any]:
    return load_json(path)


def load_example_set(path: Path | str) -> Dict[str, Any]:
    return load_json(path)


def _read_ref(ref: str, *, project_root: Path, package_root: Path) -> str:
    resolved = _resolve_ref(ref, project_root=project_root, package_root=package_root)
    if not resolved.get("ok"):
        return ""
    return Path(resolved["path"]).read_text(encoding="utf-8")


def analyze_installer_surface(payload: Dict[str, Any], *, project_root: Path | str, package_root: Path | str) -> Dict[str, Any]:
    project = Path(project_root).resolve()
    package = Path(package_root).resolve()
    policy = _policy_dict(payload)
    scripts = policy.get("required_scripts") if isinstance(policy.get("required_scripts"), dict) else {}
    setup_text = _read_ref(str(scripts.get("setup") or ""), project_root=project, package_root=package)
    installer_text = _read_ref(str(scripts.get("installer") or ""), project_root=project, package_root=package)
    cli_text = _read_ref(str(scripts.get("cli") or ""), project_root=project, package_root=package)
    failures: List[str] = []
    for token in _as_string_list(policy.get("required_setup_tokens")):
        if token not in setup_text:
            failures.append(f"setup_token_missing:{token}")
    for token in _as_string_list(policy.get("required_installer_tokens")):
        if token not in installer_text:
            failures.append(f"installer_token_missing:{token}")
    for token in _as_string_list(policy.get("required_cli_tokens")):
        if token not in cli_text:
            failures.append(f"cli_token_missing:{token}")
    if "exec \"$PKG_DIR/install_noemaforge_0.32.2_mvp.sh\"" not in setup_text:
        failures.append("setup_does_not_delegate_to_current_installer")
    if re.search(r"systemctl\s+enable\s+noemaforge-autostart-gui\.service", installer_text):
        failures.append("installer_enables_direct_gui_service")
    if "systemctl enable noemaforge-autostart-gui.timer" not in installer_text:
        failures.append("installer_missing_gui_timer_enable")
    if "systemctl disable noemaforge-autostart-gui.service" not in installer_text:
        failures.append("installer_missing_direct_gui_service_disable")
    return {
        "ok": not failures,
        "failures": failures,
        "flags": {
            "dry_run_first": "--dry-run" in setup_text and "--dry-run" in installer_text,
            "root_guarded_install": "non-dry-run install requires sudo/root" in setup_text and "run live install as root" in installer_text,
            "timer_driven_gui_autostart": "noemaforge-autostart-gui.timer" in installer_text and "GUI autostart uses delayed timer" in setup_text,
            "runtime_only_gui": "runtime_only" in installer_text,
            "no_heavy_llm_autostart": "heavy_llm_autostart=manual_only" in installer_text or "heavy_llm_autostart\": \"manual_only\"" in installer_text,
        },
    }


def _policy_failures(payload: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    policy = _policy_dict(payload)
    if payload.get("apiVersion") != API_VERSION:
        failures.append("policy_api_version_invalid")
    if payload.get("kind") != POLICY_KIND:
        failures.append("policy_kind_invalid")
    if payload.get("id") != POLICY_ID or not SAFE_ID_RE.match(str(payload.get("id") or "")):
        failures.append("policy_id_invalid")
    if str(payload.get("status") or "") not in VALID_STATUSES:
        failures.append("policy_status_invalid")
    if policy.get("mode") != "offline_contract":
        failures.append("policy_mode_invalid")
    if policy.get("activation_state") != "setup_installer_gui_readiness_contract":
        failures.append("policy_activation_state_invalid")
    if policy.get("selected_todo") != SELECTED_TODO:
        failures.append("policy_selected_todo_invalid")
    for key in ["require_docs_and_changelog_refs", "require_registry_attachment", "require_no_live_host_dependency"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    if not str(policy.get("required_pipeline_ref") or "").startswith("pipeline:"):
        failures.append("policy_required_pipeline_ref_invalid")
    for key in ["required_gui_assets", "required_gui_units", "required_existing_contracts", "required_setup_tokens", "required_installer_tokens", "required_cli_tokens", "required_example_sets", "required_doc_refs"]:
        if not _as_string_list(policy.get(key)):
            failures.append(f"policy_{key}_empty")
    scripts = policy.get("required_scripts") if isinstance(policy.get("required_scripts"), dict) else {}
    for key in ["setup", "installer", "cli"]:
        if not _is_safe_relative_ref(str(scripts.get(key) or "")):
            failures.append(f"policy_required_script_invalid:{key}")
    service_tokens = policy.get("required_service_tokens") if isinstance(policy.get("required_service_tokens"), dict) else {}
    if not service_tokens:
        failures.append("policy_required_service_tokens_empty")
    return failures


def _asset_report(policy: Dict[str, Any], *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    failures: List[str] = []
    resolved_assets: List[Dict[str, Any]] = []
    for ref in _as_string_list(policy.get("required_gui_assets")):
        resolved = _resolve_ref(ref, project_root=project_root, package_root=package_root)
        if not resolved.get("ok"):
            failures.append(f"gui_asset_missing:{ref}")
        resolved_assets.append(resolved)
    return {"failures": failures, "resolved_assets": resolved_assets}


def _unit_report(policy: Dict[str, Any], *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    failures: List[str] = []
    unit_reports: List[Dict[str, Any]] = []
    service_tokens = policy.get("required_service_tokens") if isinstance(policy.get("required_service_tokens"), dict) else {}
    for ref in _as_string_list(policy.get("required_gui_units")):
        resolved = _resolve_ref(ref, project_root=project_root, package_root=package_root)
        local_failures: List[str] = []
        text = Path(resolved["path"]).read_text(encoding="utf-8") if resolved.get("ok") else ""
        if not resolved.get("ok"):
            local_failures.append("unit_missing")
        for token in _as_string_list(service_tokens.get(ref)):
            if token not in text:
                local_failures.append(f"unit_token_missing:{token}")
        if ref.endswith("noemaforge-autostart-gui.service") and "[Install]" in text:
            local_failures.append("gui_service_has_install_section")
        if ref.endswith("noemaforge-autostart-gui.timer") and "OnBootSec=3min" not in text:
            local_failures.append("gui_timer_delay_missing")
        failures.extend(f"unit:{ref}:{item}" for item in local_failures)
        unit_reports.append({"ref": ref, "ok": not local_failures, "failures": local_failures, "resolved": resolved})
    return {"failures": failures, "unit_reports": unit_reports}


def _contract_report(policy: Dict[str, Any], *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    failures: List[str] = []
    contracts: List[Dict[str, Any]] = []
    for ref in _as_string_list(policy.get("required_existing_contracts")):
        resolved = _resolve_ref(ref, project_root=project_root, package_root=package_root)
        if not resolved.get("ok"):
            failures.append(f"existing_contract_missing:{ref}")
        contracts.append(resolved)
    return {"failures": failures, "contracts": contracts}


def _registry_report(payload: Dict[str, Any], *, package_root: Path) -> Dict[str, Any]:
    failures: List[str] = []
    policy = _policy_dict(payload)
    registry = load_json(package_root / "configs" / "unified-registry.json")
    entries = registry.get("entries") if isinstance(registry.get("entries"), list) else []
    eval_ref = f"eval-pack:{payload.get('id')}:{payload.get('version')}"
    matches = [entry for entry in entries if entry.get("kind") == "eval-pack" and entry.get("id") == POLICY_ID]
    if len(matches) != 1:
        failures.append(f"registry_eval_pack_count_invalid:{len(matches)}")
        refs: set[str] = set()
        metrics: set[str] = set()
    else:
        refs = set(_as_string_list(matches[0].get("refs")))
        metadata = matches[0].get("metadata") if isinstance(matches[0].get("metadata"), dict) else {}
        metrics = set(_as_string_list(metadata.get("metrics")))
    for ref in REGISTRY_REFS:
        if ref not in refs:
            failures.append(f"registry_ref_missing:{ref}")
    for metric in ["dry_run_first", "timer_driven_gui_autostart", "stateful_admin_gui", "systemd_happy_path", "refs_resolved"]:
        if metric not in metrics:
            failures.append(f"registry_metric_missing:{metric}")
    pipeline_ref = str(policy.get("required_pipeline_ref") or "")
    pipeline = next((entry for entry in entries if f"{entry.get('kind')}:{entry.get('id')}:{entry.get('version')}" == pipeline_ref), {})
    if not pipeline:
        failures.append(f"registry_pipeline_missing:{pipeline_ref}")
    else:
        if eval_ref not in _as_string_list(pipeline.get("eval_pack_refs")):
            failures.append(f"registry_pipeline_eval_pack_missing:{eval_ref}")
        pipeline_refs = set(_as_string_list(pipeline.get("refs")))
        for ref in ["configs/production-gui-installer-policy.json", "contracts/production_gui_installer.schema.json", "src/production_gui_installer_runtime.py", "prelaunch/governance/production_gui_installer.example.json"]:
            if ref not in pipeline_refs:
                failures.append(f"registry_pipeline_ref_missing:{ref}")
    return {"failures": failures, "entries": matches}


def _docs_report(policy: Dict[str, Any], *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    failures: List[str] = []
    docs: List[Dict[str, Any]] = []
    for ref in _as_string_list(policy.get("required_doc_refs")):
        resolved = _resolve_ref(ref, project_root=project_root, package_root=package_root)
        text = Path(resolved["path"]).read_text(encoding="utf-8") if resolved.get("ok") else ""
        local_failures: List[str] = []
        if not resolved.get("ok"):
            local_failures.append("doc_missing")
        if POLICY_ID not in text:
            local_failures.append("policy_id_missing")
        if "Production GUI installer boundary" not in text and not ref.endswith("CHANGELOG.md"):
            local_failures.append("boundary_phrase_missing")
        if ref.endswith("ROADMAP_AND_TODO.md") and f"[x] {SELECTED_TODO}" not in text:
            local_failures.append("selected_todo_not_closed")
        if ref.endswith("ROADMAP_AND_TODO.md") and f"[ ] {SELECTED_TODO}" in text:
            local_failures.append("selected_todo_still_open")
        if ref.endswith("TODO.md") and f"[x] {SELECTED_TODO}" not in text:
            local_failures.append("selected_todo_not_closed")
        failures.extend(f"doc:{ref}:{item}" for item in local_failures)
        docs.append({"ref": ref, "ok": not local_failures, "failures": local_failures})
    return {"failures": failures, "docs": docs}


def _example_report(policy: Dict[str, Any], *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    failures: List[str] = []
    reports: List[Dict[str, Any]] = []
    for ref in _as_string_list(policy.get("required_example_sets")):
        resolved = _resolve_ref(ref, project_root=project_root, package_root=package_root)
        if not resolved.get("ok"):
            failures.append(f"example_missing:{ref}")
            continue
        example = load_example_set(resolved["path"])
        local_failures: List[str] = []
        if example.get("apiVersion") != API_VERSION or example.get("kind") != EXAMPLE_KIND:
            local_failures.append("example_header_invalid")
        scenarios = example.get("scenarios") if isinstance(example.get("scenarios"), list) else []
        if not scenarios:
            local_failures.append("example_scenarios_empty")
        scenario_reports: List[Dict[str, Any]] = []
        for scenario in scenarios:
            sid = str(scenario.get("id") or "")
            scenario_failures: List[str] = []
            if not SAFE_ID_RE.match(sid):
                scenario_failures.append("scenario_id_invalid")
            if not str(scenario.get("trace_id") or "").startswith("trace:"):
                scenario_failures.append("scenario_trace_id_invalid")
            outputs = set(_as_string_list(scenario.get("expected_outputs")))
            blocked = set(_as_string_list(scenario.get("blocked_side_effects")))
            missing_outputs = sorted(REQUIRED_OUTPUTS - outputs)
            missing_blocked = sorted(BLOCKED_SIDE_EFFECTS - blocked)
            scenario_failures.extend(f"expected_output_missing:{item}" for item in missing_outputs)
            scenario_failures.extend(f"blocked_side_effect_missing:{item}" for item in missing_blocked)
            if len(_as_string_list(scenario.get("operator_path"))) < 4:
                scenario_failures.append("operator_path_too_short")
            scenario_reports.append({"id": sid, "ok": not scenario_failures, "failures": scenario_failures})
            local_failures.extend(f"scenario:{sid}:{item}" for item in scenario_failures)
        failures.extend(f"example:{ref}:{item}" for item in local_failures)
        reports.append({"ref": ref, "ok": not local_failures, "failures": local_failures, "scenarios": scenario_reports})
    return {"failures": failures, "reports": reports}


def validate_production_gui_installer_policy(
    payload: Dict[str, Any],
    *,
    project_root: Path | str,
    package_root: Path | str,
    policy_path: Path | str | None = None,
) -> Dict[str, Any]:
    project = Path(project_root).resolve()
    package = Path(package_root).resolve()
    policy = _policy_dict(payload)
    failures: List[str] = []
    failures.extend(_policy_failures(payload))
    refs = _resolve_refs(_as_string_list(payload.get("refs")), project_root=project, package_root=package, owner=POLICY_ID)
    failures.extend(refs["failures"])
    surface = analyze_installer_surface(payload, project_root=project, package_root=package)
    failures.extend(surface["failures"])
    assets = _asset_report(policy, project_root=project, package_root=package)
    failures.extend(assets["failures"])
    units = _unit_report(policy, project_root=project, package_root=package)
    failures.extend(units["failures"])
    contracts = _contract_report(policy, project_root=project, package_root=package)
    failures.extend(contracts["failures"])
    registry = _registry_report(payload, package_root=package)
    failures.extend(registry["failures"])
    docs = _docs_report(policy, project_root=project, package_root=package)
    failures.extend(docs["failures"])
    examples = _example_report(policy, project_root=project, package_root=package)
    failures.extend(examples["failures"])
    metrics = {
        "refs": len(_as_string_list(payload.get("refs"))),
        "resolved_refs": len(refs["resolved_refs"]),
        "gui_assets": len(assets["resolved_assets"]),
        "gui_units": len(units["unit_reports"]),
        "existing_contracts": len(contracts["contracts"]),
        "scenarios": sum(len(item.get("scenarios") or []) for item in examples["reports"]),
        "passing_scenarios": sum(1 for item in examples["reports"] for scenario in item.get("scenarios", []) if scenario.get("ok")),
        "registry_entries": len(registry["entries"]),
        "surface_flags": sum(1 for value in surface["flags"].values() if value),
    }
    return {
        "apiVersion": API_VERSION,
        "kind": REPORT_KIND,
        "id": str(payload.get("id") or POLICY_ID),
        "version": str(payload.get("version") or ""),
        "ok": not failures,
        "validated_at": _nowz(),
        "policy_path": _display_path(Path(policy_path).resolve()) if policy_path else "",
        "failures": failures,
        "metrics": metrics,
        "refs": refs,
        "surface": surface,
        "assets": assets,
        "units": units,
        "contracts": contracts,
        "registry": registry,
        "docs": docs,
        "examples": examples,
    }


def benchmark_production_gui_installer(*, package_root: Path | str, iterations: int = 80) -> Dict[str, Any]:
    package = Path(package_root).resolve()
    project = package.parent
    policy = load_policy(package / "configs" / "production-gui-installer-policy.json")
    import time

    started = time.perf_counter()
    failures = 0
    for _ in range(iterations):
        report = validate_production_gui_installer_policy(policy, project_root=project, package_root=package)
        if not report["ok"]:
            failures += 1
    elapsed = time.perf_counter() - started
    return {
        "ok": failures == 0,
        "iterations": iterations,
        "failures": failures,
        "elapsed_seconds": elapsed,
        "iterations_per_second": iterations / elapsed if elapsed else iterations,
    }


def build_summary(report: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "apiVersion": API_VERSION,
        "kind": "ProductionGuiInstallerValidationSummary",
        "ok": bool(report.get("ok")),
        "id": report.get("id"),
        "version": report.get("version"),
        "metrics": report.get("metrics", {}),
        "failures": report.get("failures", []),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate NoemaForge production GUI installer readiness contract")
    parser.add_argument("--policy", default=str(SRC_DIR.parent / "configs" / "production-gui-installer-policy.json"))
    parser.add_argument("--project-root", default=str(SRC_DIR.parent.parent))
    parser.add_argument("--package-root", default=str(SRC_DIR.parent))
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(argv)
    report = validate_production_gui_installer_policy(
        load_policy(args.policy),
        project_root=Path(args.project_root),
        package_root=Path(args.package_root),
        policy_path=Path(args.policy),
    )
    print(json.dumps(build_summary(report) if args.summary else report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
