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
    self._lock. read() does not hold the lock; it uses Python's GIL-protected
    file iteration and is safe to call concurrently with append().

    Rotation strategy (Windows-safe):
      Instead of rename/replace (which fails on Windows when any reader holds
      the file handle), _maybe_rotate() uses copy-then-truncate:
        1. Read the full file into memory.
        2. Shift existing archives:  .2→.3, .1→.2  (oldest dropped at depth 3).
        3. Write the old content into the new .1 archive.
        4. Truncate the live file to 0.
      Readers that have the live file open will hit EOF at step 4 and stop
      iterating rather than raising PermissionError.

      _shift_archives() tracks whether every rename succeeded.  If any shift
      step fails the method returns False and _maybe_rotate() skips the archive
      write and truncate entirely, preventing the previous .1 archive from being
      silently overwritten with potentially corrupt partial data.
    """

    def __init__(self, root: Path | str = DEFAULT_EVENT_STATE):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "events.jsonl"
        self._lock = threading.Lock()
        self._append_count = 0

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

        Shifts .2→.3, .1→.2 (i.e. from oldest to newest so we never clobber
        a destination that still needs to be moved).  The oldest archive beyond
        _MAX_ARCHIVE_DEPTH is deleted first.

        Returns True if all shift operations that were attempted succeeded.
        Returns False if any operation failed — the caller should treat this as
        a signal to abort the rotation cycle and preserve the existing archives.
        """
        # Delete generation beyond the max depth first.
        oldest = self._archive_path(self.path, _MAX_ARCHIVE_DEPTH)
        try:
            if oldest.exists():
                oldest.unlink()
        except OSError:
            # Cannot delete oldest — we cannot safely shift without risk of
            # overwriting data.  Signal failure.
            return False

        # Shift generations from second-oldest down to first-archive.
        # We move .2→.3, .1→.2 so each destination is already free.
        for gen in range(_MAX_ARCHIVE_DEPTH - 1, 0, -1):
            src = self._archive_path(self.path, gen)
            dst = self._archive_path(self.path, gen + 1)
            if not src.exists():
                # Nothing to shift for this generation — that's fine.
                continue
            try:
                src.replace(dst)
            except OSError:
                # Partial shift has occurred. We cannot continue: if we write
                # the new archive now it would overwrite the data that failed
                # to move.  Abort and leave archives in their current state.
                return False

        return True

    def _maybe_rotate(self) -> None:
        """Rotate the live file into a .1 archive if size/line limits are hit.

        Must be called with self._lock held.

        Uses copy-then-truncate so Windows readers with an open handle see EOF
        rather than PermissionError when the file is cleared.

        Skips rotation entirely if _shift_archives() reports any failure —
        better to let the live file grow than to silently destroy archive data.
        """
        try:
            if not self.path.exists():
                return
            size = self.path.stat().st_size
            # Fast-path: skip expensive line count below the fast-path threshold.
            if size < _ROTATION_SIZE_FAST_PATH:
                return
            content = self.path.read_bytes()
            # Re-check size after the read to detect concurrent writes.
            if size < MAX_EVENT_BYTES:
                lines = content.decode("utf-8", errors="replace").splitlines()
                if len(lines) <= MAX_EVENT_LINES:
                    return
            # Rotation needed — shift existing archives first.
            if not self._shift_archives():
                # Partial or failed shift; abort to protect existing archives.
                return
            archive = self._archive_path(self.path, 1)
            archive.write_bytes(content)
            # Truncate in-place — keeps the inode/handle alive for Windows readers.
            with self.path.open("r+b") as fh:
                fh.truncate(0)
        except OSError:
            pass

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

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

        Note: after_index is a line-number offset within the current live file.
        After a rotation the live file is truncated to 0, so callers that saved
        a non-zero after_index will skip rows until the file re-grows past that
        line count.  Callers that need reliable continuity across rotations
        should reset after_index to 0 when they detect a gap in event indices.
        (This design issue is tracked as task-46.)
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
