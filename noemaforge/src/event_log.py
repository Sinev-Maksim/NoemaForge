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
Side effects: Appends JSONL rows only; rotates archive when size/line cap is reached.
Tests: python3 -m py_compile noemaforge/src/event_log.py; event append/read smoke.
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

# Rotation thresholds: archive when the file exceeds either bound.
MAX_EVENT_LINES = 10_000
MAX_EVENT_BYTES = 10 * 1024 * 1024  # 10 MB

# Size below which the expensive full-file line count is skipped entirely.
_ROTATION_SIZE_FAST_PATH = 1024 * 1024  # 1 MB

# Check rotation at most once every N appends to avoid the stat/read overhead on
# every single call.  The check is always done while holding self._lock.
_ROTATION_CHECK_INTERVAL = 50


class EventLog:
    """Append-only JSONL event log with bounded readback and thread-safe rotation.

    Threading model
    ---------------
    self._lock serialises the entire append + optional-rotation sequence so that
    the file write and any subsequent rename (rotation) are never interleaved:

    * Thread A: acquire lock → open "a" → write row → close → maybe rotate → release
    * Thread B: acquire lock → (waits for A) → ... same sequence

    This eliminates two race classes identified in code review:

    1. **Write-after-rotate archive pollution (Linux)** — without the lock, Thread A
       could finish the ``path.open("a")`` call just after Thread B renamed the file.
       On Linux the old fd remains valid, so Thread A's row lands in the archive
       (events.jsonl.1) instead of the live log.

    2. **PermissionError on Windows** — without the lock, ``path.replace(archive)``
       (MoveFileEx) inside ``_maybe_rotate()`` would race with another thread that
       still had the file open for append, causing a PermissionError swallowed by
       ``except OSError: pass``, preventing rotation indefinitely.

    ``read()`` intentionally does NOT hold the lock.  Readers open their own file
    handle, so they observe a consistent view of whatever is on disk at open time.
    A concurrent rotation can move the file while read() is mid-iteration; on
    Windows this manifests as a silently failed rotation (task-38), which is
    addressed separately.
    """

    def __init__(self, root: Path | str = DEFAULT_EVENT_STATE):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "events.jsonl"
        self._lock = threading.Lock()
        # Counts successful appends; used to throttle the expensive rotation check.
        self._append_count = 0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _maybe_rotate(self) -> None:
        """Archive the log file when it exceeds the size or line cap.

        MUST be called with ``self._lock`` held.  Both the stat check and the
        rename are performed under the lock so that no other thread writes to or
        reads the file while it is being renamed.
        """
        try:
            if not self.path.exists():
                return
            size = self.path.stat().st_size
            # Fast-path: skip the expensive full-read line count for small files.
            if size < _ROTATION_SIZE_FAST_PATH:
                return
            lines = self.path.read_text(encoding="utf-8", errors="replace").splitlines()
            if size < MAX_EVENT_BYTES and len(lines) <= MAX_EVENT_LINES:
                return
            archive = self.path.with_suffix(self.path.suffix + ".1")
            self.path.replace(archive)
        except OSError:
            pass

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def append(
        self,
        event_type: str,
        data: Dict[str, Any] | None = None,
        *,
        actor: str = "system",
        trace_id: str = "",
    ) -> Dict[str, Any]:
        """Append one event row and optionally rotate the log.

        The entire file-write + rotation sequence is performed under
        ``self._lock`` to prevent the write-after-rotate and PermissionError
        races described in the class docstring.
        """
        row = {
            "ts": nowz(),
            "type": str(event_type or "event"),
            "actor": str(actor or "system"),
            "trace_id": str(trace_id or ""),
            "version": RUNTIME_VERSION,
            "data": data or {},
        }
        with self._lock:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            self._append_count += 1
            # Throttle: only check rotation every _ROTATION_CHECK_INTERVAL appends.
            if self._append_count % _ROTATION_CHECK_INTERVAL == 0:
                self._maybe_rotate()
        return row

    def read(self, after_index: int = 0, limit: int = 200) -> list[Dict[str, Any]]:
        """Return up to *limit* rows starting from *after_index*.

        Uses streaming iteration (``path.open()`` + line-by-line) so that only
        the requested slice is held in memory, regardless of log file size.
        An ``OSError`` (e.g. file renamed mid-read during rotation) is silently
        swallowed and returns whatever rows were collected before the error.
        """
        if not self.path.exists():
            return []
        rows: list[Dict[str, Any]] = []
        try:
            with self.path.open(encoding="utf-8", errors="replace") as fh:
                for idx, line in enumerate(fh):
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
        except OSError:
            pass
        return rows


__all__ = [
    "EventLog",
    "DEFAULT_EVENT_STATE",
    "MAX_EVENT_LINES",
    "MAX_EVENT_BYTES",
    "_ROTATION_SIZE_FAST_PATH",
    "_ROTATION_CHECK_INTERVAL",
]
