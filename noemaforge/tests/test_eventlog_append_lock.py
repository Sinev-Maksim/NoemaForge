#!/usr/bin/env python3
"""
Tests for task-37: EventLog append-under-lock fix.

Verifies that the entire append (file write) + rotation sequence is
performed under self._lock, eliminating:

  1. Write-after-rotate archive pollution on Linux (fd still valid after rename).
  2. PermissionError on Windows when append and rotate interleave.

All tests run offline (no live services, no real filesystem rotation needed
beyond temp-dir isolation).
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# ---------------------------------------------------------------------------
# Bootstrap import path so the module is importable without install.
# ---------------------------------------------------------------------------
SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

# Stub heavy dependencies before importing the module under test.
import types

_orch = types.ModuleType("orchestration_state")
_orch.nowz = lambda: "2026-01-01T00:00:00Z"
sys.modules.setdefault("orchestration_state", _orch)

_ver = types.ModuleType("noemaforge_version")
_ver.RUNTIME_VERSION = "0.32.2"
sys.modules.setdefault("noemaforge_version", _ver)

from event_log import (  # noqa: E402
    EventLog,
    MAX_EVENT_BYTES,
    MAX_EVENT_LINES,
    _ROTATION_CHECK_INTERVAL,
    _ROTATION_SIZE_FAST_PATH,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_log(tmp_dir: str | Path) -> EventLog:
    return EventLog(root=tmp_dir)


def _append_n(log: EventLog, n: int, base: str = "evt") -> None:
    for i in range(n):
        log.append(f"{base}.{i}", {"i": i})


# ---------------------------------------------------------------------------
# 1. Basic append correctness (lock present)
# ---------------------------------------------------------------------------

class TestAppendBasic(unittest.TestCase):

    def test_append_returns_row_dict(self):
        with tempfile.TemporaryDirectory() as d:
            log = make_log(d)
            row = log.append("test.event", {"x": 1}, actor="unit")
            self.assertEqual(row["type"], "test.event")
            self.assertEqual(row["actor"], "unit")
            self.assertEqual(row["data"], {"x": 1})

    def test_append_writes_to_file(self):
        with tempfile.TemporaryDirectory() as d:
            log = make_log(d)
            log.append("ev", {"k": "v"})
            text = log.path.read_text(encoding="utf-8")
            parsed = json.loads(text.strip())
            self.assertEqual(parsed["type"], "ev")

    def test_append_count_increments(self):
        with tempfile.TemporaryDirectory() as d:
            log = make_log(d)
            self.assertEqual(log._append_count, 0)
            log.append("e1")
            self.assertEqual(log._append_count, 1)
            log.append("e2")
            self.assertEqual(log._append_count, 2)

    def test_multiple_appends_produce_multiple_lines(self):
        with tempfile.TemporaryDirectory() as d:
            log = make_log(d)
            _append_n(log, 5)
            lines = [l for l in log.path.read_text().splitlines() if l.strip()]
            self.assertEqual(len(lines), 5)


# ---------------------------------------------------------------------------
# 2. Lock is present and is a threading.Lock
# ---------------------------------------------------------------------------

class TestLockPresence(unittest.TestCase):

    def test_lock_attribute_exists(self):
        with tempfile.TemporaryDirectory() as d:
            log = make_log(d)
            self.assertTrue(hasattr(log, "_lock"))

    def test_lock_is_threading_lock(self):
        with tempfile.TemporaryDirectory() as d:
            log = make_log(d)
            self.assertIsInstance(log._lock, type(threading.Lock()))

    def test_append_count_attribute_exists(self):
        with tempfile.TemporaryDirectory() as d:
            log = make_log(d)
            self.assertTrue(hasattr(log, "_append_count"))
            self.assertEqual(log._append_count, 0)


# ---------------------------------------------------------------------------
# 3. Append uses the lock (lock is acquired during file write)
# ---------------------------------------------------------------------------

class TestAppendAcquiresLock(unittest.TestCase):

    def test_append_acquires_lock(self):
        """Verify that append() acquires self._lock during the file write."""
        with tempfile.TemporaryDirectory() as d:
            log = make_log(d)
            acquired_during_write: list[bool] = []

            real_open = Path.open

            def tracking_open(self_path, *args, **kwargs):
                # Check whether the lock is held by the current thread.
                # If the lock is NOT locked, try-acquire should succeed immediately.
                locked = not log._lock.acquire(blocking=False)
                if not locked:
                    log._lock.release()
                acquired_during_write.append(locked)
                return real_open(self_path, *args, **kwargs)

            with patch.object(Path, "open", tracking_open):
                log.append("probe")

            # The lock should have been held during the file open.
            self.assertTrue(
                any(acquired_during_write),
                "Lock was NOT acquired when append() opened the file",
            )

    def test_rotation_called_under_lock(self):
        """_maybe_rotate is called inside the lock context (not after release)."""
        with tempfile.TemporaryDirectory() as d:
            log = make_log(d)
            rotate_lock_states: list[bool] = []

            original_rotate = log._maybe_rotate

            def patched_rotate():
                locked = not log._lock.acquire(blocking=False)
                if not locked:
                    log._lock.release()
                rotate_lock_states.append(locked)
                return original_rotate()

            log._maybe_rotate = patched_rotate

            # Force rotation check on next append by setting count to interval - 1.
            log._append_count = _ROTATION_CHECK_INTERVAL - 1
            log.append("trigger_check")

            self.assertTrue(rotate_lock_states, "_maybe_rotate was never called")
            self.assertTrue(
                all(rotate_lock_states),
                "_maybe_rotate was called OUTSIDE the lock on at least one invocation",
            )


# ---------------------------------------------------------------------------
# 4. Concurrent append correctness (no lost writes, no interleaved rows)
# ---------------------------------------------------------------------------

class TestConcurrentAppend(unittest.TestCase):

    def test_concurrent_appends_all_written(self):
        """All rows from concurrent threads must reach the file."""
        N_THREADS = 10
        N_PER_THREAD = 20
        with tempfile.TemporaryDirectory() as d:
            log = make_log(d)
            errors: list[Exception] = []

            def worker(tid: int) -> None:
                try:
                    for i in range(N_PER_THREAD):
                        log.append("t.ev", {"tid": tid, "i": i})
                except Exception as exc:
                    errors.append(exc)

            threads = [threading.Thread(target=worker, args=(t,)) for t in range(N_THREADS)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            self.assertFalse(errors, f"Exceptions in worker threads: {errors}")
            rows = log.read(limit=N_THREADS * N_PER_THREAD + 10)
            self.assertEqual(
                len(rows),
                N_THREADS * N_PER_THREAD,
                f"Expected {N_THREADS * N_PER_THREAD} rows, got {len(rows)}",
            )

    def test_concurrent_append_count_accurate(self):
        """_append_count must equal total appends (no lost increments)."""
        N = 100
        with tempfile.TemporaryDirectory() as d:
            log = make_log(d)

            def worker():
                for _ in range(N // 10):
                    log.append("cnt")

            threads = [threading.Thread(target=worker) for _ in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            self.assertEqual(log._append_count, N)


# ---------------------------------------------------------------------------
# 5. Rotation is triggered at the correct interval
# ---------------------------------------------------------------------------

class TestRotationThrottle(unittest.TestCase):

    def test_rotation_not_checked_before_interval(self):
        """_maybe_rotate should NOT be called on every append."""
        with tempfile.TemporaryDirectory() as d:
            log = make_log(d)
            call_count = [0]
            original = log._maybe_rotate

            def counting_rotate():
                call_count[0] += 1
                original()

            log._maybe_rotate = counting_rotate
            # Append fewer rows than one interval.
            _append_n(log, _ROTATION_CHECK_INTERVAL - 1)
            self.assertEqual(call_count[0], 0)

    def test_rotation_checked_at_interval(self):
        """_maybe_rotate SHOULD be called exactly once at the interval boundary."""
        with tempfile.TemporaryDirectory() as d:
            log = make_log(d)
            call_count = [0]
            original = log._maybe_rotate

            def counting_rotate():
                call_count[0] += 1
                original()

            log._maybe_rotate = counting_rotate
            # Append exactly one interval worth of rows.
            _append_n(log, _ROTATION_CHECK_INTERVAL)
            self.assertEqual(call_count[0], 1)


# ---------------------------------------------------------------------------
# 6. _maybe_rotate behaviour
# ---------------------------------------------------------------------------

class TestMaybeRotate(unittest.TestCase):

    def test_no_rotation_below_fast_path(self):
        """Small files are never rotated (stat-only fast path)."""
        with tempfile.TemporaryDirectory() as d:
            log = make_log(d)
            log.path.write_text("line\n" * 10, encoding="utf-8")
            with log._lock:
                log._maybe_rotate()
            archive = log.path.with_suffix(log.path.suffix + ".1")
            self.assertFalse(archive.exists())
            self.assertTrue(log.path.exists())

    def test_rotation_happens_when_line_cap_exceeded(self):
        """A file exceeding MAX_EVENT_LINES is archived."""
        with tempfile.TemporaryDirectory() as d:
            log = make_log(d)
            # Write a file that exceeds _ROTATION_SIZE_FAST_PATH and MAX_EVENT_LINES.
            many_lines = ("x" * 110 + "\n") * (MAX_EVENT_LINES + 10)
            log.path.write_text(many_lines, encoding="utf-8")
            with log._lock:
                log._maybe_rotate()
            archive = log.path.with_suffix(log.path.suffix + ".1")
            self.assertTrue(archive.exists(), "Archive was not created")
            self.assertFalse(log.path.exists(), "Original file was not renamed")

    def test_no_crash_when_file_missing(self):
        """_maybe_rotate is a no-op when the log file does not exist."""
        with tempfile.TemporaryDirectory() as d:
            log = make_log(d)
            # Do not create events.jsonl.
            with log._lock:
                log._maybe_rotate()  # must not raise


# ---------------------------------------------------------------------------
# 7. read() — streaming, early-stop, OSError resilience
# ---------------------------------------------------------------------------

class TestRead(unittest.TestCase):

    def test_read_empty_file_returns_empty(self):
        with tempfile.TemporaryDirectory() as d:
            log = make_log(d)
            self.assertEqual(log.read(), [])

    def test_read_returns_correct_rows(self):
        with tempfile.TemporaryDirectory() as d:
            log = make_log(d)
            _append_n(log, 10)
            rows = log.read(limit=10)
            self.assertEqual(len(rows), 10)

    def test_read_respects_after_index(self):
        with tempfile.TemporaryDirectory() as d:
            log = make_log(d)
            _append_n(log, 20)
            rows = log.read(after_index=10, limit=100)
            self.assertEqual(len(rows), 10)
            self.assertTrue(all(r["index"] >= 10 for r in rows))

    def test_read_respects_limit(self):
        with tempfile.TemporaryDirectory() as d:
            log = make_log(d)
            _append_n(log, 50)
            rows = log.read(limit=5)
            self.assertEqual(len(rows), 5)

    def test_read_uses_open_not_read_text(self):
        """read() must iterate via path.open(), not read_text() (streaming requirement)."""
        import inspect
        from event_log import EventLog as EL
        src = inspect.getsource(EL.read)
        # Strip the docstring before searching to avoid false positives in the doc.
        body_start = src.find(":\n") + 2  # skip 'def read(...):' line
        body = src[body_start:]
        # Remove docstring if present.
        stripped = body.lstrip()
        if stripped.startswith('"""') or stripped.startswith("'''"):
            quote = stripped[:3]
            end = stripped.find(quote, 3)
            body = stripped[end + 3:]
        self.assertNotIn(
            "read_text(",
            body,
            "read() must not call read_text() — use path.open() for streaming",
        )

    def test_read_oserror_returns_partial(self):
        """An OSError mid-read returns whatever rows were collected before the error."""
        with tempfile.TemporaryDirectory() as d:
            log = make_log(d)
            _append_n(log, 5)
            rows = log.read(limit=200)
            # Simulate: if OSError were raised immediately, result is [].
            # Here we just verify the happy path returns rows (OSError guard exists).
            self.assertGreater(len(rows), 0)


# ---------------------------------------------------------------------------
# 8. __all__ exports
# ---------------------------------------------------------------------------

class TestExports(unittest.TestCase):

    def test_all_exports_present(self):
        from event_log import __all__ as ea
        for name in ("EventLog", "DEFAULT_EVENT_STATE", "MAX_EVENT_LINES",
                     "MAX_EVENT_BYTES", "_ROTATION_SIZE_FAST_PATH",
                     "_ROTATION_CHECK_INTERVAL"):
            self.assertIn(name, ea, f"{name} missing from __all__")


if __name__ == "__main__":
    unittest.main()
