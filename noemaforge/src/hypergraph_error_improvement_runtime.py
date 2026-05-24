#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/hypergraph_error_improvement_runtime.py
Zone: release/package
Version: 0.31.21.alpha
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate the offline model-improvement loop from reviewed hypergraph errors.
Inputs: Hypergraph Error Improvement policy, error-learning SQL, unified registry and offline examples.
Outputs: JSON-compatible HypergraphErrorImprovementValidationReport artifacts.
Side effects: None; CLI writes JSON to stdout.
Tests: noemaforge/tests/test_hypergraph_error_improvement_runtime.py
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


API_VERSION = "noemaforge.hypergraph-error-improvement/v1"
POLICY_KIND = "HypergraphErrorImprovementPolicy"
SET_KIND = "HypergraphErrorImprovementExampleSet"
REPORT_KIND = "HypergraphErrorImprovementValidationReport"

VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,220}$")
REQUIRED_STORES = {"error_events", "corrections", "regression_cases"}
REQUIRED_RUN_FIELDS = {"run_id", "component", "model_id", "profile_id"}
REQUIRED_DEFECT_CLASSES = {
    "source_defect",
    "labeling_defect",
    "chunking_defect",
    "extraction_defect",
    "linking_defect",
}
PIPELINE_DEFECT_CLASSES = REQUIRED_DEFECT_CLASSES - {"source_defect"}
REQUIRED_REUSE_TARGETS = {"retraining", "evaluation"}
REQUIRED_CONTROLS = {
    "error_events_store_required",
    "corrections_store_required",
    "regression_cases_store_required",
    "source_defects_separated",
    "pipeline_defects_classified",
    "approved_corrections_reused_for_training",
    "approved_corrections_reused_for_evaluation",
    "model_run_profile_tracking_required",
    "no_live_host_required",
}
REQUIRED_REGISTRY_REFS = [
    "configs/hypergraph-error-improvement-policy.json",
    "contracts/hypergraph_error_improvement.schema.json",
    "sql/error_learning_loop.sqlite.sql",
    "src/hypergraph_error_improvement_runtime.py",
    "src/knowledge/error_learning.py",
    "src/knowledge/eval_runtime.py",
    "src/knowledge/extraction_pipeline.py",
    "src/knowledge/prep_pipeline.py",
    "tests/test_error_learning_runtime.py",
    "tests/test_hypergraph_error_improvement_runtime.py",
    "tests/test_hypergraph_error_improvement_qa.py",
    "tests/test_hypergraph_error_improvement_performance.py",
    "prelaunch/governance/hypergraph_error_improvement.example.json",
]
REQUIRED_PIPELINE_REFS = [
    "configs/hypergraph-error-improvement-policy.json",
    "contracts/hypergraph_error_improvement.schema.json",
    "src/hypergraph_error_improvement_runtime.py",
    "prelaunch/governance/hypergraph_error_improvement.example.json",
]
COMPONENT_DEFECT_DEFAULTS = {
    "prep_labeler": "labeling_defect",
    "labeler": "labeling_defect",
    "chunk_planner": "chunking_defect",
    "chunker": "chunking_defect",
    "claim_extractor": "extraction_defect",
    "extractor": "extraction_defect",
    "entity_linker": "linking_defect",
    "linker": "linking_defect",
}


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


def classify_error_event(event: Dict[str, Any], run: Dict[str, Any] | None = None) -> str:
    if bool(event.get("source_defect")):
        return "source_defect"
    explicit = str(event.get("defect_class") or event.get("error_class") or "").strip()
    if explicit in REQUIRED_DEFECT_CLASSES:
        return explicit
    component = str(event.get("component") or (run or {}).get("component") or "").strip()
    return COMPONENT_DEFECT_DEFAULTS.get(component, "extraction_defect")


