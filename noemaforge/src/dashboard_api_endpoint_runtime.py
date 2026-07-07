#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/dashboard_api_endpoint_runtime.py
Zone: gui/control-plane
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-28
Purpose: Validate the dedicated installed Admin GUI dashboard backend endpoint contract.
Inputs: Dashboard API endpoint policy, Admin GUI source, dashboard UI source and Unified Registry.
Outputs: JSON-compatible DashboardApiEndpointValidationReport artifacts.
Side effects: None; tests create only in-memory fixtures.
Tests: noemaforge/tests/test_dashboard_api_endpoint_runtime.py
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

import unified_registry_runtime as urr
from noemaforge_version import RUNTIME_VERSION


API_VERSION = "noemaforge.dashboard-api-endpoint/v1"
POLICY_KIND = "DashboardApiEndpointPolicy"
REPORT_KIND = "DashboardApiEndpointValidationReport"
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


def load_json(path: Path | str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


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
    for key in ["local_first_default", "require_registry_attachment", "require_docs_and_changelog_refs"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    if policy.get("endpoint") != "/api/dashboard":
        failures.append("policy_endpoint_invalid")
    if policy.get("alias_endpoint") != "/api/dashboard/state":
        failures.append("policy_alias_endpoint_invalid")
    if policy.get("compatibility_endpoint") != "/api/gui/state":
        failures.append("policy_compatibility_endpoint_invalid")
    for key in ["required_api_paths", "required_runtime_tokens", "required_frontend_tokens", "required_sections", "required_docs"]:
        if not _as_string_list(policy.get(key)):
            failures.append(f"policy_{key}_empty")
    return failures


def _registry_ref(entry: Dict[str, Any]) -> str:
    return f"{entry.get('kind')}:{entry.get('id')}:{entry.get('version')}"


def _registry_failures(payload: Dict[str, Any], *, project_root: Path, package_root: Path, registry_path: Path) -> Dict[str, Any]:
    registry = urr.load_registry(registry_path)
    report = urr.validate_unified_registry(registry, project_root=project_root, package_root=package_root, registry_path=registry_path)
    failures = [f"registry_invalid:{item}" for item in report.get("failures", [])]
    entries = {_registry_ref(entry): entry for entry in report.get("normalized_registry", {}).get("entries", []) if isinstance(entry, dict)}
    raw_entries = {_registry_ref(entry): entry for entry in registry.get("entries", []) if isinstance(entry, dict)}
    eval_ref = f"eval-pack:{payload.get('id')}:{payload.get('version')}"
    if eval_ref not in entries:
        failures.append(f"registry_eval_pack_missing:{eval_ref}")
    pipeline_ref = "pipeline:firstboot-model-selection:0.32.1"
    pipeline = raw_entries.get(pipeline_ref) or entries.get(pipeline_ref)
    if not pipeline:
        failures.append(f"registry_pipeline_missing:{pipeline_ref}")
    else:
        if eval_ref not in _as_string_list(pipeline.get("eval_pack_refs")):
            failures.append(f"registry_pipeline_eval_pack_missing:{eval_ref}")
        for ref in ["configs/dashboard-api-endpoint-policy.json", "src/dashboard_api_endpoint_runtime.py", "src/admin_gui_server.py"]:
            if ref not in _as_string_list(pipeline.get("refs")):
                failures.append(f"registry_pipeline_ref_missing:{ref}")
    return {"failures": failures, "entries": entries, "registry_report": report}


def _source_failures(policy: Dict[str, Any], *, package_root: Path) -> Dict[str, Any]:
    failures: List[str] = []
    server_text = load_text(package_root / "src" / "admin_gui_server.py")
    app_text = load_text(package_root / "templates" / "pipeline-dashboard" / "app.js")
    for token in _as_string_list(policy.get("required_api_paths")) + _as_string_list(policy.get("required_runtime_tokens")):
        if token not in server_text:
            failures.append(f"server_token_missing:{token}")
    for token in _as_string_list(policy.get("required_frontend_tokens")):
        if token not in app_text:
            failures.append(f"frontend_token_missing:{token}")
    if app_text.find("/api/dashboard") > app_text.find("/api/gui/state"):
        failures.append("frontend_dashboard_endpoint_not_preferred")
    return {"failures": failures, "source_lengths": {"admin_gui_server": len(server_text), "app_js": len(app_text)}}


def _docs_failures(*, project_root: Path, policy: Dict[str, Any]) -> Dict[str, Any]:
    failures: List[str] = []
    docs_seen: List[str] = []
    for rel in _as_string_list(policy.get("required_docs")):
        path = project_root / rel
        text = load_text(path) if path.exists() else ""
        if not text:
            failures.append(f"doc_missing:{rel}")
            continue
        docs_seen.append(rel)
        if "dashboard-api-endpoint-core" not in text:
            failures.append(f"doc_token_missing:{rel}:dashboard-api-endpoint-core")
    return {"failures": failures, "docs_seen": docs_seen}


def build_offline_dashboard_server(*, package_root: Path | str) -> Any:
    import admin_gui_server  # type: ignore

    root = Path(package_root).resolve()
    server = object.__new__(admin_gui_server.AdminGuiServer)
    server.root = root
    server.state = root / "_offline" / "pipeline-state"
    server.gui_state_dir = root / "_offline" / "gui"
    server.health = lambda: {"ok": True, "version": RUNTIME_VERSION, "api": ["/api/dashboard", "/api/dashboard/state", "/api/gui/state"]}
    server.dashboard_state = lambda: {"ok": True, "version": RUNTIME_VERSION, "source": "offline_dashboard_api_fixture"}
    server.conversation_history = lambda: {"conversation_id": "conv_dashboard_api", "messages": [], "artifacts": []}
    server.epoch_status = lambda: {"ok": True, "epoch": "offline"}
    server.telemetry_status = lambda: {"ok": True, "hardware": {}, "runtime": {}, "product": {}}
    server.tasks_list = lambda: {"ok": True, "summary": {"pending": 0, "blocked": 0}, "tasks": []}
    server.jobs_list = lambda: {"ok": True, "jobs": []}
    server.persona_current = lambda: {"ok": True, "active_persona": "Admin", "portrait_url": ""}
    server.inactivity_status = lambda: {"ok": True, "status": "manual"}
    server.pipeline_catalog_api = lambda: {"ok": True, "pipelines": [{"id": "offline-dashboard"}], "groups": ["offline"]}
    return server


def _workflow_failures(policy: Dict[str, Any], *, package_root: Path) -> Dict[str, Any]:
    server = build_offline_dashboard_server(package_root=package_root)
    payload = server.dashboard_api()
    failures: List[str] = []
    if payload.get("endpoint") != "/api/dashboard":
        failures.append("dashboard_endpoint_missing")
    backend = payload.get("dashboard_backend") if isinstance(payload.get("dashboard_backend"), dict) else {}
    if backend.get("contract") != "dashboard-api-endpoint-core":
        failures.append("dashboard_backend_contract_missing")
    for section in _as_string_list(policy.get("required_sections")):
        if section not in payload:
            failures.append(f"dashboard_section_missing:{section}")
    dashboard = payload.get("dashboard") if isinstance(payload.get("dashboard"), dict) else {}
    if dashboard.get("backend_endpoint") != "/api/dashboard":
        failures.append("dashboard_backend_endpoint_marker_missing")
    return {"failures": failures, "payload": payload}


def validate_dashboard_api_endpoint_policy(payload: Dict[str, Any], *, project_root: Path, package_root: Path, registry_path: Path) -> Dict[str, Any]:
    started = time.perf_counter()
    policy = _policy_dict(payload)
    failures: List[str] = []
    ref_report = _resolve_refs(_as_string_list(payload.get("refs")), project_root=project_root, package_root=package_root, owner=str(payload.get("id") or "dashboard-api-endpoint-core"))
    source = _source_failures(policy, package_root=package_root)
    docs = _docs_failures(project_root=project_root, policy=policy)
    registry = _registry_failures(payload, project_root=project_root, package_root=package_root, registry_path=registry_path)
    workflow = _workflow_failures(policy, package_root=package_root)
    for part in [_policy_failures(payload), ref_report["failures"], source["failures"], docs["failures"], registry["failures"], workflow["failures"]]:
        failures.extend(part)
    return {
        "apiVersion": API_VERSION,
        "kind": REPORT_KIND,
        "created_at": _nowz(),
        "ok": not failures,
        "failures": failures,
        "metrics": {
            "api_paths": len(_as_string_list(policy.get("required_api_paths"))),
            "runtime_tokens": len(_as_string_list(policy.get("required_runtime_tokens"))),
            "frontend_tokens": len(_as_string_list(policy.get("required_frontend_tokens"))),
            "required_sections": len(_as_string_list(policy.get("required_sections"))),
            "docs_seen": len(docs["docs_seen"]),
            "registry_entries": len(registry["entries"]),
            "duration_ms": round((time.perf_counter() - started) * 1000, 3),
        },
        "refs": ref_report,
        "source": source,
        "docs": docs,
        "workflow": workflow,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate dashboard API endpoint contract.")
    parser.add_argument("--project-root", default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument("--package-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--policy", default="configs/dashboard-api-endpoint-policy.json")
    parser.add_argument("--registry", default="configs/unified-registry.json")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(argv)
    project_root = Path(args.project_root).resolve()
    package_root = Path(args.package_root).resolve()
    policy_path = (package_root / args.policy).resolve()
    registry_path = (package_root / args.registry).resolve()
    report = validate_dashboard_api_endpoint_policy(load_json(policy_path), project_root=project_root, package_root=package_root, registry_path=registry_path)
    if args.summary:
        keep = {k: report[k] for k in ["apiVersion", "kind", "created_at", "ok", "failures", "metrics"]}
        print(json.dumps(keep, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
