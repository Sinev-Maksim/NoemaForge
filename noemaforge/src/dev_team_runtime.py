#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/dev_team_runtime.py
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-14
Modified: 2026-05-14
Purpose: Provide NoemaForge release functionality for the packaged local runtime.
Inputs: Command-line arguments, environment variables, package files and local NoemaForge runtime state as applicable.
Outputs: Structured command output, files, service state or UI state as documented by the caller.
Side effects: Limited to the documented NoemaForge paths, runtime state directories or systemd units used by this file.
Tests: Syntax validation plus the release setup selftest, consistency-audit and targeted smoke checks.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===

Existing module notes:
NoemaForge Dev Team runtime.

Provides auditable code-improvement operations that can either produce a patch
proposal or apply direct file changes under an explicit --apply flag.
"""
from __future__ import annotations

import argparse
import datetime as dt
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

RUNTIME_VERSION = "0.32.0.alpha"
DEFAULT_ROOT = Path(os.environ.get("NOEMAFORGE_ROOT", "/opt/noemaforge"))
DEFAULT_STATE = Path(os.environ.get("NOEMAFORGE_DEV_TEAM_STATE", "/var/lib/noemaforge/dev-team"))
DEFAULT_PIPELINE_STATE = Path(os.environ.get("NOEMAFORGE_PIPELINE_STATE", "/var/lib/noemaforge/pipelines"))
SAFE_ID_RE = re.compile(r"[^a-zA-Z0-9_.-]+")
OPEN_BACKLOG_STATUSES = {"new", "open", "todo", "pending", "in_progress", "blocked"}
LOOP_TERMINAL_STATUSES = {"completed", "stopped", "budget_exhausted"}
BOUNDED_LOOP_FORBIDDEN_ACTIONS = [
    "write_file",
    "replace",
    "set_version",
    "apply_patch",
    "run_privileged_command",
    "auto_apply",
]


def nowz() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True)


def safe_id(value: str, limit: int = 96) -> str:
    out = SAFE_ID_RE.sub("_", str(value or "").strip()).strip("_") or "dev_team"
    return out[:limit].strip("_") or "dev_team"


def resolve_project_file(project: Path, rel: str) -> Path:
    project = project.resolve()
    path = (project / rel).resolve()
    if path != project and project not in path.parents:
        raise SystemExit(f"refusing path outside project: {rel}")
    return path


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json_dumps(obj) + "\n", encoding="utf-8")


def unified_diff(old: str, new: str, fromfile: str, tofile: str) -> str:
    return "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), fromfile=fromfile, tofile=tofile))


def run_dir(state: Path, op: str) -> Path:
    rid = safe_id(f"{op}_{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}")
    path = state / "runs" / rid
    path.mkdir(parents=True, exist_ok=True)
    return path


def command_json(cmd: List[str]) -> Dict[str, Any]:
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out: Any = proc.stdout.strip()
    if out:
        try:
            out = json.loads(out)
        except Exception:
            pass
    return {"ok": proc.returncode == 0, "returncode": proc.returncode, "cmd": cmd, "stdout": out, "stderr": proc.stderr.strip()}


def write_context_artifacts(rd: Path, *, project: str, request: str, changed_files: List[str], mode: str) -> Dict[str, str]:
    rd.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "NoemaForge-context": rd / "NoemaForge-context.md",
        "NoemaForge-architecture": rd / "NoemaForge-architecture.md",
        "NoemaForge-qa": rd / "NoemaForge-qa.md",
        "changed-files": rd / "changed-files.json",
    }
    artifacts["NoemaForge-context"].write_text(
        "# NoemaForge Context\n\n"
        f"- created_at: {nowz()}\n"
        f"- mode: {mode}\n"
        f"- project: {project or 'not provided'}\n"
        f"- request: {request}\n\n"
        "This context packet summarizes the Admin → Dev Team handoff and must be reviewed before merge.\n",
        encoding="utf-8",
    )
    artifacts["NoemaForge-architecture"].write_text(
        "# NoemaForge Architecture Notes\n\n"
        "- Keep Admin as the control-plane owner.\n"
        "- Dev Team may propose or apply code changes only through explicit artifacts and apply gates.\n"
        "- QA must remain separate from Developer responsibilities.\n",
        encoding="utf-8",
    )
    artifacts["NoemaForge-qa"].write_text(
        "# NoemaForge QA Notes\n\n"
        "- Validate changed files.\n"
        "- Run syntax/audit checks relevant to the change.\n"
        "- Confirm rollback or backup exists before applying.\n",
        encoding="utf-8",
    )
    write_json(artifacts["changed-files"], {"created_at": nowz(), "mode": mode, "project": project, "changed_files": changed_files})
    return {k: str(v) for k, v in artifacts.items()}


def normalize_backlog_items(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [dict(item) for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ["tasks", "items", "backlog"]:
            value = payload.get(key)
            if isinstance(value, list):
                return [dict(item) for item in value if isinstance(item, dict)]
    return []


def load_backlog_items(backlog_path: str = "") -> List[Dict[str, Any]]:
    if not backlog_path:
        return []
    path = Path(backlog_path)
    if not path.exists():
        return []
    try:
        return normalize_backlog_items(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        return []


def open_dev_backlog_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    open_items: List[Dict[str, Any]] = []
    for item in items:
        category = str(item.get("category") or item.get("domain") or item.get("role") or item.get("assignee") or "").lower()
        title = str(item.get("title") or item.get("task") or "").lower()
        if category and "dev" not in category and "code" not in category and "dev" not in title:
            continue
        status = str(item.get("status") or "todo").strip().lower()
        if status in OPEN_BACKLOG_STATUSES:
            open_items.append(item)
    return open_items


def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def normalize_improvement_budget(
    max_steps: Any = 3,
    time_budget_minutes: Any = 20,
    *,
    until_stop: bool = False,
    max_steps_bound: int = 10,
    time_budget_minutes_bound: int = 60,
) -> Dict[str, Any]:
    bounded_steps = _bounded_int(max_steps, default=3, minimum=1, maximum=max_steps_bound)
    bounded_minutes = _bounded_int(time_budget_minutes, default=20, minimum=5, maximum=time_budget_minutes_bound)
    return {
        "bounded": True,
        "max_steps": bounded_steps,
        "time_budget_minutes": bounded_minutes,
        "until_stop": bool(until_stop),
        "max_steps_bound": max_steps_bound,
        "time_budget_minutes_bound": time_budget_minutes_bound,
    }


def _bounded_loop_steps(max_steps: int) -> List[Dict[str, Any]]:
    candidates = [
        ("inspect_context", "Inspect current TODOs, recent failures and low-risk offline contracts."),
        ("select_safe_item", "Select exactly one safe improvement item that does not require live services."),
        ("draft_patch_scope", "Draft the smallest runtime, QA and docs patch scope for review."),
        ("implement_offline_contract", "Prepare the offline contract implementation behind no-auto-apply gates."),
        ("run_targeted_checks", "Run targeted syntax, runtime, QA and performance checks."),
        ("record_release_note", "Record the changelog, release-note and TODO closure lines."),
        ("review_follow_up_risk", "Capture remaining risk and follow-up candidates without applying them."),
        ("prepare_next_checkpoint", "Prepare the next bounded checkpoint for Admin review."),
    ]
    steps: List[Dict[str, Any]] = []
    for index in range(max_steps):
        if index < len(candidates):
            step_id, description = candidates[index]
        else:
            step_id = f"checkpoint_review_{index + 1:02d}"
            description = "Review bounded loop progress and decide whether another offline checkpoint is still warranted."
        steps.append(
            {
                "ordinal": index + 1,
                "id": step_id,
                "kind": "checkpointed_plan_step",
                "description": description,
                "status": "planned",
                "apply": False,
                "checkpoint_required": True,
            }
        )
    return steps


def build_bounded_dev_loop_plan(
    request: str,
    *,
    max_steps: Any = 3,
    time_budget_minutes: Any = 20,
    until_stop: bool = False,
    checkpoint_interval: Any = 1,
) -> Dict[str, Any]:
    budget = normalize_improvement_budget(max_steps, time_budget_minutes, until_stop=until_stop)
    checkpoint_every = _bounded_int(
        checkpoint_interval,
        default=1,
        minimum=1,
        maximum=int(budget["max_steps"]),
    )
    return {
        "ok": True,
        "version": RUNTIME_VERSION,
        "mode": "dev_team_bounded_loop",
        "request": request or "Bounded Dev Team improvement loop",
        "plan_status": "draft_checkpoint_required",
        "loop_status": "planned",
        "auto_apply": False,
        "applied": False,
        "requires_admin_approval": True,
        "execution_policy": "plan_and_checkpoint_only_no_auto_apply",
        "improvement_budget": budget,
        "checkpoint_policy": {
            "write_after_each_step": True,
            "checkpoint_interval": checkpoint_every,
            "checkpoint_file": "checkpoint-current.json",
            "checkpoint_history_glob": "checkpoint-*.json",
            "stop_file": "stop-request.json",
            "terminal_statuses": sorted(LOOP_TERMINAL_STATUSES),
        },
        "current_step": 0,
        "steps": _bounded_loop_steps(int(budget["max_steps"])),
        "forbidden_actions": list(BOUNDED_LOOP_FORBIDDEN_ACTIONS),
        "acceptance": [
            "Creates a bounded multi-step plan with checkpoint artifacts.",
            "Never exposes auto-apply or direct file mutation controls.",
            "Stops cleanly when a stop marker or explicit stop request is present.",
            "Requires later Admin approval before any implementation is applied.",
        ],
    }


def _checkpoint_payload(
    plan: Dict[str, Any],
    *,
    run_dir_path: Path,
    checkpoint_index: int,
    status: str,
    completed_step_ids: List[str],
    observation: str = "",
    stop_requested: bool = False,
    last_step: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    total_steps = len(plan.get("steps", []))
    completed_count = len(completed_step_ids)
    return {
        "ok": True,
        "version": RUNTIME_VERSION,
        "mode": "dev_team_bounded_loop_checkpoint",
        "run_dir": str(run_dir_path),
        "plan_path": str(run_dir_path / "bounded-loop-plan.json"),
        "status": status,
        "terminal": status in LOOP_TERMINAL_STATUSES,
        "checkpoint_index": checkpoint_index,
        "current_step": completed_count,
        "total_steps": total_steps,
        "pending_steps": max(0, total_steps - completed_count),
        "completed_step_ids": completed_step_ids,
        "last_step": last_step or {},
        "observation": observation,
        "stop_requested": bool(stop_requested),
        "stop_marker_path": str(run_dir_path / "stop-request.json"),
        "auto_apply": False,
        "applied": False,
        "created_at": nowz(),
    }


def write_bounded_dev_loop_plan(
    state: Path,
    request: str,
    *,
    max_steps: Any = 3,
    time_budget_minutes: Any = 20,
    until_stop: bool = False,
    checkpoint_interval: Any = 1,
) -> Dict[str, Any]:
    rd = run_dir(state, "dev_bounded_loop")
    plan = build_bounded_dev_loop_plan(
        request,
        max_steps=max_steps,
        time_budget_minutes=time_budget_minutes,
        until_stop=until_stop,
        checkpoint_interval=checkpoint_interval,
    )
    plan["run_dir"] = str(rd)
    plan["artifacts"] = write_context_artifacts(
        rd,
        project="",
        request=plan["request"],
        changed_files=[],
        mode="dev_team_bounded_loop",
    )
    plan_path = rd / "bounded-loop-plan.json"
    checkpoint_path = rd / "checkpoint-000.json"
    current_path = rd / "checkpoint-current.json"
    plan["plan_path"] = str(plan_path)
    plan["checkpoint_current_path"] = str(current_path)
    plan["checkpoint_paths"] = [str(checkpoint_path)]
    checkpoint = _checkpoint_payload(
        plan,
        run_dir_path=rd,
        checkpoint_index=0,
        status="planned",
        completed_step_ids=[],
        observation="initial bounded loop plan created",
    )
    write_json(plan_path, plan)
    write_json(checkpoint_path, checkpoint)
    write_json(current_path, checkpoint)
    return plan


def advance_bounded_dev_loop_checkpoint(
    run_dir_path: Path,
    *,
    step_id: str = "",
    stop_requested: bool = False,
    observation: str = "",
) -> Dict[str, Any]:
    rd = Path(run_dir_path)
    plan_path = rd / "bounded-loop-plan.json"
    current_path = rd / "checkpoint-current.json"
    if not plan_path.exists():
        raise SystemExit(f"bounded loop plan not found: {plan_path}")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    previous = json.loads(current_path.read_text(encoding="utf-8")) if current_path.exists() else {}
    completed_step_ids = [str(item) for item in previous.get("completed_step_ids", []) if str(item)]
    checkpoint_index = int(previous.get("checkpoint_index") or 0) + 1
    stop_marker = rd / "stop-request.json"
    if stop_requested and not stop_marker.exists():
        write_json(stop_marker, {"created_at": nowz(), "reason": observation or "explicit stop request"})
    if stop_requested or stop_marker.exists():
        checkpoint = _checkpoint_payload(
            plan,
            run_dir_path=rd,
            checkpoint_index=checkpoint_index,
            status="stopped",
            completed_step_ids=completed_step_ids,
            observation=observation or "stop requested",
            stop_requested=True,
        )
    elif previous.get("status") in LOOP_TERMINAL_STATUSES:
        checkpoint = _checkpoint_payload(
            plan,
            run_dir_path=rd,
            checkpoint_index=checkpoint_index,
            status=str(previous.get("status")),
            completed_step_ids=completed_step_ids,
            observation=observation or "terminal checkpoint already reached",
        )
    else:
        steps = plan.get("steps", []) if isinstance(plan.get("steps"), list) else []
        next_index = len(completed_step_ids)
        if next_index >= len(steps):
            checkpoint = _checkpoint_payload(
                plan,
                run_dir_path=rd,
                checkpoint_index=checkpoint_index,
                status="completed",
                completed_step_ids=completed_step_ids,
                observation=observation or "all bounded loop steps completed",
            )
        else:
            step = dict(steps[next_index])
            if step_id and step_id != step.get("id"):
                step["requested_step_id"] = step_id
            completed_step_ids.append(str(step.get("id") or f"step_{next_index + 1}"))
            status = "completed" if len(completed_step_ids) >= len(steps) else "running"
            step["status"] = "checkpointed"
            checkpoint = _checkpoint_payload(
                plan,
                run_dir_path=rd,
                checkpoint_index=checkpoint_index,
                status=status,
                completed_step_ids=completed_step_ids,
                observation=observation or f"checkpointed {step.get('id')}",
                last_step=step,
            )
    checkpoint_path = rd / f"checkpoint-{checkpoint_index:03d}.json"
    write_json(checkpoint_path, checkpoint)
    write_json(current_path, checkpoint)
    checkpoint["checkpoint_path"] = str(checkpoint_path)
    checkpoint["checkpoint_current_path"] = str(current_path)
    return checkpoint


def build_empty_backlog_seed_self_optimization_plan(
    items: List[Dict[str, Any]],
    *,
    max_steps: int = 3,
    time_budget_minutes: int = 20,
    request: str = "Seed self-optimization plan for empty Dev backlog",
) -> Dict[str, Any]:
    open_items = open_dev_backlog_items(items)
    if open_items:
        return {
            "ok": True,
            "version": RUNTIME_VERSION,
            "mode": "dev_backlog_empty_seed_self_optimization",
            "seed_created": False,
            "reason": "dev_backlog_not_empty",
            "open_dev_backlog_items": len(open_items),
            "auto_apply": False,
            "applied": False,
            "execution_policy": "no_seed_plan_while_dev_backlog_has_open_work",
        }

    bounded_steps = max(1, min(5, int(max_steps or 3)))
    bounded_minutes = max(5, min(30, int(time_budget_minutes or 20)))
    actions = [
        {
            "id": "inspect_recent_dev_failures",
            "kind": "analysis",
            "description": "Review recent tests, TODO closures and low-risk contract gaps.",
            "apply": False,
        },
        {
            "id": "select_one_low_risk_contract",
            "kind": "planning",
            "description": "Choose one documentation/runtime contract that can be validated offline.",
            "apply": False,
        },
        {
            "id": "write_regression_plan_only",
            "kind": "qa_plan",
            "description": "Draft runtime, QA and performance checks for a later explicit task.",
            "apply": False,
        },
    ]
    return {
        "ok": True,
        "version": RUNTIME_VERSION,
        "mode": "dev_backlog_empty_seed_self_optimization",
        "seed_created": True,
        "trigger": "dev_backlog_empty",
        "request": request,
        "plan_status": "draft_review_required",
        "auto_apply": False,
        "applied": False,
        "requires_admin_approval": True,
        "execution_policy": "plan_only_no_auto_apply",
        "improvement_budget": {
            "bounded": True,
            "max_steps": bounded_steps,
            "time_budget_minutes": bounded_minutes,
            "until_stop": False,
        },
        "actions": actions,
        "forbidden_actions": [
            "write_file",
            "replace",
            "set_version",
            "apply_patch",
            "run_privileged_command",
            "auto_apply",
        ],
        "acceptance": [
            "Creates a reviewable seed plan only when no open Dev backlog items exist.",
            "Does not edit project files.",
            "Does not call direct Dev Team apply operations.",
            "Requires a later explicit task before any code change.",
        ],
    }


def cmd_seed_self_improvement_plan(args: argparse.Namespace) -> int:
    state = Path(args.state).resolve() if args.state else DEFAULT_STATE
    items = load_backlog_items(args.backlog)
    plan = build_empty_backlog_seed_self_optimization_plan(
        items,
        max_steps=args.max_steps,
        time_budget_minutes=args.time_budget_minutes,
        request=args.request or "Seed self-optimization plan for empty Dev backlog",
    )
    rd = run_dir(state, "dev_backlog_seed")
    plan["run_dir"] = str(rd)
    plan["artifacts"] = write_context_artifacts(
        rd,
        project="",
        request=plan.get("request", "Seed self-optimization plan for empty Dev backlog"),
        changed_files=[],
        mode="dev_backlog_empty_seed_self_optimization",
    )
    write_json(rd / "seed-self-optimization-plan.json", plan)
    plan["plan_path"] = str(rd / "seed-self-optimization-plan.json")
    print(json_dumps(plan) if args.json else str(rd / "seed-self-optimization-plan.json"))
    return 0 if plan.get("ok") else 1


def cmd_bounded_loop_plan(args: argparse.Namespace) -> int:
    state = Path(args.state).resolve() if args.state else DEFAULT_STATE
    plan = write_bounded_dev_loop_plan(
        state,
        args.request or "Bounded Dev Team improvement loop",
        max_steps=args.max_steps,
        time_budget_minutes=args.time_budget_minutes,
        until_stop=args.until_stop,
        checkpoint_interval=args.checkpoint_interval,
    )
    print(json_dumps(plan) if args.json else str(plan["plan_path"]))
    return 0 if plan.get("ok") else 1


def cmd_bounded_loop_checkpoint(args: argparse.Namespace) -> int:
    checkpoint = advance_bounded_dev_loop_checkpoint(
        Path(args.run_dir).resolve(),
        step_id=args.step_id or "",
        stop_requested=bool(args.stop),
        observation=args.observation or "",
    )
    print(json_dumps(checkpoint) if args.json else str(checkpoint["checkpoint_current_path"]))
    return 0 if checkpoint.get("ok") else 1


def cmd_run(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve() if args.root else DEFAULT_ROOT
    state = Path(args.pipeline_state).resolve() if args.pipeline_state else DEFAULT_PIPELINE_STATE
    dev_state = Path(args.state).resolve() if args.state else DEFAULT_STATE
    request = args.request or " ".join(args.text or []) or "development task"
    cmd = [
        sys.executable,
        str(root / "src" / "pipeline_runtime.py"),
        "--root",
        str(root),
        "--state",
        str(state),
        "run",
        args.pipeline,
        "--task-id",
        safe_id(f"dev_{request[:48]}"),
        "--request",
        request,
    ]
    if args.allow_degraded:
        cmd.append("--allow-degraded")
    result = command_json(cmd)
    rd = run_dir(dev_state, "dev_team_run")
    artifacts = write_context_artifacts(rd, project="", request=request, changed_files=[], mode="dev_team_pipeline")
    budget = {"max_steps": int(getattr(args, "max_steps", 0) or 0), "time_budget_minutes": int(getattr(args, "time_budget_minutes", 0) or 0), "until_stop": bool(getattr(args, "until_stop", False))}
    budget["active"] = bool(budget["max_steps"] or budget["time_budget_minutes"] or budget["until_stop"])
    doc = {"ok": result["ok"], "version": RUNTIME_VERSION, "mode": "dev_team_pipeline", "pipeline": args.pipeline, "result": result, "run_dir": str(rd), "artifacts": artifacts, "improvement_budget": budget}
    print(json_dumps(doc) if args.json else json_dumps(doc))
    return 0 if result["ok"] else 1


def cmd_replace(args: argparse.Namespace) -> int:
    project = Path(args.project).resolve()
    state = Path(args.state).resolve() if args.state else DEFAULT_STATE
    path = resolve_project_file(project, args.path)
    if not path.exists():
        raise SystemExit(f"file not found: {path}")
    old_text = path.read_text(encoding=args.encoding, errors="replace")
    if args.old not in old_text:
        raise SystemExit("old text not found; refusing partial/ambiguous replacement")
    new_text = old_text.replace(args.old, args.new, 1 if args.once else -1)
    diff = unified_diff(old_text, new_text, str(path), str(path))
    rd = run_dir(state, "replace")
    diff_path = rd / "patch.diff"
    diff_path.write_text(diff, encoding="utf-8")
    backup_path = None
    if args.apply:
        backup_path = path.with_suffix(path.suffix + f".bak.{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}")
        shutil.copy2(path, backup_path)
        path.write_text(new_text, encoding=args.encoding)
    manifest = {
        "ok": True,
        "version": RUNTIME_VERSION,
        "mode": "replace",
        "applied": bool(args.apply),
        "project": str(project),
        "path": str(path),
        "diff": str(diff_path),
        "backup": str(backup_path) if backup_path else None,
        "changed": old_text != new_text,
        "created_at": nowz(),
    }
    manifest["artifacts"] = write_context_artifacts(rd, project=str(project), request=f"replace {args.path}", changed_files=[str(path)], mode="replace")
    write_json(rd / "manifest.json", manifest)
    print(json_dumps(manifest) if args.json else str(diff_path))
    return 0


def cmd_write_file(args: argparse.Namespace) -> int:
    project = Path(args.project).resolve()
    state = Path(args.state).resolve() if args.state else DEFAULT_STATE
    path = resolve_project_file(project, args.path)
    old_text = path.read_text(encoding=args.encoding, errors="replace") if path.exists() else ""
    new_text = args.content if args.content is not None else Path(args.content_file).read_text(encoding=args.encoding)
    diff = unified_diff(old_text, new_text, str(path), str(path))
    rd = run_dir(state, "write_file")
    diff_path = rd / "patch.diff"
    diff_path.write_text(diff, encoding="utf-8")
    backup_path = None
    if args.apply:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            backup_path = path.with_suffix(path.suffix + f".bak.{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}")
            shutil.copy2(path, backup_path)
        path.write_text(new_text, encoding=args.encoding)
    manifest = {"ok": True, "version": RUNTIME_VERSION, "mode": "write_file", "applied": bool(args.apply), "project": str(project), "path": str(path), "diff": str(diff_path), "backup": str(backup_path) if backup_path else None, "created_at": nowz()}
    manifest["artifacts"] = write_context_artifacts(rd, project=str(project), request=f"write-file {args.path}", changed_files=[str(path)], mode="write_file")
    write_json(rd / "manifest.json", manifest)
    print(json_dumps(manifest) if args.json else str(diff_path))
    return 0


def _replace_regex(path: Path, pattern: str, repl: str) -> bool:
    if not path.exists() or path.is_dir():
        return False
    text = path.read_text(encoding="utf-8", errors="replace")
    new = re.sub(pattern, repl, text)
    if new != text:
        path.write_text(new, encoding="utf-8")
        return True
    return False


def cmd_set_version(args: argparse.Namespace) -> int:
    project = Path(args.project).resolve()
    state = Path(args.state).resolve() if args.state else DEFAULT_STATE
    version = args.version
    candidates = [project / "VERSION", project / "noemaforge" / "VERSION", project / "release.json"]
    for cfg in (project / "noemaforge" / "configs").glob("*.json") if (project / "noemaforge" / "configs").exists() else []:
        candidates.append(cfg)
    if (project / "noemaforge" / "src").exists():
        candidates.extend((project / "noemaforge" / "src").glob("*.py"))
    candidates.append(project / "noemaforge" / "bin" / "noemaforge")
    rd = run_dir(state, "set_version")
    changes: List[Dict[str, Any]] = []
    for path in sorted(set(candidates)):
        if not path.exists() or path.is_dir():
            continue
        old = path.read_text(encoding="utf-8", errors="replace")
        new = old
        if path.name == "VERSION":
            new = version + "\n"
        elif path.suffix == ".json":
            try:
                obj = json.loads(old)
                if isinstance(obj, dict) and "version" in obj:
                    obj["version"] = version
                    if path.name == "release.json":
                        obj["package"] = f"noemaforge_{version}_release_candidate_prelaunch"
                    new = json_dumps(obj) + "\n"
            except Exception:
                pass
        else:
            new = re.sub(r'RUNTIME_VERSION\s*=\s*"0\.31\.\d+(?:\.pre-alpha(?:-patched\d*)?|\.alpha(?:-patched\d+)?)?"', ''.join(['RUNTIME_VERSION', ' = ']) + json.dumps(version), new)
            new = re.sub(r'VERSION\s*=\s*"0\.31\.\d+(?:\.pre-alpha(?:-patched\d*)?|\.alpha(?:-patched\d+)?)?"', ''.join(['VERSION', ' = ']) + json.dumps(version), new)
            new = re.sub(r'echo "0\.31\.\d+(?:\.pre-alpha(?:-patched\d*)?|\.alpha(?:-patched\d+)?)?"', 'echo ' + json.dumps(version), new)
        if new != old:
            diff = unified_diff(old, new, str(path), str(path))
            changes.append({"path": str(path), "diff": diff})
            if args.apply:
                shutil.copy2(path, path.with_suffix(path.suffix + f".bak.{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"))
                path.write_text(new, encoding="utf-8")
    patch = "\n".join(c["diff"] for c in changes)
    (rd / "version.patch").write_text(patch, encoding="utf-8")
    manifest = {"ok": True, "version": RUNTIME_VERSION, "mode": "set_version", "target_version": version, "applied": bool(args.apply), "changed_files": [c["path"] for c in changes], "patch": str(rd / "version.patch")}
    manifest["artifacts"] = write_context_artifacts(rd, project=str(project), request=f"set-version {version}", changed_files=[c["path"] for c in changes], mode="set_version")
    write_json(rd / "manifest.json", manifest)
    print(json_dumps(manifest))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="noemaforge dev-team")
    parser.add_argument("--root")
    parser.add_argument("--state")
    parser.add_argument("--pipeline-state")
    sub = parser.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run")
    run.add_argument("text", nargs="*")
    run.add_argument("--state")
    run.add_argument("--pipeline-state")
    run.add_argument("--request")
    run.add_argument("--pipeline", default="dev_pipeline_member_cells")
    run.add_argument("--allow-degraded", action="store_true")
    run.add_argument("--max-steps", type=int, default=0)
    run.add_argument("--time-budget-minutes", type=int, default=0)
    run.add_argument("--until-stop", action="store_true")
    run.add_argument("--json", action="store_true")
    run.set_defaults(func=cmd_run)

    seed = sub.add_parser("seed-self-improvement-plan")
    seed.add_argument("--state")
    seed.add_argument("--backlog", default="")
    seed.add_argument("--request", default="")
    seed.add_argument("--max-steps", type=int, default=3)
    seed.add_argument("--time-budget-minutes", type=int, default=20)
    seed.add_argument("--json", action="store_true")
    seed.set_defaults(func=cmd_seed_self_improvement_plan)

    bounded = sub.add_parser("bounded-loop-plan")
    bounded.add_argument("--state")
    bounded.add_argument("--request", default="")
    bounded.add_argument("--max-steps", type=int, default=3)
    bounded.add_argument("--time-budget-minutes", type=int, default=20)
    bounded.add_argument("--until-stop", action="store_true")
    bounded.add_argument("--checkpoint-interval", type=int, default=1)
    bounded.add_argument("--json", action="store_true")
    bounded.set_defaults(func=cmd_bounded_loop_plan)

    checkpoint = sub.add_parser("bounded-loop-checkpoint")
    checkpoint.add_argument("--run-dir", required=True)
    checkpoint.add_argument("--step-id", default="")
    checkpoint.add_argument("--observation", default="")
    checkpoint.add_argument("--stop", action="store_true")
    checkpoint.add_argument("--json", action="store_true")
    checkpoint.set_defaults(func=cmd_bounded_loop_checkpoint)

    rep = sub.add_parser("replace")
    rep.add_argument("--state")
    rep.add_argument("--project", required=True)
    rep.add_argument("--path", required=True)
    rep.add_argument("--old", required=True)
    rep.add_argument("--new", required=True)
    rep.add_argument("--once", action="store_true")
    rep.add_argument("--apply", action="store_true")
    rep.add_argument("--encoding", default="utf-8")
    rep.add_argument("--json", action="store_true")
    rep.set_defaults(func=cmd_replace)

    wr = sub.add_parser("write-file")
    wr.add_argument("--project", required=True)
    wr.add_argument("--path", required=True)
    wr.add_argument("--content")
    wr.add_argument("--content-file")
    wr.add_argument("--apply", action="store_true")
    wr.add_argument("--encoding", default="utf-8")
    wr.add_argument("--json", action="store_true")
    wr.set_defaults(func=cmd_write_file)

    sv = sub.add_parser("set-version")
    sv.add_argument("--state")
    sv.add_argument("--project", required=True)
    sv.add_argument("--version", required=True)
    sv.add_argument("--apply", action="store_true")
    sv.add_argument("--json", action="store_true")
    sv.set_defaults(func=cmd_set_version)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "cmd", "") == "write-file" and not args.content and not args.content_file:
        parser.error("write-file requires --content or --content-file")
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())


