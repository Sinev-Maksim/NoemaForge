#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/dev_bounded_loop_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate bounded Dev Team loops with checkpoint and stop handling.
Inputs: dev-bounded-loop policy and Dev Team runtime source.
Outputs: JSON-compatible DevBoundedLoopValidationReport artifacts.
Side effects: None; CLI writes JSON to stdout.
Tests: noemaforge/tests/test_dev_bounded_loop_runtime.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Sequence


SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import dev_team_runtime as dtr


API_VERSION = "noemaforge.dev-bounded-loop/v1"
POLICY_KIND = "DevBoundedLoopPolicy"
REPORT_KIND = "DevBoundedLoopValidationReport"
VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
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


def load_text(path: Path | str) -> str:
    return Path(path).read_text(encoding="utf-8")


def _slice_between(text: str, start_marker: str, end_markers: Sequence[str]) -> str:
    start = text.find(start_marker)
    if start < 0:
        return ""
    ends = [text.find(marker, start + len(start_marker)) for marker in end_markers]
    ends = [pos for pos in ends if pos > start]
    end = min(ends) if ends else len(text)
    return text[start:end]


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
    if str(policy.get("activation_state") or "") != "bounded_dev_team_loop_checkpoint_stop":
        failures.append("policy_activation_state_invalid")
    for key in [
        "require_docs_and_changelog_refs",
        "require_no_live_dependency",
        "forbid_auto_apply",
        "require_admin_approval",
        "require_checkpoint_stop_handling",
    ]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    if int(policy.get("max_steps_bound") or 0) > 10:
        failures.append("policy_max_steps_bound_too_high")
    if int(policy.get("time_budget_minutes_bound") or 0) > 60:
        failures.append("policy_time_budget_unbounded")
    for key in ["required_dev_team_tokens", "required_plan_fields", "required_checkpoint_fields"]:
        if not _as_string_list(policy.get(key)):
            failures.append(f"policy_{key}_empty")
    return failures


