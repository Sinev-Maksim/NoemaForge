#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/cpu_gpu_scorecard_separation_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate separate CPU and GPU model scorecard recording.
Inputs: CPU/GPU scorecard separation policy, model scorecard writers and examples.
Outputs: JSON-compatible CpuGpuScorecardSeparationValidationReport artifacts.
Side effects: None; CLI writes JSON to stdout.
Tests: noemaforge/tests/test_cpu_gpu_scorecard_separation_runtime.py
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
API_VERSION = "noemaforge.cpu-gpu-scorecard-separation/v1"
POLICY_KIND = "CpuGpuScorecardSeparationPolicy"
EXAMPLE_KIND = "CpuGpuScorecardSeparationExampleSet"
REPORT_KIND = "CpuGpuScorecardSeparationValidationReport"
POLICY_ID = "cpu-gpu-scorecard-separation-core"
VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,220}$")
DEVICE_ALIASES = {"cpu": "cpu", "gpu": "gpu", "cuda": "gpu", "nvidia": "gpu"}
REGISTRY_REFS = [
    "configs/cpu-gpu-scorecard-separation-policy.json",
    "contracts/cpu_gpu_scorecard_separation.schema.json",
    "src/cpu_gpu_scorecard_separation_runtime.py",
    "src/model_scorecards.py",
    "src/role_tournament.py",
    "tests/test_cpu_gpu_scorecard_separation_runtime.py",
    "tests/test_cpu_gpu_scorecard_separation_qa.py",
    "tests/test_cpu_gpu_scorecard_separation_performance.py",
    "prelaunch/governance/cpu_gpu_scorecard_separation.example.json",
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


def normalize_runtime_device(value: str) -> str:
    return DEVICE_ALIASES.get(str(value or "").strip().lower(), "unspecified")


def scorecard_device_root(scorecards_root: str, runtime_device: str) -> str:
    device = normalize_runtime_device(runtime_device)
    if device in {"cpu", "gpu"}:
        return str(PurePosixPath(scorecards_root) / device)
    return str(PurePosixPath(scorecards_root))


def scorecard_path(scorecards_root: str, model_id: str, stream_id: str, role: str, capability: str, runtime_device: str) -> str:
    model = str(model_id or "").strip()
    stream = str(stream_id or "").replace("/", "_")
    role_id = str(role or "").replace("/", "_")
    cap = str(capability or "llm").strip() or "llm"
    return str(PurePosixPath(scorecard_device_root(scorecards_root, runtime_device)) / model / f"{stream}__{role_id}__{cap}.json")


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
        failures.append("policy_mode_not_offline_contract")
    if policy.get("activation_state") != "cpu_gpu_scorecards_separate_by_runtime_device":
        failures.append("policy_activation_state_invalid")
    if PurePosixPath(str(policy.get("cpu_scorecards_root") or "")).name != "cpu":
        failures.append("policy_cpu_root_invalid")
    if PurePosixPath(str(policy.get("gpu_scorecards_root") or "")).name != "gpu":
        failures.append("policy_gpu_root_invalid")
    if set(_as_string_list(policy.get("allowed_runtime_devices"))) != {"cpu", "gpu"}:
        failures.append("policy_allowed_runtime_devices_invalid")
    aliases = policy.get("aliases") if isinstance(policy.get("aliases"), dict) else {}
    if aliases.get("cuda") != "gpu":
        failures.append("policy_cuda_alias_missing")
    for key in ["require_runtime_device_field", "require_device_specific_paths", "require_docs_and_changelog_refs", "require_registry_attachment", "require_no_live_backend_dependency"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    tokens = policy.get("required_runtime_tokens") if isinstance(policy.get("required_runtime_tokens"), dict) else {}
    if not tokens:
        failures.append("policy_required_runtime_tokens_empty")
    if not _as_string_list(policy.get("required_example_sets")):
        failures.append("policy_required_example_sets_empty")
    return failures


def _source_failures(policy: Dict[str, Any], *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    failures: List[str] = []
    reports: List[Dict[str, Any]] = []
    refs = {
        "model_scorecards": "noemaforge/src/model_scorecards.py",
        "role_tournament": "noemaforge/src/role_tournament.py",
    }
    required = policy.get("required_runtime_tokens") if isinstance(policy.get("required_runtime_tokens"), dict) else {}
    for key, ref in refs.items():
        resolved = _resolve_ref(ref, project_root=project_root, package_root=package_root)
        text = load_text(resolved["path"]) if resolved.get("ok") else ""
        local: List[str] = []
        if not resolved.get("ok"):
            local.append(f"source_missing:{ref}")
        for token in _as_string_list(required.get(key)):
            if token not in text:
                local.append(f"source_token_missing:{key}:{token}")
        if key == "model_scorecards" and "yaml is None" not in text:
            local.append("model_scorecards_import_not_yaml_optional")
        reports.append({"key": key, "ref": ref, "ok": not local, "failures": local, "resolved": resolved})
        failures.extend(local)
    return {"failures": failures, "reports": reports}


def _registry_failures(payload: Dict[str, Any], *, package_root: Path) -> Dict[str, Any]:
    registry = load_json(package_root / "configs" / "unified-registry.json")
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
        for metric in ["cpu_scorecard_namespace", "gpu_scorecard_namespace", "runtime_device_field", "registry_attachment", "refs_resolved"]:
            if metric not in metrics:
                failures.append(f"registry_metric_missing:{metric}")
    return {"failures": failures, "eval_ref": eval_ref, "registry_entries": len(entries)}


def _example_failures(example: Dict[str, Any], *, scorecards_root: str) -> Dict[str, Any]:
    failures: List[str] = []
    scenario_reports: List[Dict[str, Any]] = []
    passing = 0
    if example.get("apiVersion") != API_VERSION:
        failures.append("examples_api_version_invalid")
    if example.get("kind") != EXAMPLE_KIND:
        failures.append("examples_kind_invalid")
    scenarios = example.get("scenarios") if isinstance(example.get("scenarios"), list) else []
    if not scenarios:
        failures.append("examples_scenarios_empty")
    seen_devices: set[str] = set()
    for scenario in scenarios:
        sid = str(scenario.get("id") or "")
        local: List[str] = []
        if not SAFE_ID_RE.match(sid):
            local.append("scenario_id_invalid")
        if not str(scenario.get("trace_id") or "").startswith("trace:"):
            local.append("scenario_trace_id_missing")
        runtime_device = normalize_runtime_device(str(scenario.get("runtime_device") or ""))
        seen_devices.add(runtime_device)
        expected_suffix = str(scenario.get("expected_path_suffix") or "")
        path = scorecard_path(
            scorecards_root,
            str(scenario.get("model_id") or ""),
            str(scenario.get("stream_id") or ""),
            str(scenario.get("role") or ""),
            str(scenario.get("capability") or "llm"),
            str(scenario.get("runtime_device") or ""),
        )
        if not path.endswith(expected_suffix):
            local.append(f"scenario_path_mismatch:{path}")
        if runtime_device not in {"cpu", "gpu"}:
            local.append("scenario_runtime_device_not_cpu_or_gpu")
        scenario_reports.append({"id": sid, "ok": not local, "failures": local, "path": path})
        if local:
            failures.extend([f"scenario:{sid}:{item}" for item in local])
        else:
            passing += 1
    if not {"cpu", "gpu"}.issubset(seen_devices):
        failures.append("examples_missing_cpu_or_gpu_scenario")
    return {"failures": failures, "scenario_reports": scenario_reports, "examples": len(scenarios), "passing_examples": passing}


def validate_cpu_gpu_scorecard_separation_policy(
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
    source = _source_failures(policy, project_root=project, package_root=package)
    failures.extend(source["failures"])
    registry = _registry_failures(payload, package_root=package)
    failures.extend(registry["failures"])
    example_reports: List[Dict[str, Any]] = []
    for ref in _as_string_list(policy.get("required_example_sets")):
        resolved = _resolve_ref(ref, project_root=project, package_root=package)
        if not resolved.get("ok"):
            failures.append(f"example_ref_missing:{ref}")
            continue
        report = _example_failures(load_example_set(resolved["path"]), scorecards_root=str(policy.get("scorecards_root") or "model_scorecards"))
        failures.extend(report["failures"])
        example_reports.append({"ref": ref, **report})
    metrics = {
        "refs": len(_as_string_list(payload.get("refs"))),
        "resolved_refs": len(ref_report["resolved_refs"]),
        "examples": sum(int(item.get("examples") or 0) for item in example_reports),
        "passing_examples": sum(int(item.get("passing_examples") or 0) for item in example_reports),
        "registry_entries": registry["registry_entries"],
        "checked_runtime_tokens": sum(len(_as_string_list(tokens)) for tokens in (policy.get("required_runtime_tokens") or {}).values()) if isinstance(policy.get("required_runtime_tokens"), dict) else 0,
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
        "source": source,
        "registry": registry,
        "examples": example_reports,
    }


def cpu_gpu_scorecard_separation_report_to_gate_evidence(report: Dict[str, Any], *, artifact_uri: str = "") -> Dict[str, Any]:
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


def benchmark_cpu_gpu_scorecard_separation(*, package_root: Path | str, iterations: int = 120) -> Dict[str, Any]:
    package = Path(package_root).resolve()
    policy = load_policy(package / "configs" / "cpu-gpu-scorecard-separation-policy.json")
    started = time.perf_counter()
    failures = 0
    for _ in range(iterations):
        report = validate_cpu_gpu_scorecard_separation_policy(policy, project_root=package.parent, package_root=package)
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
        "kind": "CpuGpuScorecardSeparationValidationSummary",
        "ok": bool(report.get("ok")),
        "id": report.get("id"),
        "version": report.get("version"),
        "metrics": report.get("metrics", {}),
        "failures": report.get("failures", []),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate NoemaForge CPU/GPU scorecard separation")
    parser.add_argument("--policy", default=str(SRC_DIR.parent / "configs" / "cpu-gpu-scorecard-separation-policy.json"))
    parser.add_argument("--project-root", default=str(SRC_DIR.parent.parent))
    parser.add_argument("--package-root", default=str(SRC_DIR.parent))
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = validate_cpu_gpu_scorecard_separation_policy(
        load_policy(args.policy),
        project_root=Path(args.project_root),
        package_root=Path(args.package_root),
        policy_path=Path(args.policy),
    )
    print(json.dumps(build_summary(report) if args.summary else report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
