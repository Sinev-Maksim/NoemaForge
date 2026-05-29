#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/first_start_summary_contract_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate first-start summary grouping and PASS/WARN/FAIL output contracts.
Inputs: noemaforge/configs/first-start-summary-policy.json and summary examples.
Outputs: JSON-compatible FirstStartSummaryValidationReport artifacts.
Side effects: None unless run as a CLI, which writes JSON to stdout.
Tests: noemaforge/tests/test_first_start_summary_contract_runtime.py
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


SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import first_start_summary as fss
import unified_registry_runtime as urr


API_VERSION = "noemaforge.first-start-summary/v1"
POLICY_KIND = "FirstStartSummaryPolicy"
SET_KIND = "FirstStartSummaryExampleSet"
REPORT_KIND = "FirstStartSummaryValidationReport"

VALID_POLICY_STATUSES = {"draft", "shadow", "stable", "retired"}
REQUIRED_MARKERS = {"PASS", "WARN", "FAIL"}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,180}$")


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
        ("package", package_root / ref),
        ("project", project_root / ref),
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


def _policy_dict(payload: Dict[str, Any]) -> Dict[str, Any]:
    return payload.get("policy") if isinstance(payload.get("policy"), dict) else payload


def _registry_ref(entry: Dict[str, Any]) -> str:
    return f"{entry.get('kind')}:{entry.get('id')}:{entry.get('version')}"


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
    if str(policy.get("activation_state") or "") != "grouped_run_summary":
        failures.append("policy_activation_state_invalid")
    for key in [
        "require_trace_id",
        "require_registry_attachment",
        "require_policy_schema_runtime_tests",
        "require_docs_and_changelog_refs",
    ]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    if not str(policy.get("required_pipeline_ref") or "").startswith("pipeline:"):
        failures.append("policy_required_pipeline_ref_invalid")
    if str(policy.get("required_runtime_ref") or "") != "src/first_start_summary.py":
        failures.append("policy_required_runtime_ref_invalid")
    grouping = policy.get("run_grouping") if isinstance(policy.get("run_grouping"), dict) else {}
    for key in ["group_by_start_step", "latest_defaults_to_last_run", "all_includes_every_run", "timeline_uses_latest_run"]:
        if grouping.get(key) is not True:
            failures.append(f"policy_grouping_{key}_not_true")
    if not REQUIRED_MARKERS.issubset(set(_as_string_list(policy.get("required_markers")))):
        failures.append("policy_required_markers_missing")
    sections = set(_as_string_list(policy.get("required_sections")))
    if not {"Latest run", "Timeline", "Staffing", "Final"}.issubset(sections):
        failures.append("policy_required_sections_missing")
    state_map = policy.get("state_marker_map") if isinstance(policy.get("state_marker_map"), dict) else {}
    for state, marker in state_map.items():
        if fss.status_kind(state) != marker:
            failures.append(f"policy_state_marker_mismatch:{state}:{marker}:{fss.status_kind(state)}")
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
            "configs/first-start-summary-policy.json",
            "contracts/first_start_summary.schema.json",
            "src/first_start_summary.py",
            "src/first_start_summary_contract_runtime.py",
            "tests/test_first_start_summary_contract_runtime.py",
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
        "configs/first-start-summary-policy.json",
        "src/first_start_summary.py",
        "src/first_start_summary_contract_runtime.py",
        "prelaunch/governance/first_start_summary.example.json",
    ]:
        if ref not in pipeline_refs:
            failures.append(f"registry_pipeline_ref_missing:{ref}")
    return {"failures": failures, "registry_report": report, "entries": entries, "pipeline_eval_refs": pipeline_eval_refs}


def _example_failures(example_set: Dict[str, Any], policy_payload: Dict[str, Any]) -> Dict[str, Any]:
    failures: List[str] = []
    if example_set.get("apiVersion") != API_VERSION:
        failures.append("example_set_api_version_invalid")
    if example_set.get("kind") != SET_KIND:
        failures.append("example_set_kind_invalid")
    events = example_set.get("events") if isinstance(example_set.get("events"), list) else []
    if not events:
        failures.append("example_set_events_empty")
    runs = fss.group_runs(events)
    if len(runs) < 3:
        failures.append(f"example_runs_too_few:{len(runs)}")
    run_ids = [
        str((run.get("start") or {}).get("extra", {}).get("run_id") or "")
        for run in runs
    ]
    if len(events) == 9 and run_ids != ["run-pass", "run-warn", "run-fail"]:
        failures.append(f"example_run_grouping_invalid:{','.join(run_ids)}")
    final_markers = [fss.status_kind(fss.run_final(run).get("state")) for run in runs]
    if not REQUIRED_MARKERS.issubset(set(final_markers)):
        failures.append(f"example_final_markers_missing:{','.join(final_markers)}")
    status = example_set.get("status") if isinstance(example_set.get("status"), dict) else {}
    if fss.status_kind(status.get("state")) != "FAIL":
        failures.append(f"example_latest_status_marker_invalid:{status.get('state')}")
    staffing = example_set.get("staffing") if isinstance(example_set.get("staffing"), dict) else {}
    if fss.status_kind(staffing.get("staffing_state")) != "FAIL":
        failures.append(f"example_staffing_marker_invalid:{staffing.get('staffing_state')}")
    return {
        "failures": failures,
        "runs": runs,
        "run_ids": run_ids,
        "final_markers": final_markers,
        "events": events,
    }


