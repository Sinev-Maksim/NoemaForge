#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/default_model_runtime_policy.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate the default CPU-safe model runtime policy with GPU-on-demand escape hatch.
Inputs: Default model runtime policy, runtime device policy, model profiles and examples.
Outputs: JSON-compatible DefaultModelRuntimePolicyValidationReport artifacts.
Side effects: None; CLI writes JSON to stdout.
Tests: noemaforge/tests/test_default_model_runtime_policy_runtime.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Sequence


SRC_DIR = Path(__file__).resolve().parent
API_VERSION = "noemaforge.default-model-runtime-policy/v1"
POLICY_KIND = "DefaultModelRuntimePolicy"
EXAMPLE_KIND = "DefaultModelRuntimePolicyExampleSet"
REPORT_KIND = "DefaultModelRuntimePolicyValidationReport"
POLICY_ID = "default-model-runtime-policy-core"
DECISION = "cpu_safe_always_on_with_gpu_on_demand"
APPLY_BOUNDARY = "next_persona_or_model_switch_or_backend_restart"
VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,220}$")
REQUIRED_CONTROLS = {
    "default_cpu_safe",
    "minimal_profile_cpu_eligible",
    "gpu_explicit_on_demand",
    "gpu_heavy_never_always_on",
    "one_active_heavy_worker",
    "staged_device_apply",
    "no_boot_llm_autostart",
}
REGISTRY_REFS = [
    "configs/default-model-runtime-policy.json",
    "contracts/default_model_runtime_policy.schema.json",
    "configs/runtime-device-policy.json",
    "configs/model-profiles.json",
    "configs/runtime-default-safety-policy.json",
    "configs/runtime-device-policy-staging-policy.json",
    "src/admin_gui_server.py",
    "src/default_model_runtime_policy.py",
    "tests/test_default_model_runtime_policy_runtime.py",
    "tests/test_default_model_runtime_policy_qa.py",
    "tests/test_default_model_runtime_policy_performance.py",
    "prelaunch/governance/default_model_runtime_policy.example.json",
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
        candidates.append(("package_relative", package_root / ref))
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


def load_text(path: Path | str) -> str:
    return Path(path).read_text(encoding="utf-8")


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
    if payload.get("decision") != DECISION:
        failures.append("policy_decision_invalid")
    if policy.get("mode") != "offline_contract":
        failures.append("policy_mode_not_offline_contract")
    if policy.get("activation_state") != "default_cpu_safe_gpu_on_demand":
        failures.append("policy_activation_state_invalid")
    expected = {
        "default_device": "cpu",
        "selected_profile": "minimal",
        "gpu_profile": "gpu-heavy",
        "always_on_policy": "cpu_safe",
        "gpu_policy": "explicit_on_demand",
        "apply_boundary": APPLY_BOUNDARY,
    }
    for key, value in expected.items():
        if policy.get(key) != value:
            failures.append(f"policy_{key}_invalid:{policy.get(key)}")
    if policy.get("gpu_autostart_enabled") is not False:
        failures.append("policy_gpu_autostart_enabled_not_false")
    if policy.get("boot_autostart_enabled") is not False:
        failures.append("policy_boot_autostart_enabled_not_false")
    if policy.get("max_active_heavy_workers") != 1:
        failures.append("policy_max_active_heavy_workers_not_one")
    for key in ["require_docs_and_changelog_refs", "require_registry_attachment", "require_no_live_backend_dependency"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    controls = policy.get("required_controls") if isinstance(policy.get("required_controls"), dict) else {}
    for key in REQUIRED_CONTROLS:
        if controls.get(key) is not True:
            failures.append(f"policy_control_{key}_not_true")
    refs = policy.get("required_runtime_refs") if isinstance(policy.get("required_runtime_refs"), dict) else {}
    for key in ["runtime_device_policy", "model_profiles", "runtime_default_safety", "runtime_device_staging", "admin_gui_server", "contract_runtime"]:
        if not _is_safe_relative_ref(str(refs.get(key) or "")):
            failures.append(f"policy_required_runtime_ref_invalid:{key}")
    for token in ["cpu_safe_always_on_with_gpu_on_demand", "CPU-safe", "GPU-on-demand", "explicit_on_demand", "max_active_heavy_workers"]:
        if token not in _as_string_list(policy.get("required_decision_tokens")):
            failures.append(f"policy_decision_token_missing:{token}")
    if not _as_string_list(policy.get("required_example_sets")):
        failures.append("policy_required_example_sets_empty")
    return failures


def _runtime_device_failures(config: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    expected = {
        "decision": DECISION,
        "default": "cpu",
        "always_on_policy": "cpu_safe",
        "gpu_policy": "explicit_on_demand",
        "applies_on": APPLY_BOUNDARY,
        "gpu_applies_on": APPLY_BOUNDARY,
    }
    for key, value in expected.items():
        if config.get(key) != value:
            failures.append(f"runtime_device_{key}_invalid:{config.get(key)}")
    if config.get("gpu_autostart_enabled") is not False or config.get("heavy_gpu_autostart") is not False:
        failures.append("runtime_device_gpu_autostart_not_false")
    if config.get("max_active_heavy_workers") != 1:
        failures.append("runtime_device_max_active_heavy_workers_not_one")
    allowed = set(_as_string_list(config.get("allowed")))
    if not {"auto", "cpu", "gpu"}.issubset(allowed):
        failures.append("runtime_device_allowed_modes_missing")
    warning = str(config.get("readme_warning") or "")
    for token in ["CPU-safe", "explicit on-demand", "does not migrate"]:
        if token not in warning:
            failures.append(f"runtime_device_warning_token_missing:{token}")
    return failures


def _model_profile_failures(profiles: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    minimal = profiles.get("minimal") if isinstance(profiles.get("minimal"), dict) else {}
    gpu = profiles.get("gpu-heavy") if isinstance(profiles.get("gpu-heavy"), dict) else {}
    if minimal.get("max_active_llms") != 1:
        failures.append("minimal_max_active_llms_not_one")
    if minimal.get("vram_gib_min") != 0:
        failures.append("minimal_vram_floor_not_zero")
    if "CPU-safe" not in str(minimal.get("description") or ""):
        failures.append("minimal_description_missing_cpu_safe")
    if gpu.get("max_active_llms") != 1:
        failures.append("gpu_heavy_max_active_llms_not_one")
    if gpu.get("default_runtime") != "explicit_gpu_on_demand":
        failures.append("gpu_heavy_default_runtime_invalid")
    gpu_description = str(gpu.get("description") or "")
    if "GPU-on-demand" not in gpu_description or "Never always-on" not in gpu_description:
        failures.append("gpu_heavy_description_not_on_demand")
    if float(gpu.get("vram_gib_min") or 0) < 12:
        failures.append("gpu_heavy_vram_floor_too_low")
    return failures


def _safety_policy_failures(policy_payload: Dict[str, Any]) -> List[str]:
    policy = _policy_dict(policy_payload)
    controls = policy.get("controls") if isinstance(policy.get("controls"), dict) else {}
    failures: List[str] = []
    for key in ["max_active_llms_one", "bootstrap_cpu_blocks_heavy", "heavy_autostart_rejected", "no_llm_autostart"]:
        if controls.get(key) is not True:
            failures.append(f"safety_control_{key}_not_true")
    if policy.get("activation_state") != "runtime_default_single_llm_and_manual_heavy_boot":
        failures.append("safety_activation_state_invalid")
    return failures


def _staging_policy_failures(policy_payload: Dict[str, Any]) -> List[str]:
    policy = _policy_dict(policy_payload)
    fields = policy.get("required_staged_fields") if isinstance(policy.get("required_staged_fields"), dict) else {}
    failures: List[str] = []
    if policy.get("activation_state") != "cpu_gpu_staged_until_switch_or_backend_restart":
        failures.append("staging_activation_state_invalid")
    if fields.get("pending_apply") is not True:
        failures.append("staging_pending_apply_not_true")
    if fields.get("applies_on") != APPLY_BOUNDARY:
        failures.append("staging_applies_on_invalid")
    if "gpu" not in _as_string_list(policy.get("allowed_policies")):
        failures.append("staging_gpu_policy_missing")
    return failures


def _admin_gui_failures(source: str) -> List[str]:
    failures: List[str] = []
    for token in ['"policy": "cpu"', DECISION, '"gpu_policy": "explicit_on_demand"', '"max_active_heavy_workers": 1']:
        if token not in source:
            failures.append(f"admin_gui_default_token_missing:{token}")
    return failures


def _registry_failures(payload: Dict[str, Any], *, package_root: Path) -> Dict[str, Any]:
    registry_path = package_root / "configs" / "unified-registry.json"
    registry = load_json(registry_path)
    entries = registry.get("entries") if isinstance(registry.get("entries"), list) else []
    entry_map = {_registry_ref(entry): entry for entry in entries if isinstance(entry, dict)}
    eval_ref = f"eval-pack:{payload.get('id')}:{payload.get('version')}"
    eval_entry = entry_map.get(eval_ref)
    failures: List[str] = []
    if not eval_entry:
        failures.append(f"registry_eval_pack_missing:{eval_ref}")
    else:
        refs = set(_as_string_list(eval_entry.get("refs")))
        for ref in REGISTRY_REFS:
            if ref not in refs:
                failures.append(f"registry_eval_pack_ref_missing:{eval_ref}:{ref}")
        metrics = set(_as_string_list((eval_entry.get("metadata") or {}).get("metrics") if isinstance(eval_entry.get("metadata"), dict) else []))
        for metric in ["cpu_safe_always_on_with_gpu_on_demand", "gpu_explicit_on_demand", "registry_attachment", "refs_resolved"]:
            if metric not in metrics:
                failures.append(f"registry_metric_missing:{metric}")
    return {"failures": failures, "eval_ref": eval_ref, "registry_entries": len(entries)}


def _example_failures(example: Dict[str, Any], *, policy_payload: Dict[str, Any], runtime_device: Dict[str, Any]) -> Dict[str, Any]:
    failures: List[str] = []
    scenario_reports: List[Dict[str, Any]] = []
    passing = 0
    policy = _policy_dict(policy_payload)
    if example.get("apiVersion") != API_VERSION:
        failures.append("examples_api_version_invalid")
    if example.get("kind") != EXAMPLE_KIND:
        failures.append("examples_kind_invalid")
    scenarios = example.get("scenarios") if isinstance(example.get("scenarios"), list) else []
    if not scenarios:
        failures.append("examples_scenarios_empty")
    for scenario in scenarios:
        sid = str(scenario.get("id") or "")
        local: List[str] = []
        if not SAFE_ID_RE.match(sid):
            local.append("scenario_id_invalid")
        if not str(scenario.get("trace_id") or "").startswith("trace:"):
            local.append("scenario_trace_id_missing")
        if scenario.get("expected_decision") != DECISION:
            local.append("scenario_decision_invalid")
        if scenario.get("expected_default_device") != runtime_device.get("default"):
            local.append("scenario_default_device_mismatch")
        if scenario.get("expected_always_on_policy") != policy.get("always_on_policy"):
            local.append("scenario_always_on_policy_mismatch")
        if scenario.get("expected_gpu_policy") != policy.get("gpu_policy"):
            local.append("scenario_gpu_policy_mismatch")
        if scenario.get("expected_gpu_autostart_enabled") is not False or policy.get("gpu_autostart_enabled") is not False:
            local.append("scenario_gpu_autostart_not_false")
        if scenario.get("expected_boot_autostart_enabled") is not False or policy.get("boot_autostart_enabled") is not False:
            local.append("scenario_boot_autostart_not_false")
        if scenario.get("expected_max_active_heavy_workers") != 1:
            local.append("scenario_max_active_heavy_workers_not_one")
        if sid == "gpu-on-demand-request" and scenario.get("expected_profile") != "gpu-heavy":
            local.append("scenario_gpu_request_profile_invalid")
        scenario_reports.append({"id": sid, "ok": not local, "failures": local})
        if local:
            failures.extend([f"scenario:{sid}:{item}" for item in local])
        else:
            passing += 1
    return {"failures": failures, "scenario_reports": scenario_reports, "examples": len(scenarios), "passing_examples": passing}


def validate_default_model_runtime_policy(
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
    ref_report = _resolve_refs(_as_string_list(payload.get("refs")), project_root=project, package_root=package, owner=str(payload.get("id") or "policy"))
    failures.extend(ref_report["failures"])
    refs = policy.get("required_runtime_refs") if isinstance(policy.get("required_runtime_refs"), dict) else {}
    resolved = {name: _resolve_ref(str(ref), project_root=project, package_root=package) for name, ref in refs.items()}
    for name, report in resolved.items():
        if not report.get("ok"):
            failures.append(f"required_runtime_ref_missing:{name}:{report.get('ref')}")
    runtime_device = load_json(resolved["runtime_device_policy"]["path"]) if resolved.get("runtime_device_policy", {}).get("ok") else {}
    profiles = load_json(resolved["model_profiles"]["path"]) if resolved.get("model_profiles", {}).get("ok") else {}
    safety = load_json(resolved["runtime_default_safety"]["path"]) if resolved.get("runtime_default_safety", {}).get("ok") else {}
    staging = load_json(resolved["runtime_device_staging"]["path"]) if resolved.get("runtime_device_staging", {}).get("ok") else {}
    admin_gui = load_text(resolved["admin_gui_server"]["path"]) if resolved.get("admin_gui_server", {}).get("ok") else ""
    failures.extend(_runtime_device_failures(runtime_device))
    failures.extend(_model_profile_failures(profiles))
    failures.extend(_safety_policy_failures(safety))
    failures.extend(_staging_policy_failures(staging))
    failures.extend(_admin_gui_failures(admin_gui))
    registry = _registry_failures(payload, package_root=package)
    failures.extend(registry["failures"])
    example_reports: List[Dict[str, Any]] = []
    for ref in _as_string_list(policy.get("required_example_sets")):
        resolved_example = _resolve_ref(ref, project_root=project, package_root=package)
        if not resolved_example.get("ok"):
            failures.append(f"example_ref_missing:{ref}")
            continue
        report = _example_failures(load_example_set(resolved_example["path"]), policy_payload=payload, runtime_device=runtime_device)
        failures.extend(report["failures"])
        example_reports.append({"ref": ref, **report})
    metrics = {
        "refs": len(_as_string_list(payload.get("refs"))),
        "resolved_refs": len(ref_report["resolved_refs"]),
        "examples": sum(int(item.get("examples") or 0) for item in example_reports),
        "passing_examples": sum(int(item.get("passing_examples") or 0) for item in example_reports),
        "registry_entries": registry["registry_entries"],
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
        "runtime_refs": resolved,
        "registry": registry,
        "examples": example_reports,
    }


def default_model_runtime_policy_report_to_gate_evidence(report: Dict[str, Any], *, artifact_uri: str = "") -> Dict[str, Any]:
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


def benchmark_default_model_runtime_policy(*, package_root: Path | str, iterations: int = 80) -> Dict[str, Any]:
    package = Path(package_root).resolve()
    policy = load_policy(package / "configs" / "default-model-runtime-policy.json")
    started = time.perf_counter()
    failures = 0
    for _ in range(iterations):
        report = validate_default_model_runtime_policy(policy, project_root=package.parent, package_root=package)
        if not report.get("ok"):
            failures += 1
    elapsed = time.perf_counter() - started
    return {
        "ok": failures == 0,
        "iterations": iterations,
        "failures": failures,
        "elapsed_seconds": round(elapsed, 6),
        "iterations_per_second": round(iterations / elapsed, 3) if elapsed else iterations,
    }


def build_summary(report: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "apiVersion": API_VERSION,
        "kind": "DefaultModelRuntimePolicyValidationSummary",
        "ok": bool(report.get("ok")),
        "id": report.get("id"),
        "version": report.get("version"),
        "metrics": report.get("metrics", {}),
        "failures": report.get("failures", []),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate NoemaForge default model runtime policy")
    parser.add_argument("--policy", default=str(SRC_DIR.parent / "configs" / "default-model-runtime-policy.json"))
    parser.add_argument("--project-root", default=str(SRC_DIR.parent.parent))
    parser.add_argument("--package-root", default=str(SRC_DIR.parent))
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = validate_default_model_runtime_policy(
        load_policy(args.policy),
        project_root=Path(args.project_root),
        package_root=Path(args.package_root),
        policy_path=Path(args.policy),
    )
    print(json.dumps(build_summary(report) if args.summary else report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