def build_improvement_loop(scenario: Dict[str, Any]) -> Dict[str, Any]:
    runs = {
        str(item.get("run_id") or ""): item
        for item in scenario.get("processing_runs", [])
        if isinstance(item, dict) and str(item.get("run_id") or "")
    }
    corrections_by_error: Dict[str, List[Dict[str, Any]]] = {}
    for correction in scenario.get("corrections", []):
        if isinstance(correction, dict):
            corrections_by_error.setdefault(str(correction.get("error_id") or ""), []).append(correction)

    failures: List[str] = []
    tracked_errors: List[Dict[str, Any]] = []
    retraining_deltas: List[Dict[str, Any]] = []
    regression_cases: List[Dict[str, Any]] = []

    for event in scenario.get("error_events", []):
        if not isinstance(event, dict):
            failures.append("error_event_not_object")
            continue
        error_id = str(event.get("error_id") or "")
        run_id = str(event.get("run_id") or "")
        run = runs.get(run_id)
        if not error_id:
            failures.append("error_id_missing")
        if not run:
            failures.append(f"run_missing:{error_id}:{run_id}")
            run = {}
        defect_class = classify_error_event(event, run)
        tracked = {
            "error_id": error_id,
            "defect_class": defect_class,
            "run_id": run_id,
            "component": str(event.get("component") or run.get("component") or ""),
            "model_id": str(event.get("model_id") or run.get("model_id") or ""),
            "profile_id": str(event.get("profile_id") or run.get("profile_id") or ""),
            "source_defect": defect_class == "source_defect",
        }
        for field in REQUIRED_RUN_FIELDS:
            if not str(tracked.get(field) or "").strip():
                failures.append(f"tracked_field_missing:{error_id}:{field}")
        if defect_class not in REQUIRED_DEFECT_CLASSES:
            failures.append(f"defect_class_unknown:{error_id}:{defect_class}")
        if bool(event.get("source_defect")) and defect_class != "source_defect":
            failures.append(f"source_defect_not_separated:{error_id}")
        tracked_errors.append(tracked)

        for correction in corrections_by_error.get(error_id, []):
            approved_training = bool(correction.get("approved_for_training"))
            approved_eval = bool(correction.get("approved_for_eval"))
            if approved_training:
                retraining_deltas.append(
                    {
                        "source_error_id": error_id,
                        "source_correction_id": correction.get("correction_id"),
                        "target_model_family": tracked["component"],
                        "defect_class": defect_class,
                    }
                )
            if approved_eval:
                regression_cases.append(
                    {
                        "source_error_id": error_id,
                        "source_correction_id": correction.get("correction_id"),
                        "component": tracked["component"],
                        "defect_class": defect_class,
                    }
                )

    defect_classes = sorted({item["defect_class"] for item in tracked_errors})
    return {
        "apiVersion": API_VERSION,
        "kind": "HypergraphErrorImprovementPlan",
        "ok": not failures,
        "trace_id": str(scenario.get("trace_id") or ""),
        "generated_at": _nowz(),
        "failures": failures,
        "tracked_errors": tracked_errors,
        "retraining_deltas": retraining_deltas,
        "regression_cases": regression_cases,
        "metrics": {
            "runs": len(runs),
            "tracked_errors": len(tracked_errors),
            "source_defects": sum(1 for item in tracked_errors if item["defect_class"] == "source_defect"),
            "pipeline_defects": sum(1 for item in tracked_errors if item["defect_class"] in PIPELINE_DEFECT_CLASSES),
            "defect_classes": defect_classes,
            "approved_retraining_deltas": len(retraining_deltas),
            "approved_regression_cases": len(regression_cases),
            "models": len({item["model_id"] for item in tracked_errors if item["model_id"]}),
            "profiles": len({item["profile_id"] for item in tracked_errors if item["profile_id"]}),
        },
    }


def _extract_table_body(sql_text: str, table_name: str) -> str:
    pattern = re.compile(rf"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+{re.escape(table_name)}\s*\((.*?)\);", re.IGNORECASE | re.DOTALL)
    match = pattern.search(sql_text)
    return match.group(1).lower() if match else ""


