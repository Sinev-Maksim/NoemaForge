#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_eventlog_shift_abort.py
Zone: tests
Version: 0.32.2
Created: 2026-05-30
Modified: 2026-05-30
Purpose: Verify that _shift_archives() returns False on any failure and that
         _maybe_rotate() aborts the rotation cycle (no archive write, no
         truncate) when _shift_archives() signals failure.
Inputs: EventLog from event_log; temporary directories.
Outputs: pytest pass/fail.
Side effects: Writes and removes files under tempfile.mkdtemp().
Tests: python3 -m unittest noemaforge/tests/test_eventlog_shift_abort.py -v
Notes: Code comments are English-only.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Minimal stubs
# ---------------------------------------------------------------------------

def _install_stubs() -> None:
    stub_ver = types.ModuleType("noemaforge_version")
    stub_ver.RUNTIME_VERSION = "0.32.2"
    sys.modules.setdefault("noemaforge_version", stub_ver)

    stub_orch = types.ModuleType("orchestration_state")
    stub_orch.nowz = lambda: "2026-05-30T00:00:00Z"
    stub_orch.normalize_session_record = lambda s: dict(s)
    sys.modules.setdefault("orchestration_state", stub_orch)


_install_stubs()

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from event_log import EventLog, _MAX_ARCHIVE_DEPTH  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_log(root: Path) -> EventLog:
    return EventLog(root=root)


def _append_n(log: EventLog, n: int) -> None:
    for i in range(n):
        log.append("test.event", {"i": i})


def _plant_archive(log: EventLog, gen: int, content: str = "old data") -> None:
    """Write a fake archive file for the given generation."""
    p = EventLog._archive_path(log.path, gen)
    p.write_text(content, encoding="utf-8")


def _archive_exists(log: EventLog, gen: int) -> bool:
    return EventLog._archive_path(log.path, gen).exists()


def _archive_content(log: EventLog, gen: int) -> str:
    p = EventLog._archive_path(log.path, gen)
    return p.read_text(encoding="utf-8") if p.exists() else ""


# ===========================================================================
# Section 1 — _shift_archives() return value
# ===========================================================================

