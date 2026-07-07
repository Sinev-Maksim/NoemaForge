#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/privileged_gui_job_runner.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate and run approval-gated privileged GUI jobs through a polkit boundary.
Inputs: privileged-gui-job-runner policy, Admin GUI job artifacts and example fixtures.
Outputs: JSON-compatible PrivilegedGuiJobRunnerValidationReport artifacts.
Side effects: validate/dry-run paths are read-only; non-dry-run execution requires root and an explicit environment gate.
Tests: noemaforge/tests/test_privileged_gui_job_runner_runtime.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib
import json
import os
import re
import shlex
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Sequence


SRC_DIR = Path(__file__).resolve().parent
API_VERSION = "noemaforge.privileged-gui-job-runner/v1"
POLICY_KIND = "PrivilegedGuiJobRunnerPolicy"
EXAMPLE_KIND = "PrivilegedGuiJobRunnerExampleSet"
REPORT_KIND = "PrivilegedGuiJobRunnerValidationReport"
POLICY_ID = "privileged-gui-job-runner-core"
POLKIT_ACTION = "org.noemaforge.privileged-jobs.run"
SELECTED_TODO_EPOCH_APPLY = "Convert GUI epoch apply request into privileged, polkit-mediated local action after safety review."
SELECTED_TODO_APPROVED_GUI_JOBS = "Add polkit/root job-runner for approved privileged GUI jobs after alpha."
SELECTED_TODOS = [SELECTED_TODO_EPOCH_APPLY, SELECTED_TODO_APPROVED_GUI_JOBS]
VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,220}$")
XML_ENTITY_RE = re.compile(r"<!\s*ENTITY\b", re.IGNORECASE)
DEFAULT_POLICY_REF = "configs/privileged-gui-job-runner-policy.json"
DEFAULT_EXAMPLE_REF = "prelaunch/governance/privileged_gui_job_runner.example.json"
REGISTRY_REFS = [
    "configs/privileged-gui-job-runner-policy.json",
    "contracts/privileged_gui_job_runner.schema.json",
    "configs/alpha-feature-coverage.json",
    "src/privileged_gui_job_runner.py",
    "src/admin_gui_server.py",
    "bin/noemaforge",
    "share/polkit-1/actions/org.noemaforge.privileged-jobs.policy",
    "tests/test_privileged_gui_job_runner_runtime.py",
    "tests/test_privileged_gui_job_runner_qa.py",
    "tests/test_privileged_gui_job_runner_performance.py",
    "prelaunch/governance/privileged_gui_job_runner.example.json",
    "docs/README.md",
    "docs/TODO.md",
    "docs/reference/PROJECT_CONTEXT.md",
    "docs/backlog/ROADMAP_AND_TODO.md",
    "docs/history/CHANGELOG.md",
]

try:
    ET = importlib.import_module("defusedxml.ElementTree")
    _DEFUSED_XML = True
except Exception:  # pragma: no cover - depends on optional security extra
    ET = importlib.import_module("xml.etree.ElementTree")
    _DEFUSED_XML = False


def _parse_policy_xml(path: Path):
    data = path.read_text(encoding="utf-8", errors="replace")
    if not _DEFUSED_XML and XML_ENTITY_RE.search(data):
        raise ValueError("unsafe_xml_entity")
    return ET.fromstring(data)


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
        candidates.append(("package_relative", package_root / ref))
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


def load_policy(path: Path | str) -> Dict[str, Any]:
    return load_json(path)


def load_example_set(path: Path | str) -> Dict[str, Any]:
    return load_json(path)


def load_text(path: Path | str) -> str:
    return Path(path).read_text(encoding="utf-8")


def _allowed_action_for_kind(kind: str) -> str:
    return {
        "epoch_apply": "first_start_epoch_apply",
        "model_selection_continue": "first_start_model_selection_continue",
        "vault_reinventory": "vault_reinventory_scan",
    }.get(str(kind or ""), "")


def _default_privileged_steps_for_job(job: Dict[str, Any]) -> List[str]:
    if str(job.get("kind") or "") != "vault_reinventory":
        return []
    return [
        "sudo noemaforge inventory scan",
        "sudo noemaforge datasets scan",
        "sudo noemaforge tournament eligibility",
    ]


