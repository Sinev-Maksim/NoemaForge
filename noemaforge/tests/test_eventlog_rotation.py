#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_eventlog_rotation.py
Zone: test
Version: 0.32.2
Created: 2026-05-30
Modified: 2026-05-30
Purpose: TDD tests for EventLog rotation/size-cap (_maybe_rotate()).
  Verifies that events.jsonl is rotated to events.jsonl.1 when either
  MAX_EVENT_LINES (10,000) or MAX_EVENT_BYTES (10 MB) is exceeded,
  that normal-sized logs are never rotated, and that rotation is
  non-fatal even when OSError occurs.
Inputs: event_log.EventLog, event_log.MAX_EVENT_LINES, event_log.MAX_EVENT_BYTES.
Outputs: test pass/fail.
Side effects: Creates and removes temporary directories.
Tests: python noemaforge/tests/test_eventlog_rotation.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_SRC = Path(__file__).parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from event_log import EventLog, MAX_EVENT_LINES, MAX_EVENT_BYTES, _ROTATION_SIZE_FAST_PATH  # noqa: E402


class TestConstantsExported(unittest.TestCase):
    """Rotation constants are exported from event_log and have expected values."""

    def test_max_event_lines_is_10000(self) -> None:
        self.assertEqual(MAX_EVENT_LINES, 10_000)

    def test_max_event_bytes_is_10mb(self) -> None:
        self.assertEqual(MAX_EVENT_BYTES, 10 * 1024 * 1024)

    def test_fast_path_threshold_positive(self) -> None:
        self.assertGreater(_ROTATION_SIZE_FAST_PATH, 0)