class TestShiftArchivesReturnValue(unittest.TestCase):
    """_shift_archives() must return True on full success, False on any failure."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._root = Path(self._tmpdir)
        self.log = _make_log(self._root)

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_returns_true_with_no_archives(self):
        """No archives present — nothing to move, must return True."""
        result = self.log._shift_archives()
        self.assertTrue(result)

    def test_returns_true_with_one_archive(self):
        """Single .1 archive — shifts to .2, must return True."""
        _plant_archive(self.log, 1, "archive one")
        result = self.log._shift_archives()
        self.assertTrue(result)
        self.assertTrue(_archive_exists(self.log, 2))
        self.assertFalse(_archive_exists(self.log, 1))

    def test_returns_true_with_full_depth(self):
        """Archives at all depths — oldest deleted, rest shifted, True returned."""
        for gen in range(1, _MAX_ARCHIVE_DEPTH + 1):
            _plant_archive(self.log, gen, f"gen{gen}")
        result = self.log._shift_archives()
        self.assertTrue(result)
        # .1 is now free (caller will write new archive there)
        self.assertFalse(_archive_exists(self.log, 1))
        # .2 has what was in .1
        self.assertEqual(_archive_content(self.log, 2), "gen1")
        # .3 has what was in .2
        self.assertEqual(_archive_content(self.log, 3), "gen2")
        # old .3 (gen3) was deleted — it's gone

    def test_returns_false_when_replace_raises(self):
        """If a replace() raises OSError, _shift_archives must return False."""
        _plant_archive(self.log, 1, "precious")

        # Patch Path.replace at class level — WindowsPath instances don't allow
        # per-instance attribute patches; we filter to only raise for archive paths.
        original_replace = Path.replace

        def failing_replace(self_path, target):
            if "events.jsonl" in self_path.name:
                raise OSError("simulated replace failure")
            return original_replace(self_path, target)

        with patch.object(Path, "replace", failing_replace):
            result = self.log._shift_archives()
        self.assertFalse(result)

    def test_returns_false_when_oldest_unlink_raises(self):
        """If unlinking the oldest archive raises OSError, return False."""
        for gen in range(1, _MAX_ARCHIVE_DEPTH + 1):
            _plant_archive(self.log, gen, f"gen{gen}")

        original_unlink = Path.unlink

        def failing_unlink(self_path, missing_ok: bool = False):
            if "events.jsonl" in self_path.name:
                raise OSError("simulated unlink failure")
            return original_unlink(self_path, missing_ok=missing_ok)

        with patch.object(Path, "unlink", failing_unlink):
            result = self.log._shift_archives()
        self.assertFalse(result)


# ===========================================================================
# Section 2 — _maybe_rotate() honours False return from _shift_archives
# ===========================================================================

class TestMaybeRotateAbortsOnShiftFailure(unittest.TestCase):
    """If _shift_archives() returns False, _maybe_rotate() must not write the
    new archive or truncate the live file."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._root = Path(self._tmpdir)
        self.log = _make_log(self._root)

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _force_rotation_needed(self) -> bytes:
        """Write enough JSONL lines to exceed both _ROTATION_SIZE_FAST_PATH and MAX_EVENT_LINES."""
        from event_log import MAX_EVENT_LINES, _ROTATION_SIZE_FAST_PATH

        # Each line is ~120 bytes; 10001 lines exceeds MAX_EVENT_LINES (10000)
        # and their combined size (~1.2 MB) exceeds _ROTATION_SIZE_FAST_PATH (1 MB),
        # so both checks in _maybe_rotate() reach the rotation-needed branch.
        line = (json.dumps({"event": "test", "data": "x" * 80}) + "\n").encode("utf-8")
        count = max(MAX_EVENT_LINES + 1, (_ROTATION_SIZE_FAST_PATH // len(line)) + 1)
        content = line * count
        self.log.path.write_bytes(content)
        return content

    def test_archive_not_written_on_shift_failure(self):
        """When _shift_archives() returns False, .1 archive must not be created."""
        original_content = self._force_rotation_needed()
        _plant_archive(self.log, 1, "precious archive")
        precious = _archive_content(self.log, 1)

        with patch.object(self.log, "_shift_archives", return_value=False):
            with self.log._lock:
                self.log._maybe_rotate()

        # Archive must still be the original precious content
        self.assertEqual(_archive_content(self.log, 1), precious)

    def test_live_file_not_truncated_on_shift_failure(self):
        """When _shift_archives() returns False, the live file must not be truncated."""
        original_content = self._force_rotation_needed()

        with patch.object(self.log, "_shift_archives", return_value=False):
            with self.log._lock:
                self.log._maybe_rotate()

        # Live file must still have its original content
        self.assertEqual(self.log.path.read_bytes(), original_content)

    def test_archive_written_on_shift_success(self):
        """When _shift_archives() returns True, the archive must be written."""
        self._force_rotation_needed()

        with patch.object(self.log, "_shift_archives", return_value=True):
            with self.log._lock:
                self.log._maybe_rotate()

        # Archive .1 must now exist (content was written before truncation)
        self.assertTrue(_archive_exists(self.log, 1))

    def test_live_file_truncated_on_shift_success(self):
        """When _shift_archives() returns True, the live file must be truncated."""
        self._force_rotation_needed()

        with patch.object(self.log, "_shift_archives", return_value=True):
            with self.log._lock:
                self.log._maybe_rotate()

        # Live file should now be empty (truncated to 0)
        self.assertEqual(self.log.path.stat().st_size, 0)


# ===========================================================================
# Section 3 — integration: real shift failure preserves both archives and data
# ===========================================================================

class TestIntegrationShiftFailurePreservesData(unittest.TestCase):
    """End-to-end: when a shift replace() fails, both the existing archive and
    the live file data are preserved."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._root = Path(self._tmpdir)
        self.log = _make_log(self._root)

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_precious_archive_preserved_on_replace_failure(self):
        """After a replace() failure during shift, the precious .1 archive survives."""
        from event_log import _ROTATION_SIZE_FAST_PATH

        precious = "precious archive content that must not be overwritten"
        _plant_archive(self.log, 1, precious)
        self.log.path.write_bytes(b"x" * (_ROTATION_SIZE_FAST_PATH + 1024))

        original_replace = Path.replace

        def failing_replace(self_path, target):
            if "events.jsonl" in self_path.name:
                raise OSError("simulated cross-device failure")
            return original_replace(self_path, target)

        with patch.object(Path, "replace", failing_replace):
            with self.log._lock:
                self.log._maybe_rotate()

        self.assertEqual(_archive_content(self.log, 1), precious,
                         "Precious archive must survive a shift failure")

    def test_live_file_data_preserved_on_replace_failure(self):
        """After a replace() failure during shift, the live file data survives."""
        from event_log import _ROTATION_SIZE_FAST_PATH

        _plant_archive(self.log, 1, "precious")
        live_content = b"important live events\n" * 1000
        # Pad to exceed fast-path size
        live_content += b"x" * (_ROTATION_SIZE_FAST_PATH - len(live_content) + 100)
        self.log.path.write_bytes(live_content)

        original_replace = Path.replace

        def failing_replace(self_path, target):
            if "events.jsonl" in self_path.name:
                raise OSError("simulated failure")
            return original_replace(self_path, target)

        with patch.object(Path, "replace", failing_replace):
            with self.log._lock:
                self.log._maybe_rotate()

        self.assertEqual(self.log.path.read_bytes(), live_content,
                         "Live file must not be truncated when shift failed")


# ===========================================================================
# Section 4 — thread safety: _shift_archives() called under lock
# ===========================================================================

class TestShiftCalledUnderLock(unittest.TestCase):
    """append() must hold the lock while calling _maybe_rotate (and thus _shift_archives)."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._root = Path(self._tmpdir)
        self.log = _make_log(self._root)

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_lock_held_during_rotation(self):
        """Verify that _lock is held when _maybe_rotate is called."""
        from event_log import _ROTATION_CHECK_INTERVAL

        lock_held_during_rotate = []

        original_maybe_rotate = self.log._maybe_rotate

        def spy_maybe_rotate():
            lock_held_during_rotate.append(self.log._lock.locked())
            original_maybe_rotate()

        self.log._maybe_rotate = spy_maybe_rotate
        self.log._append_count = _ROTATION_CHECK_INTERVAL - 1
        self.log.append("test.event", {})

        self.assertTrue(any(lock_held_during_rotate),
                        "_maybe_rotate should be called with _lock held")


if __name__ == "__main__":
    unittest.main()
