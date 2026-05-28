#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/runtime_default_safety_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate default single-LLM runtime safety and manual-only heavy boot policy.
Inputs: runtime-default-safety policy, autostart policy, runtime scripts and examples.
Outputs: JSON-compatible RuntimeDefaultSafetyValidationReport artifacts.
Side effects: None; CLI writes JSON to stdout.
Tests: noemaforge/tests/test_runtime_default_safety_runtime.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import argparse
import contextlib
import io
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

import pipeline_runtime as prt
import team_member_runtime as tmrt
import unified_registry_runtime as urr


API_VERSION = "noemaforge.runtime-default-safety/v1"
POLICY_KIND = "RuntimeDefaultSafetyPolicy"
SET_KIND = "RuntimeDefaultSafetyExampleSet"
REPORT_KIND = "RuntimeDefaultSafetyValidationReport"

VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
REQUIRED_CONTROLS = {
    "max_active_llms_one",
    "switchable_runtime_default",
    "gui_default_runtime_only",
    "runtime_only_starts_no_llm",
    "wogui_default_cpu_bootstrap_only",
    "bootstrap_cpu_blocks_heavy",
    "heavy_autostart_rejected",
    "team_member_default_sequential",
    "no_live_host_required",
    "no_llm_autostart",
}
REQUIRED_STATIC_TOKENS = {
    "pipeline_runtime": [
        '"max_active_llms": 1',
        '"mode": "switchable"',
        '"heavy_llm_autostart": "conditional_safe_start_only"',
    ],
    "team_member_runtime": [
        '"max_active_llms": 1',
        '"default_execution": "sequential"',
    ],
    "autostart_safe_script": [
        "heavy LLM autostart is disabled",
        "heavy_llm=manual_only max_active_llms=1",
        "runtime_only) safe_args+=(--llm-profile=runtime_only --no-health-wait)",
        "bootstrap_cpu_llm) safe_args+=(--llm-profile=bootstrap_cpu_llm)",
    ],
    "boot_mode_script": [
        "manual: no runtime autostart.",
        "Default profile: runtime_only",
        "heavy LLM autostart is disabled",
        "bootstrap_cpu_llm",
    ],
}
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


def _registry_ref(entry: Dict[str, Any]) -> str:
    return f"{entry.get('kind')}:{entry.get('id')}:{entry.get('version')}"


def _is_safe_relative_ref(ref: str) -> bool:
    text = str(ref or "").strip().replace("\\", "/")
    if not text or text.startswith("/") or text.startswith("~"):
        return False
    parts = PurePosixPath(text).parts
    return not any(part in {"", ".", ".."} for part in parts)


