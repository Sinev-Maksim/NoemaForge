#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/vault_reinventory_job_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate GUI Vault re-inventory returns a privileged job and fallback command.
Inputs: vault-reinventory-job policy, Admin GUI server source and CLI dispatcher.
Outputs: JSON-compatible VaultReinventoryJobValidationReport artifacts.
Side effects: None; CLI writes JSON to stdout.
Tests: noemaforge/tests/test_vault_reinventory_job_runtime.py
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
API_VERSION = "noemaforge.vault-reinventory-job/v1"
POLICY_KIND = "VaultReinventoryJobPolicy"
REPORT_KIND = "VaultReinventoryJobValidationReport"
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
    if str(policy.get("activation_state") or "") != "vault_reinventory_privileged_job_fallback_command_regression":
        failures.append("policy_activation_state_invalid")
    for key in ["require_docs_and_changelog_refs", "require_no_live_gui_dependency"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    for key in [
        "required_runtime_scripts",
        "required_gui_tokens",
        "required_cli_tokens",
        "required_command_parts",
        "forbidden_runtime_tokens",
    ]:
        if not _as_string_list(policy.get(key)):
            failures.append(f"policy_{key}_empty")
    return failures


def _slice_between(text: str, start_marker: str, end_markers: Sequence[str]) -> str:
    start = text.find(start_marker)
    if start < 0:
        return ""
    ends = [text.find(marker, start + len(start_marker)) for marker in end_markers]
    ends = [pos for pos in ends if pos > start]
    end = min(ends) if ends else len(text)
    return text[start:end]


def _script_reports(policy: Dict[str, Any], *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    failures: List[str] = []
    reports: List[Dict[str, Any]] = []
    for ref in _as_string_list(policy.get("required_runtime_scripts")):
        resolved = _resolve_ref(ref, project_root=project_root, package_root=package_root)
        text = load_text(resolved["path"]) if resolved.get("ok") else ""
        local_failures: List[str] = []
        if not resolved.get("ok"):
            local_failures.append(f"script_missing:{ref}")
        if ref.endswith("admin_gui_server.py"):
            for token in _as_string_list(policy.get("required_gui_tokens")):
                if text and token not in text:
                    local_failures.append(f"admin_gui_token_missing:{token}")
            block = _slice_between(text, "def vault_reinventory", ["def model_evolution", "def task_"])
            if not block:
                local_failures.append("vault_reinventory_block_missing")
            for token in _as_string_list(policy.get("required_command_parts")):
                if block and token not in block:
                    local_failures.append(f"vault_reinventory_command_part_missing:{token}")
            for token in _as_string_list(policy.get("forbidden_runtime_tokens")):
                if block and token in block:
                    local_failures.append(f"vault_reinventory_forbidden_runtime_token:{token}")
        elif ref.endswith("bin/noemaforge"):
            for token in _as_string_list(policy.get("required_cli_tokens")):
                if text and token not in text:
                    local_failures.append(f"cli_token_missing:{token}")
        failures.extend(local_failures)
        reports.append({"ref": ref, "ok": not local_failures, "failures": local_failures, "resolved": resolved})
    return {"failures": failures, "reports": reports}


def build_offline_admin_gui_server(*, package_root: Path | str) -> Any:
    if str(SRC_DIR) not in sys.path:
        sys.path.insert(0, str(SRC_DIR))
    import admin_gui_server  # type: ignore

    root = Path(package_root).resolve()
    data_root = root / "_memory_only_gui_state"
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
    server._read_json = lambda _path, default: default
    server._write_json = lambda _path, _obj: None
    server._append_jsonl = lambda _path, _obj: None
    return server


def build_vault_reinventory_response(*, package_root: Path | str) -> Dict[str, Any]:
    server = build_offline_admin_gui_server(package_root=package_root)
    return server.vault_reinventory()


def _response_report(policy: Dict[str, Any], *, package_root: Path) -> Dict[str, Any]:
    failures: List[str] = []
    response = build_vault_reinventory_response(package_root=package_root)
    command = str(response.get("fallback_command") or response.get("suggested_command") or "")
    job = response.get("job") if isinstance(response.get("job"), dict) else {}
    artifacts = job.get("artifacts") if isinstance(job.get("artifacts"), list) else []
    if response.get("ok") is not True:
        failures.append("response_not_ok")
    if response.get("privilege_required") is not True:
        failures.append("response_privilege_required_not_true")
    if str(job.get("status") or "") != "needs_privilege":
        failures.append("job_status_not_needs_privilege")
    if str(job.get("kind") or "") != "vault_reinventory":
        failures.append("job_kind_not_vault_reinventory")
    if str(job.get("idempotency_key") or "") != "vault-reinventory":
        failures.append("job_idempotency_key_invalid")
    if command != str(job.get("command") or ""):
        failures.append("fallback_command_not_equal_job_command")
    if not any(item.get("type") == "privileged_fallback_command" and item.get("command") == command for item in artifacts if isinstance(item, dict)):
        failures.append("job_missing_privileged_fallback_command_artifact")
    for token in _as_string_list(policy.get("required_command_parts")):
        if token not in command:
            failures.append(f"response_command_part_missing:{token}")
    if "gui_plan_only" not in str(response.get("execution_policy") or ""):
        failures.append("response_execution_policy_not_gui_plan_only")
    return {"failures": failures, "response": response}


def validate_vault_reinventory_job_policy(
    payload: Dict[str, Any],
    *,
    project_root: Path | str,
    package_root: Path | str,
    policy_path: Path | str | None = None,
) -> Dict[str, Any]:
    project = Path(project_root).resolve()
    package = Path(package_root).resolve()
    policy = _policy_dict(payload)
    failures: List[str] = []
    failures.extend(_policy_failures(payload))
    ref_report = _resolve_refs(_as_string_list(payload.get("refs")), project_root=project, package_root=package, owner=str(payload.get("id") or "policy"))
    failures.extend(ref_report["failures"])
    scripts = _script_reports(policy, project_root=project, package_root=package)
    failures.extend(scripts["failures"])
    response = _response_report(policy, package_root=package)
    failures.extend(response["failures"])
    metrics = {
        "refs": len(_as_string_list(payload.get("refs"))),
        "resolved_refs": len(ref_report["resolved_refs"]),
        "script_reports": len(scripts["reports"]),
        "valid_script_reports": sum(1 for item in scripts["reports"] if item.get("ok")),
        "required_command_parts": len(_as_string_list(policy.get("required_command_parts"))),
        "response_artifacts": len(((response.get("response") or {}).get("job") or {}).get("artifacts") or []),
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
        "scripts": scripts,
        "response": response,
    }


def build_summary(report: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "apiVersion": API_VERSION,
        "kind": "VaultReinventoryJobValidationSummary",
        "ok": bool(report.get("ok")),
        "id": report.get("id"),
        "version": report.get("version"),
        "metrics": report.get("metrics", {}),
        "failures": report.get("failures", []),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate NoemaForge GUI Vault re-inventory job/fallback contract")
    parser.add_argument("--policy", default=str(SRC_DIR.parent / "configs" / "vault-reinventory-job-policy.json"))
    parser.add_argument("--project-root", default=str(SRC_DIR.parent.parent))
    parser.add_argument("--package-root", default=str(SRC_DIR.parent))
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = validate_vault_reinventory_job_policy(
        load_policy(args.policy),
        project_root=Path(args.project_root),
        package_root=Path(args.package_root),
        policy_path=Path(args.policy),
    )
    print(json.dumps(build_summary(report) if args.summary else report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
