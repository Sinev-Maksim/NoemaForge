#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/job_progress_stream_runtime.py
Zone: gui/control-plane
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate the Admin GUI job-progress SSE stream contract.
Inputs: Job progress stream policy, Admin GUI server code and dashboard frontend.
Outputs: JSON-compatible validation reports and synthetic SSE event plans.
Side effects: None; CLI writes JSON to stdout.
Tests: noemaforge/tests/test_job_progress_stream_runtime.py
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

_SRC = Path(__file__).resolve().parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
from noemaforge_version import RUNTIME_VERSION

API_VERSION = "noemaforge.job-progress-stream/v1"
POLICY_KIND = "JobProgressStreamPolicy"
REPORT_KIND = "JobProgressStreamValidationReport"
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
    if not text or text.startswith("~"):
        return False
    if text.startswith("/") and not text.startswith("/opt/noemaforge/"):
        return False
    parts = PurePosixPath(text.lstrip("/")).parts
    return not any(part in {"", ".", ".."} for part in parts)


def _localize_ref(ref: str) -> str:
    text = str(ref or "").strip().replace("\\", "/")
    prefix = "/opt/noemaforge/"
    if text.startswith(prefix):
        return text[len(prefix):]
    return text.lstrip("/")


def _resolve_ref(ref: str, *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    local = _localize_ref(ref)
    candidates = [("project", project_root / local), ("package", package_root / local)]
    if not local.startswith("noemaforge/"):
        candidates.append(("project_noemaforge", project_root / "noemaforge" / local))
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


def load_policy(policy_path: Path | str) -> Dict[str, Any]:
    return load_json(policy_path)


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
    if str(policy.get("activation_state") or "") != "sse_snapshot_stream":
        failures.append("policy_activation_state_invalid")
    if str(policy.get("stream_endpoint") or "") != "/api/jobs/stream":
        failures.append("policy_stream_endpoint_invalid")
    if str(policy.get("stream_content_type") or "") != "text/event-stream":
        failures.append("policy_stream_content_type_invalid")
    for key in ["require_registry_attachment", "require_docs_and_changelog_refs", "require_no_live_host_dependency"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    for key in [
        "required_events",
        "required_server_tokens",
        "required_frontend_tokens",
        "required_runtime_scripts",
        "required_runtime_tokens",
        "required_docs",
    ]:
        if not _as_string_list(policy.get(key)):
            failures.append(f"policy_{key}_empty")
    return failures


def _token_report(ref: str, tokens: Sequence[str], *, project_root: Path, package_root: Path, owner: str) -> Dict[str, Any]:
    resolved = _resolve_ref(ref, project_root=project_root, package_root=package_root)
    text = Path(resolved["path"]).read_text(encoding="utf-8", errors="replace") if resolved.get("ok") else ""
    failures: List[str] = []
    if not resolved.get("ok"):
        failures.append(f"{owner}_missing:{ref}")
    for token in tokens:
        if text and token not in text:
            failures.append(f"{owner}_token_missing:{ref}:{token}")
    return {"ref": ref, "ok": not failures, "failures": failures, "resolved": resolved}


def build_job_stream_events(jobs: Sequence[Dict[str, Any]], *, version: str = RUNTIME_VERSION) -> List[Dict[str, Any]]:
    safe_jobs = [dict(job) for job in jobs if isinstance(job, dict)]
    events = [{
        "event": "jobs_snapshot",
        "id": "jobs-snapshot",
        "data": {
            "ok": True,
            "version": version,
            "stream": "job_progress_sse",
            "jobs": safe_jobs,
        },
    }]
    for job in safe_jobs[-20:]:
        events.append({
            "event": "job_progress",
            "id": str(job.get("job_id") or "job"),
            "data": {
                "ok": True,
                "version": version,
                "stream": "job_progress_sse",
                "job": job,
                "progress": job.get("progress") if isinstance(job.get("progress"), dict) else {},
            },
        })
    return events


def format_sse_events(events: Sequence[Dict[str, Any]]) -> str:
    chunks = ["retry: 3000\n\n"]
    for item in events:
        event = str(item.get("event") or "message")
        event_id = str(item.get("id") or "")
        data = item.get("data") if isinstance(item.get("data"), dict) else {}
        if event_id:
            chunks.append(f"id: {event_id}\n")
        chunks.append(f"event: {event}\n")
        chunks.append("data: " + json.dumps(data, ensure_ascii=False, sort_keys=True) + "\n\n")
    return "".join(chunks)


def validate_job_progress_stream_policy(
    payload: Dict[str, Any],
    *,
    project_root: Path,
    package_root: Path,
) -> Dict[str, Any]:
    policy = _policy_dict(payload)
    failures = _policy_failures(payload)
    ref_report = _resolve_refs(_as_string_list(payload.get("refs")), project_root=project_root, package_root=package_root, owner="policy.refs")
    doc_report = _resolve_refs(_as_string_list(policy.get("required_docs")), project_root=project_root, package_root=package_root, owner="policy.required_docs")
    runtime_report = _token_report("noemaforge/src/job_progress_stream_runtime.py", _as_string_list(policy.get("required_runtime_tokens")), project_root=project_root, package_root=package_root, owner="runtime")
    server_report = _token_report("noemaforge/src/admin_gui_server.py", _as_string_list(policy.get("required_server_tokens")), project_root=project_root, package_root=package_root, owner="server")
    frontend_report = _token_report("noemaforge/templates/pipeline-dashboard/app.js", _as_string_list(policy.get("required_frontend_tokens")), project_root=project_root, package_root=package_root, owner="frontend")
    events = build_job_stream_events([
        {"job_id": "job_demo", "kind": "demo", "status": "running", "progress": {"step": 1, "total": 2}},
    ])
    sse_text = format_sse_events(events)
    for event_name in _as_string_list(policy.get("required_events")):
        if f"event: {event_name}" not in sse_text:
            failures.append(f"sse_event_missing:{event_name}")
    if "data: " not in sse_text or "text/event-stream" not in str(policy.get("stream_content_type")):
        failures.append("sse_format_invalid")
    failures.extend(ref_report["failures"])
    failures.extend(doc_report["failures"])
    failures.extend(runtime_report["failures"])
    failures.extend(server_report["failures"])
    failures.extend(frontend_report["failures"])
    return {
        "apiVersion": API_VERSION,
        "kind": REPORT_KIND,
        "created_at": _nowz(),
        "ok": not failures,
        "id": payload.get("id"),
        "version": payload.get("version"),
        "metrics": {
            "refs": len(_as_string_list(payload.get("refs"))),
            "resolved_refs": len(ref_report["resolved_refs"]),
            "required_docs": len(_as_string_list(policy.get("required_docs"))),
            "required_events": len(_as_string_list(policy.get("required_events"))),
            "synthetic_events": len(events),
        },
        "failures": failures,
        "refs": ref_report,
        "docs": doc_report,
        "runtime": runtime_report,
        "server": server_report,
        "frontend": frontend_report,
        "sse_sample": sse_text,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Admin GUI job-progress SSE stream contract.")
    parser.add_argument("--policy", default="noemaforge/configs/job-progress-stream-policy.json")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--package-root", default="noemaforge")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(argv)

    project_root = Path(args.project_root).resolve()
    package_root = (project_root / args.package_root).resolve() if not Path(args.package_root).is_absolute() else Path(args.package_root).resolve()
    policy_path = Path(args.policy)
    policy = load_policy(policy_path if policy_path.is_absolute() else project_root / policy_path)
    report = validate_job_progress_stream_policy(policy, project_root=project_root, package_root=package_root)
    if args.summary:
        report = {
            "apiVersion": API_VERSION,
            "kind": REPORT_KIND,
            "ok": report["ok"],
            "metrics": report["metrics"],
            "failures": report["failures"],
        }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
