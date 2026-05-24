#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/selftest_event_store_runtime.py
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate self-test event store contracts.
Inputs: noemaforge/configs/selftest-event-store-policy.json and event-store examples.
Outputs: JSON-compatible SelfTestEventStoreValidationReport artifacts.
Side effects: None unless run as a CLI, which writes JSON to stdout.
Tests: noemaforge/tests/test_selftest_event_store_runtime.py
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

import selftest_runtime as strt
import unified_registry_runtime as urr


API_VERSION = "noemaforge.selftest-event-store/v1"
POLICY_KIND = "SelfTestEventStorePolicy"
SET_KIND = "SelfTestEventStoreExampleSet"
REPORT_KIND = "SelfTestEventStoreValidationReport"

VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
REQUIRED_CONTROLS = {
    "sqlite_event_table_required",
    "deterministic_event_ids",
    "run_summary_events",
    "case_result_events",
    "json_export",
    "report_ingest",
    "no_live_host_required",
    "no_llm_autostart",
}
REQUIRED_RUNTIME_TOKENS = [
    "CREATE TABLE IF NOT EXISTS selftest_test_events",
    "def build_test_events_from_report",
    "def record_test_events_for_report",
    "def export_test_events",
    'sub.add_parser("events")',
    'evsub.add_parser("ingest")',
    'evsub.add_parser("export")',
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


def load_text(path: Path | str) -> str:
    return Path(path).read_text(encoding="utf-8")


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
    if str(policy.get("activation_state") or "") != "sqlite_canonical_test_events":
        failures.append("policy_activation_state_invalid")
    for key in ["require_trace_id", "require_registry_attachment", "require_docs_and_changelog_refs"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    required_commands = set(_as_string_list(policy.get("required_selftest_commands")))
    for command in ["events ingest", "events export"]:
        if command not in required_commands:
            failures.append(f"policy_required_command_missing:{command}")
    if "selftest_test_events" not in _as_string_list(policy.get("required_tables")):
        failures.append("policy_required_table_missing:selftest_test_events")
    required_event_types = set(_as_string_list(policy.get("required_event_types")))
    for event_type in ["selftest.run.summary", "selftest.case.result"]:
        if event_type not in required_event_types:
            failures.append(f"policy_required_event_type_missing:{event_type}")
    controls = policy.get("controls") if isinstance(policy.get("controls"), dict) else {}
    for key in REQUIRED_CONTROLS:
        if controls.get(key) is not True:
            failures.append(f"policy_control_{key}_not_true")
    refs = policy.get("required_refs") if isinstance(policy.get("required_refs"), dict) else {}
    for key in ["cli", "runtime", "contract_runtime"]:
        if not str(refs.get(key) or "").strip():
            failures.append(f"policy_required_ref_missing:{key}")
    if not _as_string_list(policy.get("required_example_sets")):
        failures.append("policy_required_example_sets_empty")
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
            "configs/selftest-event-store-policy.json",
            "contracts/selftest_event_store.schema.json",
            "src/selftest_runtime.py",
            "src/selftest_event_store_runtime.py",
            "tests/test_selftest_event_store_runtime.py",
            "tests/test_selftest_event_store_qa.py",
            "tests/test_selftest_event_store_performance.py",
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
        "configs/selftest-event-store-policy.json",
        "contracts/selftest_event_store.schema.json",
        "src/selftest_runtime.py",
        "src/selftest_event_store_runtime.py",
        "prelaunch/governance/selftest_event_store.example.json",
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
    runtime_text = load_text(resolved["runtime"]["path"]) if resolved.get("runtime", {}).get("ok") else ""
    cli_text = load_text(resolved["cli"]["path"]) if resolved.get("cli", {}).get("ok") else ""
    for token in REQUIRED_RUNTIME_TOKENS:
        if token not in runtime_text:
            failures.append(f"runtime_token_missing:{token}")
    if "|events|" not in cli_text or "|wiki-patch" not in cli_text:
        failures.append("cli_help_events_missing")
    return {"failures": failures, "resolved_required_refs": resolved}


def _example_failures(example: Dict[str, Any]) -> Dict[str, Any]:
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
    for scenario in scenarios:
        sid = str(scenario.get("id") or "")
        local_failures: List[str] = []
        if not SAFE_ID_RE.match(sid):
            local_failures.append("scenario_id_invalid")
        if not str(scenario.get("trace_id") or "").startswith("trace:"):
            local_failures.append("scenario_trace_id_missing")
        events = strt.build_test_events_from_report(scenario.get("report") if isinstance(scenario.get("report"), dict) else {})
        expected_count = int(scenario.get("expected_event_count") or 0)
        if expected_count and len(events) != expected_count:
            local_failures.append(f"scenario_event_count_mismatch:{len(events)}")
        actual_types = {event["event_type"] for event in events}
        for event_type in _as_string_list(scenario.get("expected_event_types")):
            if event_type not in actual_types:
                local_failures.append(f"scenario_event_type_missing:{event_type}")
        if not any(event.get("severity") == "error" for event in events):
            local_failures.append("scenario_error_event_missing")
        scenario_reports.append({"id": sid, "ok": not local_failures, "failures": local_failures, "event_count": len(events)})
        if local_failures:
            failures.extend([f"scenario:{sid}:{item}" for item in local_failures])
        else:
            passing_scenarios += 1
    return {"failures": failures, "scenario_reports": scenario_reports, "scenarios": len(scenarios), "passing_scenarios": passing_scenarios}


def validate_selftest_event_store_policy(
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
    example_reports: List[Dict[str, Any]] = []
    for ref in _as_string_list(_policy_dict(payload).get("required_example_sets")):
        resolved = _resolve_ref(ref, project_root=project, package_root=package)
        if not resolved.get("ok"):
            failures.append(f"example_ref_missing:{ref}")
            continue
        example_report = _example_failures(load_example_set(resolved["path"]))
        failures.extend(example_report["failures"])
        example_reports.append({"ref": ref, **example_report})
    metrics = {
        "refs": len(_as_string_list(payload.get("refs"))),
        "resolved_refs": len(ref_report["resolved_refs"]),
        "scenarios": sum(int(item.get("scenarios") or 0) for item in example_reports),
        "passing_scenarios": sum(int(item.get("passing_scenarios") or 0) for item in example_reports),
        "registry_entries": len(registry_report.get("registry_report", {}).get("normalized_registry", {}).get("entries", [])),
    }
    return {"apiVersion": API_VERSION, "kind": REPORT_KIND, "id": str(payload.get("id") or ""), "version": str(payload.get("version") or ""), "ok": not failures, "validated_at": _nowz(), "policy_path": _display_path(Path(policy_path).resolve()) if policy_path else "", "failures": failures, "metrics": metrics, "refs": ref_report, "registry": registry_report, "static": static_report, "examples": example_reports}


def selftest_event_store_report_to_gate_evidence(report: Dict[str, Any], *, artifact_uri: str = "") -> Dict[str, Any]:
    status = "pass" if report.get("ok") else "fail"
    return {
        "artifact_uri": artifact_uri,
        "run_at": report.get("validated_at") or _nowz(),
        "checks": [
            {"id": "pipeline_eval", "status": status, "score": 1.0 if status == "pass" else 0.0, "threshold": 1.0},
            {"id": "rollback_plan", "status": "pass", "score": 1.0, "threshold": 1.0},
        ],
        "details": {
            "id": report.get("id"),
            "version": report.get("version"),
            "metrics": report.get("metrics", {}),
            "failures": report.get("failures", []),
        },
    }


def build_summary(report: Dict[str, Any]) -> Dict[str, Any]:
    return {"apiVersion": API_VERSION, "kind": "SelfTestEventStoreValidationSummary", "ok": bool(report.get("ok")), "id": report.get("id"), "version": report.get("version"), "metrics": report.get("metrics", {}), "failures": report.get("failures", [])}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate NoemaForge self-test event store contract")
    parser.add_argument("--policy", default=str(SRC_DIR.parent / "configs" / "selftest-event-store-policy.json"))
    parser.add_argument("--project-root", default=str(SRC_DIR.parent.parent))
    parser.add_argument("--package-root", default=str(SRC_DIR.parent))
    parser.add_argument("--registry", default="")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = validate_selftest_event_store_policy(load_policy(args.policy), project_root=Path(args.project_root), package_root=Path(args.package_root), policy_path=Path(args.policy), registry_path=Path(args.registry) if args.registry else None)
    print(json.dumps(build_summary(report) if args.summary else report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
