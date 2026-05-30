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
Side effects: Appends JSONL rows only; rotates to bounded archive files when size/line caps are hit.
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

# Rotation thresholds: rotate when the live file hits EITHER limit.
MAX_EVENT_LINES = 10_000
MAX_EVENT_BYTES = 10 * 1024 * 1024  # 10 MB

# Fast-path: skip the line-count check below this size (avoids a full file decode on every append).
_ROTATION_SIZE_FAST_PATH = 1024 * 1024  # 1 MB

# Only check rotation every N appends to reduce stat() calls.
_ROTATION_CHECK_INTERVAL = 50

# Maximum number of archived files kept alongside the live file.
# events.jsonl.1 is the most recent archive, .2 is older, up to .N.
_MAX_ARCHIVE_DEPTH = 3


class EventLog:
    """Append-only JSONL event log with bounded readback and size-capped rotation.

    Thread-safety: all write paths (append, rotate) are serialised under
    self._lock.  read() does not hold the lock.

    Rotation strategy (Windows-safe):
      _maybe_rotate() uses copy-then-truncate instead of rename/replace.
      _shift_archives() must return True for rotation to proceed; any shift
      failure aborts the cycle to preserve existing archives.

    After-rotation polling pattern:
      read() uses line-number offsets within the live file. After rotation
      truncates the file to 0 the cursor must be reset to 0.

      Use status() to detect rotation:

        last_rotation = log.status()["rotation_count"]
        after_index = 0
        while True:
            s = log.status()
            if s["rotation_count"] != last_rotation:
                after_index = 0
                last_rotation = s["rotation_count"]
            rows = log.read(after_index=after_index)
            if rows:
                after_index = rows[-1]["index"] + 1
            time.sleep(10)
    """

    def __init__(self, root: Path | str = DEFAULT_EVENT_STATE):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "events.jsonl"
        self._lock = threading.Lock()
        self._append_count = 0
        # Incremented once per successful rotation (truncation of the live file).
        # Callers compare this value across status() calls to detect rotation and
        # reset after_index to 0.  Resets to 0 on each process start.
        self._rotation_count = 0

    # ------------------------------------------------------------------
    # Archive helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _archive_path(base: Path, generation: int) -> Path:
        """Return the path for archive generation N (e.g. events.jsonl.1)."""
        return base.with_suffix(base.suffix + f".{generation}")

    def _shift_archives(self) -> bool:
        """Shift existing archives one generation older.

        Must be called with self._lock held.

        Returns True if all operations succeeded; False if any failed.
        Caller (i.e., _maybe_rotate) must abort the rotation cycle on False.
        """
        oldest = self._archive_path(self.path, _MAX_ARCHIVE_DEPTH)
        try:
            if oldest.exists():
                oldest.unlink()
        except OSError:
            return False
        for gen in range(_MAX_ARCHIVE_DEPTH - 1, 0, -1):
            src = self._archive_path(self.path, gen)
            dst = self._archive_path(self.path, gen + 1)
            if not src.exists():
                continue
            try:
                src.replace(dst)
            except OSError:
                return False
        return True

    def _maybe_rotate(self) -> None:
        """Rotate the live file into a .1 archive if size/line limits are hit.

        Must be called with self._lock held.

        Uses copy-then-truncate (Windows-safe: no rename of an open file).
        Aborts entirely if _shift_archives() returns False to protect existing
        archives from being overwritten by partial or failed renames.

        Note: the outer except OSError catches only I/O failures.
        KeyboardInterrupt or SystemExit between archive.write_bytes() (step A)
        and fh.truncate(0) (step B) will leave both the live file and the
        archive holding the same content.  The next successful rotation shifts
        that archive forward, producing a harmless duplicate in the archive
        chain.  This is accepted: the live file is always intact on any
        non-I/O interruption.
        """
        try:
            if not self.path.exists():
                return
            size = self.path.stat().st_size
            if size < _ROTATION_SIZE_FAST_PATH:
                return
            content = self.path.read_bytes()
            if size < MAX_EVENT_BYTES:
                lines = content.decode("utf-8", errors="replace").splitlines()
                if len(lines) <= MAX_EVENT_LINES:
                    return
            if not self._shift_archives():
                return
            archive = self._archive_path(self.path, 1)
            archive.write_bytes(content)          # step A
            with self.path.open("r+b") as fh:
                fh.truncate(0)                    # step B
            self._rotation_count += 1
        except OSError:
            pass

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def status(self) -> Dict[str, Any]:
        """Return a snapshot of the current log state.

        Keys:
          rotation_count (int): number of completed rotations since process start.
            Callers polling with a saved after_index should reset after_index to 0
            whenever this value changes between calls.
            Note: rotation_count resets to 0 on each process restart; it is an
            in-process-lifetime counter only.
          current_size_bytes (int): best-effort size of the live file in bytes.
            Sampled outside self._lock for performance; may not be consistent
            with rotation_count in the same snapshot (e.g. caller may see a
            post-rotation rotation_count alongside a pre-rotation size).
            Use for monitoring and diagnostics only — do not rely on it being
            consistent with rotation_count within a single call.
          path (str): absolute path to the live events file.
        """
        # current_size_bytes is sampled outside _lock intentionally to avoid
        # blocking append() callers.  It is a best-effort diagnostic value.
        size = 0
        if self.path.exists():
            try:
                size = self.path.stat().st_size
            except OSError:
                pass
        with self._lock:
            rotation_count = self._rotation_count
        return {
            "rotation_count": rotation_count,
            "current_size_bytes": size,
            "path": str(self.path),
        }

    def append(self, event_type: str, data: Dict[str, Any] | None = None, *, actor: str = "system", trace_id: str = "") -> Dict[str, Any]:
        """Append one event row and trigger a rotation check every N appends."""
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
            if self._append_count % _ROTATION_CHECK_INTERVAL == 0:
                self._maybe_rotate()
        return row

    def read(self, after_index: int = 0, limit: int = 200) -> list[Dict[str, Any]]:
        """Return up to *limit* rows starting at line *after_index*.

        Streams the file line-by-line to avoid loading the full file into RAM.

        After-rotation blind spot: after_index is a line-number offset within the
        current live file.  After _maybe_rotate() truncates events.jsonl to 0, the
        live file restarts at line 0.  Callers with a saved non-zero after_index
        will not receive new events until the log re-grows past that line count.

        Callers that need reliable continuity should poll status() before each read()
        and reset after_index to 0 when rotation_count has changed since the last check.
        Alternatively, include rotation_count in the HTTP response (as in /api/events)
        so browser pollers can detect and recover from rotation automatically.
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


__all__ = ["EventLog", "DEFAULT_EVENT_STATE", "_MAX_ARCHIVE_DEPTH"]
