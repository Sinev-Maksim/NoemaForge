#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/orchestration_state.py
Zone: runtime/orchestration
Version: 0.32.2
Created: 2026-05-25
Modified: 2026-05-25
Purpose: Define lightweight orchestration state records used by Admin GUI and runtime jobs.
Inputs: Runtime job/session dictionaries.
Outputs: Normalized dictionaries for JSON persistence and GUI display.
Side effects: None.
Tests: python3 -m py_compile noemaforge/src/orchestration_state.py.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from noemaforge_version import RUNTIME_VERSION

ACTIVE_JOB_STATES = {"queued", "starting", "running", "cancel_requested"}
FINAL_JOB_STATES = {"done", "failed", "cancelled"}


def nowz() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_job_record(record: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "job_id": str(record.get("job_id") or ""),
        "kind": str(record.get("kind") or "unknown"),
        "status": str(record.get("status") or "queued"),
        "lock_key": str(record.get("lock_key") or ""),
        "progress": record.get("progress") if isinstance(record.get("progress"), dict) else {"current": 0, "total": 0, "label": "queued"},
        "artifacts": list(record.get("artifacts") or []),
        "created_at": str(record.get("created_at") or nowz()),
        "updated_at": str(record.get("updated_at") or nowz()),
        "finished_at": str(record.get("finished_at") or ""),
        "version": str(record.get("version") or RUNTIME_VERSION),
    }


def is_active_job(record: Dict[str, Any]) -> bool:
    return str(record.get("status") or "") in ACTIVE_JOB_STATES


def _safe_int(value: Any, default: int = 0) -> int:
    """Convert value to int safely; return default if conversion fails.

    Needed because session files may be manually edited or migrated and could
    contain string values where integers are expected.  Using ``int(x or 0)``
    raises ValueError when x is a non-numeric string like "abc".
    """
    if isinstance(value, (int, float)):
        return int(value)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def normalize_session_record(record: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "session_id": str(record.get("session_id") or "default"),
        "active_persona": str(record.get("active_persona") or "operator.admin/administrator"),
        "selected_mode": str(record.get("selected_mode") or "normal"),
        "selected_composite_top_n": _safe_int(record.get("selected_composite_top_n"), 0),
        "messages": list(record.get("messages") or []),
        "active_jobs": list(record.get("active_jobs") or []),
        "last_route": record.get("last_route") if isinstance(record.get("last_route"), dict) else {},
        "last_event_index": _safe_int(record.get("last_event_index"), 0),
        "updated_at": nowz(),
        "version": RUNTIME_VERSION,
    }
