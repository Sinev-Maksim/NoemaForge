#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/pipeline_performance_metrics_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-21
Modified: 2026-05-21
Purpose: Validate pipeline performance metrics for latency, memory, operation count and artifact size.
Inputs: Pipeline performance metrics policy and local metric artifact examples.
Outputs: JSON-compatible PipelinePerformanceMetricsValidationReport artifacts.
Side effects: None; CLI writes JSON to stdout.
Tests: noemaforge/tests/test_pipeline_performance_metrics_runtime.py, QA and performance tests.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional, Sequence


API_VERSION = "noemaforge.pipeline-performance-metrics/v1"
POLICY_KIND = "PipelinePerformanceMetricsPolicy"
EXAMPLE_KIND = "PipelinePerformanceMetricsExampleSet"
REPORT_KIND = "PipelinePerformanceMetricsValidationReport"
POLICY_ID = "pipeline-performance-metrics-core"
PRIMARY_TODO = "Add performance metrics: latency, memory, operation count, artifact size."

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = PACKAGE_ROOT.parent
DEFAULT_POLICY = PACKAGE_ROOT / "configs" / "pipeline-performance-metrics-policy.json"
DEFAULT_EXAMPLE = PROJECT_ROOT / "prelaunch" / "governance" / "pipeline_performance_metrics.example.json"

VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
REQUIRED_METRIC_FIELDS = [
    "stage_id",
    "latency_ms",
    "memory_mb",
    "operation_count",
    "artifact_bytes",
    "status",
]
SUMMARY_FIELDS = [
    "sample_count",
    "max_latency_ms",
    "max_memory_mb",
    "total_operation_count",
    "total_artifact_bytes",
    "status_counts",
]
REQUIRED_CONTROLS = [
    "metrics_are_non_negative",
    "operation_count_integer",
    "artifact_bytes_integer",
    "summary_required",
    "stage_id_required",
    "no_live_probe",
    "artifact_only_input",
]
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,220}$")


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