class TestMaybeRotate(unittest.TestCase):
    """EventLog._maybe_rotate() rotates only when thresholds are exceeded."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.td = Path(self._td.name)

    def tearDown(self) -> None:
        self._td.cleanup()

    def _make_log(self) -> EventLog:
        return EventLog(self.td / "events")

    def _write_fake_log(self, log: EventLog, n_lines: int, line_bytes: int = 100) -> None:
        """Write n_lines of fake content to events.jsonl without going through append()."""
        content = ("x" * (line_bytes - 1) + "\n") * n_lines
        log.path.write_text(content, encoding="utf-8")

    def test_small_file_not_rotated(self) -> None:
        """Files under 1 MB fast path are never rotated."""
        log = self._make_log()
        # Write 500 lines — well under both thresholds
        self._write_fake_log(log, 500, line_bytes=100)
        log._maybe_rotate()
        self.assertTrue(log.path.exists(), "events.jsonl must still exist")
        archive = log.path.with_suffix(log.path.suffix + ".1")
        self.assertFalse(archive.exists(), "No archive expected for small file")

    def test_nonexistent_file_no_error(self) -> None:
        """_maybe_rotate() is a no-op when events.jsonl does not exist."""
        log = self._make_log()
        self.assertFalse(log.path.exists())
        log._maybe_rotate()  # must not raise

    def test_line_threshold_triggers_rotation(self) -> None:
        """When line count > MAX_EVENT_LINES, the file is rotated."""
        log = self._make_log()
        # Fake a file that is > 1 MB and has > MAX_EVENT_LINES lines
        # 10,001 lines × 200 bytes = ~2 MB (above fast-path threshold)
        self._write_fake_log(log, MAX_EVENT_LINES + 1, line_bytes=200)
        log._maybe_rotate()
        archive = log.path.with_suffix(log.path.suffix + ".1")
        self.assertTrue(archive.exists(), "Archive events.jsonl.1 must exist after rotation")

    def test_line_threshold_rotation_removes_active_log(self) -> None:
        """After rotation the active events.jsonl is gone."""
        log = self._make_log()
        self._write_fake_log(log, MAX_EVENT_LINES + 1, line_bytes=200)
        log._maybe_rotate()
        self.assertFalse(log.path.exists(), "events.jsonl must be renamed away")

    def test_size_threshold_triggers_rotation(self) -> None:
        """When file size > MAX_EVENT_BYTES (10 MB), the file is rotated."""
        log = self._make_log()
        # Write a file just over 10 MB; use large lines so line count stays low
        line_bytes = 1024  # 1 KB per line
        n_lines = MAX_EVENT_BYTES // line_bytes + 1
        self._write_fake_log(log, n_lines, line_bytes=line_bytes)
        log._maybe_rotate()
        archive = log.path.with_suffix(log.path.suffix + ".1")
        self.assertTrue(archive.exists())

    def test_at_line_threshold_not_rotated(self) -> None:
        """Exactly MAX_EVENT_LINES lines (not exceeding) — no rotation."""
        log = self._make_log()
        # Exactly MAX_EVENT_LINES lines at 200 bytes each = 2 MB (above fast path)
        self._write_fake_log(log, MAX_EVENT_LINES, line_bytes=200)
        log._maybe_rotate()
        archive = log.path.with_suffix(log.path.suffix + ".1")
        self.assertFalse(archive.exists(), "Should not rotate at exactly the limit")

    def test_rotation_preserves_archive_content(self) -> None:
        """The archive (events.jsonl.1) has the same content as the pre-rotation log."""
        log = self._make_log()
        marker = "MARKER_LINE\n" + "x" * 199 + "\n"
        # Write a file that will trigger rotation
        lines = [marker] + ["x" * 199 + "\n"] * MAX_EVENT_LINES
        log.path.write_text("".join(lines), encoding="utf-8")
        log._maybe_rotate()
        archive = log.path.with_suffix(log.path.suffix + ".1")
        self.assertTrue(archive.exists())
        archive_text = archive.read_text(encoding="utf-8")
        self.assertTrue(archive_text.startswith("MARKER_LINE"))

    def test_previous_archive_overwritten(self) -> None:
        """An existing events.jsonl.1 is replaced on subsequent rotation."""
        log = self._make_log()
        archive = log.path.with_suffix(log.path.suffix + ".1")
        archive.write_text("OLD_ARCHIVE\n", encoding="utf-8")
        self._write_fake_log(log, MAX_EVENT_LINES + 1, line_bytes=200)
        log._maybe_rotate()
        new_content = archive.read_text(encoding="utf-8")
        self.assertNotIn("OLD_ARCHIVE", new_content)

    def test_oserror_is_non_fatal(self) -> None:
        """An OSError during stat/read/rename does not propagate to caller."""
        log = self._make_log()
        log.path.write_text("x\n", encoding="utf-8")
        with patch.object(Path, "stat", side_effect=OSError("simulated")):
            log._maybe_rotate()  # must not raise


class TestAppendCallsRotate(unittest.TestCase):
    """append() calls _maybe_rotate() after writing the row."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.td = Path(self._td.name)

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_append_calls_maybe_rotate(self) -> None:
        """append() invokes _maybe_rotate() exactly once per call."""
        log = EventLog(self.td / "events")
        call_count = []
        orig = log._maybe_rotate
        log._maybe_rotate = lambda: call_count.append(1) or orig()  # type: ignore[method-assign]
        log.append("test.event", {})
        self.assertEqual(len(call_count), 1)

    def test_append_returns_row_even_after_rotation(self) -> None:
        """append() still returns the newly written row after rotating."""
        log = EventLog(self.td / "events")
        # Force rotation by always rotating in _maybe_rotate
        log._maybe_rotate = lambda: (  # type: ignore[method-assign]
            log.path.replace(log.path.with_suffix(log.path.suffix + ".1")) if log.path.exists() else None
        )
        row = log.append("test.event", {"x": 1})
        self.assertIn("type", row)
        self.assertEqual(row["type"], "test.event")


class TestSourceContainsRotation(unittest.TestCase):
    """Source-text assertions: rotation constants and helper must be present."""

    def setUp(self) -> None:
        src_path = Path(__file__).parent.parent / "src" / "event_log.py"
        self._src = src_path.read_text(encoding="utf-8")

    def test_max_event_lines_defined(self) -> None:
        self.assertIn("MAX_EVENT_LINES = 10_000", self._src)

    def test_max_event_bytes_defined(self) -> None:
        self.assertIn("MAX_EVENT_BYTES = 10 * 1024 * 1024", self._src)

    def test_maybe_rotate_defined(self) -> None:
        self.assertIn("def _maybe_rotate(", self._src)

    def test_append_calls_maybe_rotate(self) -> None:
        """append() body contains a call to _maybe_rotate()."""
        start = self._src.index("def append(")
        end = self._src.index("\n    def ", start + 1)
        body = self._src[start:end]
        self.assertIn("_maybe_rotate()", body)

    def test_oserror_caught_in_maybe_rotate(self) -> None:
        """_maybe_rotate() has a bare except OSError to stay non-fatal."""
        start = self._src.index("def _maybe_rotate(")
        end = self._src.index("\n    def ", start + 1)
        body = self._src[start:end]
        self.assertIn("OSError", body)


if __name__ == "__main__":
    unittest.main()
