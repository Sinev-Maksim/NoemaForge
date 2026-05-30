#!/usr/bin/env python3
"""
Tests for task-41: EventLog archive-shift rotation (no overwrite).

Verifies that _maybe_rotate() shifts existing archives (.1 → .2 → .3)
before writing the new archive, so that a second rotation does NOT
overwrite and destroy the first archive.

All tests run offline with temp-dir isolation.
"""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path

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
    _MAX_ARCHIVE_DEPTH,
    _ROTATION_CHECK_INTERVAL,
    _ROTATION_SIZE_FAST_PATH,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_log(tmp: str | Path) -> EventLog:
    return EventLog(root=tmp)


def _big_content(n_lines: int = MAX_EVENT_LINES + 10) -> bytes:
    """Return content that exceeds both rotation thresholds."""
    return (("x" * 110 + "\n") * n_lines).encode()


# ---------------------------------------------------------------------------
# 1. First rotation — archive written correctly
# ---------------------------------------------------------------------------

class TestFirstRotation(unittest.TestCase):

    def test_first_rotation_creates_archive_1(self):
        with tempfile.TemporaryDirectory() as d:
            log = make_log(d)
            log.path.write_bytes(_big_content())
            with log._lock:
                log._maybe_rotate()
            archive1 = log._archive_path(log.path, 1)
            self.assertTrue(archive1.exists(), "events.jsonl.1 not created")

    def test_first_rotation_truncates_original(self):
        with tempfile.TemporaryDirectory() as d:
            log = make_log(d)
            log.path.write_bytes(_big_content())
            with log._lock:
                log._maybe_rotate()
            self.assertEqual(log.path.stat().st_size, 0)

    def test_first_rotation_archive_content_correct(self):
        with tempfile.TemporaryDirectory() as d:
            log = make_log(d)
            original = _big_content()
            log.path.write_bytes(original)
            with log._lock:
                log._maybe_rotate()
            archive1 = log._archive_path(log.path, 1)
            self.assertEqual(archive1.read_bytes(), original)


# ---------------------------------------------------------------------------
# 2. Second rotation — archive shifted, not overwritten
# ---------------------------------------------------------------------------

class TestArchiveShift(unittest.TestCase):

    def _do_two_rotations(self, d: str) -> "tuple[bytes, bytes]":
        log = make_log(d)
        content_a = _big_content()
        log.path.write_bytes(content_a)
        with log._lock:
            log._maybe_rotate()
        # Now the log is empty; write more data and rotate again.
        content_b = _big_content(n_lines=MAX_EVENT_LINES + 20)
        log.path.write_bytes(content_b)
        with log._lock:
            log._maybe_rotate()
        return content_a, content_b

    def test_second_rotation_does_not_overwrite_first_archive(self):
        with tempfile.TemporaryDirectory() as d:
            content_a, content_b = self._do_two_rotations(d)
            log = make_log(d)
            archive1 = log._archive_path(log.path, 1)
            archive2 = log._archive_path(log.path, 2)
            self.assertTrue(archive2.exists(), "events.jsonl.2 not created after second rotation")
            # Archive .2 must contain the FIRST batch (content_a), not content_b.
            self.assertEqual(
                archive2.read_bytes(),
                content_a,
                "First archive was overwritten by second rotation",
            )
            # Archive .1 must contain the SECOND batch (content_b).
            self.assertEqual(archive1.read_bytes(), content_b)

    def test_three_rotations_keep_max_depth(self):
        with tempfile.TemporaryDirectory() as d:
            log = make_log(d)
            contents = []
            for i in range(_MAX_ARCHIVE_DEPTH + 1):
                c = _big_content(n_lines=MAX_EVENT_LINES + 10 + i)
                log.path.write_bytes(c)
                contents.append(c)
                with log._lock:
                    log._maybe_rotate()
            # Only _MAX_ARCHIVE_DEPTH archives should exist.
            for gen in range(1, _MAX_ARCHIVE_DEPTH + 1):
                arc = log._archive_path(log.path, gen)
                self.assertTrue(arc.exists(), f"events.jsonl.{gen} missing")
            # Generation _MAX_ARCHIVE_DEPTH + 1 must NOT exist.
            overflow = log._archive_path(log.path, _MAX_ARCHIVE_DEPTH + 1)
            self.assertFalse(overflow.exists(), f"Archive depth exceeded: {overflow} should not exist")

    def test_oldest_archive_dropped_when_depth_exceeded(self):
        """The oldest archive is deleted when a new rotation would exceed depth."""
        with tempfile.TemporaryDirectory() as d:
            log = make_log(d)
            # Fill all archive slots.
            sentinel_content = b"OLDEST CONTENT\n" * 5000
            log.path.write_bytes(_big_content())
            with log._lock:
                log._maybe_rotate()
            for _ in range(_MAX_ARCHIVE_DEPTH - 1):
                log.path.write_bytes(_big_content())
                with log._lock:
                    log._maybe_rotate()
            # Verify depth is full before the triggering rotation.
            oldest_before = log._archive_path(log.path, _MAX_ARCHIVE_DEPTH)
            self.assertTrue(oldest_before.exists())
            # One more rotation should drop the oldest.
            log.path.write_bytes(_big_content())
            with log._lock:
                log._maybe_rotate()
            # The slot _MAX_ARCHIVE_DEPTH still exists (filled by the shift),
            # but a depth+1 slot must not exist.
            overflow = log._archive_path(log.path, _MAX_ARCHIVE_DEPTH + 1)
            self.assertFalse(overflow.exists())


