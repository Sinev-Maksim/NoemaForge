#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/model_selection_continue_idempotency_runtime.py
Zone: release/package
Version: 0.31.21.alpha
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate GUI Continue model selection idempotency across refresh/retry.
Inputs: model-selection-continue-idempotency policy and Admin GUI server source.
Outputs: JSON-compatible ModelSelectionContinueIdempotencyValidationReport artifacts.
Side effects: None; CLI writes JSON to stdout.
Tests: noemaforge/tests/test_model_selection_continue_idempotency_runtime.py
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
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Sequence


SRC_DIR = Path(__file__).resolve().parent
API_VERSION = "noemaforge.model-selection-continue-idempotency/v1"
POLICY_KIND = "ModelSelectionContinueIdempotencyPolicy"
REPORT_KIND = "ModelSelectionContinueIdempotencyValidationReport"
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
    if str(policy.get("activation_state") or "") != "gui_continue_model_selection_refresh_safe_idempotency":
        failures.append("policy_activation_state_invalid")
    for key in ["require_docs_and_changelog_refs", "require_no_live_model_dependency"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    for key in ["required_runtime_scripts", "required_gui_tokens", "required_command_parts", "forbidden_runtime_tokens"]:
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
            block = _slice_between(text, "def model_selection_continue", ["def epoch_apply"])
            if not block:
                local_failures.append("model_selection_continue_block_missing")
            for token in _as_string_list(policy.get("required_command_parts")):
                if block and token not in block:
                    local_failures.append(f"continue_command_part_missing:{token}")
            for token in _as_string_list(policy.get("forbidden_runtime_tokens")):
                if block and token in block:
                    local_failures.append(f"continue_forbidden_runtime_token:{token}")
        failures.extend(local_failures)
        reports.append({"ref": ref, "ok": not local_failures, "failures": local_failures, "resolved": resolved})
    return {"failures": failures, "reports": reports}


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


def build_continue_idempotency_sequence(*, package_root: Path | str, mode: str = "full_composite", composite_top_n: int = 4) -> Dict[str, Any]:
    server = build_offline_admin_gui_server(package_root=package_root)
    body = {"mode": mode, "composite_top_n": composite_top_n}
    first = server.model_selection_continue(body)
    after_refresh = server.jobs_list()
    second = server.model_selection_continue(body)
    final_jobs = server.jobs_list()
    jobs = final_jobs.get("jobs", [])
    job_ids = [item.get("job_id") for item in jobs if item.get("idempotency_key") == f"model-selection-continue:{mode}:{composite_top_n}"]
    artifacts = first.get("job", {}).get("artifacts", [])
    return {
        "first": first,
        "after_refresh": after_refresh,
        "second": second,
        "final_jobs": final_jobs,
        "matching_job_ids": job_ids,
        "same_job": first.get("job", {}).get("job_id") == second.get("job", {}).get("job_id"),
        "matching_job_count": len(job_ids),
        "artifact_count": len(artifacts),
        "store_keys": sorted(getattr(server, "_memory_store", {}).keys()),
    }


def _response_report(policy: Dict[str, Any], *, package_root: Path) -> Dict[str, Any]:
    failures: List[str] = []
    sequence = build_continue_idempotency_sequence(package_root=package_root)
    first_job = sequence["first"].get("job") or {}
    second_job = sequence["second"].get("job") or {}
    jobs = sequence["final_jobs"].get("jobs") or []
    safe_command = str(first_job.get("safe_command") or first_job.get("command") or "")
    if sequence["matching_job_count"] != 1:
        failures.append("duplicate_active_continue_jobs")
    if not sequence["same_job"]:
        failures.append("repeat_continue_did_not_return_same_job")
    if first_job.get("job_id") != second_job.get("job_id"):
        failures.append("job_id_changed_between_refresh_attempts")
    if str(first_job.get("status") or "") != "needs_privilege":
        failures.append("job_status_not_needs_privilege")
    if str(first_job.get("idempotency_key") or "") != "model-selection-continue:full_composite:4":
        failures.append("job_idempotency_key_invalid")
    if "safe_command" not in first_job or "real_command_requires_operator_terminal" not in first_job:
        failures.append("job_missing_safe_or_real_command")
    if not any(item.get("type") == "model_selection_continue" for item in first_job.get("artifacts", []) if isinstance(item, dict)):
        failures.append("job_missing_continue_artifact")
    if not jobs or jobs[0].get("safe_command") != first_job.get("safe_command"):
        failures.append("jobs_list_missing_enriched_safe_command_after_refresh")
    for token in _as_string_list(policy.get("required_command_parts")):
        if token not in safe_command:
            failures.append(f"safe_command_part_missing:{token}")
    return {"failures": failures, "sequence": sequence}


def validate_model_selection_continue_idempotency_policy(
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
        "matching_job_count": response["sequence"]["matching_job_count"],
        "artifact_count": response["sequence"]["artifact_count"],
        "required_command_parts": len(_as_string_list(policy.get("required_command_parts"))),
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
        "kind": "ModelSelectionContinueIdempotencyValidationSummary",
        "ok": bool(report.get("ok")),
        "id": report.get("id"),
        "version": report.get("version"),
        "metrics": report.get("metrics", {}),
        "failures": report.get("failures", []),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate NoemaForge GUI Continue model selection idempotency contract")
    parser.add_argument("--policy", default=str(SRC_DIR.parent / "configs" / "model-selection-continue-idempotency-policy.json"))
    parser.add_argument("--project-root", default=str(SRC_DIR.parent.parent))
    parser.add_argument("--package-root", default=str(SRC_DIR.parent))
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = validate_model_selection_continue_idempotency_policy(
        load_policy(args.policy),
        project_root=Path(args.project_root),
        package_root=Path(args.package_root),
        policy_path=Path(args.policy),
    )
    print(json.dumps(build_summary(report) if args.summary else report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
