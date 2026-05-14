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
import time
from typing import Any, Dict, Optional


def _nowz() -> str:
    import datetime as dt
    return dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _atomic_write(path: str, payload: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(payload)
    os.replace(tmp, path)


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
    # 0.31.13.alpha: status files must be fresh per update.
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
    os.makedirs(os.path.dirname(path), exist_ok=True)
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
    started = _nowz()
    run_id = 'first-start-' + started.replace(':', '').replace('-', '')
    write_status(status_path, step='start', state='running', message='First-boot orchestration started.', extra={
        'started_at': started,
        'run_id': run_id,
        'pid': os.getpid(),
        'share_root': share_root,
        'vault_root': vault_root,
    })
    append_event(events_path, step='start', state='running', message='First-boot orchestration started.', extra={'share_root': share_root, 'vault_root': vault_root, 'run_id': run_id, 'pid': os.getpid()})


def mark_step(status_path: str, events_path: str, *, step: str, state: str, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
    write_status(status_path, step=step, state=state, message=message, extra=extra)
    append_event(events_path, step=step, state=state, message=message, extra=extra)


def mark_finished(status_path: str, events_path: str, *, state: str, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
    payload = dict(extra or {})
    payload.setdefault('finished_at', _nowz())
    write_status(status_path, step='complete', state=state, message=message, extra=payload)
    append_event(events_path, step='complete', state=state, message=message, extra=payload)