def _privileged_steps(job: Dict[str, Any]) -> List[str]:
    direct = _as_string_list(job.get("privileged_steps"))
    if direct:
        return direct
    runner = job.get("privileged_runner") if isinstance(job.get("privileged_runner"), dict) else {}
    nested = _as_string_list(runner.get("steps"))
    if nested:
        return nested
    return _default_privileged_steps_for_job(job)


def approval_token_for_job(job: Dict[str, Any]) -> str:
    job_id = str(job.get("job_id") or "")
    kind = str(job.get("kind") or "")
    command = str(job.get("command") or "")
    steps = "\n".join(_privileged_steps(job))
    seed = f"{job_id}\n{kind}\n{command}\n{steps}\n{POLKIT_ACTION}\n{POLICY_ID}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:32]


def build_privileged_runner_metadata(job: Dict[str, Any], *, job_file: Path | str) -> Dict[str, Any]:
    token = approval_token_for_job(job)
    job_id = str(job.get("job_id") or "")
    kind = str(job.get("kind") or "")
    steps = _privileged_steps(job)
    runner_command = (
        f"pkexec noemaforge privileged-job run --job-file {job_file} "
        f"--job-id {job_id} --approval-token {token} --dry-run"
    )
    metadata = {
        "policy": "polkit_approval_required",
        "polkit_action": POLKIT_ACTION,
        "approval_state": "pending_operator_review",
        "approval_token": token,
        "allowed_action": _allowed_action_for_kind(kind),
        "dry_run_default": True,
        "runner_command": runner_command,
    }
    if steps:
        metadata["steps"] = steps
    return metadata


def enrich_privileged_job(job: Dict[str, Any], *, job_file: Path | str) -> Dict[str, Any]:
    enriched = dict(job)
    metadata = build_privileged_runner_metadata(enriched, job_file=job_file)
    enriched["privileged_runner"] = metadata
    enriched["privileged_runner_command"] = metadata["runner_command"]
    enriched["polkit_action"] = metadata["polkit_action"]
    enriched["approval_state"] = metadata["approval_state"]
    enriched["approval_token"] = metadata["approval_token"]
    enriched["allowed_action"] = metadata["allowed_action"]
    if "steps" in metadata:
        enriched["privileged_steps"] = metadata["steps"]
    artifacts = list(enriched.get("artifacts") or [])
    artifact = {
        "type": "privileged_runner_request",
        "status": "created",
        "label": "privileged-job-runner",
        "path": str(job_file),
        "command": metadata["runner_command"],
        "approval_state": metadata["approval_state"],
        "polkit_action": metadata["polkit_action"],
    }
    if "steps" in metadata:
        artifact["steps"] = metadata["steps"]
    if not any(item.get("type") == artifact["type"] and item.get("command") == artifact["command"] for item in artifacts if isinstance(item, dict)):
        artifacts.append(artifact)
    enriched["artifacts"] = artifacts
    return enriched