# ---------------------------------------------------------------------------
# 3. _shift_archives() behaviour in isolation
# ---------------------------------------------------------------------------

class TestShiftArchives(unittest.TestCase):

    def test_shift_moves_gen1_to_gen2(self):
        with tempfile.TemporaryDirectory() as d:
            log = make_log(d)
            arc1 = log._archive_path(log.path, 1)
            arc1.write_bytes(b"gen1 content")
            with log._lock:
                log._shift_archives()
            arc2 = log._archive_path(log.path, 2)
            self.assertTrue(arc2.exists(), "events.jsonl.2 not created by shift")
            self.assertFalse(arc1.exists(), "events.jsonl.1 not moved by shift")
            self.assertEqual(arc2.read_bytes(), b"gen1 content")

    def test_shift_drops_oldest_when_full(self):
        with tempfile.TemporaryDirectory() as d:
            log = make_log(d)
            # Create all archive slots.
            for gen in range(1, _MAX_ARCHIVE_DEPTH + 1):
                arc = log._archive_path(log.path, gen)
                arc.write_bytes(f"gen{gen}".encode())
            with log._lock:
                log._shift_archives()
            # Generation _MAX_ARCHIVE_DEPTH + 1 must NOT exist (would overflow).
            overflow = log._archive_path(log.path, _MAX_ARCHIVE_DEPTH + 1)
            self.assertFalse(overflow.exists())

    def test_shift_noop_when_no_archives(self):
        with tempfile.TemporaryDirectory() as d:
            log = make_log(d)
            with log._lock:
                log._shift_archives()  # must not raise


# ---------------------------------------------------------------------------
# 4. No rotation below fast-path threshold
# ---------------------------------------------------------------------------

class TestNoRotationSmall(unittest.TestCase):

    def test_no_rotation_for_small_file(self):
        with tempfile.TemporaryDirectory() as d:
            log = make_log(d)
            log.path.write_text("line\n" * 5, encoding="utf-8")
            with log._lock:
                log._maybe_rotate()
            arc1 = log._archive_path(log.path, 1)
            self.assertFalse(arc1.exists())

    def test_no_rotation_missing_file(self):
        with tempfile.TemporaryDirectory() as d:
            log = make_log(d)
            with log._lock:
                log._maybe_rotate()  # must not raise


# ---------------------------------------------------------------------------
# 5. __all__ exports
# ---------------------------------------------------------------------------

class TestExports(unittest.TestCase):

    def test_all_exports_present(self):
        from event_log import __all__ as ea
        for name in ("EventLog", "DEFAULT_EVENT_STATE", "MAX_EVENT_LINES",
                     "MAX_EVENT_BYTES", "_ROTATION_SIZE_FAST_PATH",
                     "_ROTATION_CHECK_INTERVAL", "_MAX_ARCHIVE_DEPTH"):
            self.assertIn(name, ea)


# ---------------------------------------------------------------------------
# 6. Concurrent append safety with rotation
# ---------------------------------------------------------------------------

class TestConcurrentWithRotation(unittest.TestCase):

    def test_concurrent_appends_survive_rotation(self):
        """All threads complete without exception even when rotation fires."""
        N_THREADS = 8
        with tempfile.TemporaryDirectory() as d:
            log = make_log(d)
            errors: list[Exception] = []

            def worker():
                try:
                    for i in range(20):
                        log.append("t", {"i": i})
                except Exception as exc:
                    errors.append(exc)

            # Pre-fill to trigger rotation on early appends.
            log.path.write_bytes(_big_content())

            threads = [threading.Thread(target=worker) for _ in range(N_THREADS)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=10)

            self.assertFalse(errors, f"Thread errors: {errors}")


if __name__ == "__main__":
    unittest.main()
