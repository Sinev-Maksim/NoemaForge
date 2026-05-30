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
Side effects: Appends JSONL rows only; rotates and shifts archive files when size/line cap is reached.
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

# Check rotation at most once every N appends to avoid stat/read overhead on
# every call.  The check is always done while holding self._lock.
_ROTATION_CHECK_INTERVAL = 50

# Number of shifted archive generations to keep.
# events.jsonl → events.jsonl.1 → events.jsonl.2 → events.jsonl.3 (oldest; dropped)
_MAX_ARCHIVE_DEPTH = 3


class EventLog:
    """Append-only JSONL event log with bounded readback, Windows-safe rotation,
    and multi-generation archive shifting.

    Threading model
    ---------------
    ``self._lock`` serialises the entire append + optional-rotation sequence so
    that the file write and rotation are never interleaved between threads:

    * Thread A: acquire lock → open "a" → write row → close → maybe rotate → release
    * Thread B: acquire lock → (waits for A) → ... same sequence

    Rotation uses **copy-then-truncate** instead of ``path.replace()`` (MoveFileEx).
    On Windows, MoveFileEx fails with PermissionError if any handle has the file
    open.  With copy-then-truncate, readers that are mid-iteration hit EOF at the
    truncation boundary — a safe, clean degradation on both Linux and Windows.

    Archive shifting
    ----------------
    Before copying content to ``events.jsonl.1``, existing archives are shifted
    one generation older up to ``_MAX_ARCHIVE_DEPTH``:

      events.jsonl.3 → deleted (oldest; exceeds depth)
      events.jsonl.2 → events.jsonl.3
      events.jsonl.1 → events.jsonl.2
      events.jsonl   → events.jsonl.1  (current: copy-then-truncate)

    This prevents the archive overwrite bug where a second rotation (after the
    log re-grows) would silently destroy the first archive and lose audit history.
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

    @staticmethod
    def _archive_path(base: Path, generation: int) -> Path:
        """Return the archive path for the given generation (1-based).

        Generation 1 is the most recent archive (``events.jsonl.1``).
        """
        return base.with_suffix(base.suffix + f".{generation}")

    def _shift_archives(self) -> None:
        """Shift existing archive files one generation older.

        MUST be called with ``self._lock`` held.

        Drops the oldest archive when it exceeds ``_MAX_ARCHIVE_DEPTH``.
        Uses ``replace()`` for shifting (not for the live log file), which is
        safe because archive files are never held open by readers or writers.
        """
        # Remove the archive that would overflow the depth limit.
        oldest = self._archive_path(self.path, _MAX_ARCHIVE_DEPTH)
        try:
            if oldest.exists():
                oldest.unlink()
        except OSError:
            pass
        # Shift .2 → .3, .1 → .2 (from oldest surviving to newest).
        for gen in range(_MAX_ARCHIVE_DEPTH - 1, 0, -1):
            src = self._archive_path(self.path, gen)
            dst = self._archive_path(self.path, gen + 1)
            try:
                if src.exists():
                    src.replace(dst)
            except OSError:
                pass

    def _maybe_rotate(self) -> None:
        """Archive the log file when it exceeds the size or line cap.

        MUST be called with ``self._lock`` held.

        Uses copy-then-truncate + archive shifting (not ``path.replace()``) so
        that:
        1. Readers with an open handle continue reading; they hit EOF at the
           truncation boundary instead of PermissionError (Windows).
        2. Existing archives are not overwritten; they are shifted one generation
           older before the new archive is written.
        """
        try:
            if not self.path.exists():
                return
            size = self.path.stat().st_size
            # Fast-path: skip the expensive full-read line count for small files.
            if size < _ROTATION_SIZE_FAST_PATH:
                return
            # Read the full content once; reuse for line count and archive write.
            content = self.path.read_bytes()
            lines = content.decode("utf-8", errors="replace").splitlines()
            if size < MAX_EVENT_BYTES and len(lines) <= MAX_EVENT_LINES:
                return
            # Shift existing archives to make room for the new generation-1 archive.
            self._shift_archives()
            # Write archive first so content is never lost even if truncate fails.
            archive = self._archive_path(self.path, 1)
            archive.write_bytes(content)
            # Truncate the original in-place (Windows-safe: no MoveFileEx/rename).
            # Readers that have the file open will see EOF at the truncation point.
            with self.path.open("r+b") as fh:
                fh.truncate(0)
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
        ``self._lock`` to prevent concurrent write/rotate interleaving.
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

        If rotation truncates the file mid-iteration the iterator reaches EOF
        early; whatever rows were collected before the truncation are returned.
        An ``OSError`` (e.g. file deleted) is swallowed and returns the partial
        result.
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
    "_MAX_ARCHIVE_DEPTH",
]
