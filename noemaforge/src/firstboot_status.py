#!/usr/bin/env python3
from __future__ import annotations

# === NoemaForge Autodoc File Header ===
# File: src/firstboot_status.py
# Purpose: Provide the module 'firstboot_status'.
# Invoked by / imported from:
#   - direct operator invocation or test discovery
# Public API / entry functions:
#   - module-level helpers / CLI entrypoint
# Inputs:
#   - local filesystem paths, command-line arguments, and NoemaForge runtime/install state
# Output formats / side effects:
#   - local JSON/YAML/text artifacts or process exit status
# AutoDoc: refreshed 2026-04-13 (manual)
# === End NoemaForge Autodoc File Header ===


# === NoemaForge File Header ===
# File: src/firstboot_status.py
# Zone: spinal
# Purpose: Persist visible first-boot progress/status artifacts for operator review and resume logic.
# Callers: src/firstboot_orchestrator.py, src/ui_snapshot.py (optional future consumer), operator tooling.
# Inputs: status/events file paths, structured status/event payloads.
# Outputs: JSON status file and JSONL event log.
# Side effects: writes /var/lib/noemaforge/bootstrap/* artifacts.
# Security notes:
#   - Install-time / first-boot only; must not mutate epoch directly.
#   - Writes only structured local state for operator visibility and resume safety.
# === End NoemaForge File Header ===


import json
import os
import shutil
import time
from typing import Any, Dict, Optional


ARCHIVABLE_FIRSTBOOT_FILES = [
    "firstboot-status.json",
    "firstboot-events.jsonl",
    "effective-first-start-options.json",
    "model-profile-manifest.json",
    "dataset-assurance.json",
    "model-inventory.json",
    "dataset-inventory.json",
    "role-tournament-results.json",
    "role-candidate-map.json",
    "firstboot-staffing-summary.json",
    "candidate-selection-plan.json",
    "model-selection-decision.json",
    "rollback_plan.json",
    "model-run-records.json",
    "composite-selection-plan.json",
]

SUCCESS_STATES = {
    "done",
    "success",
    "completed",
    "selection_ready_no_apply",
    "applied_no_reboot",
    "applied_reboot_scheduled",
    "reboot_pending",
}
FAILED_STATES = {"failed", "error", "unstaffed"}
ACTIVE_STATES = {"running", "pending", "started", "warning"}
RUN_LEASE_FILE = "firstboot-run.lock"


def _nowz() -> str:
    import datetime as dt
    return dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _atomic_write(path: str, payload: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(payload)
    os.replace(tmp, path)


def _slug(value: str, *, fallback: str = "attempt") -> str:
    text = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(value or ""))
    text = "-".join(part for part in text.split("-") if part)
    return text[:80] or fallback


def _read_archive_status(path: str) -> tuple[Dict[str, Any], str]:
    if not os.path.exists(path):
        return {}, "missing"
    if not os.path.isfile(path):
        return {}, "status_not_file"
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
    except Exception:
        return {}, "status_invalid_json"
    if not isinstance(obj, dict):
        return {}, "status_not_object"
    if obj.get("kind") and obj.get("kind") != "FirstbootStatus":
        return obj, "status_kind_invalid"
    return obj, ""


def _state_dir_for(status_path: str, events_path: str = "") -> str:
    base = status_path or events_path
    return os.path.dirname(os.path.abspath(base)) if base else os.getcwd()


def _run_lease_path(status_path: str, events_path: str = "", state_dir: Optional[str] = None) -> str:
    return os.path.join(state_dir or _state_dir_for(status_path, events_path), RUN_LEASE_FILE)


def _status_is_active(status: Dict[str, Any]) -> bool:
    state = str(status.get("state") or "").strip().lower()
    step = str(status.get("step") or "").strip().lower()
    if state.startswith("blocked") or state in SUCCESS_STATES or state in FAILED_STATES:
        return False
    return state in ACTIVE_STATES or (step and step != "complete")


def _pid_is_active(pid: int) -> bool:
    if pid <= 0:
        return False
    if pid == os.getpid():
        return True
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def _load_run_lease(lock_path: str) -> Dict[str, Any]:
    try:
        with open(lock_path, "r", encoding="utf-8") as f:
            obj = json.load(f)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _write_run_lease(lock_path: str, doc: Dict[str, Any], *, exclusive: bool = False) -> None:
    payload = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
    if not exclusive:
        _atomic_write(lock_path, payload)
        return
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)
    fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
    except Exception:
        os.close(fd)
        raise


