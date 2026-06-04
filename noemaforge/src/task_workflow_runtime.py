#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/task_workflow_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate Admin GUI task add/edit/prioritize/block/complete workflows through chat and API.
Inputs: task-workflow policy and Admin GUI server source.
Outputs: JSON-compatible TaskWorkflowValidationReport artifacts.
Side effects: None; CLI writes JSON to stdout.
Tests: noemaforge/tests/test_task_workflow_runtime.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Sequence


SRC_DIR = Path(__file__).resolve().parent
API_VERSION = "noemaforge.task-workflow/v1"
POLICY_KIND = "TaskWorkflowPolicy"
REPORT_KIND = "TaskWorkflowValidationReport"
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
    if str(policy.get("activation_state") or "") != "admin_chat_and_api_task_workflow":
        failures.append("policy_activation_state_invalid")
    for key in ["require_docs_and_changelog_refs", "require_no_live_gui_dependency"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    for key in ["required_runtime_scripts", "required_api_tokens", "required_chat_tokens", "required_workflow_steps", "allowed_statuses"]:
        if not _as_string_list(policy.get(key)):
            failures.append(f"policy_{key}_empty")
    return failures


def build_offline_admin_gui_server(*, package_root: Path | str) -> Any:
    if str(SRC_DIR) not in sys.path:
        sys.path.insert(0, str(SRC_DIR))
    import admin_gui_server  # type: ignore

    root = Path(package_root).resolve()
    data_root = root / "_memory_only_gui_state"
    store: Dict[str, Any] = {}
    server = object.__new__(admin_gui_server.AdminGuiServer)
    server.root = root
    server.state = data_root / "pipelines"
    server.persona_state = data_root / "personas"
    server.evolution_state = data_root / "model-evolution"
    server.model_selection_state = data_root / "model-selection"
    server.dev_team_state = data_root / "dev-team"
    server.data_root = data_root
    server.gui_state_dir = data_root / "gui"
    server.jobs_dir = data_root / "jobs"
    server.tasks_dir = data_root / "tasks"
    server.review_dir = data_root / "review"
    server.runtime_dir = data_root / "runtime"
    server.bootstrap_dir = data_root / "bootstrap"
    server.modelstore_dir = data_root / "modelstore"
    server.ui_dir = root / "templates" / "pipeline-dashboard"
    # Parity with AdminGuiServer.__init__: read-modify-write locks. The double
    # bypasses __init__ via object.__new__, so these must be set explicitly or
    # job/task/conversation paths raise AttributeError.
    server._jobs_lock = threading.Lock()
    server._tasks_lock = threading.Lock()
    server._conv_lock = threading.Lock()

    def read_json(path: Path, default: Any) -> Any:
        key = _display_path(Path(path))
        if key not in store:
            return copy.deepcopy(default)
        return copy.deepcopy(store[key])

    def write_json(path: Path, obj: Any) -> None:
        store[_display_path(Path(path))] = copy.deepcopy(obj)

    def append_jsonl(path: Path, obj: Dict[str, Any]) -> None:
        key = _display_path(Path(path))
        store.setdefault(key, []).append(copy.deepcopy(obj))

    server._memory_store = store
    server._read_json = read_json
    server._write_json = write_json
    server._append_jsonl = append_jsonl
    return server


def build_task_workflow_sequence(*, package_root: Path | str) -> Dict[str, Any]:
    server = build_offline_admin_gui_server(package_root=package_root)
    api_create = server.task_create({"title": "API seed task", "category": "qa", "priority": 40})
    task_id = api_create["task"]["task_id"]
    api_edit = server.task_update({"task_id": task_id, "title": "API edited task"})
    api_prioritize = server.task_prioritize({"task_id": task_id, "priority": 90})
    api_block = server.task_block({"task_id": task_id, "reason": "waiting on fixture"})
    api_complete = server.task_complete({"task_id": task_id})

    chat_create = server.admin_message("добавь задачу: Проверить Admin task flow приоритет высокий", execute=False, prepare_media=False, allow_degraded=True, apply=False, locale="ru")
    chat_task_id = chat_create["task"]["task_id"]
    chat_edit = server.admin_message(f"измени задачу {chat_task_id}: Проверить Admin task flow через чат", execute=False, prepare_media=False, allow_degraded=True, apply=False, locale="ru")
    chat_prioritize = server.admin_message(f"приоритет задачи {chat_task_id} 95", execute=False, prepare_media=False, allow_degraded=True, apply=False, locale="ru")
    chat_block = server.admin_message(f"заблокируй задачу {chat_task_id} причина нужна проверка", execute=False, prepare_media=False, allow_degraded=True, apply=False, locale="ru")
    chat_complete = server.admin_message(f"заверши задачу {chat_task_id}", execute=False, prepare_media=False, allow_degraded=True, apply=False, locale="ru")
    return {
        "api": {
            "create": api_create,
            "edit": api_edit,
            "prioritize": api_prioritize,
            "block": api_block,
            "complete": api_complete,
        },
        "chat": {
            "create": chat_create,
            "edit": chat_edit,
            "prioritize": chat_prioritize,
            "block": chat_block,
            "complete": chat_complete,
        },
        "tasks": server.tasks_list(),
        "store_keys": sorted(getattr(server, "_memory_store", {}).keys()),
    }


def _source_report(policy: Dict[str, Any], *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    failures: List[str] = []
    reports: List[Dict[str, Any]] = []
    for ref in _as_string_list(policy.get("required_runtime_scripts")):
        resolved = _resolve_ref(ref, project_root=project_root, package_root=package_root)
        text = load_text(resolved["path"]) if resolved.get("ok") else ""
        local_failures: List[str] = []
        if not resolved.get("ok"):
            local_failures.append(f"script_missing:{ref}")
        for token in _as_string_list(policy.get("required_api_tokens")) + _as_string_list(policy.get("required_chat_tokens")):
            if text and token not in text:
                local_failures.append(f"source_token_missing:{token}")
        reports.append({"ref": ref, "ok": not local_failures, "failures": local_failures, "resolved": resolved})
        failures.extend(local_failures)
    return {"failures": failures, "reports": reports}


def _workflow_report(policy: Dict[str, Any], *, package_root: Path) -> Dict[str, Any]:
    failures: List[str] = []
    sequence = build_task_workflow_sequence(package_root=package_root)
    api = sequence["api"]
    chat = sequence["chat"]
    if not all(api[step].get("ok") for step in ["create", "edit", "prioritize", "block", "complete"]):
        failures.append("api_task_workflow_step_failed")
    if not all(chat[step].get("ok") for step in ["create", "edit", "prioritize", "block", "complete"]):
        failures.append("chat_task_workflow_step_failed")
    if api["edit"]["task"].get("title") != "API edited task":
        failures.append("api_edit_title_not_persisted")
    if int(api["prioritize"]["task"].get("priority") or 0) != 90:
        failures.append("api_priority_not_persisted")
    if api["block"]["task"].get("status") != "blocked":
        failures.append("api_block_not_persisted")
    if api["complete"]["task"].get("status") != "completed":
        failures.append("api_complete_not_persisted")
    if chat["edit"]["task"].get("title") != "Проверить Admin task flow через чат":
        failures.append("chat_edit_title_not_persisted")
    if int(chat["prioritize"]["task"].get("priority") or 0) != 95:
        failures.append("chat_priority_not_persisted")
    if chat["block"]["task"].get("status") != "blocked":
        failures.append("chat_block_not_persisted")
    if chat["complete"]["task"].get("status") != "completed":
        failures.append("chat_complete_not_persisted")
    allowed = set(_as_string_list(policy.get("allowed_statuses")))
    for task in sequence["tasks"].get("tasks", []):
        if task.get("status") not in allowed:
            failures.append(f"task_status_not_allowed:{task.get('status')}")
    return {"failures": failures, "sequence": sequence}


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
    tokens = [str(payload.get("id") or ""), "task add/edit/prioritize/block/complete", "Admin chat and API"]
    reports: List[Dict[str, Any]] = []
    for path in docs:
        text = load_text(path) if path.exists() else ""
        missing = [token for token in tokens if token and token not in text]
        if missing:
            failures.append(f"docs_tokens_missing:{_display_path(path)}:{','.join(missing)}")
        reports.append({"path": _display_path(path), "ok": not missing, "missing": missing})
    return {"failures": failures, "reports": reports}


def validate_task_workflow_policy(
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
    workflow = _workflow_report(policy, package_root=package)
    failures.extend(workflow["failures"])
    docs = _docs_report(payload, project_root=project, package_root=package) if include_docs else {"failures": [], "reports": []}
    failures.extend(docs["failures"])
    metrics = {
        "refs": len(_as_string_list(payload.get("refs"))),
        "resolved_refs": len(ref_report["resolved_refs"]),
        "source_reports": len(source["reports"]),
        "valid_source_reports": sum(1 for item in source["reports"] if item.get("ok")),
        "task_count": len(workflow["sequence"]["tasks"].get("tasks", [])),
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


def benchmark_task_workflow(*, package_root: Path | str, iterations: int = 80) -> Dict[str, Any]:
    root = Path(package_root).resolve()
    policy = load_policy(root / "configs" / "task-workflow-policy.json")
    started = time.perf_counter()
    failures = 0
    for _ in range(iterations):
        report = validate_task_workflow_policy(policy, project_root=root.parent, package_root=root, include_docs=False)
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


def _redact_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: Dict[str, Any] = {}
        for key, item in value.items():
            if key in {"required_api_tokens", "required_chat_tokens"}:
                if isinstance(item, list):
                    redacted[key] = ["***REDACTED***" for _ in item]
                elif item:
                    redacted[key] = "***REDACTED***"
                else:
                    redacted[key] = item
                continue
            redacted[key] = _redact_sensitive(item)
        return redacted
    if isinstance(value, list):
        return [_redact_sensitive(item) for item in value]
    if isinstance(value, str):
        if value.startswith("source_token_missing:"):
            return "source_token_missing:***REDACTED***"
        if ":" in value:
            prefix, _, suffix = value.partition(":")
            if prefix.endswith("_token_missing") and suffix:
                return f"{prefix}:***REDACTED***"
    return value


def build_summary(report: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "apiVersion": API_VERSION,
        "kind": "TaskWorkflowValidationSummary",
        "ok": bool(report.get("ok")),
        "id": report.get("id"),
        "version": report.get("version"),
        "metrics": report.get("metrics", {}),
        "failures": report.get("failures", []),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate NoemaForge Admin task workflow through chat and API")
    parser.add_argument("--policy", default=str(SRC_DIR.parent / "configs" / "task-workflow-policy.json"))
    parser.add_argument("--project-root", default=str(SRC_DIR.parent.parent))
    parser.add_argument("--package-root", default=str(SRC_DIR.parent))
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--skip-docs", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = validate_task_workflow_policy(
        load_policy(args.policy),
        project_root=Path(args.project_root),
        package_root=Path(args.package_root),
        policy_path=Path(args.policy),
        include_docs=not args.skip_docs,
    )
    output = build_summary(report) if args.summary else report
    print(json.dumps(_redact_sensitive(output), ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