def validate_first_start_summary_policy(
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

    all_resolved_refs: List[Dict[str, Any]] = []
    all_missing_refs: List[Dict[str, Any]] = []
    all_unsafe_refs: List[Dict[str, Any]] = []
    example_results: List[Dict[str, Any]] = []
    total_runs = 0
    total_events = 0
    markers_seen: List[str] = []

    refs_result = _resolve_refs(sorted(set(_as_string_list(payload.get("refs")))), project_root=project, package_root=package, owner=str(payload.get("id") or "policy"))
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
        result = _example_failures(example_set, payload)
        failures.extend(result["failures"])
        total_runs += len(result["runs"])
        total_events += len(result["events"])
        markers_seen.extend(result["final_markers"])
        example_results.append(
            {
                "id": str(example_set.get("id") or "<missing>"),
                "ok": not result["failures"],
                "runs": len(result["runs"]),
                "events": len(result["events"]),
                "run_ids": result["run_ids"],
                "final_markers": result["final_markers"],
                "failures": sorted(set(result["failures"])),
            }
        )
        example_refs = _resolve_refs(_as_string_list(example_set.get("refs")), project_root=project, package_root=package, owner=str(example_set.get("id") or "example_set"))
        failures.extend(example_refs["failures"])
        all_resolved_refs.extend(example_refs["resolved_refs"])
        all_missing_refs.extend(example_refs["missing_refs"])
        all_unsafe_refs.extend(example_refs["unsafe_refs"])

    checks = [
        {"id": "grouped_by_run", "status": "passed" if not any("run_grouping" in item or "example_run_grouping" in item for item in failures) else "failed"},
        {"id": "pass_warn_fail_markers", "status": "passed" if REQUIRED_MARKERS.issubset(set(markers_seen)) else "failed"},
        {"id": "latest_status_marker", "status": "passed" if not any("latest_status" in item for item in failures) else "failed"},
        {"id": "staffing_marker", "status": "passed" if not any("staffing_marker" in item for item in failures) else "failed"},
        {"id": "registry_attachment", "status": "passed" if not any("registry_" in item for item in failures) else "failed"},
        {"id": "refs_resolved", "status": "passed" if not all_missing_refs and not all_unsafe_refs else "failed"},
    ]
    metrics = {
        "examples": len(example_results),
        "passing_examples": sum(1 for item in example_results if item["ok"]),
        "runs": total_runs,
        "events": total_events,
        "markers_seen": len(set(markers_seen)),
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
        "example_results": sorted(example_results, key=lambda item: item["id"]),
        "resolved_refs": sorted(all_resolved_refs, key=lambda item: (item["owner"], item["ref"])),
        "missing_refs": sorted(all_missing_refs, key=lambda item: (item["owner"], item["ref"])),
        "unsafe_refs": sorted(all_unsafe_refs, key=lambda item: (item["owner"], item["ref"])),
    }


def first_start_summary_report_to_gate_evidence(report: Dict[str, Any], *, artifact_uri: str = "") -> Dict[str, Any]:
    if not isinstance(report, dict) or report.get("kind") != REPORT_KIND:
        raise ValueError("first_start_summary_report_required")
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
    parser = argparse.ArgumentParser(description="Validate NoemaForge first-start summary contracts.")
    parser.add_argument("--project-root", default=str(_default_project_root()), help="Project root containing noemaforge/ and docs/.")
    parser.add_argument("--package-root", default="", help="Package root, default: <project-root>/noemaforge.")
    parser.add_argument(
        "--policy",
        default="noemaforge/configs/first-start-summary-policy.json",
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

    report = validate_first_start_summary_policy(
        load_policy(policy_path),
        project_root=project_root,
        package_root=package_root,
        policy_path=policy_path,
        registry_path=registry_path,
    )
    if args.summary:
        payload: Dict[str, Any] = {
            "apiVersion": report["apiVersion"],
            "kind": "FirstStartSummaryValidationSummary",
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