def _sql_failures(policy: Dict[str, Any], *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    ref = str(policy.get("sql_schema_ref") or "")
    resolved = _resolve_ref(ref, project_root=project_root, package_root=package_root)
    failures: List[str] = []
    if not resolved.get("ok"):
        return {"failures": [f"sql_schema_missing:{ref}"], "resolved": resolved, "tables": []}
    sql_text = Path(resolved["path"]).read_text(encoding="utf-8")
    lower_sql = sql_text.lower()
    tables: List[str] = []
    for table in sorted(REQUIRED_STORES | {"processing_runs", "training_deltas"}):
        if re.search(rf"create\s+table\s+if\s+not\s+exists\s+{re.escape(table)}\s*\(", lower_sql):
            tables.append(table)
        elif table in REQUIRED_STORES:
            failures.append(f"store_table_missing:{table}")
    run_body = _extract_table_body(sql_text, "processing_runs")
    for field in REQUIRED_RUN_FIELDS:
        if field not in run_body:
            failures.append(f"processing_run_field_missing:{field}")
    error_body = _extract_table_body(sql_text, "error_events")
    for field in ["run_id", "component", "error_type", "source_defect"]:
        if field not in error_body:
            failures.append(f"error_events_field_missing:{field}")
    corrections_body = _extract_table_body(sql_text, "corrections")
    for field in ["error_id", "approved_for_training", "approved_for_eval"]:
        if field not in corrections_body:
            failures.append(f"corrections_field_missing:{field}")
    regression_body = _extract_table_body(sql_text, "regression_cases")
    for field in ["source_error_id", "source_correction_id", "component"]:
        if field not in regression_body:
            failures.append(f"regression_cases_field_missing:{field}")
    return {"failures": failures, "resolved": resolved, "tables": tables}


def _adapter_failures(policy: Dict[str, Any], *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    ref = str(policy.get("store_adapter_ref") or "")
    resolved = _resolve_ref(ref, project_root=project_root, package_root=package_root)
    failures: List[str] = []
    if not resolved.get("ok"):
        return {"failures": [f"store_adapter_missing:{ref}"], "resolved": resolved, "methods": []}
    text = Path(resolved["path"]).read_text(encoding="utf-8")
    required_methods = [
        "start_run",
        "add_error_event",
        "add_correction",
        "promote_regression_case",
        "promote_training_delta",
        "export_regression_cases",
    ]
    methods: List[str] = []
    for method in required_methods:
        if re.search(rf"def\s+{re.escape(method)}\s*\(", text):
            methods.append(method)
        else:
            failures.append(f"store_adapter_method_missing:{method}")
    return {"failures": failures, "resolved": resolved, "methods": methods}


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
    if str(policy.get("activation_state") or "") != "reviewed_hypergraph_errors_feed_training_and_eval":
        failures.append("policy_activation_state_invalid")
    if not str(policy.get("required_pipeline_ref") or "").startswith("pipeline:"):
        failures.append("policy_required_pipeline_ref_invalid")
    for key in ["sql_schema_ref", "store_adapter_ref"]:
        if not _is_safe_relative_ref(str(policy.get(key) or "")):
            failures.append(f"policy_{key}_invalid")
    for key in ["require_trace_id", "require_registry_attachment", "require_docs_and_changelog_refs", "require_no_live_dependency"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    stores = set(_as_string_list(policy.get("required_stores")))
    for item in REQUIRED_STORES:
        if item not in stores:
            failures.append(f"policy_store_missing:{item}")
    run_fields = set(_as_string_list(policy.get("required_run_fields")))
    for item in REQUIRED_RUN_FIELDS:
        if item not in run_fields:
            failures.append(f"policy_run_field_missing:{item}")
    defect_classes = set(_as_string_list(policy.get("required_defect_classes")))
    for item in REQUIRED_DEFECT_CLASSES:
        if item not in defect_classes:
            failures.append(f"policy_defect_class_missing:{item}")
    reuse_targets = set(_as_string_list(policy.get("approved_reuse_targets")))
    for item in REQUIRED_REUSE_TARGETS:
        if item not in reuse_targets:
            failures.append(f"policy_reuse_target_missing:{item}")
    for key in ["required_boundary_refs", "required_runtime_refs", "required_example_sets"]:
        if not _as_string_list(policy.get(key)):
            failures.append(f"policy_{key}_empty")
    controls = policy.get("controls") if isinstance(policy.get("controls"), dict) else {}
    for key in REQUIRED_CONTROLS:
        if controls.get(key) is not True:
            failures.append(f"policy_control_{key}_not_true")
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
        for ref in REQUIRED_REGISTRY_REFS:
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
    for ref in REQUIRED_PIPELINE_REFS:
        if ref not in pipeline_refs:
            failures.append(f"registry_pipeline_ref_missing:{ref}")
    return {"failures": failures, "registry_report": report, "pipeline_eval_refs": pipeline_eval_refs, "pipeline_refs": pipeline_refs}


def _docs_failures(payload: Dict[str, Any], *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    policy = _policy_dict(payload)
    boundary = str(policy.get("boundary_phrase") or "")
    failures: List[str] = []
    boundary_reports: List[Dict[str, Any]] = []
    for ref in _as_string_list(policy.get("required_boundary_refs")):
        resolved = _resolve_ref(ref, project_root=project_root, package_root=package_root)
        has_phrase = False
        if resolved.get("ok"):
            has_phrase = _contains(Path(resolved["path"]).read_text(encoding="utf-8"), boundary)
        else:
            failures.append(f"boundary_ref_missing:{ref}")
        if resolved.get("ok") and not has_phrase:
            failures.append(f"boundary_phrase_missing:{ref}")
        boundary_reports.append({"ref": ref, "ok": bool(resolved.get("ok")) and has_phrase, "has_phrase": has_phrase, "resolved": resolved})
    return {"failures": failures, "boundary_reports": boundary_reports}


def _example_failures(example_set: Dict[str, Any], *, policy: Dict[str, Any]) -> Dict[str, Any]:
    failures: List[str] = []
    scenario_reports: List[Dict[str, Any]] = []
    passing_scenarios = 0
    required_classes = set(_as_string_list(policy.get("required_defect_classes")))
    required_reuse_targets = set(_as_string_list(policy.get("approved_reuse_targets")))
    if example_set.get("apiVersion") != API_VERSION:
        failures.append("example_api_version_invalid")
    if example_set.get("kind") != SET_KIND:
        failures.append("example_kind_invalid")
    scenarios = example_set.get("scenarios") if isinstance(example_set.get("scenarios"), list) else []
    if not scenarios:
        failures.append("example_scenarios_empty")
    for scenario in scenarios:
        sid = str(scenario.get("id") or "scenario")
        local_failures: List[str] = []
        if not str(scenario.get("trace_id") or "").startswith("trace:"):
            local_failures.append("scenario_trace_id_invalid")
        plan = build_improvement_loop(scenario)
        local_failures.extend([f"plan:{item}" for item in plan.get("failures", [])])
        found_classes = set(plan["metrics"]["defect_classes"])
        expected_classes = set(_as_string_list(scenario.get("expected_defect_classes")))
        if found_classes != expected_classes:
            local_failures.append(f"scenario_defect_classes_mismatch:{sorted(found_classes)}:{sorted(expected_classes)}")
        if not required_classes.issubset(found_classes):
            local_failures.append("scenario_required_defect_classes_missing")
        expected_reuse = set(_as_string_list(scenario.get("expected_reuse_targets")))
        if not required_reuse_targets.issubset(expected_reuse):
            local_failures.append("scenario_reuse_targets_missing")
        if plan["metrics"]["source_defects"] < 1:
            local_failures.append("scenario_source_defect_missing")
        if plan["metrics"]["pipeline_defects"] < 4:
            local_failures.append("scenario_pipeline_defects_missing")
        if plan["metrics"]["approved_retraining_deltas"] < 1:
            local_failures.append("scenario_retraining_delta_missing")
        if plan["metrics"]["approved_regression_cases"] < 1:
            local_failures.append("scenario_regression_case_missing")
        for item in plan.get("tracked_errors", []):
            for field in REQUIRED_RUN_FIELDS:
                if not str(item.get(field) or "").strip():
                    local_failures.append(f"scenario_tracked_field_missing:{field}:{item.get('error_id')}")
        scenario_reports.append({"id": sid, "ok": not local_failures, "failures": local_failures, "plan": plan})
        if local_failures:
            failures.extend([f"scenario:{sid}:{item}" for item in local_failures])
        else:
            passing_scenarios += 1
    return {"failures": failures, "scenario_reports": scenario_reports, "scenarios": len(scenarios), "passing_scenarios": passing_scenarios}


def validate_hypergraph_error_improvement_policy(
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
    policy = _policy_dict(payload)
    failures: List[str] = []
    failures.extend(_policy_failures(payload))
    ref_report = _resolve_refs(_as_string_list(payload.get("refs")), project_root=project, package_root=package, owner=str(payload.get("id") or "policy"))
    failures.extend(ref_report["failures"])
    sql_report = _sql_failures(policy, project_root=project, package_root=package)
    failures.extend(sql_report["failures"])
    adapter_report = _adapter_failures(policy, project_root=project, package_root=package)
    failures.extend(adapter_report["failures"])
    registry_report = _registry_failures(payload, project_root=project, package_root=package, registry_path=registry)
    failures.extend(registry_report["failures"])
    docs_report = _docs_failures(payload, project_root=project, package_root=package)
    failures.extend(docs_report["failures"])
    runtime_refs = _resolve_refs(_as_string_list(policy.get("required_runtime_refs")), project_root=project, package_root=package, owner="runtime_refs")
    failures.extend(runtime_refs["failures"])
    example_reports: List[Dict[str, Any]] = []
    for ref in _as_string_list(policy.get("required_example_sets")):
        resolved = _resolve_ref(ref, project_root=project, package_root=package)
        if not resolved.get("ok"):
            failures.append(f"example_ref_missing:{ref}")
            continue
        example_report = _example_failures(load_example_set(resolved["path"]), policy=policy)
        failures.extend(example_report["failures"])
        example_reports.append({"ref": ref, **example_report})
    total_plan_metrics: Dict[str, int] = {
        "tracked_errors": 0,
        "approved_retraining_deltas": 0,
        "approved_regression_cases": 0,
    }
    for example_report in example_reports:
        for scenario_report in example_report.get("scenario_reports", []):
            metrics = scenario_report.get("plan", {}).get("metrics", {})
            for key in total_plan_metrics:
                total_plan_metrics[key] += int(metrics.get(key) or 0)
    metrics = {
        "refs": len(_as_string_list(payload.get("refs"))),
        "resolved_refs": len(ref_report["resolved_refs"]),
        "stores": len([table for table in sql_report.get("tables", []) if table in REQUIRED_STORES]),
        "defect_classes": len(_as_string_list(policy.get("required_defect_classes"))),
        "approved_reuse_targets": len(_as_string_list(policy.get("approved_reuse_targets"))),
        "boundary_refs": len(docs_report["boundary_reports"]),
        "runtime_refs": len(runtime_refs["resolved_refs"]),
        "scenarios": sum(int(item.get("scenarios") or 0) for item in example_reports),
        "passing_scenarios": sum(int(item.get("passing_scenarios") or 0) for item in example_reports),
        "registry_entries": len(registry_report.get("registry_report", {}).get("normalized_registry", {}).get("entries", [])),
        "checked_controls": len(REQUIRED_CONTROLS),
        **total_plan_metrics,
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
        "sql": sql_report,
        "adapter": adapter_report,
        "registry": registry_report,
        "docs": docs_report,
        "runtime_refs": runtime_refs,
        "examples": example_reports,
    }


def build_summary(report: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "apiVersion": API_VERSION,
        "kind": "HypergraphErrorImprovementValidationSummary",
        "ok": bool(report.get("ok")),
        "id": report.get("id"),
        "version": report.get("version"),
        "metrics": report.get("metrics", {}),
        "failures": report.get("failures", []),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate NoemaForge hypergraph error improvement contract")
    parser.add_argument("--policy", default=str(SRC_DIR.parent / "configs" / "hypergraph-error-improvement-policy.json"))
    parser.add_argument("--project-root", default=str(SRC_DIR.parent.parent))
    parser.add_argument("--package-root", default=str(SRC_DIR.parent))
    parser.add_argument("--registry", default="")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = validate_hypergraph_error_improvement_policy(
        load_policy(args.policy),
        project_root=Path(args.project_root),
        package_root=Path(args.package_root),
        policy_path=Path(args.policy),
        registry_path=Path(args.registry) if args.registry else None,
    )
    print(json.dumps(build_summary(report) if args.summary else report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
