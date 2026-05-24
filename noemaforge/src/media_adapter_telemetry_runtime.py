#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/media_adapter_telemetry_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate telemetry and selftest coverage for local media adapters.
Inputs: Media adapter telemetry policy, media pipeline catalogs, selftest catalog and examples.
Outputs: JSON-compatible MediaAdapterTelemetryValidationReport artifacts.
Side effects: None unless run as a CLI, which writes JSON to stdout.
Tests: noemaforge/tests/test_media_adapter_telemetry_runtime.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional, Sequence


SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import unified_registry_runtime as urr


API_VERSION = "noemaforge.media-adapter-telemetry/v1"
POLICY_KIND = "MediaAdapterTelemetryPolicy"
EXAMPLE_KIND = "MediaAdapterTelemetryExampleSet"
REPORT_KIND = "MediaAdapterTelemetryValidationReport"
VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,220}$")
REQUIRED_METRICS = {
    "wall_time_ms",
    "cpu_time_ms",
    "max_rss_mb",
    "disk_read_bytes",
    "disk_write_bytes",
    "artifact_bytes",
    "status",
}
OPTIONAL_HARDWARE_METRICS = {"gpu_vram_mb", "gpu_utilization_pct", "ecc_error_count"}
REQUIRED_SELFTEST_CASES = {"metadata_probe", "plan_only_smoke", "artifact_review_stub"}
REQUIRED_ADAPTERS = {
    "voice_generation": "audio.tts_generate",
    "music_generation": "audio.music_generate",
    "photo_generation": "image.photo_generate",
    "video_generation": "video.generate",
    "image_analysis": "image.metadata_and_caption",
    "camera_mask_bridge": "video_call.masks_virtual_camera",
}
REQUIRED_DOCS = [
    "noemaforge/docs/README.md",
    "noemaforge/docs/TODO.md",
    "noemaforge/docs/backlog/ROADMAP_AND_TODO.md",
    "noemaforge/docs/reference/PROJECT_CONTEXT.md",
    "noemaforge/docs/history/CHANGELOG.md",
]
REGISTRY_REFS = [
    "configs/media-adapter-telemetry-policy.json",
    "contracts/media_adapter_telemetry.schema.json",
    "src/media_adapter_telemetry_runtime.py",
    "src/selftest_runtime.py",
    "tests/test_media_adapter_telemetry_runtime.py",
    "tests/test_media_adapter_telemetry_qa.py",
    "tests/test_media_adapter_telemetry_performance.py",
    "configs/media-pipeline-catalog.json",
    "configs/pipelines.json",
    "configs/selftest-case-catalog.json",
    "prelaunch/governance/media_adapter_telemetry.example.json",
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
    candidates = [("project", project_root / ref), ("package", package_root / ref)]
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


def load_json(path: Path | str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_text(path: Path | str) -> str:
    return Path(path).read_text(encoding="utf-8")


def load_policy(path: Path | str) -> Dict[str, Any]:
    return load_json(path)


def load_example_set(path: Path | str) -> Dict[str, Any]:
    return load_json(path)


def _policy_dict(payload: Dict[str, Any]) -> Dict[str, Any]:
    return payload.get("policy") if isinstance(payload.get("policy"), dict) else payload


def _adapter_entries(policy_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    policy = _policy_dict(policy_payload)
    entries = policy.get("required_media_adapters") if isinstance(policy.get("required_media_adapters"), list) else []
    return [item for item in entries if isinstance(item, dict)]


def _adapter_map(policy_payload: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {str(item.get("pipeline_id") or ""): item for item in _adapter_entries(policy_payload)}


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
    for key in ["local_first_default", "require_registry_attachment", "require_docs_and_changelog_refs", "require_media_catalog_attachment"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    if str(policy.get("mode") or "") != "offline_contract":
        failures.append("policy_mode_not_offline_contract")
    metrics = set(_as_string_list(policy.get("required_metrics")))
    missing_metrics = REQUIRED_METRICS.difference(metrics)
    failures.extend(f"policy_required_metric_missing:{item}" for item in sorted(missing_metrics))
    optional_metrics = set(_as_string_list(policy.get("optional_hardware_metrics")))
    missing_optional = OPTIONAL_HARDWARE_METRICS.difference(optional_metrics)
    failures.extend(f"policy_optional_metric_missing:{item}" for item in sorted(missing_optional))
    cases = set(_as_string_list(policy.get("required_selftest_cases")))
    failures.extend(f"policy_selftest_case_missing:{item}" for item in sorted(REQUIRED_SELFTEST_CASES.difference(cases)))
    adapters = _adapter_map(payload)
    failures.extend(f"policy_adapter_missing:{item}" for item in sorted(set(REQUIRED_ADAPTERS).difference(adapters)))
    for pipeline_id, catalog_id in sorted(REQUIRED_ADAPTERS.items()):
        entry = adapters.get(pipeline_id)
        if not entry:
            continue
        if entry.get("catalog_id") != catalog_id:
            failures.append(f"policy_catalog_mismatch:{pipeline_id}:{entry.get('catalog_id')}")
        if entry.get("live_backend_required") is not False:
            failures.append(f"policy_live_backend_not_false:{pipeline_id}")
        if not str(entry.get("telemetry_profile") or ""):
            failures.append(f"policy_profile_missing:{pipeline_id}")
    if not _as_string_list(policy.get("required_example_sets")):
        failures.append("policy_required_example_sets_empty")
    return failures


def _registry_ref(entry: Dict[str, Any]) -> str:
    return f"{entry.get('kind')}:{entry.get('id')}:{entry.get('version')}"


def _registry_failures(payload: Dict[str, Any], *, project_root: Path, package_root: Path, registry_path: Path) -> Dict[str, Any]:
    registry = urr.load_registry(registry_path)
    report = urr.validate_unified_registry(registry, project_root=project_root, package_root=package_root, registry_path=registry_path)
    failures = [f"registry_invalid:{item}" for item in report.get("failures", [])]
    entries = {_registry_ref(entry): entry for entry in report.get("normalized_registry", {}).get("entries", []) if isinstance(entry, dict)}
    raw_entries = {_registry_ref(entry): entry for entry in registry.get("entries", []) if isinstance(entry, dict)}
    eval_ref = f"eval-pack:{payload.get('id')}:{payload.get('version')}"
    if eval_ref not in entries:
        failures.append(f"registry_eval_pack_missing:{eval_ref}")
    pipeline_ref = "pipeline:firstboot-model-selection:0.32.1"
    pipeline = raw_entries.get(pipeline_ref) or entries.get(pipeline_ref)
    if not pipeline:
        failures.append(f"registry_pipeline_missing:{pipeline_ref}")
    else:
        if eval_ref not in _as_string_list(pipeline.get("eval_pack_refs")):
            failures.append(f"registry_pipeline_eval_pack_missing:{eval_ref}")
        for ref in ["configs/media-adapter-telemetry-policy.json", "src/media_adapter_telemetry_runtime.py", "prelaunch/governance/media_adapter_telemetry.example.json"]:
            if ref not in _as_string_list(pipeline.get("refs")):
                failures.append(f"registry_pipeline_ref_missing:{ref}")
    return {"failures": failures, "entries": entries, "registry_report": report}


def _catalog_failures(payload: Dict[str, Any], *, package_root: Path) -> List[str]:
    failures: List[str] = []
    media_catalog = load_json(package_root / "configs" / "media-pipeline-catalog.json")
    contract = media_catalog.get("adapter_telemetry_contract") if isinstance(media_catalog.get("adapter_telemetry_contract"), dict) else {}
    if contract.get("id") != payload.get("id"):
        failures.append("media_catalog_contract_id_missing")
    if contract.get("live_backend_required") is not False:
        failures.append("media_catalog_live_backend_not_false")
    contract_metrics = set(_as_string_list(contract.get("required_metrics")))
    failures.extend(f"media_catalog_metric_missing:{item}" for item in sorted(REQUIRED_METRICS.difference(contract_metrics)))
    contract_cases = set(_as_string_list(contract.get("required_selftest_cases")))
    failures.extend(f"media_catalog_case_missing:{item}" for item in sorted(REQUIRED_SELFTEST_CASES.difference(contract_cases)))
    adapter_map = contract.get("adapter_map") if isinstance(contract.get("adapter_map"), dict) else {}
    catalog_entries = {str(item.get("id") or ""): item for item in media_catalog.get("pipelines", []) if isinstance(item, dict)}
    for pipeline_id, catalog_id in sorted(REQUIRED_ADAPTERS.items()):
        if adapter_map.get(pipeline_id) != catalog_id:
            failures.append(f"media_catalog_adapter_map_missing:{pipeline_id}:{catalog_id}")
        entry = catalog_entries.get(catalog_id)
        if not entry:
            failures.append(f"media_catalog_entry_missing:{catalog_id}")
        elif entry.get("autostart") is not False:
            failures.append(f"media_catalog_autostart_not_false:{catalog_id}")
    return failures


def _pipeline_failures(payload: Dict[str, Any], *, package_root: Path) -> List[str]:
    failures: List[str] = []
    pipelines = load_json(package_root / "configs" / "pipelines.json")
    for pipeline_id, catalog_id in sorted(REQUIRED_ADAPTERS.items()):
        pipeline = pipelines.get(pipeline_id) if isinstance(pipelines.get(pipeline_id), dict) else {}
        if not pipeline:
            failures.append(f"pipeline_missing:{pipeline_id}")
            continue
        telemetry = pipeline.get("resource_telemetry") if isinstance(pipeline.get("resource_telemetry"), dict) else {}
        if telemetry.get("contract") != payload.get("id"):
            failures.append(f"pipeline_telemetry_contract_missing:{pipeline_id}")
        if telemetry.get("catalog_id") != catalog_id:
            failures.append(f"pipeline_telemetry_catalog_mismatch:{pipeline_id}:{telemetry.get('catalog_id')}")
        if telemetry.get("live_backend_required") is not False:
            failures.append(f"pipeline_telemetry_live_backend_not_false:{pipeline_id}")
        metrics = set(_as_string_list(telemetry.get("required_metrics")))
        failures.extend(f"pipeline_telemetry_metric_missing:{pipeline_id}:{item}" for item in sorted(REQUIRED_METRICS.difference(metrics)))
        cases = set(_as_string_list(telemetry.get("selftest_cases")))
        failures.extend(f"pipeline_telemetry_case_missing:{pipeline_id}:{item}" for item in sorted(REQUIRED_SELFTEST_CASES.difference(cases)))
    return failures


def _selftest_catalog_failures(*, package_root: Path) -> List[str]:
    failures: List[str] = []
    catalog = load_json(package_root / "configs" / "selftest-case-catalog.json")
    suite = _as_string_list((catalog.get("suites") or {}).get("media_adapters"))
    cases = {str(item.get("id") or ""): item for item in catalog.get("cases", []) if isinstance(item, dict)}
    for pipeline_id in sorted(REQUIRED_ADAPTERS):
        case_id = f"media_adapter_telemetry_{pipeline_id}"
        if case_id not in suite:
            failures.append(f"selftest_suite_case_missing:{case_id}")
        case = cases.get(case_id)
        if not case:
            failures.append(f"selftest_case_missing:{case_id}")
            continue
        if case.get("live") is not False:
            failures.append(f"selftest_case_live_not_false:{case_id}")
        command = _as_string_list(case.get("command"))
        if command[:3] != ["__media_adapter_telemetry__", pipeline_id, "plan_only_smoke"]:
            failures.append(f"selftest_case_command_invalid:{case_id}")
    return failures


def _example_failures(payload: Dict[str, Any], *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    policy = _policy_dict(payload)
    failures: List[str] = []
    adapter_results: List[Dict[str, Any]] = []
    refs_result = _resolve_refs(_as_string_list(policy.get("required_example_sets")), project_root=project_root, package_root=package_root, owner=str(payload.get("id") or "policy"))
    failures.extend(refs_result["failures"])
    for item in refs_result["resolved_refs"]:
        example_set = load_example_set(Path(item["path"]))
        if example_set.get("apiVersion") != API_VERSION:
            failures.append(f"example_set_api_version_invalid:{item['ref']}")
        if example_set.get("kind") != EXAMPLE_KIND:
            failures.append(f"example_set_kind_invalid:{item['ref']}")
        examples = example_set.get("adapters") if isinstance(example_set.get("adapters"), list) else []
        by_pipeline = {str(example.get("pipeline_id") or ""): example for example in examples if isinstance(example, dict)}
        for pipeline_id, catalog_id in sorted(REQUIRED_ADAPTERS.items()):
            example = by_pipeline.get(pipeline_id)
            if not example:
                failures.append(f"example_adapter_missing:{pipeline_id}")
                continue
            if example.get("catalog_id") != catalog_id:
                failures.append(f"example_catalog_mismatch:{pipeline_id}:{example.get('catalog_id')}")
            if example.get("live_backend_required") is not False:
                failures.append(f"example_live_backend_not_false:{pipeline_id}")
            cases = set(_as_string_list(example.get("selftest_cases")))
            missing_cases = REQUIRED_SELFTEST_CASES.difference(cases)
            failures.extend(f"example_case_missing:{pipeline_id}:{case}" for case in sorted(missing_cases))
            metrics = set(_as_string_list(example.get("expected_metrics")))
            missing_metrics = REQUIRED_METRICS.difference(metrics)
            failures.extend(f"example_metric_missing:{pipeline_id}:{metric}" for metric in sorted(missing_metrics))
            scenario_ref_result = _resolve_refs(_as_string_list(example.get("refs")), project_root=project_root, package_root=package_root, owner=pipeline_id)
            failures.extend(scenario_ref_result["failures"])
            adapter_results.append({"pipeline_id": pipeline_id, "catalog_id": catalog_id, "case_count": len(cases), "metric_count": len(metrics), "ok": not missing_cases and not missing_metrics})
    return {
        "failures": failures,
        "adapter_results": adapter_results,
        "resolved_refs": refs_result["resolved_refs"],
        "missing_refs": refs_result["missing_refs"],
        "unsafe_refs": refs_result["unsafe_refs"],
    }


def _docs_failures(*, project_root: Path) -> Dict[str, Any]:
    failures: List[str] = []
    docs_seen: List[str] = []
    for rel in REQUIRED_DOCS:
        path = project_root / rel
        text = load_text(path) if path.exists() else ""
        if not text:
            failures.append(f"doc_missing:{rel}")
            continue
        docs_seen.append(rel)
        if "media-adapter-telemetry-core" not in text:
            failures.append(f"doc_token_missing:{rel}:media-adapter-telemetry-core")
    return {"failures": failures, "docs_seen": docs_seen}


def validate_telemetry_sample(sample: Dict[str, Any], policy_payload: Dict[str, Any]) -> Dict[str, Any]:
    adapter = str(sample.get("adapter") or "")
    case_type = str(sample.get("case_type") or "")
    metrics = sample.get("metrics") if isinstance(sample.get("metrics"), dict) else {}
    failures: List[str] = []
    if adapter not in _adapter_map(policy_payload):
        failures.append("unknown_adapter")
    if case_type not in REQUIRED_SELFTEST_CASES:
        failures.append("unknown_case_type")
    if sample.get("live_backend_started") is not False:
        failures.append("live_backend_started")
    for metric in sorted(REQUIRED_METRICS):
        if metric not in metrics:
            failures.append(f"metric_missing:{metric}")
            continue
        value = metrics.get(metric)
        if metric == "status":
            if str(value) not in {"pass", "warn", "fail", "skip"}:
                failures.append("metric_status_invalid")
        elif not isinstance(value, (int, float)) or float(value) < 0:
            failures.append(f"metric_invalid:{metric}")
    return {"ok": not failures, "adapter": adapter, "case_type": case_type, "failures": sorted(failures), "metrics": metrics}


def synthetic_telemetry_sample(adapter: str, case_type: str, index: int = 0) -> Dict[str, Any]:
    size = len(adapter) + len(case_type) + int(index % 7)
    return {
        "adapter": adapter,
        "case_type": case_type,
        "live_backend_started": False,
        "metrics": {
            "wall_time_ms": 1.0 + size,
            "cpu_time_ms": 0.5 + (size / 10.0),
            "max_rss_mb": 8.0 + (size / 20.0),
            "disk_read_bytes": 0,
            "disk_write_bytes": 0,
            "artifact_bytes": 128 if case_type == "artifact_review_stub" else 0,
            "status": "pass",
        },
    }


def evaluate_adapter_selftest_case(adapter: str, case_type: str, policy_payload: Dict[str, Any]) -> Dict[str, Any]:
    sample = synthetic_telemetry_sample(adapter, case_type)
    result = validate_telemetry_sample(sample, policy_payload)
    return {
        "apiVersion": API_VERSION,
        "kind": "MediaAdapterTelemetrySelfTestResult",
        "ok": result["ok"],
        "adapter": adapter,
        "case_type": case_type,
        "live_backend_started": False,
        "failures": result["failures"],
        "metrics": result["metrics"],
    }


def validate_media_adapter_telemetry_policy(
    payload: Dict[str, Any],
    *,
    project_root: Path | str,
    package_root: Path | str,
    policy_path: Optional[Path | str] = None,
    registry_path: Optional[Path | str] = None,
) -> Dict[str, Any]:
    project = _as_path(project_root)
    package = _as_path(package_root)
    registry = _as_path(registry_path) if registry_path else package / "configs" / "unified-registry.json"
    failures: List[str] = []
    failures.extend(_policy_failures(payload))
    registry_result = _registry_failures(payload, project_root=project, package_root=package, registry_path=registry)
    failures.extend(registry_result["failures"])
    failures.extend(_catalog_failures(payload, package_root=package))
    failures.extend(_pipeline_failures(payload, package_root=package))
    failures.extend(_selftest_catalog_failures(package_root=package))
    example_result = _example_failures(payload, project_root=project, package_root=package)
    failures.extend(example_result["failures"])
    docs_result = _docs_failures(project_root=project)
    failures.extend(docs_result["failures"])
    refs = sorted(set(_as_string_list(payload.get("refs")) + REGISTRY_REFS))
    refs_result = _resolve_refs(refs, project_root=project, package_root=package, owner=str(payload.get("id") or "policy"))
    failures.extend(refs_result["failures"])
    adapter_count = len(_adapter_map(payload))
    metrics = {
        "adapters": adapter_count,
        "required_metrics": len(REQUIRED_METRICS),
        "optional_hardware_metrics": len(OPTIONAL_HARDWARE_METRICS),
        "required_selftest_cases": len(REQUIRED_SELFTEST_CASES),
        "selftest_case_slots": adapter_count * len(REQUIRED_SELFTEST_CASES),
        "example_adapters": len(example_result["adapter_results"]),
        "registry_entries": len(registry_result["entries"]),
        "docs_seen": len(docs_result["docs_seen"]),
    }
    checks = [
        {"id": "policy_shape", "status": "passed" if not any(item.startswith("policy_") for item in failures) else "failed"},
        {"id": "media_catalog", "status": "passed" if not any(item.startswith("media_catalog_") for item in failures) else "failed"},
        {"id": "pipeline_contracts", "status": "passed" if not any(item.startswith("pipeline_") for item in failures) else "failed"},
        {"id": "selftest_catalog", "status": "passed" if not any(item.startswith("selftest_") for item in failures) else "failed"},
        {"id": "examples", "status": "passed" if not any(item.startswith("example_") for item in failures) else "failed"},
        {"id": "registry_attachment", "status": "passed" if not any(item.startswith("registry_") for item in failures) else "failed"},
        {"id": "docs", "status": "passed" if not any(item.startswith("doc_") for item in failures) else "failed"},
    ]
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
        "adapter_results": sorted(example_result["adapter_results"], key=lambda item: item["pipeline_id"]),
        "resolved_refs": sorted(refs_result["resolved_refs"] + example_result["resolved_refs"], key=lambda item: (item["owner"], item["ref"])),
        "missing_refs": sorted(refs_result["missing_refs"] + example_result["missing_refs"], key=lambda item: (item["owner"], item["ref"])),
        "unsafe_refs": sorted(refs_result["unsafe_refs"] + example_result["unsafe_refs"], key=lambda item: (item["owner"], item["ref"])),
    }


def benchmark_media_adapter_telemetry(policy_payload: Dict[str, Any], *, iterations: int = 600) -> Dict[str, Any]:
    adapters = sorted(_adapter_map(policy_payload)) or sorted(REQUIRED_ADAPTERS)
    cases = sorted(REQUIRED_SELFTEST_CASES)
    started = time.perf_counter()
    passed = 0
    failed = 0
    for index in range(iterations):
        adapter = adapters[index % len(adapters)]
        case_type = cases[index % len(cases)]
        result = validate_telemetry_sample(synthetic_telemetry_sample(adapter, case_type, index), policy_payload)
        if result["ok"]:
            passed += 1
        else:
            failed += 1
    elapsed = time.perf_counter() - started
    return {"iterations": iterations, "passed": passed, "failed": failed, "elapsed_sec": elapsed, "ok": passed == iterations and failed == 0}


def _default_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate NoemaForge media adapter telemetry contracts.")
    parser.add_argument("--project-root", default=str(_default_project_root()))
    parser.add_argument("--package-root", default="")
    parser.add_argument("--policy", default="noemaforge/configs/media-adapter-telemetry-policy.json")
    parser.add_argument("--registry", default="")
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--adapter", default="")
    parser.add_argument("--case", default="plan_only_smoke")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    project_root = _as_path(args.project_root)
    package_root = _as_path(args.package_root) if args.package_root else project_root / "noemaforge"
    policy_path = Path(args.policy)
    if not policy_path.is_absolute():
        policy_path = project_root / policy_path
    policy = load_policy(policy_path)
    if args.adapter:
        payload = evaluate_adapter_selftest_case(args.adapter, args.case, policy)
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if payload["ok"] else 1
    registry_path = Path(args.registry) if args.registry else package_root / "configs" / "unified-registry.json"
    if not registry_path.is_absolute():
        registry_path = project_root / registry_path
    report = validate_media_adapter_telemetry_policy(
        policy,
        project_root=project_root,
        package_root=package_root,
        policy_path=policy_path,
        registry_path=registry_path,
    )
    payload: Dict[str, Any]
    if args.summary:
        payload = {
            "apiVersion": report["apiVersion"],
            "kind": "MediaAdapterTelemetryValidationSummary",
            "ok": report["ok"],
            "created_at": report["created_at"],
            "metrics": report["metrics"],
            "failures": report["failures"],
        }
    else:
        payload = report
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
