#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/executor_stage_worker_runtime.py
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate contract-driven executor-step stage worker behavior.
Inputs: noemaforge/configs/executor-stage-worker-policy.json and executor-stage-worker examples.
Outputs: JSON-compatible ExecutorStageWorkerValidationReport artifacts.
Side effects: Temporary files only during example validation; CLI writes JSON to stdout.
Tests: noemaforge/tests/test_executor_stage_worker_runtime.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import argparse
import contextlib
import gc
import io
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Sequence


SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import pipeline_runtime as prt
import unified_registry_runtime as urr


API_VERSION = "noemaforge.pipeline.executor-stage-worker/v1"
POLICY_KIND = "ExecutorStageWorkerPolicy"
SET_KIND = "ExecutorStageWorkerExampleSet"
REPORT_KIND = "ExecutorStageWorkerValidationReport"

VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
REQUIRED_CONTROLS = {
    "context_packet_required",
    "non_placeholder_output_required",
    "contract_matching_artifact_required",
    "apply_advances_stage_only_when_ready",
    "wait_event_when_not_ready",
    "degraded_mutation_guard",
    "no_live_host_required",
    "no_llm_autostart",
}
ALLOWED_DOC_REF_PREFIXES = ("docs/", "noemaforge/docs/")
PROHIBITED_DOC_REFS = {"README.md", "TODO.md", "noemaforge/TODO.md"}
REQUIRED_CANONICAL_DOC_REFS = {
    "docs/README.md",
    "docs/TODO.md",
    "docs/reference/PROJECT_CONTEXT.md",
    "docs/backlog/ROADMAP_AND_TODO.md",
    "docs/history/CHANGELOG.md",
}
REQUIRED_RUNTIME_TOKENS = [
    "def executor_step_cmd",
    "_pipeline_stage_contract",
    "worker_contract_version",
    "stage_contract",
    "contract_artifact_count",
    "pipeline_executor_step",
    "pipeline_executor_wait",
    "guard_degraded_mutation(\"pipeline executor-step --apply\"",
    'sub.add_parser("executor-step")',
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


def _call_pipeline(argv: Sequence[str]) -> tuple[int, Dict[str, Any]]:
    stdout = io.StringIO()
    code = 0
    with contextlib.redirect_stdout(stdout):
        try:
            prt.main(list(argv))
        except SystemExit as exc:
            code = int(exc.code or 0)
    gc.collect()
    raw = stdout.getvalue().strip()
    payload = json.loads(raw) if raw else {}
    return code, payload


def _write_ready_stage_output(path: Path, stage: str) -> None:
    path.write_text(
        f"# {stage}\n\nDecision: stage evidence is complete.\n\nRisk: low; synthetic offline validation only.\n\nNext handoff: advance to the next stage.\n\nDetails: contract-driven executor-step validation.\n",
        encoding="utf-8",
    )


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
    if str(policy.get("activation_state") or "") != "contract_driven_executor_step":
        failures.append("policy_activation_state_invalid")
    for key in ["require_trace_id", "require_registry_attachment", "require_docs_and_changelog_refs"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    for command in ["run", "artifact add", "executor-step", "event-log"]:
        if command not in _as_string_list(policy.get("required_pipeline_commands")):
            failures.append(f"policy_required_command_missing:{command}")
    for output in ["stage_contract", "contract_artifact_gate", "pipeline_executor_step_event", "pipeline_executor_wait_event"]:
        if output not in _as_string_list(policy.get("required_outputs")):
            failures.append(f"policy_required_output_missing:{output}")
    controls = policy.get("controls") if isinstance(policy.get("controls"), dict) else {}
    for key in REQUIRED_CONTROLS:
        if controls.get(key) is not True:
            failures.append(f"policy_control_{key}_not_true")
    refs = policy.get("required_refs") if isinstance(policy.get("required_refs"), dict) else {}
    for key in ["cli", "runtime", "contract_runtime"]:
        if not str(refs.get(key) or "").strip():
            failures.append(f"policy_required_ref_missing:{key}")
    payload_refs = set(_as_string_list(payload.get("refs")))
    for ref in sorted(REQUIRED_CANONICAL_DOC_REFS - payload_refs):
        failures.append(f"policy_canonical_doc_ref_missing:{ref}")
    for ref in sorted(payload_refs & PROHIBITED_DOC_REFS):
        failures.append(f"policy_legacy_doc_ref_forbidden:{ref}")
    for ref in sorted(item for item in payload_refs if item.endswith(".md")):
        if not ref.startswith(ALLOWED_DOC_REF_PREFIXES):
            failures.append(f"policy_doc_ref_not_canonical:{ref}")
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
            "configs/executor-stage-worker-policy.json",
            "contracts/executor_stage_worker.schema.json",
            "src/pipeline_runtime.py",
            "src/executor_stage_worker_runtime.py",
            "tests/test_executor_stage_worker_runtime.py",
            "tests/test_executor_stage_worker_qa.py",
            "tests/test_executor_stage_worker_performance.py",
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
        "configs/executor-stage-worker-policy.json",
        "contracts/executor_stage_worker.schema.json",
        "src/executor_stage_worker_runtime.py",
        "prelaunch/governance/executor_stage_worker.example.json",
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
    if "executor-step" not in cli_text:
        failures.append("cli_help_executor_step_missing")
    return {"failures": failures, "resolved_required_refs": resolved}


def _example_failures(example: Dict[str, Any], *, package_root: Path) -> Dict[str, Any]:
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
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            state = tmp / "state"
            run_id = f"run_{sid.replace('-', '_')}"
            stage = str(scenario.get("stage") or "orient")
            code, created = _call_pipeline([
                "run",
                str(scenario.get("pipeline_id") or "public_mwp"),
                "--task-id",
                str(scenario.get("task_id") or sid),
                "--run-id",
                run_id,
                "--request",
                "executor stage worker contract validation",
                "--trace-id",
                str(scenario.get("trace_id") or ""),
                "--state",
                str(state),
                "--root",
                str(package_root),
            ])
            if code != 0 or created.get("ok") is not True:
                local_failures.append(f"scenario_run_failed:{code}")
            wait_code, wait = _call_pipeline(["executor-step", run_id, "--apply", "--state", str(state), "--root", str(package_root)])
            if wait_code != 0 or wait.get("ready") is not False or wait.get("action") != "wait":
                local_failures.append("scenario_unready_wait_failed")
            if wait.get("worker_contract_version") != API_VERSION:
                local_failures.append("scenario_worker_contract_version_missing")
            contract = wait.get("stage_contract") if isinstance(wait.get("stage_contract"), dict) else {}
            artifact_type = str(scenario.get("artifact_type") or "note")
            if artifact_type not in _as_string_list(contract.get("artifact_types")):
                local_failures.append(f"scenario_artifact_type_not_allowed:{artifact_type}")
            run_dir = Path(str(created.get("run_dir") or ""))
            output = run_dir / "outputs" / f"{stage}.md"
            _write_ready_stage_output(output, stage)
            artifact_code, artifact = _call_pipeline([
                "artifact",
                "add",
                run_id,
                "--stage",
                stage,
                "--type",
                artifact_type,
                "--path",
                str(output),
                "--status",
                "draft",
                "--state",
                str(state),
                "--root",
                str(package_root),
            ])
            if artifact_code != 0 or artifact.get("ok") is not True:
                local_failures.append(f"scenario_artifact_failed:{artifact_code}")
            apply_code, applied = _call_pipeline(["executor-step", run_id, "--apply", "--state", str(state), "--root", str(package_root)])
            if apply_code != 0 or applied.get("ready") is not True or applied.get("action") != "advance":
                local_failures.append("scenario_ready_advance_failed")
            if applied.get("current_stage") != scenario.get("expected_next_stage"):
                local_failures.append(f"scenario_next_stage_mismatch:{applied.get('current_stage')}")
            events_code, events = _call_pipeline(["event-log", "--run-id", run_id, "--json", "--state", str(state), "--root", str(package_root)])
            event_types = [str(item.get("event_type") or "") for item in events.get("items", [])] if events_code == 0 else []
            if "pipeline_executor_wait" not in event_types:
                local_failures.append("scenario_wait_event_missing")
            if "pipeline_executor_step" not in event_types:
                local_failures.append("scenario_step_event_missing")
            for output_name in _as_string_list(scenario.get("expected_outputs")):
                if output_name == "stage_contract" and not isinstance(applied.get("stage_contract"), dict):
                    local_failures.append("scenario_output_missing:stage_contract")
                elif output_name == "contract_artifact_gate" and int(applied.get("contract_artifact_count") or 0) < 1:
                    local_failures.append("scenario_output_missing:contract_artifact_gate")
                elif output_name == "pipeline_executor_step_event" and "pipeline_executor_step" not in event_types:
                    local_failures.append("scenario_output_missing:pipeline_executor_step_event")
                elif output_name == "pipeline_executor_wait_event" and "pipeline_executor_wait" not in event_types:
                    local_failures.append("scenario_output_missing:pipeline_executor_wait_event")
        scenario_reports.append({"id": sid, "ok": not local_failures, "failures": local_failures})
        if local_failures:
            failures.extend([f"scenario:{sid}:{item}" for item in local_failures])
        else:
            passing_scenarios += 1
    return {"failures": failures, "scenario_reports": scenario_reports, "scenarios": len(scenarios), "passing_scenarios": passing_scenarios}


def validate_executor_stage_worker_policy(
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
    policy = _policy_dict(payload)
    for ref in _as_string_list(policy.get("required_example_sets")):
        resolved = _resolve_ref(ref, project_root=project, package_root=package)
        if not resolved.get("ok"):
            failures.append(f"example_ref_missing:{ref}")
            continue
        example_report = _example_failures(load_example_set(resolved["path"]), package_root=package)
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


def executor_stage_worker_report_to_gate_evidence(report: Dict[str, Any], *, artifact_uri: str = "") -> Dict[str, Any]:
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
    return {"apiVersion": API_VERSION, "kind": "ExecutorStageWorkerValidationSummary", "ok": bool(report.get("ok")), "id": report.get("id"), "version": report.get("version"), "metrics": report.get("metrics", {}), "failures": report.get("failures", [])}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate NoemaForge contract-driven executor stage worker")
    parser.add_argument("--policy", default=str(SRC_DIR.parent / "configs" / "executor-stage-worker-policy.json"))
    parser.add_argument("--project-root", default=str(SRC_DIR.parent.parent))
    parser.add_argument("--package-root", default=str(SRC_DIR.parent))
    parser.add_argument("--registry", default="")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = validate_executor_stage_worker_policy(load_policy(args.policy), project_root=Path(args.project_root), package_root=Path(args.package_root), policy_path=Path(args.policy), registry_path=Path(args.registry) if args.registry else None)
    print(json.dumps(build_summary(report) if args.summary else report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
