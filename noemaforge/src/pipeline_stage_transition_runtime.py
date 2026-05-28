#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/pipeline_stage_transition_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate deterministic NoemaForge pipeline stage transition commands.
Inputs: pipeline-stage-transition policy, examples, unified registry and pipeline runtime.
Outputs: JSON validation reports and summaries.
Side effects: Writes bounded offline scenario state under project trash only.
Tests: noemaforge/tests/test_pipeline_stage_transition_runtime.py, QA and performance tests.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import io
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SRC_DIR = Path(__file__).resolve().parent
PACKAGE_ROOT = SRC_DIR.parent
PROJECT_ROOT = PACKAGE_ROOT.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import pipeline_runtime  # noqa: E402

API_VERSION = "noemaforge.pipeline.stage-transition/v1"
POLICY_KIND = "PipelineStageTransitionPolicy"
EXAMPLE_KIND = "PipelineStageTransitionExampleSet"
REPORT_KIND = "PipelineStageTransitionValidationReport"
VALID_STATUSES = {"draft", "shadow", "active", "retired"}
SAFE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
REQUIRED_COMMANDS = ["run", "approve", "advance", "pause", "resume", "fail", "event-log", "show"]
REQUIRED_EVENT_TYPES = ["pipeline_created", "pipeline_approved", "pipeline_paused", "pipeline_resumed", "pipeline_stage_updated", "pipeline_failed"]
REQUIRED_OUTPUTS = ["approved_status", "paused_status", "resumed_status", "advanced_stage", "failed_status", "event_log_evidence", "invalid_stage_rejected"]
REQUIRED_CONTROLS = ["stage_validation_required", "event_log_required", "terminal_fail_state_required", "deterministic_state_dir_required", "no_live_host_required", "no_llm_autostart"]
REQUIRED_DOC_REFS = {
    "noemaforge/docs/README.md",
    "noemaforge/docs/TODO.md",
    "noemaforge/docs/reference/PROJECT_CONTEXT.md",
    "noemaforge/docs/backlog/ROADMAP_AND_TODO.md",
    "noemaforge/docs/history/CHANGELOG.md",
}
_SCENARIO_COUNTER = 0


def _nowz() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _as_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, (str, int, float))]


def _policy(payload: Dict[str, Any]) -> Dict[str, Any]:
    value = payload.get("policy")
    return value if isinstance(value, dict) else {}


def _resolve_ref(ref: str, *, project_root: Path = PROJECT_ROOT, package_root: Path = PACKAGE_ROOT) -> Optional[Path]:
    candidates = [
        project_root / ref,
        package_root / ref,
        project_root / ref.replace("/", os.sep),
        package_root / ref.replace("/", os.sep),
    ]
    if ref.startswith("noemaforge/"):
        candidates.append(project_root / ref)
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return None


def _call_pipeline(args: List[str], *, state: Path, root: Path = PACKAGE_ROOT) -> Tuple[int, Dict[str, Any], str, str]:
    argv = ["--root", str(root), "--state", str(state), *args]
    out = io.StringIO()
    err = io.StringIO()
    code = 0
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            pipeline_runtime.main(argv)
        except SystemExit as exc:
            code = int(exc.code) if isinstance(exc.code, int) else 1
            if not isinstance(exc.code, int) and exc.code:
                err.write(str(exc.code))
    stdout = out.getvalue().strip()
    stderr = err.getvalue().strip()
    parsed: Dict[str, Any] = {}
    if stdout:
        try:
            parsed = json.loads(stdout)
        except json.JSONDecodeError:
            parsed = {"raw": stdout}
    return code, parsed, stdout, stderr