def _number(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return float(value)
    return None


def summarize_metric_samples(samples: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    status_counts: Dict[str, int] = {}
    max_latency = 0.0
    max_memory = 0.0
    total_operations = 0
    total_artifact_bytes = 0
    for sample in samples:
        latency = _number(sample.get("latency_ms")) or 0.0
        memory = _number(sample.get("memory_mb")) or 0.0
        operations = int(sample.get("operation_count") or 0)
        artifact_bytes = int(sample.get("artifact_bytes") or 0)
        status = str(sample.get("status") or "unknown")
        max_latency = max(max_latency, latency)
        max_memory = max(max_memory, memory)
        total_operations += operations
        total_artifact_bytes += artifact_bytes
        status_counts[status] = status_counts.get(status, 0) + 1
    return {
        "sample_count": len(samples),
        "max_latency_ms": round(max_latency, 6),
        "max_memory_mb": round(max_memory, 6),
        "total_operation_count": total_operations,
        "total_artifact_bytes": total_artifact_bytes,
        "status_counts": status_counts,
    }


def _sample_failures(sample: Dict[str, Any], *, allowed_statuses: set[str], index: int) -> List[str]:
    failures: List[str] = []
    for field in REQUIRED_METRIC_FIELDS:
        if field not in sample:
            failures.append(f"metric_field_missing:{index}:{field}")
    stage_id = str(sample.get("stage_id") or "")
    if not SAFE_ID_RE.match(stage_id):
        failures.append(f"stage_id_invalid:{index}")
    for field in ["latency_ms", "memory_mb"]:
        value = _number(sample.get(field))
        if value is None or value < 0:
            failures.append(f"metric_non_negative_number_invalid:{index}:{field}")
    for field in ["operation_count", "artifact_bytes"]:
        value = sample.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            failures.append(f"metric_non_negative_integer_invalid:{index}:{field}")
    status = str(sample.get("status") or "")
    if status not in allowed_statuses:
        failures.append(f"metric_status_invalid:{index}:{status}")
    return failures


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
    if str(policy.get("activation_state") or "") != "pipeline_performance_metrics_contract":
        failures.append("policy_activation_state_invalid")
    if str(policy.get("required_pipeline_ref") or "") != "pipeline:firstboot-model-selection:0.32.1":
        failures.append("policy_required_pipeline_ref_invalid")
    if PRIMARY_TODO not in _as_string_list(policy.get("closed_todo_refs")):
        failures.append("policy_closed_todo_ref_missing")
    for key in ["require_registry_attachment", "require_docs_and_changelog_refs", "require_no_live_probe"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    if _as_string_list(policy.get("required_metric_fields")) != REQUIRED_METRIC_FIELDS:
        failures.append("policy_required_metric_fields_invalid")
    units = policy.get("metric_units") if isinstance(policy.get("metric_units"), dict) else {}
    for metric in ["latency_ms", "memory_mb", "operation_count", "artifact_bytes"]:
        if not str(units.get(metric) or ""):
            failures.append(f"policy_metric_unit_missing:{metric}")
    allowed = set(_as_string_list(policy.get("allowed_statuses")))
    if not {"passed", "warn", "failed", "skipped"}.issubset(allowed):
        failures.append("policy_allowed_statuses_missing")
    controls = policy.get("controls") if isinstance(policy.get("controls"), dict) else {}
    for key in REQUIRED_CONTROLS:
        if controls.get(key) is not True:
            failures.append(f"control_{key}_not_true")
    if _as_string_list(policy.get("summary_fields")) != SUMMARY_FIELDS:
        failures.append("policy_summary_fields_invalid")
    if not _as_string_list(policy.get("required_outputs")):
        failures.append("policy_required_outputs_empty")
    if not _as_string_list(policy.get("required_refs")):
        failures.append("policy_required_refs_empty")
    return failures


def _example_failures(example: Dict[str, Any], *, allowed_statuses: set[str]) -> Dict[str, Any]:
    failures: List[str] = []
    if example.get("apiVersion") != API_VERSION:
        failures.append("example_api_version_invalid")
    if example.get("kind") != EXAMPLE_KIND:
        failures.append("example_kind_invalid")
    samples = example.get("samples") if isinstance(example.get("samples"), list) else []
    if not samples:
        failures.append("example_samples_empty")
    for index, sample in enumerate(samples):
        if not isinstance(sample, dict):
            failures.append(f"metric_sample_not_object:{index}")
            continue
        failures.extend(_sample_failures(sample, allowed_statuses=allowed_statuses, index=index))
    summary = summarize_metric_samples(samples)
    expected = example.get("expected_summary") if isinstance(example.get("expected_summary"), dict) else {}
    for key in [
        "sample_count",
        "max_latency_ms",
        "max_memory_mb",
        "total_operation_count",
        "total_artifact_bytes",
        "status_counts",
    ]:
        if summary.get(key) != expected.get(key):
            failures.append(f"example_summary_mismatch:{key}")
    return {"failures": failures, "samples": samples, "summary": summary}


def validate_pipeline_performance_metrics_policy(
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

    allowed_statuses = set(_as_string_list(policy.get("allowed_statuses")))
    example_report = _example_failures(load_example(example_path), allowed_statuses=allowed_statuses)
    failures.extend(example_report["failures"])

    return {
        "apiVersion": API_VERSION,
        "kind": REPORT_KIND,
        "ok": not failures,
        "created_at": _nowz(),
        "id": POLICY_ID,
        "failures": sorted(failures),
        "pipeline_performance_metrics_summary": example_report["summary"],
        "stage_metric_matrix": example_report["samples"],
        "resolved_refs": ref_report["resolved_refs"],
        "missing_refs": ref_report["missing_refs"],
        "unsafe_refs": ref_report["unsafe_refs"],
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate NoemaForge pipeline performance metric contracts.")
    parser.add_argument("--policy", default=str(DEFAULT_POLICY), help="Policy JSON path.")
    parser.add_argument("--example", default=str(DEFAULT_EXAMPLE), help="Example metric artifact path.")
    parser.add_argument("--summary", action="store_true", help="Emit compact summary.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    report = validate_pipeline_performance_metrics_policy(load_policy(args.policy), example_path=args.example)
    payload: Dict[str, Any]
    if args.summary:
        payload = {
            "apiVersion": API_VERSION,
            "kind": "PipelinePerformanceMetricsSummary",
            "id": POLICY_ID,
            "ok": report["ok"],
            "failures": report["failures"],
            "metrics": report["pipeline_performance_metrics_summary"],
        }
    else:
        payload = report
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