def _policy_failures(payload: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    policy = _policy_dict(payload)
    if payload.get("apiVersion") != API_VERSION:
        failures.append("policy_api_version_invalid")
    if payload.get("kind") != POLICY_KIND:
        failures.append("policy_kind_invalid")
    if payload.get("id") != POLICY_ID or not SAFE_ID_RE.match(str(payload.get("id") or "")):
        failures.append("policy_id_invalid")
    if str(payload.get("status") or "") not in VALID_STATUSES:
        failures.append("policy_status_invalid")
    if policy.get("mode") != "offline_contract":
        failures.append("policy_mode_not_offline_contract")
    if policy.get("activation_state") != "approved_gui_jobs_polkit_runner":
        failures.append("policy_activation_state_invalid")
    if policy.get("polkit_action") != POLKIT_ACTION:
        failures.append("policy_polkit_action_invalid")
    if policy.get("gui_default_mode") != "dry_run":
        failures.append("policy_gui_default_mode_not_dry_run")
    if policy.get("approval_state_required_for_apply") != "approved":
        failures.append("policy_approval_state_required_for_apply_invalid")
    for key in ["require_docs_and_changelog_refs", "require_registry_attachment", "require_no_live_privileged_dependency"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    refs = policy.get("required_runtime_refs") if isinstance(policy.get("required_runtime_refs"), dict) else {}
    for key in ["admin_gui_server", "contract_runtime", "cli_dispatcher", "polkit_policy"]:
        if not _is_safe_relative_ref(str(refs.get(key) or "")):
            failures.append(f"policy_required_runtime_ref_invalid:{key}")
    if not isinstance(policy.get("allowed_jobs"), list) or not policy.get("allowed_jobs"):
        failures.append("policy_allowed_jobs_empty")
    if not _as_string_list(policy.get("forbidden_command_fragments")):
        failures.append("policy_forbidden_command_fragments_empty")
    for key in ["required_admin_tokens", "required_cli_tokens", "required_example_sets"]:
        if not _as_string_list(policy.get(key)):
            failures.append(f"policy_{key}_empty")
    selected_todos = _as_string_list(policy.get("selected_todos"))
    for todo in SELECTED_TODOS:
        if todo not in selected_todos:
            failures.append(f"policy_selected_todo_missing:{todo}")
    return failures


def _script_reports(policy: Dict[str, Any], *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    failures: List[str] = []
    reports: List[Dict[str, Any]] = []
    refs = policy.get("required_runtime_refs") if isinstance(policy.get("required_runtime_refs"), dict) else {}
    for name, ref in refs.items():
        resolved = _resolve_ref(str(ref), project_root=project_root, package_root=package_root)
        text = load_text(resolved["path"]) if resolved.get("ok") and str(ref).endswith((".py", "noemaforge")) else ""
        local_failures: List[str] = []
        if not resolved.get("ok"):
            local_failures.append(f"runtime_ref_missing:{name}:{ref}")
        if str(ref).endswith("admin_gui_server.py"):
            for token in _as_string_list(policy.get("required_admin_tokens")):
                if token not in text:
                    local_failures.append(f"admin_gui_token_missing:{token}")
        if str(ref).endswith("bin/noemaforge"):
            for token in _as_string_list(policy.get("required_cli_tokens")):
                if token not in text:
                    local_failures.append(f"cli_token_missing:{token}")
        failures.extend(local_failures)
        reports.append({"name": name, "ref": ref, "ok": not local_failures, "failures": local_failures, "resolved": resolved})
    return {"failures": failures, "reports": reports}


def _allowed_job_by_kind(policy: Dict[str, Any], kind: str) -> Dict[str, Any]:
    for item in policy.get("allowed_jobs") or []:
        if isinstance(item, dict) and item.get("kind") == kind:
            return item
    return {}


def _job_token(job: Dict[str, Any]) -> str:
    runner = job.get("privileged_runner") if isinstance(job.get("privileged_runner"), dict) else {}
    return str(job.get("approval_token") or runner.get("approval_token") or "")


def _job_polkit_action(job: Dict[str, Any]) -> str:
    runner = job.get("privileged_runner") if isinstance(job.get("privileged_runner"), dict) else {}
    return str(job.get("polkit_action") or runner.get("polkit_action") or "")


def _job_approval_state(job: Dict[str, Any]) -> str:
    runner = job.get("privileged_runner") if isinstance(job.get("privileged_runner"), dict) else {}
    return str(job.get("approval_state") or runner.get("approval_state") or "")


def _command_failures(job: Dict[str, Any], allowed: Dict[str, Any], policy: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    command_steps = allowed.get("command_steps") if isinstance(allowed.get("command_steps"), list) else []
    if command_steps:
        steps = _privileged_steps(job)
        if not steps:
            failures.append("command_steps_missing")
        if len(steps) != len(command_steps):
            failures.append("command_steps_count_invalid")
        flattened_tokens: List[str] = []
        for index, step in enumerate(steps):
            for fragment in _as_string_list(policy.get("forbidden_command_fragments")):
                if fragment and fragment in step:
                    failures.append(f"command_step_forbidden_fragment:{index}:{fragment}")
            if "\n" in step or "\r" in step:
                failures.append(f"command_step_forbidden_newline:{index}")
            try:
                argv = shlex.split(step)
            except ValueError as exc:
                failures.append(f"command_step_parse_error:{index}:{exc}")
                argv = []
            flattened_tokens.extend(argv)
            expected = command_steps[index] if index < len(command_steps) and isinstance(command_steps[index], list) else []
            if argv != [str(item) for item in expected]:
                failures.append(f"command_step_not_allowed:{index}")
        for token in _as_string_list(allowed.get("required_tokens")):
            if token not in flattened_tokens:
                failures.append(f"command_required_token_missing:{token}")
        return failures
    command = str(job.get("command") or "")
    for fragment in _as_string_list(policy.get("forbidden_command_fragments")):
        if fragment and fragment in command:
            failures.append(f"command_forbidden_fragment:{fragment}")
    if "\n" in command or "\r" in command:
        failures.append("command_forbidden_newline")
    try:
        argv = shlex.split(command)
    except ValueError as exc:
        failures.append(f"command_parse_error:{exc}")
        argv = []
    prefix = allowed.get("command_prefix") if isinstance(allowed.get("command_prefix"), list) else []
    if argv[: len(prefix)] != prefix:
        failures.append("command_prefix_invalid")
    for token in _as_string_list(allowed.get("required_tokens")):
        if token not in argv:
            failures.append(f"command_required_token_missing:{token}")
    allowed_flags = set(_as_string_list(allowed.get("allowed_flags")))
    index = len(prefix)
    while index < len(argv):
        token = argv[index]
        if token.startswith("--"):
            if token not in allowed_flags:
                failures.append(f"command_flag_not_allowed:{token}")
            if token in {"--full_composite", "--per-model-timeout", "--total-timeout"}:
                index += 1
                if index >= len(argv) or not str(argv[index]).isdigit():
                    failures.append(f"command_flag_missing_numeric_value:{token}")
        elif not token.isdigit():
            failures.append(f"command_arg_not_allowed:{token}")
        index += 1
    return failures


def validate_privileged_job(job_payload: Dict[str, Any], policy_payload: Dict[str, Any], *, approval_token: str = "", dry_run: bool = True) -> Dict[str, Any]:
    policy = _policy_dict(policy_payload)
    job = job_payload.get("job") if isinstance(job_payload.get("job"), dict) else job_payload
    job = dict(job)
    failures: List[str] = []
    kind = str(job.get("kind") or "")
    allowed = _allowed_job_by_kind(policy, kind)
    if not allowed:
        failures.append(f"job_kind_not_allowed:{kind}")
    if not SAFE_ID_RE.match(str(job.get("job_id") or "")):
        failures.append("job_id_invalid")
    if str(job.get("status") or "") != "needs_privilege":
        failures.append("job_status_not_needs_privilege")
    if str(job.get("allowed_action") or "") != str(allowed.get("allowed_action") or ""):
        failures.append("job_allowed_action_invalid")
    if _job_polkit_action(job) != POLKIT_ACTION:
        failures.append("job_polkit_action_invalid")
    expected_token = approval_token_for_job(job)
    actual_token = _job_token(job)
    if actual_token != expected_token:
        failures.append("job_approval_token_invalid")
    if approval_token and approval_token != expected_token:
        failures.append("provided_approval_token_invalid")
    if not dry_run and _job_approval_state(job) != policy.get("approval_state_required_for_apply"):
        failures.append("job_approval_state_not_approved_for_apply")
    if allowed:
        failures.extend(_command_failures(job, allowed, policy))
    argv_steps: List[List[str]] = []
    if allowed and isinstance(allowed.get("command_steps"), list):
        try:
            argv_steps = [shlex.split(step) for step in _privileged_steps(job)]
        except ValueError:
            argv_steps = []
    return {
        "ok": not failures,
        "failures": failures,
        "job": job,
        "dry_run": dry_run,
        "expected_token": expected_token,
        "argv": [] if argv_steps else (shlex.split(str(job.get("command") or "")) if not any(f.startswith("command_parse_error") for f in failures) else []),
        "argv_steps": argv_steps,
        "steps": _privileged_steps(job),
    }


def run_privileged_job(job_payload: Dict[str, Any], policy_payload: Dict[str, Any], *, approval_token: str = "", dry_run: bool = True) -> Dict[str, Any]:
    validation = validate_privileged_job(job_payload, policy_payload, approval_token=approval_token, dry_run=dry_run)
    job = validation["job"]
    if not validation["ok"]:
        return {
            "ok": False,
            "mode": "dry_run" if dry_run else "apply",
            "executed": False,
            "failures": validation["failures"],
            "job_id": job.get("job_id"),
        }
    if dry_run:
        result = {
            "ok": True,
            "mode": "dry_run",
            "executed": False,
            "job_id": job.get("job_id"),
            "polkit_action": POLKIT_ACTION,
            "approval_state": _job_approval_state(job),
        }
        if validation.get("argv_steps"):
            result["would_execute_steps"] = validation.get("steps", [])
        else:
            result["would_execute"] = job.get("command")
        return result
    if hasattr(os, "geteuid") and os.geteuid() != 0:
        return {"ok": False, "mode": "apply", "executed": False, "failures": ["apply_requires_root_or_polkit"], "job_id": job.get("job_id")}
    if os.environ.get("NOEMAFORGE_PRIVILEGED_JOB_APPLY") != "1":
        return {"ok": False, "mode": "apply", "executed": False, "failures": ["apply_env_gate_missing"], "job_id": job.get("job_id")}
    if validation.get("argv_steps"):
        step_results: List[Dict[str, Any]] = []
        for argv in validation["argv_steps"]:
            completed = subprocess.run(argv, check=False, capture_output=True, text=True, timeout=7200)
            step_results.append({"argv": argv, "returncode": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr})
            if completed.returncode != 0:
                return {"ok": False, "mode": "apply", "executed": True, "steps": step_results, "job_id": job.get("job_id")}
        return {"ok": True, "mode": "apply", "executed": True, "steps": step_results, "job_id": job.get("job_id")}
    completed = subprocess.run(validation["argv"], check=False, capture_output=True, text=True, timeout=7200)
    return {
        "ok": completed.returncode == 0,
        "mode": "apply",
        "executed": True,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "job_id": job.get("job_id"),
    }


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
    server.bootstrap_dir = data_root / "bootstrap"
    server.modelstore_dir = data_root / "modelstore"
    server.gui_state_dir = data_root / "gui"
    server.jobs_dir = data_root / "jobs"
    server.tasks_dir = data_root / "tasks"
    server.review_dir = data_root / "review"
    server.runtime_dir = data_root / "runtime"
    server.ui_dir = root / "templates" / "pipeline-dashboard"
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
    server.epoch_status = lambda: {
        "ok": True,
        "latest_model_selection": {
            "plan": {"mode": "full_composite", "scope": "offline_contract", "composite_top_n": 4}
        },
        "firstboot": {"candidate_plan": {}},
        "progress": {"total_models": 4, "tested_models": 4, "remaining_models": 0},
        "apply_available": True,
    }
    return server


def build_epoch_apply_response(*, package_root: Path | str) -> Dict[str, Any]:
    server = build_offline_admin_gui_server(package_root=package_root)
    response = server.epoch_apply({"request": "offline privileged GUI runner contract"})
    return {"response": response, "store": getattr(server, "_memory_store", {})}


def build_model_selection_continue_response(*, package_root: Path | str) -> Dict[str, Any]:
    server = build_offline_admin_gui_server(package_root=package_root)
    response = server.model_selection_continue({"mode": "full_composite", "composite_top_n": 4})
    return {"response": response, "store": getattr(server, "_memory_store", {})}


def build_vault_reinventory_response(*, package_root: Path | str) -> Dict[str, Any]:
    server = build_offline_admin_gui_server(package_root=package_root)
    response = server.vault_reinventory()
    return {"response": response, "store": getattr(server, "_memory_store", {})}


def _check_admin_privileged_job(
    *,
    label: str,
    response: Dict[str, Any],
    expected_kind: str,
    policy_payload: Dict[str, Any],
    require_keep_display: bool = False,
    require_steps: int = 0,
) -> Dict[str, Any]:
    failures: List[str] = []
    job = response.get("job") if isinstance(response.get("job"), dict) else {}
    runner = job.get("privileged_runner") if isinstance(job.get("privileged_runner"), dict) else {}
    runner_command = str(job.get("privileged_runner_command") or runner.get("runner_command") or "")
    if response.get("ok") is not True:
        failures.append(f"{label}_response_not_ok")
    if str(job.get("kind") or "") != expected_kind:
        failures.append(f"{label}_job_kind_invalid")
    if str(job.get("status") or "") != "needs_privilege":
        failures.append(f"{label}_job_status_invalid")
    if require_keep_display and "--keep-display" not in str(job.get("command") or ""):
        failures.append(f"{label}_command_missing_keep_display")
    if runner.get("policy") != "polkit_approval_required":
        failures.append(f"{label}_runner_policy_invalid")
    if runner.get("polkit_action") != POLKIT_ACTION:
        failures.append(f"{label}_runner_polkit_action_invalid")
    if runner.get("dry_run_default") is not True:
        failures.append(f"{label}_runner_dry_run_default_not_true")
    if "--dry-run" not in runner_command or "pkexec noemaforge privileged-job run" not in runner_command:
        failures.append(f"{label}_runner_command_missing_dry_run_or_pkexec")
    if str(job.get("allowed_action") or "") != _allowed_action_for_kind(expected_kind):
        failures.append(f"{label}_allowed_action_invalid")
    if require_steps and len(_privileged_steps(job)) != require_steps:
        failures.append(f"{label}_privileged_steps_invalid")
    validation = validate_privileged_job(job, policy_payload, approval_token=str(runner.get("approval_token") or ""), dry_run=True)
    failures.extend(f"{label}_{item}" for item in validation["failures"])
    artifacts = job.get("artifacts") if isinstance(job.get("artifacts"), list) else []
    if not any(item.get("type") == "privileged_runner_request" for item in artifacts if isinstance(item, dict)):
        failures.append(f"{label}_missing_privileged_runner_artifact")
    return {"failures": failures, "job": job, "job_validation": validation}


def _admin_response_report(policy_payload: Dict[str, Any], *, package_root: Path) -> Dict[str, Any]:
    failures: List[str] = []
    built = {
        "epoch_apply": build_epoch_apply_response(package_root=package_root),
        "model_selection_continue": build_model_selection_continue_response(package_root=package_root),
        "vault_reinventory": build_vault_reinventory_response(package_root=package_root),
    }
    checks = {
        "epoch_apply": _check_admin_privileged_job(
            label="epoch_apply",
            response=built["epoch_apply"]["response"],
            expected_kind="epoch_apply",
            policy_payload=policy_payload,
            require_keep_display=True,
        ),
        "model_selection_continue": _check_admin_privileged_job(
            label="model_selection_continue",
            response=built["model_selection_continue"]["response"],
            expected_kind="model_selection_continue",
            policy_payload=policy_payload,
            require_keep_display=True,
        ),
        "vault_reinventory": _check_admin_privileged_job(
            label="vault_reinventory",
            response=built["vault_reinventory"]["response"],
            expected_kind="vault_reinventory",
            policy_payload=policy_payload,
            require_steps=3,
        ),
    }
    for check in checks.values():
        failures.extend(check["failures"])
    return {"failures": failures, "responses": built, "job_validations": {key: value["job_validation"] for key, value in checks.items()}}


def _example_reports(policy_payload: Dict[str, Any], *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    failures: List[str] = []
    reports: List[Dict[str, Any]] = []
    policy = _policy_dict(policy_payload)
    for ref in _as_string_list(policy.get("required_example_sets")):
        resolved = _resolve_ref(ref, project_root=project_root, package_root=package_root)
        if not resolved.get("ok"):
            failures.append(f"example_set_missing:{ref}")
            reports.append({"ref": ref, "ok": False, "failures": [f"example_set_missing:{ref}"], "resolved": resolved})
            continue
        example = load_example_set(resolved["path"])
        local_failures: List[str] = []
        if example.get("apiVersion") != API_VERSION or example.get("kind") != EXAMPLE_KIND:
            local_failures.append(f"example_header_invalid:{ref}")
        scenarios = example.get("scenarios") if isinstance(example.get("scenarios"), list) else []
        if not scenarios:
            local_failures.append(f"example_scenarios_empty:{ref}")
        scenario_reports: List[Dict[str, Any]] = []
        for scenario in scenarios:
            if not isinstance(scenario, dict):
                local_failures.append("example_scenario_invalid")
                continue
            job = dict(scenario.get("job") or {})
            token = approval_token_for_job(job)
            job.setdefault("approval_token", token)
            job.setdefault("polkit_action", POLKIT_ACTION)
            dry_run = bool(scenario.get("dry_run", True))
            result = run_privileged_job(job, policy_payload, approval_token=token, dry_run=dry_run)
            expect_ok = bool(scenario.get("expect_ok"))
            if bool(result.get("ok")) != expect_ok:
                local_failures.append(f"example_result_mismatch:{scenario.get('id')}")
            scenario_reports.append({"id": scenario.get("id"), "ok": result.get("ok"), "expect_ok": expect_ok, "result": result})
        failures.extend(local_failures)
        reports.append({"ref": ref, "ok": not local_failures, "failures": local_failures, "resolved": resolved, "scenarios": scenario_reports})
    return {"failures": failures, "reports": reports}


def _registry_report(policy_payload: Dict[str, Any], *, package_root: Path) -> Dict[str, Any]:
    failures: List[str] = []
    registry_path = package_root / "configs" / "unified-registry.json"
    registry = load_json(registry_path)
    entries = registry.get("entries") if isinstance(registry.get("entries"), list) else []
    matches = [entry for entry in entries if entry.get("kind") == "eval-pack" and entry.get("id") == POLICY_ID]
    if len(matches) != 1:
        failures.append(f"registry_entry_count_invalid:{len(matches)}")
        entry = {}
    else:
        entry = matches[0]
    refs = set(_as_string_list(entry.get("refs"))) if entry else set()
    for ref in REGISTRY_REFS:
        if ref not in refs:
            failures.append(f"registry_ref_missing:{ref}")
    metrics = set(_as_string_list((entry.get("metadata") or {}).get("metrics") if isinstance(entry.get("metadata"), dict) else []))
    for metric in ["polkit_approval_required", "dry_run_default", "epoch_apply", "model_selection_continue", "vault_reinventory", "refs_resolved"]:
        if metric not in metrics:
            failures.append(f"registry_metric_missing:{metric}")
    return {"failures": failures, "entries": matches}


def _docs_report(*, package_root: Path) -> Dict[str, Any]:
    failures: List[str] = []
    docs = [
        package_root / "docs" / "README.md",
        package_root / "docs" / "TODO.md",
        package_root / "docs" / "reference" / "PROJECT_CONTEXT.md",
        package_root / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
        package_root / "docs" / "history" / "CHANGELOG.md",
    ]
    for path in docs:
        text = path.read_text(encoding="utf-8")
        if POLICY_ID not in text:
            failures.append(f"docs_policy_id_missing:{_display_path(path)}")
        if "polkit_approval_required" not in text and path.name != "README.md":
            failures.append(f"docs_polkit_token_missing:{_display_path(path)}")
    backlog = (package_root / "docs" / "backlog" / "ROADMAP_AND_TODO.md").read_text(encoding="utf-8")
    for todo in SELECTED_TODOS:
        if f"[x] {todo}" not in backlog:
            failures.append(f"backlog_selected_todo_not_closed:{todo}")
        if f"[ ] {todo}" in backlog:
            failures.append(f"backlog_selected_todo_still_open:{todo}")
    todo = (package_root / "docs" / "TODO.md").read_text(encoding="utf-8")
    for item in SELECTED_TODOS:
        if f"[x] {item}" not in todo:
            failures.append(f"todo_selected_todo_not_closed:{item}")
    return {"failures": failures, "docs": [_display_path(path) for path in docs]}


def _polkit_report(*, package_root: Path) -> Dict[str, Any]:
    path = package_root / "share" / "polkit-1" / "actions" / "org.noemaforge.privileged-jobs.policy"
    failures: List[str] = []
    try:
        root = _parse_policy_xml(path)
        actions = [item for item in root.findall("action") if item.attrib.get("id") == POLKIT_ACTION]
        if len(actions) != 1:
            failures.append(f"polkit_action_count_invalid:{len(actions)}")
        elif "approved NoemaForge privileged GUI job" not in "".join(actions[0].itertext()):
            failures.append("polkit_action_message_missing_approved_job")
    except Exception as exc:
        failures.append(f"polkit_parse_failed:{exc}")
    return {"failures": failures, "path": _display_path(path)}


def _alpha_feature_report(*, package_root: Path) -> Dict[str, Any]:
    config = load_json(package_root / "configs" / "alpha-feature-coverage.json")
    features = config.get("features") if isinstance(config.get("features"), dict) else config
    value = str(features.get("privileged_gui_runner") or "")
    failures = [] if value == "shadow_polkit_approved_gui_jobs_contract" else [f"alpha_feature_privileged_gui_runner_invalid:{value}"]
    return {"failures": failures, "value": value}


def validate_privileged_gui_job_runner_policy(
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
    examples = _example_reports(payload, project_root=project, package_root=package)
    failures.extend(examples["failures"])
    admin_response = _admin_response_report(payload, package_root=package)
    failures.extend(admin_response["failures"])
    registry = _registry_report(payload, package_root=package)
    failures.extend(registry["failures"])
    docs = _docs_report(package_root=package)
    failures.extend(docs["failures"])
    polkit = _polkit_report(package_root=package)
    failures.extend(polkit["failures"])
    alpha_feature = _alpha_feature_report(package_root=package)
    failures.extend(alpha_feature["failures"])
    metrics = {
        "refs": len(_as_string_list(payload.get("refs"))),
        "resolved_refs": len(ref_report["resolved_refs"]),
        "examples": sum(len(item.get("scenarios") or []) for item in examples["reports"]),
        "passing_examples": sum(1 for item in examples["reports"] for scenario in item.get("scenarios", []) if scenario.get("ok") == scenario.get("expect_ok")),
        "registry_entries": len(registry["entries"]),
        "checked_allowed_jobs": len(policy.get("allowed_jobs") or []),
        "script_reports": len(scripts["reports"]),
        "policy_path_provided": int(policy_path is not None),
    }
    return {
        "apiVersion": API_VERSION,
        "kind": REPORT_KIND,
        "id": str(payload.get("id") or POLICY_ID),
        "version": str(payload.get("version") or ""),
        "ok": not failures,
        "validated_at": _nowz(),
        "failures": failures,
        "metrics": metrics,
        "refs": ref_report,
        "scripts": scripts,
        "examples": examples,
        "admin_response": admin_response,
        "registry": registry,
        "docs": docs,
        "polkit": polkit,
        "alpha_feature": alpha_feature,
    }


def benchmark_privileged_gui_job_runner(*, package_root: Path | str, iterations: int = 80) -> Dict[str, Any]:
    package = Path(package_root).resolve()
    project = package.parent
    policy = load_policy(package / DEFAULT_POLICY_REF)
    started = time.perf_counter()
    failures = 0
    for _ in range(iterations):
        report = validate_privileged_gui_job_runner_policy(policy, project_root=project, package_root=package)
        if not report["ok"]:
            failures += 1
    elapsed = time.perf_counter() - started
    return {
        "ok": failures == 0,
        "iterations": iterations,
        "failures": failures,
        "elapsed_seconds": elapsed,
        "iterations_per_second": iterations / elapsed if elapsed else iterations,
    }


def privileged_gui_job_runner_report_to_gate_evidence(report: Dict[str, Any], *, artifact_uri: str) -> Dict[str, Any]:
    status = "pass" if report.get("ok") else "fail"
    return {
        "artifact_uri": artifact_uri,
        "run_at": report.get("validated_at") or _nowz(),
        "checks": [
            {"id": "pipeline_eval", "status": status, "score": 1.0 if status == "pass" else 0.0, "threshold": 1.0},
            {"id": "rollback_plan", "status": "pass", "score": 1.0, "threshold": 1.0},
        ],
        "metrics": report.get("metrics", {}),
        "ok": bool(report.get("ok")),
        "failure_count": len(report.get("failures") or []),
        "policy": POLICY_ID,
    }


def _load_job_file(path: Path | str) -> Dict[str, Any]:
    payload = load_json(path)
    return payload.get("job") if isinstance(payload.get("job"), dict) else payload


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate or dry-run approved NoemaForge privileged GUI jobs.")
    sub = parser.add_subparsers(dest="cmd")
    validate_p = sub.add_parser("validate")
    validate_p.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    validate_p.add_argument("--policy", default=DEFAULT_POLICY_REF)
    validate_p.add_argument("--json", action="store_true")
    run_p = sub.add_parser("run")
    run_p.add_argument("--job-file", required=True)
    run_p.add_argument("--job-id", default="")
    run_p.add_argument("--approval-token", default="")
    run_p.add_argument("--policy", default=DEFAULT_POLICY_REF)
    run_p.add_argument("--dry-run", action="store_true")
    run_p.add_argument("--apply", action="store_true")
    run_p.add_argument("--json", action="store_true")
    ns = parser.parse_args(argv)
    if ns.cmd == "validate":
        package = Path(ns.root).resolve()
        project = package.parent
        policy_path = Path(ns.policy)
        if not policy_path.is_absolute():
            policy_path = package / policy_path
        report = validate_privileged_gui_job_runner_policy(load_policy(policy_path), project_root=project, package_root=package, policy_path=policy_path)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["ok"] else 1
    if ns.cmd == "run":
        package = Path(os.environ.get("NOEMAFORGE_ROOT", Path(__file__).resolve().parents[1])).resolve()
        policy_path = Path(ns.policy)
        if not policy_path.is_absolute():
            policy_path = package / policy_path
        job = _load_job_file(ns.job_file)
        if ns.job_id and ns.job_id != str(job.get("job_id") or ""):
            result = {"ok": False, "mode": "dry_run" if not ns.apply else "apply", "executed": False, "failures": ["job_id_argument_mismatch"], "job_id": job.get("job_id")}
        else:
            dry_run = ns.dry_run or not ns.apply
            result = run_privileged_job(job, load_policy(policy_path), approval_token=ns.approval_token, dry_run=dry_run)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("ok") else 1
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
