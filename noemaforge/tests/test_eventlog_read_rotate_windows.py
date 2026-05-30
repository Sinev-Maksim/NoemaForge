#!/usr/bin/env python3
"""
Tests for task-38: EventLog copy-then-truncate rotation (Windows-safe).

Verifies that _maybe_rotate() uses copy-to-archive + truncate-original
instead of path.replace() (MoveFileEx), so that a reader holding a file
handle does not cause PermissionError and silently block rotation.

All tests run offline (temp-dir isolation, no live services).
"""
from __future__ import annotations

import inspect
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock, call

# ---------------------------------------------------------------------------
# Bootstrap import path.
# ---------------------------------------------------------------------------
SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

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


def _big_enough_content(n_lines: int = MAX_EVENT_LINES + 10) -> bytes:
    """Produce content that exceeds both size and line caps."""
    line = ("x" * 110 + "\n").encode()
    return line * n_lines


# ---------------------------------------------------------------------------
# 1. _maybe_rotate uses copy-then-truncate, not path.replace()
# ---------------------------------------------------------------------------

class TestRotationMechanism(unittest.TestCase):

    def test_rotate_does_not_call_replace(self):
        """_maybe_rotate must NOT call path.replace() (MoveFileEx rename) — Windows incompatible.

        Specifically checks that self.path.replace(...) (the rename operation)
        is absent from the implementation.  The string 'errors="replace"' and
        docstring mentions of path.replace() are acceptable; the forbidden pattern
        is the actual rename call.
        """
        src = inspect.getsource(EventLog._maybe_rotate)
        # Strip the docstring before searching so explanatory text is excluded.
        body_start = src.find(":\n") + 2
        body = src[body_start:]
        stripped = body.lstrip()
        if stripped.startswith('"""') or stripped.startswith("'''"):
            quote = stripped[:3]
            end = stripped.find(quote, 3)
            body = stripped[end + 3:]
        # The MoveFileEx rename call would appear as 'self.path.replace(' or
        # 'archive).replace(' etc.  The specific pattern to forbid is '.replace('
        # on a Path object used as the rotation target, which always looks like
        # 'self.path.replace(' in this module.
        self.assertNotIn(
            "self.path.replace(",
            body,
            "_maybe_rotate calls self.path.replace() (MoveFileEx) — must use copy-then-truncate",
        )

    def test_rotate_writes_archive_file(self):
        """Rotation must create an archive file next to the original."""
        with tempfile.TemporaryDirectory() as d:
            log = make_log(d)
            log.path.write_bytes(_big_enough_content())
            with log._lock:
                log._maybe_rotate()
            archive = log.path.with_suffix(log.path.suffix + ".1")
            self.assertTrue(archive.exists(), "Archive file was not created")

    def test_rotate_truncates_original(self):
        """After rotation the original file must be empty (truncated to 0 bytes)."""
        with tempfile.TemporaryDirectory() as d:
            log = make_log(d)
            log.path.write_bytes(_big_enough_content())
            with log._lock:
                log._maybe_rotate()
            self.assertTrue(log.path.exists(), "Original file must still exist after rotation")
            self.assertEqual(log.path.stat().st_size, 0, "Original file was not truncated")

    def test_rotate_archive_content_matches_original(self):
        """Archive content must be identical to the pre-rotation original."""
        with tempfile.TemporaryDirectory() as d:
            log = make_log(d)
            original_content = _big_enough_content()
            log.path.write_bytes(original_content)
            with log._lock:
                log._maybe_rotate()
            archive = log.path.with_suffix(log.path.suffix + ".1")
            self.assertEqual(archive.read_bytes(), original_content)

    def test_rotate_original_still_writable_after_truncate(self):
        """After rotation, new appends must go into the (now-empty) original."""
        with tempfile.TemporaryDirectory() as d:
            log = make_log(d)
            log.path.write_bytes(_big_enough_content())
            with log._lock:
                log._maybe_rotate()
            # Append after rotation should succeed and produce a non-empty file.
            log.append("post.rotate")
            self.assertGreater(log.path.stat().st_size, 0)


# ---------------------------------------------------------------------------
# 2. No rotation below fast-path threshold
# ---------------------------------------------------------------------------

class TestRotationFastPath(unittest.TestCase):

    def test_no_rotation_small_file(self):
        with tempfile.TemporaryDirectory() as d:
            log = make_log(d)
            log.path.write_text("line\n" * 5, encoding="utf-8")
            with log._lock:
                log._maybe_rotate()
            archive = log.path.with_suffix(log.path.suffix + ".1")
            self.assertFalse(archive.exists())

    def test_no_rotation_missing_file(self):
        with tempfile.TemporaryDirectory() as d:
            log = make_log(d)
            # events.jsonl does not exist yet.
            with log._lock:
                log._maybe_rotate()  # must not raise


# ---------------------------------------------------------------------------
# 3. read() uses streaming open() — no full read_text() load
# ---------------------------------------------------------------------------