def _resolve_ref(ref: str, *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    candidates = [("project", project_root / ref), ("package", package_root / ref)]
    if not ref.startswith("noemaforge/"):
        candidates.append(("project_noemaforge", project_root / "noemaforge" / ref))
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


def load_autostart_policy(path: Path | str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_text(path: Path | str) -> str:
    return Path(path).read_text(encoding="utf-8")


def pipeline_policy_snapshot() -> Dict[str, Any]:
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        prt.main(["policy"])
    return json.loads(stdout.getvalue())


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
    if str(policy.get("activation_state") or "") != "runtime_default_single_llm_and_manual_heavy_boot":
        failures.append("policy_activation_state_invalid")
    for key in ["require_trace_id", "require_registry_attachment", "require_docs_and_changelog_refs"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    for output in ["single_active_llm_default", "heavy_llm_manual_only", "gui_runtime_only_default", "wogui_cpu_bootstrap_only", "sequential_team_member_default"]:
        if output not in _as_string_list(policy.get("required_outputs")):
            failures.append(f"policy_required_output_missing:{output}")
    controls = policy.get("controls") if isinstance(policy.get("controls"), dict) else {}
    for key in REQUIRED_CONTROLS:
        if controls.get(key) is not True:
            failures.append(f"policy_control_{key}_not_true")
    refs = policy.get("required_refs") if isinstance(policy.get("required_refs"), dict) else {}
    for key in ["cli", "pipeline_runtime", "team_member_runtime", "autostart_policy", "autostart_safe_script", "boot_mode_script", "contract_runtime"]:
        if not str(refs.get(key) or "").strip():
            failures.append(f"policy_required_ref_missing:{key}")
    if not _as_string_list(policy.get("required_example_sets")):
        failures.append("policy_required_example_sets_empty")
    return failures


def _autostart_policy_failures(payload: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    invariant = payload.get("invariant") if isinstance(payload.get("invariant"), dict) else {}
    modes = payload.get("modes") if isinstance(payload.get("modes"), dict) else {}
    profiles = payload.get("profiles") if isinstance(payload.get("profiles"), dict) else {}
    if invariant.get("max_active_llms") != 1:
        failures.append("autostart_invariant_max_active_llms_not_one")
    if invariant.get("mode") != "switchable":
        failures.append("autostart_invariant_mode_not_switchable")
    if (modes.get("manual") or {}).get("runtime") != "manual":
        failures.append("manual_mode_not_manual")
    if (modes.get("gui") or {}).get("default_llm_profile") != "runtime_only":
        failures.append("gui_default_profile_not_runtime_only")
    if (modes.get("gui") or {}).get("heavy_llm") != "manual_only":
        failures.append("gui_heavy_llm_not_manual_only")
    if (modes.get("wogui") or {}).get("default_llm_profile") != "bootstrap_cpu_llm":
        failures.append("wogui_default_profile_not_bootstrap_cpu_llm")
    if (modes.get("wogui") or {}).get("heavy_llm") != "manual_only":
        failures.append("wogui_heavy_llm_not_manual_only")
    runtime_only = profiles.get("runtime_only") if isinstance(profiles.get("runtime_only"), dict) else {}
    bootstrap = profiles.get("bootstrap_cpu_llm") if isinstance(profiles.get("bootstrap_cpu_llm"), dict) else {}
    heavy = profiles.get("heavy_manual") if isinstance(profiles.get("heavy_manual"), dict) else {}
    if runtime_only.get("starts_llm") is not False:
        failures.append("runtime_only_starts_llm_not_false")
    if bootstrap.get("cpu_only") is not True:
        failures.append("bootstrap_cpu_not_cpu_only")
    if bootstrap.get("blocks_heavy_models") is not True:
        failures.append("bootstrap_cpu_does_not_block_heavy")
    if heavy.get("requires_explicit_flag") is not True:
        failures.append("heavy_manual_does_not_require_explicit_flag")
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
        for ref in [
            "configs/runtime-default-safety-policy.json",
            "contracts/runtime_default_safety.schema.json",
            "configs/autostart-llm-policy.json",
            "src/pipeline_runtime.py",
            "src/team_member_runtime.py",
            "src/runtime_default_safety_runtime.py",
            "tests/test_runtime_default_safety_runtime.py",
            "tests/test_runtime_default_safety_qa.py",
            "tests/test_runtime_default_safety_performance.py",
        ]:
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
    for ref in [
        "configs/runtime-default-safety-policy.json",
        "contracts/runtime_default_safety.schema.json",
        "src/runtime_default_safety_runtime.py",
        "prelaunch/governance/runtime_default_safety.example.json",
    ]:
        if ref not in pipeline_refs:
            failures.append(f"registry_pipeline_ref_missing:{ref}")
    return {"failures": failures, "registry_report": report, "pipeline_eval_refs": pipeline_eval_refs, "pipeline_refs": pipeline_refs}


def _static_failures(payload: Dict[str, Any], *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    refs = _policy_dict(payload).get("required_refs") if isinstance(_policy_dict(payload).get("required_refs"), dict) else {}
    resolved = {key: _resolve_ref(str(ref), project_root=project_root, package_root=package_root) for key, ref in refs.items()}
    failures: List[str] = []
    for key, item in resolved.items():
        if not item.get("ok"):
            failures.append(f"static_required_ref_unresolved:{key}:{refs.get(key)}")
    for key, tokens in REQUIRED_STATIC_TOKENS.items():
        text = load_text(resolved[key]["path"]) if resolved.get(key, {}).get("ok") else ""
        for token in tokens:
            if token not in text:
                failures.append(f"static_token_missing:{key}:{token}")
    cli_text = load_text(resolved["cli"]["path"]) if resolved.get("cli", {}).get("ok") else ""
    if "start-llm-safe" not in cli_text:
        failures.append("cli_help_start_llm_safe_missing")
    return {"failures": failures, "resolved_required_refs": resolved}


def _runtime_failures() -> List[str]:
    failures: List[str] = []
    policy = pipeline_policy_snapshot()
    invariant = policy.get("runtime_invariant") if isinstance(policy.get("runtime_invariant"), dict) else {}
    if invariant.get("mode") != "switchable":
        failures.append("pipeline_policy_mode_not_switchable")
    if invariant.get("max_active_llms") != 1:
        failures.append("pipeline_policy_max_active_llms_not_one")
    if invariant.get("heavy_llm_autostart") != "conditional_safe_start_only":
        failures.append("pipeline_policy_heavy_autostart_not_conditional_safe_start_only")
    team_policy = tmrt.default_policy()
    team_invariant = team_policy.get("invariant") if isinstance(team_policy.get("invariant"), dict) else {}
    if team_invariant.get("max_active_llms") != 1:
        failures.append("team_policy_max_active_llms_not_one")
    if team_invariant.get("default_execution") != "sequential":
        failures.append("team_policy_default_execution_not_sequential")
    return failures


def _example_failures(example: Dict[str, Any], *, autostart_policy: Dict[str, Any]) -> Dict[str, Any]:
    failures: List[str] = []
    scenario_reports: List[Dict[str, Any]] = []
    passing_scenarios = 0
    if example.get("apiVersion") != API_VERSION:
        failures.append("examples_api_version_invalid")
    if example.get("kind") != SET_KIND:
        failures.append("examples_kind_invalid")
    scenarios = example.get("scenarios") if isinstance(example.get("scenarios"), list) else []
    if not scenarios:
        failures.append("examples_scenarios_empty")
    runtime_policy = pipeline_policy_snapshot()
    team_policy = tmrt.default_policy()
    for scenario in scenarios:
        sid = str(scenario.get("id") or "")
        local_failures: List[str] = []
        if not SAFE_ID_RE.match(sid):
            local_failures.append("scenario_id_invalid")
        if not str(scenario.get("trace_id") or "").startswith("trace:"):
            local_failures.append("scenario_trace_id_missing")
        invariant = autostart_policy.get("invariant") if isinstance(autostart_policy.get("invariant"), dict) else {}
        modes = autostart_policy.get("modes") if isinstance(autostart_policy.get("modes"), dict) else {}
        profiles = autostart_policy.get("profiles") if isinstance(autostart_policy.get("profiles"), dict) else {}
        runtime_invariant = runtime_policy.get("runtime_invariant") if isinstance(runtime_policy.get("runtime_invariant"), dict) else {}
        team_invariant = team_policy.get("invariant") if isinstance(team_policy.get("invariant"), dict) else {}
        if invariant.get("max_active_llms") != scenario.get("expected_max_active_llms") or runtime_invariant.get("max_active_llms") != scenario.get("expected_max_active_llms"):
            local_failures.append("scenario_max_active_llms_mismatch")
        if invariant.get("mode") != scenario.get("expected_runtime_mode") or runtime_invariant.get("mode") != scenario.get("expected_runtime_mode"):
            local_failures.append("scenario_runtime_mode_mismatch")
        if (modes.get("gui") or {}).get("default_llm_profile") != scenario.get("expected_gui_default_profile"):
            local_failures.append("scenario_gui_default_mismatch")
        if (modes.get("wogui") or {}).get("default_llm_profile") != scenario.get("expected_wogui_default_profile"):
            local_failures.append("scenario_wogui_default_mismatch")
        if (modes.get("gui") or {}).get("heavy_llm") != scenario.get("expected_heavy_llm") or (modes.get("wogui") or {}).get("heavy_llm") != scenario.get("expected_heavy_llm"):
            local_failures.append("scenario_heavy_llm_not_manual_only")
        if (profiles.get("runtime_only") or {}).get("starts_llm") is not False:
            local_failures.append("scenario_runtime_only_starts_llm")
        if (profiles.get("bootstrap_cpu_llm") or {}).get("blocks_heavy_models") is not True:
            local_failures.append("scenario_bootstrap_does_not_block_heavy")
        if team_invariant.get("default_execution") != scenario.get("expected_team_member_default_execution"):
            local_failures.append("scenario_team_member_default_not_sequential")
        for output in _as_string_list(scenario.get("expected_outputs")):
            if output == "single_active_llm_default" and runtime_invariant.get("max_active_llms") != 1:
                local_failures.append("scenario_output_missing:single_active_llm_default")
            elif output == "heavy_llm_manual_only" and (modes.get("gui") or {}).get("heavy_llm") != "manual_only":
                local_failures.append("scenario_output_missing:heavy_llm_manual_only")
            elif output == "gui_runtime_only_default" and (modes.get("gui") or {}).get("default_llm_profile") != "runtime_only":
                local_failures.append("scenario_output_missing:gui_runtime_only_default")
            elif output == "wogui_cpu_bootstrap_only" and (modes.get("wogui") or {}).get("default_llm_profile") != "bootstrap_cpu_llm":
                local_failures.append("scenario_output_missing:wogui_cpu_bootstrap_only")
            elif output == "sequential_team_member_default" and team_invariant.get("default_execution") != "sequential":
                local_failures.append("scenario_output_missing:sequential_team_member_default")
        scenario_reports.append({"id": sid, "ok": not local_failures, "failures": local_failures})
        if local_failures:
            failures.extend([f"scenario:{sid}:{item}" for item in local_failures])
        else:
            passing_scenarios += 1
    return {"failures": failures, "scenario_reports": scenario_reports, "scenarios": len(scenarios), "passing_scenarios": passing_scenarios}


def validate_runtime_default_safety_policy(
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
    failures: List[str] = []
    failures.extend(_policy_failures(payload))
    ref_report = _resolve_refs(_as_string_list(payload.get("refs")), project_root=project, package_root=package, owner=str(payload.get("id") or "policy"))
    failures.extend(ref_report["failures"])
    registry_report = _registry_failures(payload, project_root=project, package_root=package, registry_path=registry)
    failures.extend(registry_report["failures"])
    static_report = _static_failures(payload, project_root=project, package_root=package)
    failures.extend(static_report["failures"])
    refs = _policy_dict(payload).get("required_refs") if isinstance(_policy_dict(payload).get("required_refs"), dict) else {}
    autostart_ref = str(refs.get("autostart_policy") or "")
    autostart_resolved = _resolve_ref(autostart_ref, project_root=project, package_root=package)
    autostart_payload = load_autostart_policy(autostart_resolved["path"]) if autostart_resolved.get("ok") else {}
    autostart_failures = _autostart_policy_failures(autostart_payload)
    failures.extend(autostart_failures)
    runtime_failures = _runtime_failures()
    failures.extend(runtime_failures)
    example_reports: List[Dict[str, Any]] = []
    policy = _policy_dict(payload)
    for ref in _as_string_list(policy.get("required_example_sets")):
        resolved = _resolve_ref(ref, project_root=project, package_root=package)
        if not resolved.get("ok"):
            failures.append(f"example_ref_missing:{ref}")
            continue
        example_report = _example_failures(load_example_set(resolved["path"]), autostart_policy=autostart_payload)
        failures.extend(example_report["failures"])
        example_reports.append({"ref": ref, **example_report})
    metrics = {
        "refs": len(_as_string_list(payload.get("refs"))),
        "resolved_refs": len(ref_report["resolved_refs"]),
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
        "registry": registry_report,
        "static": static_report,
        "autostart": {"failures": autostart_failures},
        "runtime": {"failures": runtime_failures},
        "examples": example_reports,
    }


def runtime_default_safety_report_to_gate_evidence(report: Dict[str, Any], *, artifact_uri: str = "") -> Dict[str, Any]:
    status = "pass" if report.get("ok") else "fail"
    return {
        "artifact_uri": artifact_uri,
        "run_at": report.get("validated_at") or _nowz(),
        "checks": [
            {"id": "pipeline_eval", "status": status, "score": 1.0 if status == "pass" else 0.0, "threshold": 1.0},
            {"id": "rollback_plan", "status": "pass", "score": 1.0, "threshold": 1.0},
        ],
        "details": {"id": report.get("id"), "version": report.get("version"), "metrics": report.get("metrics", {}), "failures": report.get("failures", [])},
    }


def build_summary(report: Dict[str, Any]) -> Dict[str, Any]:
    return {"apiVersion": API_VERSION, "kind": "RuntimeDefaultSafetyValidationSummary", "ok": bool(report.get("ok")), "id": report.get("id"), "version": report.get("version"), "metrics": report.get("metrics", {}), "failures": report.get("failures", [])}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate NoemaForge runtime default safety contract")
    parser.add_argument("--policy", default=str(SRC_DIR.parent / "configs" / "runtime-default-safety-policy.json"))
    parser.add_argument("--project-root", default=str(SRC_DIR.parent.parent))
    parser.add_argument("--package-root", default=str(SRC_DIR.parent))
    parser.add_argument("--registry", default="")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = validate_runtime_default_safety_policy(load_policy(args.policy), project_root=Path(args.project_root), package_root=Path(args.package_root), policy_path=Path(args.policy), registry_path=Path(args.registry) if args.registry else None)
    print(json.dumps(build_summary(report) if args.summary else report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