def _scenario_dir(project_root: Path = PROJECT_ROOT) -> Path:
    global _SCENARIO_COUNTER
    _SCENARIO_COUNTER += 1
    path = project_root / "trash" / "p" / f"{_SCENARIO_COUNTER:x}"
    while path.exists():
        _SCENARIO_COUNTER += 1
        path = project_root / "trash" / "p" / f"{_SCENARIO_COUNTER:x}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _policy_failures(payload: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    policy = _policy(payload)
    if payload.get("apiVersion") != API_VERSION:
        failures.append("policy_api_version_invalid")
    if payload.get("kind") != POLICY_KIND:
        failures.append("policy_kind_invalid")
    if payload.get("id") != "pipeline-stage-transition-core":
        failures.append("policy_id_invalid")
    if str(payload.get("status") or "") not in VALID_STATUSES:
        failures.append("policy_status_invalid")
    if policy.get("mode") != "offline_contract":
        failures.append("policy_mode_not_offline_contract")
    if policy.get("activation_state") != "deterministic_stage_transition_commands":
        failures.append("policy_activation_state_invalid")
    for key in ["require_registry_attachment", "require_docs_and_changelog_refs"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    commands = set(_as_list(policy.get("required_pipeline_commands")))
    for command in REQUIRED_COMMANDS:
        if command not in commands:
            failures.append(f"policy_required_command_missing:{command}")
    events = set(_as_list(policy.get("required_event_types")))
    for event_type in REQUIRED_EVENT_TYPES:
        if event_type not in events:
            failures.append(f"policy_required_event_missing:{event_type}")
    outputs = set(_as_list(policy.get("required_outputs")))
    for output in REQUIRED_OUTPUTS:
        if output not in outputs:
            failures.append(f"policy_required_output_missing:{output}")
    controls = policy.get("controls") if isinstance(policy.get("controls"), dict) else {}
    for control in REQUIRED_CONTROLS:
        if controls.get(control) is not True:
            failures.append(f"policy_control_{control}_not_true")
    refs = policy.get("required_refs") if isinstance(policy.get("required_refs"), dict) else {}
    for key in ["cli", "runtime", "contract_runtime"]:
        if not str(refs.get(key) or "").strip():
            failures.append(f"policy_required_ref_missing:{key}")
    example_sets = _as_list(policy.get("required_example_sets"))
    if not example_sets:
        failures.append("policy_required_example_sets_empty")
    payload_refs = set(_as_list(payload.get("refs")))
    for ref in REQUIRED_DOC_REFS - payload_refs:
        failures.append(f"policy_canonical_doc_ref_missing:{ref}")
    return failures


def _static_failures(payload: Dict[str, Any], *, project_root: Path = PROJECT_ROOT, package_root: Path = PACKAGE_ROOT) -> Dict[str, Any]:
    policy = _policy(payload)
    refs = policy.get("required_refs") if isinstance(policy.get("required_refs"), dict) else {}
    resolved = {key: _resolve_ref(str(ref), project_root=project_root, package_root=package_root) for key, ref in refs.items()}
    failures: List[str] = []
    for key in ["cli", "runtime", "contract_runtime"]:
        if not resolved.get(key):
            failures.append(f"static_required_ref_unresolved:{key}:{refs.get(key)}")
    runtime_text = resolved["runtime"].read_text(encoding="utf-8", errors="replace") if resolved.get("runtime") else ""
    cli_text = resolved["cli"].read_text(encoding="utf-8", errors="replace") if resolved.get("cli") else ""
    for command in ["advance", "pause", "resume", "fail", "approve"]:
        if f'sub.add_parser("{command}")' not in runtime_text:
            failures.append(f"runtime_command_parser_missing:{command}")
        if command not in cli_text:
            failures.append(f"cli_help_command_missing:{command}")
    for token in ["assert_stage(run, str(stage))", "pipeline_paused", "pipeline_resumed", "pipeline_failed"]:
        if token not in runtime_text:
            failures.append(f"runtime_stage_transition_token_missing:{token}")
    return {"failures": failures, "resolved": {key: str(value) if value else "" for key, value in resolved.items()}}


def _registry_ref(entry: Dict[str, Any]) -> str:
    return f"{entry.get('kind')}:{entry.get('id')}:{entry.get('version')}"


def _registry_failures(payload: Dict[str, Any], *, project_root: Path = PROJECT_ROOT, package_root: Path = PACKAGE_ROOT) -> Dict[str, Any]:
    registry_path = package_root / "configs" / "unified-registry.json"
    registry = load_json(registry_path)
    entries = {_registry_ref(entry): entry for entry in registry.get("entries", []) if isinstance(entry, dict)}
    eval_ref = f"eval-pack:{payload.get('id')}:{payload.get('version')}"
    policy = _policy(payload)
    pipeline_ref = str(policy.get("required_pipeline_ref") or "")
    failures: List[str] = []
    eval_entry = entries.get(eval_ref)
    if not eval_entry:
        failures.append(f"registry_eval_pack_missing:{eval_ref}")
    else:
        refs = set(_as_list(eval_entry.get("refs")))
        for ref in [
            "configs/pipeline-stage-transition-policy.json",
            "contracts/pipeline_stage_transition.schema.json",
            "src/pipeline_stage_transition_runtime.py",
            "src/pipeline_runtime.py",
            "tests/test_pipeline_stage_transition_runtime.py",
            "tests/test_pipeline_stage_transition_qa.py",
            "tests/test_pipeline_stage_transition_performance.py",
        ]:
            if ref not in refs:
                failures.append(f"registry_eval_pack_ref_missing:{eval_ref}:{ref}")
    pipeline_entry = entries.get(pipeline_ref)
    pipeline_eval_refs: List[str] = []
    pipeline_refs: List[str] = []
    if not pipeline_entry:
        failures.append(f"registry_pipeline_missing:{pipeline_ref}")
    else:
        pipeline_eval_refs = _as_list(pipeline_entry.get("eval_pack_refs"))
        pipeline_refs = _as_list(pipeline_entry.get("refs"))
    if eval_ref not in pipeline_eval_refs:
        failures.append(f"registry_pipeline_eval_pack_missing:{eval_ref}")
    for ref in [
        "configs/pipeline-stage-transition-policy.json",
        "contracts/pipeline_stage_transition.schema.json",
        "src/pipeline_stage_transition_runtime.py",
        "prelaunch/governance/pipeline_stage_transition.example.json",
    ]:
        if ref not in pipeline_refs:
            failures.append(f"registry_pipeline_ref_missing:{ref}")
    return {"failures": failures, "eval_ref": eval_ref, "pipeline_ref": pipeline_ref, "pipeline_eval_refs": pipeline_eval_refs, "pipeline_refs": pipeline_refs}


def _docs_failures(payload: Dict[str, Any], *, project_root: Path = PROJECT_ROOT) -> List[str]:
    failures: List[str] = []
    doc_paths = [
        project_root / "noemaforge" / "docs" / "README.md",
        project_root / "noemaforge" / "docs" / "TODO.md",
        project_root / "noemaforge" / "docs" / "reference" / "PROJECT_CONTEXT.md",
        project_root / "noemaforge" / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
        project_root / "noemaforge" / "docs" / "history" / "CHANGELOG.md",
    ]
    for path in doc_paths:
        text = path.read_text(encoding="utf-8", errors="replace")
        if "pipeline-stage-transition-core" not in text:
            failures.append(f"doc_missing_pipeline_stage_transition_core:{path.relative_to(project_root).as_posix()}")
    todo_text = (project_root / "noemaforge" / "docs" / "TODO.md").read_text(encoding="utf-8", errors="replace")
    backlog_text = (project_root / "noemaforge" / "docs" / "backlog" / "ROADMAP_AND_TODO.md").read_text(encoding="utf-8", errors="replace")
    closed_line = "[x] Add stage transition commands: `advance`, `pause`, `resume`, `fail`, `approve`."
    if closed_line not in todo_text:
        failures.append("todo_closed_transition_item_missing")
    if closed_line not in backlog_text:
        failures.append("backlog_closed_transition_item_missing")
    return failures


def _example_failures(example: Dict[str, Any], *, project_root: Path = PROJECT_ROOT, package_root: Path = PACKAGE_ROOT) -> Dict[str, Any]:
    failures: List[str] = []
    scenario_reports: List[Dict[str, Any]] = []
    if example.get("apiVersion") != API_VERSION:
        failures.append("example_api_version_invalid")
    if example.get("kind") != EXAMPLE_KIND:
        failures.append("example_kind_invalid")
    scenarios = example.get("scenarios") if isinstance(example.get("scenarios"), list) else []
    if not scenarios:
        failures.append("example_scenarios_empty")
        return {"failures": failures, "scenario_reports": scenario_reports, "scenarios": 0}
    work_dir = _scenario_dir(project_root)
    for raw in scenarios:
        scenario = raw if isinstance(raw, dict) else {}
        sid = str(scenario.get("id") or "")
        local: List[str] = []
        if not SAFE_ID_RE.match(sid):
            local.append("scenario_id_invalid")
        if not str(scenario.get("trace_id") or "").startswith("trace:"):
            local.append("scenario_trace_id_missing")
        state = work_dir / "s"
        run_id = str(scenario.get("run_id") or "pst_life")
        advance_stage = str(scenario.get("advance_stage") or "status_check")
        invalid_stage = str(scenario.get("invalid_stage") or "missing_stage")
        commands_seen: List[str] = []
        events_seen: List[str] = []
        if not local:
            code, created, _, _ = _call_pipeline(["run", str(scenario.get("pipeline") or "public_mwp"), "--task-id", str(scenario.get("task_id") or "stage-transition"), "--request", "offline stage transition validation", "--run-id", run_id], state=state, root=package_root)
            commands_seen.append("run")
            if code != 0 or created.get("run_id") != run_id:
                local.append(f"scenario_run_failed:{code}")
            code, approved, _, _ = _call_pipeline(["approve", run_id], state=state, root=package_root)
            commands_seen.append("approve")
            if code != 0 or approved.get("status") != "approved":
                local.append("scenario_approve_status_missing")
            code, paused, _, _ = _call_pipeline(["pause", run_id, "--stage", "orient"], state=state, root=package_root)
            commands_seen.append("pause")
            if code != 0 or paused.get("status") != "paused" or paused.get("stage") != "orient":
                local.append("scenario_pause_status_missing")
            code, resumed, _, _ = _call_pipeline(["resume", run_id, "--stage", "orient"], state=state, root=package_root)
            commands_seen.append("resume")
            if code != 0 or resumed.get("status") != "in_progress" or resumed.get("stage") != "orient":
                local.append("scenario_resume_status_missing")
            code, advanced, _, _ = _call_pipeline(["advance", run_id, "--stage", advance_stage, "--status", "in_progress"], state=state, root=package_root)
            commands_seen.append("advance")
            if code != 0 or advanced.get("stage") != advance_stage:
                local.append("scenario_advance_stage_missing")
            code, failed, _, _ = _call_pipeline(["fail", run_id, "--stage", advance_stage, "--reason", "bounded regression fixture"], state=state, root=package_root)
            commands_seen.append("fail")
            if code != 0 or failed.get("status") != "failed" or failed.get("stage") != advance_stage:
                local.append("scenario_fail_status_missing")
            bad_code, _, _, bad_err = _call_pipeline(["pause", run_id, "--stage", invalid_stage], state=state, root=package_root)
            if bad_code == 0 or "unknown stage" not in bad_err:
                local.append("scenario_invalid_stage_not_rejected")
            code, event_log, _, _ = _call_pipeline(["event-log", "--run-id", run_id, "--json", "--limit", "20"], state=state, root=package_root)
            commands_seen.append("event-log")
            items = event_log.get("items") if isinstance(event_log.get("items"), list) else []
            events_seen = [str(item.get("event_type") or "") for item in items if isinstance(item, dict)]
            if code != 0 or not events_seen:
                local.append("scenario_event_log_missing")
            for event_type in _as_list(scenario.get("expected_event_types")):
                if event_type not in events_seen:
                    local.append(f"scenario_event_missing:{event_type}")
            for command in _as_list(scenario.get("expected_commands")):
                if command not in commands_seen:
                    local.append(f"scenario_command_missing:{command}")
            expected_outputs = set(_as_list(scenario.get("expected_outputs")))
            output_checks = {
                "approved_status": approved.get("status") == "approved",
                "paused_status": paused.get("status") == "paused",
                "resumed_status": resumed.get("status") == "in_progress",
                "advanced_stage": advanced.get("stage") == advance_stage,
                "failed_status": failed.get("status") == "failed",
                "event_log_evidence": bool(events_seen),
                "invalid_stage_rejected": bad_code != 0,
            }
            for output in sorted(expected_outputs):
                if output not in output_checks or output_checks[output] is not True:
                    local.append(f"scenario_output_missing:{output}")
        scenario_reports.append({"id": sid, "ok": not local, "failures": local, "commands_seen": commands_seen, "events_seen": events_seen, "state_dir": str(state)})
        failures.extend([f"scenario:{sid}:{item}" for item in local])
    return {"failures": failures, "scenario_reports": scenario_reports, "scenarios": len(scenarios), "work_dir": str(work_dir)}


def validate_policy(policy_path: Path, *, project_root: Path = PROJECT_ROOT, package_root: Path = PACKAGE_ROOT) -> Dict[str, Any]:
    payload = load_json(policy_path)
    failures: List[str] = []
    failures.extend(_policy_failures(payload))
    static = _static_failures(payload, project_root=project_root, package_root=package_root)
    failures.extend(static["failures"])
    registry = _registry_failures(payload, project_root=project_root, package_root=package_root)
    failures.extend(registry["failures"])
    failures.extend(_docs_failures(payload, project_root=project_root))
    example_reports: List[Dict[str, Any]] = []
    for ref in _as_list(_policy(payload).get("required_example_sets")):
        path = _resolve_ref(ref, project_root=project_root, package_root=package_root)
        if not path:
            failures.append(f"example_ref_missing:{ref}")
            continue
        report = _example_failures(load_json(path), project_root=project_root, package_root=package_root)
        failures.extend(report["failures"])
        example_reports.append(report)
    metrics = {
        "required_commands": len(REQUIRED_COMMANDS),
        "required_event_types": len(REQUIRED_EVENT_TYPES),
        "required_outputs": len(REQUIRED_OUTPUTS),
        "example_sets": len(example_reports),
        "scenario_count": sum(int(report.get("scenarios") or 0) for report in example_reports),
    }
    return {
        "apiVersion": API_VERSION,
        "kind": REPORT_KIND,
        "id": str(payload.get("id") or ""),
        "version": str(payload.get("version") or ""),
        "validated_at": _nowz(),
        "ok": not failures,
        "failures": failures,
        "metrics": metrics,
        "static": static,
        "registry": registry,
        "examples": example_reports,
    }


def build_summary(report: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "apiVersion": API_VERSION,
        "kind": "PipelineStageTransitionValidationSummary",
        "ok": bool(report.get("ok")),
        "id": report.get("id"),
        "version": report.get("version"),
        "metrics": report.get("metrics", {}),
        "failures": report.get("failures", []),
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Validate pipeline stage transition commands.")
    parser.add_argument("--policy", default=str(PACKAGE_ROOT / "configs" / "pipeline-stage-transition-policy.json"))
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(argv)
    report = validate_policy(Path(args.policy).resolve())
    print(json.dumps(build_summary(report) if args.summary else report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
