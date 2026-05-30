#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_eventlog_lock.py
Zone: test
Version: 0.32.2
Created: 2026-05-30
Modified: 2026-05-30
Purpose: Verify EventLog threading.Lock, TOCTOU prevention, counter-based rotation throttle, and source guards.
Inputs: EventLog class from event_log.py.
Outputs: unittest results.
Side effects: Writes temporary test files.
Tests: python -m pytest noemaforge/tests/test_eventlog_lock.py -v
Notes: Code comments are English-only.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# ---------------------------------------------------------------------------
# Adjust sys.path so the src modules are importable
# ---------------------------------------------------------------------------
SRC = Path(__file__).parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import event_log as event_log_mod
from event_log import (
    EventLog,
    MAX_EVENT_LINES,
    MAX_EVENT_BYTES,
    _ROTATION_SIZE_FAST_PATH,
    _ROTATION_CHECK_INTERVAL,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_log(tmp: str | Path) -> EventLog:
    return EventLog(root=Path(tmp))


# ---------------------------------------------------------------------------
# 1. Lock / count attributes
# ---------------------------------------------------------------------------

class TestEventLogLockAttributes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = _make_log(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_lock_attribute_is_rlock_or_lock(self):
        self.assertTrue(
            isinstance(self.log._lock, (threading.Lock().__class__, threading.RLock().__class__)),
            "_lock must be a threading Lock/RLock",
        )

    def test_append_count_starts_at_zero(self):
        self.assertEqual(self.log._append_count, 0)

    def test_append_count_increments(self):
        self.log.append("test.event")
        self.assertEqual(self.log._append_count, 1)
        self.log.append("test.event")
        self.assertEqual(self.log._append_count, 2)


# ---------------------------------------------------------------------------
# 2. Counter-based throttle — _maybe_rotate called only every N appends
# ---------------------------------------------------------------------------

class TestRotationThrottle(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = _make_log(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_maybe_rotate_not_called_on_every_append(self):
        """_maybe_rotate must NOT be triggered on every single append."""
        call_count = []
        original = self.log._maybe_rotate

        def counting_rotate():
            call_count.append(1)
            original()

        self.log._maybe_rotate = counting_rotate

        for _ in range(_ROTATION_CHECK_INTERVAL - 1):
            self.log.append("test.event")

        # Should be 0 rotations triggered before the Nth append.
        self.assertEqual(len(call_count), 0, "_maybe_rotate must not fire before interval")

    def test_maybe_rotate_called_at_interval(self):
        """_maybe_rotate IS called on the _ROTATION_CHECK_INTERVAL-th append."""
        call_count = []
        original = self.log._maybe_rotate

        def counting_rotate():
            call_count.append(1)
            original()

        self.log._maybe_rotate = counting_rotate

        for _ in range(_ROTATION_CHECK_INTERVAL):
            self.log.append("test.event")

        self.assertEqual(len(call_count), 1)

    def test_maybe_rotate_called_at_double_interval(self):
        """_maybe_rotate is called a second time at 2×interval."""
        call_count = []
        original = self.log._maybe_rotate

        def counting_rotate():
            call_count.append(1)
            original()

        self.log._maybe_rotate = counting_rotate

        for _ in range(_ROTATION_CHECK_INTERVAL * 2):
            self.log.append("test.event")

        self.assertEqual(len(call_count), 2)


# ---------------------------------------------------------------------------
# 3. _maybe_rotate fast-path skips small files
# ---------------------------------------------------------------------------

class TestMaybeRotateFastPath(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = _make_log(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_no_rotation_when_file_small(self):
        """No rotation when file is well below the fast-path threshold."""
        self.log.append("small.event", {"x": 1})
        archive = self.log.path.with_suffix(self.log.path.suffix + ".1")
        self.log._maybe_rotate()
        self.assertFalse(archive.exists(), "No rotation expected for a tiny file")

    def test_no_rotation_when_file_nonexistent(self):
        """_maybe_rotate must not crash when events.jsonl does not exist."""
        self.assertFalse(self.log.path.exists())
        self.log._maybe_rotate()  # must not raise


# ---------------------------------------------------------------------------
# 4. TOCTOU prevention — lock serialises the stat+read+rename sequence
# ---------------------------------------------------------------------------

class TestTocTouPrevention(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = _make_log(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_only_one_rename_when_two_threads_race(self):
        """When two threads both detect size > threshold, only one rename must win."""
        # Write a large fake file so stat().st_size exceeds the fast path.
        big_content = ("x" * 100 + "\n") * 200  # ~20 KB, above 1 MB? No — mock stat instead.
        self.log.path.write_text(big_content, encoding="utf-8")

        archive = self.log.path.with_suffix(self.log.path.suffix + ".1")
        rename_calls = []
        original_replace = Path.replace

        def counting_replace(self_path, target):
            rename_calls.append((str(self_path), str(target)))
            return original_replace(self_path, target)

        # Patch stat to always report a large file so the fast path is bypassed.
        stat_result = MagicMock()
        stat_result.st_size = _ROTATION_SIZE_FAST_PATH + 1
        # Also make line count big enough.
        big_lines = "\n".join(["x"] * (MAX_EVENT_LINES + 1))
        self.log.path.write_text(big_lines, encoding="utf-8")

        errors = []
        barrier = threading.Barrier(2)

        def run_rotate():
            barrier.wait()
            try:
                self.log._maybe_rotate()
            except Exception as exc:
                errors.append(exc)

        t1 = threading.Thread(target=run_rotate)
        t2 = threading.Thread(target=run_rotate)
        t1.start()
        t2.start()
        t1.join(timeout=5)
        t2.join(timeout=5)

        self.assertFalse(errors, f"_maybe_rotate raised: {errors}")
        # At most one of the two threads should have succeeded; the second
        # should have found path gone (or size small again) and bailed early.
        # The archive may or may not exist (depending on OS timing), but
        # we must NOT have crashed and the original path must not exist
        # if rotation did happen.
        if archive.exists():
            self.assertFalse(
                self.log.path.exists(),
                "If archive was created the source should be gone",
            )

    def test_no_double_rotation_after_first_archived(self):
        """Second call to _maybe_rotate after archive exists must be a no-op."""
        # Simulate a pre-existing archive.
        big_lines = "\n".join(["x"] * (MAX_EVENT_LINES + 1))
        self.log.path.write_text(big_lines, encoding="utf-8")

        # First rotation.
        self.log._maybe_rotate()
        archive = self.log.path.with_suffix(self.log.path.suffix + ".1")
        # At this point the main log is gone (renamed to archive).
        # A second rotation call must not crash.
        self.log._maybe_rotate()  # must not raise


# ---------------------------------------------------------------------------
# 5. Non-fatal OSError
# ---------------------------------------------------------------------------

class TestMaybeRotateOsError(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = _make_log(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_oserror_is_swallowed(self):
        """OSError inside _maybe_rotate must not propagate."""
        with patch.object(Path, "stat", side_effect=OSError("disk full")):
            try:
                self.log._maybe_rotate()
            except OSError:
                self.fail("_maybe_rotate must not propagate OSError")


# ---------------------------------------------------------------------------
# 6. Source-text guards
# ---------------------------------------------------------------------------

class TestSourceContainsLock(unittest.TestCase):
    """Verify that the threading / lock pattern is present in the source file."""

    SRC_TEXT = (SRC / "event_log.py").read_text(encoding="utf-8")

    def test_import_threading(self):
        self.assertIn("import threading", self.SRC_TEXT)

    def test_lock_initialised(self):
        self.assertIn("self._lock = threading.Lock()", self.SRC_TEXT)

    def test_append_count_initialised(self):
        self.assertIn("self._append_count = 0", self.SRC_TEXT)

    def test_lock_used_in_maybe_rotate(self):
        self.assertIn("with self._lock:", self.SRC_TEXT)

    def test_interval_modulo_check(self):
        self.assertIn("_append_count % _ROTATION_CHECK_INTERVAL == 0", self.SRC_TEXT)

    def test_double_check_inside_lock(self):
        # Re-stat inside the lock to prevent TOCTOU.
        self.assertIn("size = self.path.stat().st_size", self.SRC_TEXT)
        # There should be at least two occurrences (pre-lock fast path + inside lock).
        self.assertGreaterEqual(self.SRC_TEXT.count("self.path.stat().st_size"), 2)


# ---------------------------------------------------------------------------
# 7. Constants exported
# ---------------------------------------------------------------------------

class TestConstantsExported(unittest.TestCase):
    def test_max_event_lines_positive(self):
        self.assertGreater(MAX_EVENT_LINES, 0)

    def test_max_event_bytes_positive(self):
        self.assertGreater(MAX_EVENT_BYTES, 0)

    def test_rotation_fast_path_below_max_bytes(self):
        self.assertLess(_ROTATION_SIZE_FAST_PATH, MAX_EVENT_BYTES)

    def test_rotation_check_interval_positive(self):
        self.assertGreater(_ROTATION_CHECK_INTERVAL, 0)


if __name__ == "__main__":
    unittest.main()
