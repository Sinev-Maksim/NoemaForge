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
import uuid
from pathlib import Path
from typing import Any, Dict

from noemaforge_version import RUNTIME_VERSION
from orchestration_state import nowz

DEFAULT_EVENT_STATE = Path(os.environ.get("NOEMAFORGE_EVENT_STATE", "/var/lib/noemaforge/events"))

# Rotation thresholds: rotate when the live file hits EITHER limit.
MAX_EVENT_LINES = 10_000
MAX_EVENT_BYTES = 10 * 1024 * 1024  # 10 MB

# Fast-path: skip the line-count check below this size.
_ROTATION_SIZE_FAST_PATH = 1024 * 1024  # 1 MB

# Only check rotation every N appends to reduce stat() calls.
_ROTATION_CHECK_INTERVAL = 50

# Maximum number of archived files kept alongside the live file.
_MAX_ARCHIVE_DEPTH = 3


class EventLog:
    """Append-only JSONL event log with bounded readback and size-capped rotation.

    Thread-safety: all write paths are serialised under self._lock.
    read() does not hold the lock.

    Use status() to detect rotation events and reset after_index:

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
        # Completed rotations since process start.  Resets to 0 on each restart.
        self._rotation_count = 0
        # Stable opaque token for this process lifetime.  A new EventLog instance
        # (i.e. any server restart) generates a fresh epoch so remote pollers can
        # detect the restart even when rotation_count happens to stay at 0.
        self._server_epoch = uuid.uuid4().hex

    @staticmethod
    def _archive_path(base: Path, generation: int) -> Path:
        return base.with_suffix(base.suffix + f".{generation}")

    def _shift_archives(self) -> bool:
        """Shift existing archives one generation older.  Must hold self._lock.

        Returns True on full success, False if any operation failed.
        The caller must abort the rotation cycle on False to prevent data loss.
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
        """Rotate the live file into a .1 archive if size/line limits are exceeded.

        Must be called with self._lock held.

        Rotation strategy: copy-then-truncate (Windows-safe)
          1. Read the full file into memory.
          2. Call _shift_archives() to move .1→.2, .2→.3 (oldest dropped).
             If any shift fails, abort entirely to preserve existing archives.
          3. Write the copied content into a new .1 archive.
          4. Truncate the live file to 0 in-place (keeps the inode for readers).
          5. Increment _rotation_count.

        Exception handling:
          The outer try/except catches OSError only — not KeyboardInterrupt or
          SystemExit.  This is intentional: only I/O failures are expected here
          and catching BaseException would risk hiding process-exit signals.

          Half-rotation risk: if a KeyboardInterrupt or SystemExit is raised
          between step 3 (archive written) and step 4 (live file truncated), the
          live file retains its full content while the .1 archive also holds a
          complete copy.  On the next successful rotation:
            - _shift_archives() moves the duplicate .1 to .2.
            - A new .1 archive is written with the same live-file content again.
          After several such half-rotations, archive slots fill with identical
          copies of the current live data.  The worst-case disk overhead is
          _MAX_ARCHIVE_DEPTH * MAX_EVENT_BYTES (30 MB for default settings).

          This is accepted because:
            a) The live file is always intact — no data is lost.
            b) Duplicate archives are harmless and self-clearing: once the live
               file actually grows and rotates again, the duplicates shift out.
            c) KeyboardInterrupt during an append operation (which holds _lock)
               is extremely rare; the truncate call (step 4) is fast.

          If the caller requires stricter integrity guarantees, the rotation could
          be made atomic by using a transactional journal, but this would
          substantially increase complexity for a non-critical auxiliary log.
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
            archive.write_bytes(content)           # step 3
            with self.path.open("r+b") as fh:
                fh.truncate(0)                     # step 4
            self._rotation_count += 1              # step 5
        except OSError:
            pass

    def status(self) -> Dict[str, Any]:
        """Return a best-effort snapshot of the current log state.

        Keys:
          server_epoch (str): opaque hex token generated once at EventLog.__init__.
            Changes on every process restart (new EventLog instance).  Remote
            pollers MUST check this field first: if server_epoch differs from the
            last observed value, the process restarted — reset after_index to 0
            regardless of rotation_count.  This handles the edge case where no
            rotation has occurred in either session (rotation_count stays 0) but
            the live file was cleared by the new process.
          rotation_count (int): completed rotations since process start (resets to 0
            on restart). Protected by self._lock. Compare across calls to detect
            in-process rotation; reset after_index to 0 when it changes.
          current_size_bytes (int): approximate live file size, sampled outside
            self._lock for performance. May not be consistent with rotation_count.
          path (str): absolute path to the live events file.
        """
        size = 0
        if self.path.exists():
            try:
                size = self.path.stat().st_size
            except OSError:
                pass
        with self._lock:
            rotation_count = self._rotation_count
        return {
            "server_epoch": self._server_epoch,
            "rotation_count": rotation_count,
            "current_size_bytes": size,
            "path": str(self.path),
        }

    def append(self, event_type: str, data: Dict[str, Any] | None = None, *, actor: str = "system", trace_id: str = "") -> Dict[str, Any]:
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

        Streams the file line-by-line; callers must reset after_index to 0 after
        detecting a rotation via status()["rotation_count"] change.
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
