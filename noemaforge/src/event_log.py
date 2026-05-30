#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/event_log.py
Zone: runtime/orchestration
Version: 0.32.2
Created: 2026-05-25
Modified: 2026-05-30
Purpose: Provide a minimal append-only event log for GUI progress, Admin routing and release evidence.
Inputs: Event dictionaries from runtime modules and Admin GUI handlers.
Outputs: JSONL event records under /var/lib/noemaforge/events by default.
Side effects: Appends JSONL rows only; rotates log file when thresholds exceeded.
Tests: python3 -m py_compile noemaforge/src/event_log.py; python -m unittest noemaforge/tests/test_eventlog_lock.py.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Dict

from noemaforge_version import RUNTIME_VERSION
from orchestration_state import nowz

DEFAULT_EVENT_STATE = Path(os.environ.get("NOEMAFORGE_EVENT_STATE", "/var/lib/noemaforge/events"))

MAX_EVENT_LINES = 10_000
MAX_EVENT_BYTES = 10 * 1024 * 1024  # 10 MB
_ROTATION_SIZE_FAST_PATH = 1024 * 1024  # 1 MB: skip expensive check below this
_ROTATION_CHECK_INTERVAL = 50  # check rotation at most once every N appends past the fast-path


class EventLog:
    """Append-only JSONL event log with bounded readback and rotation."""

    def __init__(self, root: Path | str = DEFAULT_EVENT_STATE):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "events.jsonl"
        self._lock = threading.Lock()
        self._append_count = 0  # counts appends to throttle expensive rotation checks

    def _maybe_rotate(self) -> None:
        """Rotate events.jsonl to events.jsonl.1 when it exceeds size/line limits.

        Thread-safe: the full stat→read→rename sequence is performed under
        ``self._lock`` to prevent TOCTOU races where two concurrent threads
        both detect threshold exceeded and both attempt the rename (the second
        would silently overwrite the archive produced by the first).

        The caller is responsible for only calling this method every
        ``_ROTATION_CHECK_INTERVAL`` appends (after the 1 MB fast path passes)
        so the expensive ``read_text()`` is not invoked on every single append.
        """
        try:
            if not self.path.exists():
                return
            # Fast path: skip expensive line-count when file is clearly small.
            size = self.path.stat().st_size
            if size < _ROTATION_SIZE_FAST_PATH:
                return
            # Acquire lock before re-checking and rotating to prevent TOCTOU.
            with self._lock:
                # Re-stat inside the lock; another thread may have already rotated.
                if not self.path.exists():
                    return
                size = self.path.stat().st_size
                if size < _ROTATION_SIZE_FAST_PATH:
                    return
                lines = self.path.read_text(encoding="utf-8", errors="replace").splitlines()
                if size < MAX_EVENT_BYTES and len(lines) <= MAX_EVENT_LINES:
                    return
                archive = self.path.with_suffix(self.path.suffix + ".1")
                self.path.replace(archive)
        except OSError:
            pass

    def append(self, event_type: str, data: Dict[str, Any] | None = None, *, actor: str = "system", trace_id: str = "") -> Dict[str, Any]:
        row = {
            "ts": nowz(),
            "type": str(event_type or "event"),
            "actor": str(actor or "system"),
            "trace_id": str(trace_id or ""),
            "version": RUNTIME_VERSION,
            "data": data or {},
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        self._append_count += 1
        # Invoke rotation check on every _ROTATION_CHECK_INTERVAL-th append to
        # avoid reading the entire file on every single call past the fast path.
        if self._append_count % _ROTATION_CHECK_INTERVAL == 0:
            self._maybe_rotate()
        return row

    def read(self, after_index: int = 0, limit: int = 200) -> list[Dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: list[Dict[str, Any]] = []
        for idx, line in enumerate(self.path.read_text(encoding="utf-8", errors="replace").splitlines()):
            if idx < after_index or not line.strip():
                continue
            try:
                row = json.loads(line)
                row["index"] = idx
                rows.append(row)
            except Exception:
                continue
            if len(rows) >= limit:
                break
        return rows


__all__ = ["EventLog", "DEFAULT_EVENT_STATE", "MAX_EVENT_LINES", "MAX_EVENT_BYTES", "_ROTATION_SIZE_FAST_PATH", "_ROTATION_CHECK_INTERVAL"]
