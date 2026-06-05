#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/runtime_device_policy_staging_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate CPU/GPU runtime device-policy staging without live backend migration.
Inputs: runtime-device-policy-staging policy, Admin GUI server source and dashboard UI source.
Outputs: JSON-compatible RuntimeDevicePolicyStagingValidationReport artifacts.
Side effects: None; CLI writes JSON to stdout.
Tests: noemaforge/tests/test_runtime_device_policy_staging_runtime.py
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
API_VERSION = "noemaforge.runtime-device-policy-staging/v1"
POLICY_KIND = "RuntimeDevicePolicyStagingPolicy"
REPORT_KIND = "RuntimeDevicePolicyStagingValidationReport"
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
    if str(policy.get("activation_state") or "") != "cpu_gpu_staged_until_switch_or_backend_restart":
        failures.append("policy_activation_state_invalid")
    for key in ["require_docs_and_changelog_refs", "require_no_live_backend_dependency"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    for key in ["required_runtime_scripts", "required_ui_files", "allowed_policies", "required_runtime_tokens", "required_ui_tokens", "forbidden_device_policy_set_tokens"]:
        if not _as_string_list(policy.get(key)):
            failures.append(f"policy_{key}_empty")
    fields = policy.get("required_staged_fields") if isinstance(policy.get("required_staged_fields"), dict) else {}
    if fields.get("pending_apply") is not True:
        failures.append("policy_required_pending_apply_not_true")
    if not str(fields.get("applies_on") or ""):
        failures.append("policy_required_applies_on_empty")
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


def build_device_policy_sequence(*, package_root: Path | str) -> Dict[str, Any]:
    server = build_offline_admin_gui_server(package_root=package_root)
    initial = server.device_policy()
    cpu = server.device_policy_set("cpu")
    gpu = server.device_policy_set("gpu")
    cuda = server.device_policy_set("cuda")
    invalid = server.device_policy_set("tpu")
    final = server.device_policy()
    store = getattr(server, "_memory_store", {})
    return {
        "initial": initial,
        "cpu": cpu,
        "gpu": gpu,
        "cuda": cuda,
        "invalid": invalid,
        "final": final,
        "store_keys": sorted(store.keys()),
        "store": copy.deepcopy(store),
    }


def _source_report(policy: Dict[str, Any], *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    failures: List[str] = []
    reports: List[Dict[str, Any]] = []
    source_texts: Dict[str, str] = {}
    for ref in _as_string_list(policy.get("required_runtime_scripts")) + _as_string_list(policy.get("required_ui_files")):
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
    set_block = _slice_between(admin_gui, "def device_policy_set", ["def _command_output", "def telemetry_status"])
    for token in _as_string_list(policy.get("required_runtime_tokens")):
        if token not in admin_gui:
            failures.append(f"runtime_token_missing:{token}")
    for token in _as_string_list(policy.get("required_ui_tokens")):
        if token not in ui_text:
            failures.append(f"ui_token_missing:{token}")
    for token in _as_string_list(policy.get("forbidden_device_policy_set_tokens")):
        if token in set_block:
            failures.append(f"forbidden_device_policy_set_token:{token}")
    if "run_json(" in set_block:
        failures.append("device_policy_set_contains_run_json")
    return {"failures": failures, "reports": reports, "device_policy_set_chars": len(set_block)}


def _workflow_report(policy: Dict[str, Any], *, package_root: Path) -> Dict[str, Any]:
    failures: List[str] = []
    sequence = build_device_policy_sequence(package_root=package_root)
    staged = policy.get("required_staged_fields") if isinstance(policy.get("required_staged_fields"), dict) else {}
    expected_applies_on = str(staged.get("applies_on") or "")
    for key in ["cpu", "gpu", "cuda"]:
        response = sequence[key]
        doc = response.get("policy", {})
        if not response.get("ok"):
            failures.append(f"{key}_policy_set_failed")
        if doc.get("pending_apply") is not True:
            failures.append(f"{key}_pending_apply_not_true")
        if doc.get("applies_on") != expected_applies_on:
            failures.append(f"{key}_applies_on_mismatch:{doc.get('applies_on')}")
        note = str(doc.get("note") or "") + " " + str(response.get("reply") or "")
        if "currently running model" not in note or "backend restart" not in note:
            failures.append(f"{key}_staging_note_incomplete")
    if sequence["cuda"].get("policy", {}).get("policy") != "gpu":
        failures.append("cuda_alias_not_normalized_to_gpu")
    if sequence["invalid"].get("ok") is not False:
        failures.append("invalid_policy_not_rejected")
    store_keys = "\n".join(sequence.get("store_keys") or [])
    if "device-policy.json" not in store_keys:
        failures.append("device_policy_state_not_persisted")
    if any("jobs" in key for key in sequence.get("store_keys") or []):
        failures.append("device_policy_created_job_instead_of_staging")
    return {"failures": failures, "sequence": sequence}


def _docs_report(payload: Dict[str, Any], *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    failures: List[str] = []
    docs = [
        package_root / "docs" / "TODO.md",
        package_root / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
        package_root / "docs" / "history" / "CHANGELOG.md",
    ]
    tokens = [str(payload.get("id") or ""), "CPU/GPU staged policy", "next persona/model switch or backend restart"]
    reports: List[Dict[str, Any]] = []
    for path in docs:
        text = load_text(path) if path.exists() else ""
        missing = [token for token in tokens if token and token not in text]
        if missing:
            failures.append(f"docs_tokens_missing:{_display_path(path)}:{','.join(missing)}")
        reports.append({"path": _display_path(path), "ok": not missing, "missing": missing})
    return {"failures": failures, "reports": reports}


def validate_runtime_device_policy_staging_policy(
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
        "device_policy_set_chars": source["device_policy_set_chars"],
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


def benchmark_runtime_device_policy_staging(*, package_root: Path | str, iterations: int = 80) -> Dict[str, Any]:
    root = Path(package_root).resolve()
    policy = load_policy(root / "configs" / "runtime-device-policy-staging-policy.json")
    started = time.perf_counter()
    failures = 0
    for _ in range(iterations):
        report = validate_runtime_device_policy_staging_policy(policy, project_root=root.parent, package_root=root, include_docs=False)
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
        "kind": "RuntimeDevicePolicyStagingValidationSummary",
        "ok": bool(report.get("ok")),
        "id": report.get("id"),
        "version": report.get("version"),
        "metrics": report.get("metrics", {}),
        "failures": report.get("failures", []),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate NoemaForge CPU/GPU runtime device-policy staging")
    parser.add_argument("--policy", default=str(SRC_DIR.parent / "configs" / "runtime-device-policy-staging-policy.json"))
    parser.add_argument("--project-root", default=str(SRC_DIR.parent.parent))
    parser.add_argument("--package-root", default=str(SRC_DIR.parent))
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--skip-docs", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = validate_runtime_device_policy_staging_policy(
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