def _source_report(policy: Dict[str, Any], *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    failures: List[str] = []
    resolved = _resolve_ref("noemaforge/src/dev_team_runtime.py", project_root=project_root, package_root=package_root)
    text = load_text(resolved["path"]) if resolved.get("ok") else ""
    if not resolved.get("ok"):
        failures.append("dev_team_runtime_missing")
    for token in _as_string_list(policy.get("required_dev_team_tokens")):
        if token not in text:
            failures.append(f"dev_team_token_missing:{token}")
    plan_parser_block = _slice_between(
        text,
        'bounded = sub.add_parser("bounded-loop-plan")',
        ['checkpoint = sub.add_parser("bounded-loop-checkpoint")'],
    )
    checkpoint_parser_block = _slice_between(
        text,
        'checkpoint = sub.add_parser("bounded-loop-checkpoint")',
        ['rep = sub.add_parser("replace")'],
    )
    if not plan_parser_block:
        failures.append("bounded_loop_plan_parser_block_missing")
    if not checkpoint_parser_block:
        failures.append("bounded_loop_checkpoint_parser_block_missing")
    if "--apply" in plan_parser_block:
        failures.append("bounded_loop_plan_parser_exposes_apply")
    if "--apply" in checkpoint_parser_block:
        failures.append("bounded_loop_checkpoint_parser_exposes_apply")
    return {
        "failures": failures,
        "resolved": resolved,
        "dev_team_chars": len(text),
        "plan_parser_chars": len(plan_parser_block),
        "checkpoint_parser_chars": len(checkpoint_parser_block),
    }


def build_bounded_loop_policy_fixture() -> Dict[str, Any]:
    plan = dtr.build_bounded_dev_loop_plan(
        "Fixture bounded Dev Team loop",
        max_steps=999,
        time_budget_minutes=999,
        until_stop=True,
        checkpoint_interval=99,
    )
    with tempfile.TemporaryDirectory(prefix="nfg-dev-bounded-loop-") as tmp:
        started = dtr.write_bounded_dev_loop_plan(
            Path(tmp) / "started",
            "Fixture persisted bounded loop",
            max_steps=999,
            time_budget_minutes=999,
            until_stop=True,
            checkpoint_interval=99,
        )
        running_checkpoint = dtr.advance_bounded_dev_loop_checkpoint(
            Path(started["run_dir"]),
            observation="fixture first checkpoint",
        )
        stopped_checkpoint = dtr.advance_bounded_dev_loop_checkpoint(
            Path(started["run_dir"]),
            observation="fixture stop checkpoint",
            stop_requested=True,
        )
        completing = dtr.write_bounded_dev_loop_plan(
            Path(tmp) / "complete",
            "Fixture completing bounded loop",
            max_steps=2,
            time_budget_minutes=10,
        )
        first = dtr.advance_bounded_dev_loop_checkpoint(Path(completing["run_dir"]))
        completed_checkpoint = dtr.advance_bounded_dev_loop_checkpoint(Path(completing["run_dir"]))
        persisted = {
            "started_plan": started,
            "running_checkpoint": running_checkpoint,
            "stopped_checkpoint": stopped_checkpoint,
            "completing_plan": completing,
            "first_completion_checkpoint": first,
            "completed_checkpoint": completed_checkpoint,
        }
    return {"plan": plan, "persisted": persisted}


def _workflow_report(policy: Dict[str, Any]) -> Dict[str, Any]:
    failures: List[str] = []
    fixture = build_bounded_loop_policy_fixture()
    plan = fixture["plan"]
    for field in _as_string_list(policy.get("required_plan_fields")):
        if field not in plan:
            failures.append(f"bounded_plan_field_missing:{field}")
    if plan.get("mode") != "dev_team_bounded_loop":
        failures.append("bounded_plan_mode_invalid")
    if plan.get("plan_status") != "draft_checkpoint_required":
        failures.append("bounded_plan_status_invalid")
    if plan.get("auto_apply") is not False:
        failures.append("bounded_plan_auto_apply_not_false")
    if plan.get("applied") is not False:
        failures.append("bounded_plan_applied_not_false")
    if plan.get("requires_admin_approval") is not True:
        failures.append("bounded_plan_admin_approval_not_required")
    if plan.get("execution_policy") != "plan_and_checkpoint_only_no_auto_apply":
        failures.append("bounded_plan_execution_policy_invalid")
    budget = plan.get("improvement_budget") if isinstance(plan.get("improvement_budget"), dict) else {}
    if budget.get("bounded") is not True:
        failures.append("bounded_plan_budget_not_bounded")
    if int(budget.get("max_steps") or 0) > int(policy.get("max_steps_bound") or 10):
        failures.append("bounded_plan_max_steps_unbounded")
    if int(budget.get("time_budget_minutes") or 0) > int(policy.get("time_budget_minutes_bound") or 60):
        failures.append("bounded_plan_time_budget_unbounded")
    if budget.get("until_stop") is not True:
        failures.append("bounded_plan_until_stop_not_preserved")
    checkpoint_policy = plan.get("checkpoint_policy") if isinstance(plan.get("checkpoint_policy"), dict) else {}
    if checkpoint_policy.get("write_after_each_step") is not True:
        failures.append("checkpoint_policy_write_after_each_step_not_true")
    if checkpoint_policy.get("stop_file") != "stop-request.json":
        failures.append("checkpoint_policy_stop_file_invalid")
    if checkpoint_policy.get("checkpoint_file") != "checkpoint-current.json":
        failures.append("checkpoint_policy_current_file_invalid")
    if not plan.get("steps"):
        failures.append("bounded_plan_steps_empty")
    for step in plan.get("steps", []):
        if not isinstance(step, dict) or step.get("apply") is not False:
            failures.append("bounded_step_apply_not_false")
        if step.get("checkpoint_required") is not True:
            failures.append("bounded_step_checkpoint_not_required")
    for forbidden in ["write_file", "replace", "set_version", "apply_patch", "run_privileged_command", "auto_apply"]:
        if forbidden not in plan.get("forbidden_actions", []):
            failures.append(f"bounded_plan_forbidden_action_missing:{forbidden}")
    persisted = fixture["persisted"]
    for name in ["running_checkpoint", "stopped_checkpoint", "completed_checkpoint"]:
        checkpoint = persisted[name]
        for field in _as_string_list(policy.get("required_checkpoint_fields")):
            if field not in checkpoint:
                failures.append(f"{name}_field_missing:{field}")
        if checkpoint.get("auto_apply") is not False:
            failures.append(f"{name}_auto_apply_not_false")
        if checkpoint.get("applied") is not False:
            failures.append(f"{name}_applied_not_false")
    if persisted["running_checkpoint"].get("status") != "running":
        failures.append("running_checkpoint_status_invalid")
    if persisted["running_checkpoint"].get("checkpoint_index") != 1:
        failures.append("running_checkpoint_index_invalid")
    if persisted["stopped_checkpoint"].get("status") != "stopped":
        failures.append("stopped_checkpoint_status_invalid")
    if persisted["stopped_checkpoint"].get("terminal") is not True:
        failures.append("stopped_checkpoint_not_terminal")
    if persisted["stopped_checkpoint"].get("stop_requested") is not True:
        failures.append("stopped_checkpoint_stop_not_recorded")
    if persisted["completed_checkpoint"].get("status") != "completed":
        failures.append("completed_checkpoint_status_invalid")
    if persisted["completed_checkpoint"].get("pending_steps") != 0:
        failures.append("completed_checkpoint_pending_steps_not_zero")
    return {"failures": failures, "fixture": fixture}


def _docs_report(payload: Dict[str, Any], *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    failures: List[str] = []
    docs = [
        project_root / "TODO.md",
        package_root / "TODO.md",
        project_root / "docs" / "TODO.md",
        package_root / "docs" / "TODO.md",
        project_root / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
        package_root / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
        project_root / "CHANGELOG.md",
        project_root / "RELEASE_NOTES.md",
        project_root / "docs" / "history" / "CHANGELOG.md",
        package_root / "docs" / "history" / "CHANGELOG.md",
    ]
    tokens = [
        str(payload.get("id") or ""),
        "checkpoint/stop handling",
        "never auto-apply",
    ]
    reports: List[Dict[str, Any]] = []
    satisfied = False
    for path in docs:
        exists = path.exists()
        text = load_text(path) if exists else ""
        missing = [token for token in tokens if token and token not in text]
        if exists and not missing:
            satisfied = True
        reports.append({"path": _display_path(path), "ok": exists and not missing, "missing": missing, "exists": exists})
    # Documented in >=1 existing canonical doc, not every candidate (legacy/alt paths).
    if not satisfied:
        owner = str(payload.get("id") or "policy")
        failures.append(f"docs_tokens_missing:{owner}:{','.join(t for t in tokens if t)}")
    return {"failures": failures, "reports": reports}


def validate_dev_bounded_loop_policy(
    payload: Dict[str, Any],
    *,
    project_root: Path | str,
    package_root: Path | str,
    policy_path: Path | str | None = None,
    include_docs: bool = True,
) -> Dict[str, Any]:
    project = Path(project_root).resolve()
    package = Path(package_root).resolve()
    policy = _policy_dict(payload)
    failures: List[str] = []
    failures.extend(_policy_failures(payload))
    ref_report = _resolve_refs(_as_string_list(payload.get("refs")), project_root=project, package_root=package, owner=str(payload.get("id") or "policy"))
    failures.extend(ref_report["failures"])
    source = _source_report(policy, project_root=project, package_root=package)
    failures.extend(source["failures"])
    workflow = _workflow_report(policy)
    failures.extend(workflow["failures"])
    docs = _docs_report(payload, project_root=project, package_root=package) if include_docs else {"failures": [], "reports": []}
    failures.extend(docs["failures"])
    metrics = {
        "refs": len(_as_string_list(payload.get("refs"))),
        "resolved_refs": len(ref_report["resolved_refs"]),
        "dev_team_chars": source["dev_team_chars"],
        "plan_parser_chars": source["plan_parser_chars"],
        "checkpoint_parser_chars": source["checkpoint_parser_chars"],
        "bounded_plan_steps": len(workflow["fixture"]["plan"].get("steps", [])),
        "docs_reports": len(docs["reports"]),
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
        "workflow": workflow,
        "docs": docs,
    }


def benchmark_dev_bounded_loop_policy(*, package_root: Path | str, iterations: int = 80) -> Dict[str, Any]:
    root = Path(package_root).resolve()
    policy = load_policy(root / "configs" / "dev-bounded-loop-policy.json")
    started = time.perf_counter()
    failures = 0
    for _ in range(iterations):
        report = validate_dev_bounded_loop_policy(policy, project_root=root.parent, package_root=root, include_docs=False)
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
        "kind": "DevBoundedLoopValidationSummary",
        "ok": bool(report.get("ok")),
        "id": report.get("id"),
        "version": report.get("version"),
        "metrics": report.get("metrics", {}),
        "failures": report.get("failures", []),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate NoemaForge bounded Dev Team loop policy")
    parser.add_argument("--policy", default=str(SRC_DIR.parent / "configs" / "dev-bounded-loop-policy.json"))
    parser.add_argument("--project-root", default=str(SRC_DIR.parent.parent))
    parser.add_argument("--package-root", default=str(SRC_DIR.parent))
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--skip-docs", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = validate_dev_bounded_loop_policy(
        load_policy(args.policy),
        project_root=Path(args.project_root),
        package_root=Path(args.package_root),
        policy_path=Path(args.policy),
        include_docs=not args.skip_docs,
    )
    print(json.dumps(build_summary(report) if args.summary else report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