def acquire_run_lease(
    status_path: str,
    events_path: str,
    *,
    state_dir: Optional[str] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """Acquire a firstboot launcher lease to prevent duplicate active runs."""
    state_dir = state_dir or _state_dir_for(status_path, events_path)
    os.makedirs(state_dir, exist_ok=True)
    lock_path = _run_lease_path(status_path, events_path, state_dir)
    status = load_status(status_path)
    existing = _load_run_lease(lock_path)
    if existing:
        pid = int(existing.get("pid") or 0)
        lock_state = str(existing.get("state") or "").lower()
        active_lock = lock_state == "running" and _pid_is_active(pid)
        if active_lock and not force:
            return {
                "ok": False,
                "reason": "active_firstboot_run",
                "lock_path": lock_path,
                "pid": pid,
                "started_at": existing.get("started_at"),
                "status_state": status.get("state"),
                "status_step": status.get("step"),
            }

    now = _nowz()
    doc = {
        "apiVersion": "noemaforge.firstbootlease/v1",
        "kind": "FirstbootRunLease",
        "state": "running",
        "started_at": now,
        "updated_at": now,
        "pid": os.getpid(),
        "status_path": status_path,
        "events_path": events_path,
        "replaced_previous_lock": bool(existing),
        "force": bool(force),
    }
    try:
        _write_run_lease(lock_path, doc, exclusive=not bool(existing))
    except FileExistsError:
        existing = _load_run_lease(lock_path)
        pid = int(existing.get("pid") or 0)
        if str(existing.get("state") or "").lower() == "running" and _pid_is_active(pid) and not force:
            return {
                "ok": False,
                "reason": "active_firstboot_run",
                "lock_path": lock_path,
                "pid": pid,
                "started_at": existing.get("started_at"),
                "status_state": status.get("state"),
                "status_step": status.get("step"),
            }
        doc["replaced_previous_lock"] = True
        _write_run_lease(lock_path, doc, exclusive=False)
    return {"ok": True, "reason": "lease_acquired", "lock_path": lock_path, "pid": doc["pid"], "started_at": now}


def release_run_lease(status_path: str, *, state_dir: Optional[str] = None, final_state: str = "") -> Dict[str, Any]:
    state_dir = state_dir or _state_dir_for(status_path)
    lock_path = _run_lease_path(status_path, state_dir=state_dir)
    existing = _load_run_lease(lock_path)
    if not existing:
        return {"ok": True, "released": False, "reason": "no_lock", "lock_path": lock_path}
    now = _nowz()
    existing.update({
        "state": "released",
        "released_at": now,
        "updated_at": now,
        "final_state": final_state,
    })
    _write_run_lease(lock_path, existing)
    return {"ok": True, "released": True, "lock_path": lock_path, "final_state": final_state}


def _event_log_problem(path: str) -> str:
    if not os.path.exists(path):
        return ""
    if not os.path.isfile(path):
        return "events_not_file"
    try:
        with open(path, "r", encoding="utf-8") as f:
            for idx, line in enumerate(f, start=1):
                if not line.strip():
                    continue
                obj = json.loads(line)
                if not isinstance(obj, dict):
                    return f"events_line_{idx}_not_object"
    except Exception:
        return "events_invalid_jsonl"
    return ""


def _archive_reason(status_path: str, events_path: str) -> tuple[str, Dict[str, Any]]:
    status, status_problem = _read_archive_status(status_path)
    events_problem = _event_log_problem(events_path)
    if status_problem and status_problem != "missing":
        return status_problem, status
    if events_problem:
        return events_problem, status
    if status_problem == "missing":
        return ("events_without_status", status) if os.path.exists(events_path) else ("", status)

    state = str(status.get("state") or "").strip().lower()
    step = str(status.get("step") or "").strip().lower()
    if state.startswith("blocked"):
        return f"failed_state_{state}", status
    if state in FAILED_STATES:
        return f"failed_state_{state}", status
    if state in SUCCESS_STATES:
        return "", status
    if step != "complete" or state in {"running", "pending", "started", "warning"}:
        return f"interrupted_state_{state or step or 'unknown'}", status
    return f"invalid_terminal_state_{state or 'unknown'}", status


def archive_previous_attempt(
    status_path: str,
    events_path: str,
    *,
    state_dir: Optional[str] = None,
    archive_root: Optional[str] = None,
) -> Dict[str, Any]:
    """Copy a failed, interrupted or invalid firstboot attempt before restart."""
    state_dir = state_dir or os.path.dirname(os.path.abspath(status_path or events_path))
    archive_root = archive_root or os.path.join(state_dir, "firstboot-attempt-archive")
    reason, status = _archive_reason(status_path, events_path)
    report: Dict[str, Any] = {
        "apiVersion": "noemaforge.firstbootattemptarchive/v1",
        "kind": "FirstbootAttemptArchive",
        "archived": False,
        "reason": reason,
    }
    if not reason:
        return report

    stamp = _nowz().replace(":", "").replace("-", "")
    run_id = str(status.get("run_id") or "")
    archive_name = f"{stamp}-{_slug(reason)}"
    if run_id:
        archive_name = f"{archive_name}-{_slug(run_id)}"
    archive_dir = os.path.join(archive_root, archive_name)
    if os.path.exists(archive_dir):
        suffix = 2
        base_dir = archive_dir
        while os.path.exists(archive_dir):
            archive_dir = f"{base_dir}-{suffix}"
            suffix += 1
    os.makedirs(archive_dir, exist_ok=False)

    sources: Dict[str, str] = {}
    for name in ARCHIVABLE_FIRSTBOOT_FILES:
        src = os.path.join(state_dir, name)
        if os.path.isfile(src):
            sources[name] = src
    for src in [status_path, events_path]:
        if src and os.path.isfile(src):
            sources.setdefault(os.path.basename(src), src)

    copied = []
    for dest_name, src in sorted(sources.items()):
        dst = os.path.join(archive_dir, dest_name)
        shutil.copy2(src, dst)
        copied.append(dest_name)

    manifest = {
        "apiVersion": "noemaforge.firstbootattemptarchive/v1",
        "kind": "FirstbootAttemptArchiveManifest",
        "created_at": _nowz(),
        "reason": reason,
        "source_state_dir": state_dir,
        "source_status_path": status_path,
        "source_events_path": events_path,
        "run_id": run_id,
        "state": status.get("state"),
        "step": status.get("step"),
        "copied_files": copied,
    }
    _atomic_write(os.path.join(archive_dir, "archive-manifest.json"), json.dumps(manifest, ensure_ascii=False, indent=2))
    report.update({
        "archived": True,
        "archive_dir": archive_dir,
        "manifest": os.path.join(archive_dir, "archive-manifest.json"),
        "copied_files": copied,
    })
    return report


def load_status(path: str) -> Dict[str, Any]:
    try:
        with open(path, 'r', encoding='utf-8') as f:
            obj = json.load(f)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    return {}


def write_status(path: str, *, step: str, state: str, message: str, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    # 0.32.1: status files must be fresh per update.
    # Earlier builds loaded the old status and merged new fields, which mixed a
    # current running step with previous successful request_id/results/finished_at.
    doc = {
        'apiVersion': 'noemaforge.firstbootstatus/v1',
        'kind': 'FirstbootStatus',
        'updated_at': _nowz(),
        'step': step,
        'state': state,
        'message': message,
    }
    if extra:
        doc.update(extra)
    _atomic_write(path, json.dumps(doc, ensure_ascii=False, indent=2))
    return doc


def append_event(path: str, *, step: str, state: str, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    rec = {
        'ts': _nowz(),
        'step': step,
        'state': state,
        'message': message,
    }
    if extra:
        rec['extra'] = extra
    with open(path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(rec, ensure_ascii=False) + '\n')


def mark_started(status_path: str, events_path: str, *, share_root: str, vault_root: str) -> None:
    previous_archive = archive_previous_attempt(status_path, events_path)
    if previous_archive.get("archived"):
        _atomic_write(events_path, "")
    started = _nowz()
    run_id = 'first-start-' + started.replace(':', '').replace('-', '')
    extra = {
        'started_at': started,
        'run_id': run_id,
        'pid': os.getpid(),
        'share_root': share_root,
        'vault_root': vault_root,
    }
    event_extra = dict(extra)
    if previous_archive.get("archived"):
        archive_summary = {
            "reason": previous_archive.get("reason"),
            "archive_dir": previous_archive.get("archive_dir"),
            "manifest": previous_archive.get("manifest"),
            "copied_files": previous_archive.get("copied_files") or [],
        }
        extra["previous_attempt_archive"] = archive_summary
        event_extra["previous_attempt_archive"] = archive_summary
    write_status(status_path, step='start', state='running', message='First-boot orchestration started.', extra=extra)
    append_event(events_path, step='start', state='running', message='First-boot orchestration started.', extra=event_extra)


def mark_step(status_path: str, events_path: str, *, step: str, state: str, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
    write_status(status_path, step=step, state=state, message=message, extra=extra)
    append_event(events_path, step=step, state=state, message=message, extra=extra)


def mark_finished(status_path: str, events_path: str, *, state: str, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
    payload = dict(extra or {})
    payload.setdefault('finished_at', _nowz())
    write_status(status_path, step='complete', state=state, message=message, extra=payload)
    append_event(events_path, step='complete', state=state, message=message, extra=payload)
    release_run_lease(status_path, final_state=state)
