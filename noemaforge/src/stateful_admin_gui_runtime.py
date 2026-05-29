#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/stateful_admin_gui_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate the installed Admin GUI state restore and primary surface hydration contract.
Inputs: stateful-admin-gui policy, Admin GUI server source, dashboard UI source and local catalogs.
Outputs: JSON-compatible StatefulAdminGuiValidationReport artifacts.
Side effects: None; CLI writes JSON to stdout.
Tests: noemaforge/tests/test_stateful_admin_gui_runtime.py
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
import time
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Sequence


SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
from noemaforge_version import RUNTIME_VERSION
API_VERSION = "noemaforge.stateful-admin-gui/v1"
POLICY_KIND = "StatefulAdminGuiPolicy"
REPORT_KIND = "StatefulAdminGuiValidationReport"
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
    if str(policy.get("activation_state") or "") != "install_state_restore_and_surface_hydration":
        failures.append("policy_activation_state_invalid")
    for key in ["require_docs_and_changelog_refs", "require_no_live_gui_dependency"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    for key in [
        "required_runtime_scripts",
        "required_ui_files",
        "required_api_paths",
        "required_runtime_tokens",
        "required_ui_tokens",
        "required_gui_state_sections",
        "required_surface_assertions",
    ]:
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
    server.ui_dir = root / "templates" / "pipeline-dashboard"

    def read_json(path: Path, default: Any) -> Any:
        key = _display_path(Path(path))
        if key in store:
            return copy.deepcopy(store[key])
        p = Path(path)
        if root in p.resolve().parents or p.resolve() == root:
            try:
                if p.exists():
                    return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                return copy.deepcopy(default)
        if "firstboot-staffing-summary.json" in key:
            return {"staffing_state": "partial", "selected_model_count": 2, "missing_mandatory_core_roles": ["research"]}
        if "model-selection-decision.json" in key:
            return {"mode": "normal", "status": "selection_ready_no_apply"}
        if "model-inventory.json" in key:
            return {"summary": {"logical_models_total": 3}, "models": [{"id": "main"}, {"id": "writer"}, {"id": "dev"}]}
        if "model-health-registry.json" in key:
            return {"models": {}}
        if "model-run-records.json" in key:
            return [{"model_id": "main"}]
        if "firstboot-status.json" in key:
            return {"status": "ready"}
        return copy.deepcopy(default)

    def write_json(path: Path, obj: Any) -> None:
        store[_display_path(Path(path))] = copy.deepcopy(obj)

    def append_jsonl(path: Path, obj: Dict[str, Any]) -> None:
        key = _display_path(Path(path))
        store.setdefault(key, []).append(copy.deepcopy(obj))

    server._memory_store = store
    server._read_json = read_json
    server._write_json = write_json
    server._append_jsonl = append_jsonl
    server._command_output = lambda cmd, timeout=8: {"available": False, "cmd": list(cmd), "stdout": "", "stderr": "offline fixture"}
    server.runtime_status = lambda: {
        "ok": True,
        "version": RUNTIME_VERSION,
        "device_policy": {"policy": "auto", "pending_apply": False},
        "sockets": {},
        "gateway": {"ok": False, "stdout": "offline fixture"},
        "main_backend": {"ok": False, "stdout": "inactive"},
        "main_manifest": {"model_id": "fixture-main"},
    }
    server.dashboard_state = lambda: {
        "ok": True,
        "version": RUNTIME_VERSION,
        "admin_gui": {"ok": True, "version": RUNTIME_VERSION},
        "source": "offline_stateful_gui_fixture",
    }
    return server


def build_stateful_gui_fixture(*, package_root: Path | str) -> Dict[str, Any]:
    server = build_offline_admin_gui_server(package_root=package_root)
    server.save_message("user", "Validate stateful Admin GUI after install", persona="Admin", locale="en", intent="stateful_gui_install_validation")
    server.save_message("admin", "State restore fixture ready", persona="Admin", locale="en", intent="stateful_gui_install_validation")
    pending = server.task_create({"title": "Validate stateful GUI task queue", "category": "gui", "priority": 70})
    blocked = server.task_create({"title": "Validate stateful GUI blocked lane", "category": "gui", "priority": 60})
    server.task_block({"task_id": blocked["task"]["task_id"], "reason": "offline fixture checks blocked summary"})
    job = server.create_job(
        "stateful_admin_gui_install_validation",
        status="queued",
        progress={"phase": "hydrate_admin_gui_surfaces"},
        command="offline-contract",
        artifacts=[{"type": "stateful_gui_contract", "status": "created", "label": "offline fixture"}],
        idempotency_key="stateful-admin-gui-install-validation",
    )
    server.save_message("admin", "Stateful Admin GUI surfaces hydrated", persona="Admin", locale="en", intent="stateful_gui_install_validation")
    gui_state = server.gui_state()
    return {
        "ok": True,
        "version": RUNTIME_VERSION,
        "conversation_current": server.conversation_current(),
        "conversation_history": server.conversation_history(),
        "persona": server.persona_current(),
        "tasks": server.tasks_list(),
        "jobs": server.jobs_list(),
        "telemetry": server.telemetry_status(),
        "pipelines": server.pipeline_catalog_api(),
        "gui_state": gui_state,
        "seeded": {"pending_task_id": pending["task"]["task_id"], "blocked_task_id": blocked["task"]["task_id"], "job_id": job["job_id"]},
        "store_keys": sorted(getattr(server, "_memory_store", {}).keys()),
    }


def _source_report(policy: Dict[str, Any], *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    failures: List[str] = []
    reports: List[Dict[str, Any]] = []
    source_texts: Dict[str, str] = {}
    refs = _as_string_list(policy.get("required_runtime_scripts")) + _as_string_list(policy.get("required_ui_files"))
    for ref in refs:
        resolved = _resolve_ref(ref, project_root=project_root, package_root=package_root)
        text = load_text(resolved["path"]) if resolved.get("ok") else ""
        source_texts[ref] = text
        local_failures: List[str] = []
        if not resolved.get("ok"):
            local_failures.append(f"source_missing:{ref}")
        reports.append({"ref": ref, "ok": not local_failures, "failures": local_failures, "resolved": resolved})
        failures.extend(local_failures)
    admin_gui = source_texts.get("noemaforge/src/admin_gui_server.py", "")
    ui_text = "\n".join(source_texts.get(ref, "") for ref in _as_string_list(policy.get("required_ui_files")))
    for token in _as_string_list(policy.get("required_api_paths")) + _as_string_list(policy.get("required_runtime_tokens")):
        if token not in admin_gui:
            failures.append(f"runtime_token_missing:{token}")
    for token in _as_string_list(policy.get("required_ui_tokens")):
        if token not in ui_text:
            failures.append(f"ui_token_missing:{token}")
    return {"failures": failures, "reports": reports, "admin_gui_chars": len(admin_gui), "ui_chars": len(ui_text)}


def _workflow_report(policy: Dict[str, Any], *, package_root: Path) -> Dict[str, Any]:
    failures: List[str] = []
    fixture = build_stateful_gui_fixture(package_root=package_root)
    state = fixture.get("gui_state", {})
    current = fixture.get("conversation_current", {}).get("conversation", {})
    history = fixture.get("conversation_history", {})
    persona = fixture.get("persona", {})
    tasks = fixture.get("tasks", {})
    jobs = fixture.get("jobs", {})
    telemetry = fixture.get("telemetry", {})
    pipelines = fixture.get("pipelines", {})

    for section in _as_string_list(policy.get("required_gui_state_sections")):
        if section not in state:
            failures.append(f"gui_state_section_missing:{section}")
    if current.get("conversation_id") != history.get("conversation_id"):
        failures.append("conversation_current_history_id_mismatch")
    if len(history.get("messages", [])) < 2:
        failures.append("conversation_restore_messages_missing")
    if not any(item.get("intent") == "stateful_gui_install_validation" for item in history.get("messages", [])):
        failures.append("conversation_restore_intent_missing")
    if persona.get("active_persona") != "Admin":
        failures.append("persona_active_admin_missing")
    if not str(persona.get("portrait_url") or "").endswith(".svg"):
        failures.append("persona_portrait_svg_url_missing")
    if persona.get("fallback") is not False:
        failures.append("persona_portrait_real_asset_not_used")
    summary = tasks.get("summary", {}) if isinstance(tasks.get("summary"), dict) else {}
    if int(summary.get("total") or 0) < 2 or int(summary.get("pending") or 0) < 1 or int(summary.get("blocked") or 0) < 1:
        failures.append("task_queue_summary_not_hydrated")
    if not any(job.get("kind") == "stateful_admin_gui_install_validation" for job in jobs.get("jobs", [])):
        failures.append("job_panel_validation_job_missing")
    for section in ["hardware", "runtime", "product"]:
        if section not in telemetry:
            failures.append(f"telemetry_section_missing:{section}")
    if not pipelines.get("pipelines") or not pipelines.get("groups"):
        failures.append("pipeline_dock_catalog_empty")
    if pipelines.get("new_pipeline_supported") != "draft_only":
        failures.append("pipeline_dock_new_pipeline_not_draft_only")
    if not state.get("dashboard", {}).get("ok"):
        failures.append("gui_state_dashboard_not_available")
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
        "conversation restore, persona portrait, task queue, job panel, telemetry and pipeline dock",
        "stateful Admin GUI",
    ]
    reports: List[Dict[str, Any]] = []
    for path in docs:
        text = load_text(path) if path.exists() else ""
        missing = [token for token in tokens if token and token not in text]
        if missing:
            failures.append(f"docs_tokens_missing:{_display_path(path)}:{','.join(missing)}")
        reports.append({"path": _display_path(path), "ok": not missing, "missing": missing})
    return {"failures": failures, "reports": reports}


def validate_stateful_admin_gui_policy(
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
        "surface_count": len(_as_string_list(policy.get("required_surface_assertions"))),
        "docs_reports": len(docs["reports"]),
        "admin_gui_chars": source["admin_gui_chars"],
        "ui_chars": source["ui_chars"],
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


def benchmark_stateful_admin_gui(*, package_root: Path | str, iterations: int = 60) -> Dict[str, Any]:
    root = Path(package_root).resolve()
    policy = load_policy(root / "configs" / "stateful-admin-gui-policy.json")
    started = time.perf_counter()
    failures = 0
    for _ in range(iterations):
        report = validate_stateful_admin_gui_policy(policy, project_root=root.parent, package_root=root, include_docs=False)
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
        "kind": "StatefulAdminGuiValidationSummary",
        "ok": bool(report.get("ok")),
        "id": report.get("id"),
        "version": report.get("version"),
        "metrics": report.get("metrics", {}),
        "failures": report.get("failures", []),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate NoemaForge stateful Admin GUI install surfaces")
    parser.add_argument("--policy", default=str(SRC_DIR.parent / "configs" / "stateful-admin-gui-policy.json"))
    parser.add_argument("--project-root", default=str(SRC_DIR.parent.parent))
    parser.add_argument("--package-root", default=str(SRC_DIR.parent))
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--skip-docs", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = validate_stateful_admin_gui_policy(
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