class TestReadStreaming(unittest.TestCase):

    def test_read_uses_open_not_read_text(self):
        """read() must iterate via path.open(), not load the whole file with read_text()."""
        src = inspect.getsource(EventLog.read)
        # Strip the docstring before searching.
        body_start = src.find(":\n") + 2
        body = src[body_start:]
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

    def test_read_limit_respected(self):
        with tempfile.TemporaryDirectory() as d:
            log = make_log(d)
            for i in range(30):
                log.append(f"e.{i}")
            rows = log.read(limit=5)
            self.assertEqual(len(rows), 5)

    def test_read_after_index_respected(self):
        with tempfile.TemporaryDirectory() as d:
            log = make_log(d)
            for i in range(20):
                log.append(f"e.{i}")
            rows = log.read(after_index=15, limit=100)
            self.assertEqual(len(rows), 5)
            self.assertTrue(all(r["index"] >= 15 for r in rows))


# ---------------------------------------------------------------------------
# 4. Concurrent read + rotate (Windows safety)
# ---------------------------------------------------------------------------

class TestConcurrentReadRotate(unittest.TestCase):

    def test_read_while_rotate_does_not_raise(self):
        """A read() that overlaps with _maybe_rotate() must not propagate an exception."""
        with tempfile.TemporaryDirectory() as d:
            log = make_log(d)
            # Pre-populate enough data to trigger rotation.
            for i in range(5):
                log.append(f"seed.{i}")

            errors: list[Exception] = []

            def reader():
                try:
                    for _ in range(20):
                        log.read(limit=200)
                except Exception as exc:
                    errors.append(exc)

            def rotator():
                try:
                    log.path.write_bytes(_big_enough_content())
                    with log._lock:
                        log._maybe_rotate()
                except Exception as exc:
                    errors.append(exc)

            t_read = threading.Thread(target=reader)
            t_rot = threading.Thread(target=rotator)
            t_read.start()
            t_rot.start()
            t_read.join(timeout=5)
            t_rot.join(timeout=5)

            self.assertFalse(errors, f"Exceptions during concurrent read+rotate: {errors}")

    def test_rotate_does_not_prevent_subsequent_appends(self):
        """Rotation via copy+truncate must not prevent further appends."""
        with tempfile.TemporaryDirectory() as d:
            log = make_log(d)
            log.path.write_bytes(_big_enough_content())
            with log._lock:
                log._maybe_rotate()
            # These should not raise even though the file was truncated.
            for i in range(5):
                log.append(f"after.rotate.{i}")
            rows = log.read(limit=10)
            self.assertEqual(len(rows), 5)


# ---------------------------------------------------------------------------
# 5. Lock presence and append-under-lock (inherited from task-37 contract)
# ---------------------------------------------------------------------------

class TestLockContract(unittest.TestCase):

    def test_lock_attribute_present(self):
        with tempfile.TemporaryDirectory() as d:
            log = make_log(d)
            self.assertTrue(hasattr(log, "_lock"))
            self.assertIsInstance(log._lock, type(threading.Lock()))

    def test_append_under_lock(self):
        """append() must acquire self._lock before writing to the file."""
        with tempfile.TemporaryDirectory() as d:
            log = make_log(d)
            lock_held: list[bool] = []

            real_open = Path.open

            def tracking_open(self_path, *args, **kwargs):
                held = not log._lock.acquire(blocking=False)
                if not held:
                    log._lock.release()
                lock_held.append(held)
                return real_open(self_path, *args, **kwargs)

            with patch.object(Path, "open", tracking_open):
                log.append("probe")

            self.assertTrue(any(lock_held), "Lock was NOT held during append() file open")

    def test_concurrent_appends_all_written(self):
        N_THREADS, N_EACH = 8, 15
        with tempfile.TemporaryDirectory() as d:
            log = make_log(d)
            errors: list[Exception] = []

            def worker(tid):
                try:
                    for i in range(N_EACH):
                        log.append("t", {"tid": tid, "i": i})
                except Exception as exc:
                    errors.append(exc)

            threads = [threading.Thread(target=worker, args=(t,)) for t in range(N_THREADS)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            self.assertFalse(errors)
            rows = log.read(limit=N_THREADS * N_EACH + 5)
            self.assertEqual(len(rows), N_THREADS * N_EACH)


# ---------------------------------------------------------------------------
# 6. __all__ exports
# ---------------------------------------------------------------------------

class TestExports(unittest.TestCase):

    def test_all_exports_present(self):
        from event_log import __all__ as ea
        for name in ("EventLog", "DEFAULT_EVENT_STATE", "MAX_EVENT_LINES",
                     "MAX_EVENT_BYTES", "_ROTATION_SIZE_FAST_PATH",
                     "_ROTATION_CHECK_INTERVAL"):
            self.assertIn(name, ea)


if __name__ == "__main__":
    unittest.main()
