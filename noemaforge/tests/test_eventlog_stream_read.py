#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_eventlog_stream_read.py
Zone: test
Version: 0.32.2
Created: 2026-05-30
Modified: 2026-05-30
Purpose: Verify EventLog.read() iterates the file line-by-line and stops after limit rows.
Inputs: EventLog.read() from event_log.py.
Outputs: unittest results.
Side effects: Writes temporary test files.
Tests: python -m unittest noemaforge/tests/test_eventlog_stream_read.py -v
Notes: Code comments are English-only.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from event_log import EventLog


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_log(tmp: str | Path) -> EventLog:
    return EventLog(root=Path(tmp))


def _write_rows(log: EventLog, n: int) -> None:
    for i in range(n):
        log.append("test.event", {"i": i})


# ---------------------------------------------------------------------------
# 1. Correct data is returned
# ---------------------------------------------------------------------------

class TestStreamReadCorrectness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = _make_log(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_empty_file_returns_empty_list(self):
        rows = self.log.read()
        self.assertEqual(rows, [])

    def test_nonexistent_file_returns_empty_list(self):
        self.assertFalse(self.log.path.exists())
        rows = self.log.read()
        self.assertEqual(rows, [])

    def test_single_event_returned(self):
        self.log.append("ev", {"x": 1})
        rows = self.log.read()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["type"], "ev")

    def test_limit_is_respected(self):
        _write_rows(self.log, 10)
        rows = self.log.read(limit=3)
        self.assertEqual(len(rows), 3)

    def test_after_index_skips_earlier_rows(self):
        _write_rows(self.log, 5)
        rows = self.log.read(after_index=3)
        # Rows 0,1,2 skipped; rows 3,4 returned.
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["index"], 3)

    def test_index_field_equals_line_number(self):
        _write_rows(self.log, 5)
        rows = self.log.read()
        for expected_idx, row in enumerate(rows):
            self.assertEqual(row["index"], expected_idx)

    def test_after_index_and_limit_combined(self):
        _write_rows(self.log, 10)
        rows = self.log.read(after_index=5, limit=2)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["index"], 5)
        self.assertEqual(rows[1]["index"], 6)


# ---------------------------------------------------------------------------
# 2. Streaming / memory behavior
# ---------------------------------------------------------------------------

class TestStreamReadUsesOpen(unittest.TestCase):
    """Verify read() uses open() for streaming, not read_text()."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = _make_log(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_read_text_not_called(self):
        """read() must not call Path.read_text() — that loads the whole file."""
        _write_rows(self.log, 5)
        with patch.object(Path, "read_text") as mock_rt:
            self.log.read(limit=3)
        mock_rt.assert_not_called()

    def test_open_called_for_iteration(self):
        """read() must call Path.open() to iterate the file."""
        _write_rows(self.log, 5)
        open_calls = []
        original_open = Path.open

        def tracking_open(self_path, *a, **kw):
            open_calls.append(self_path)
            return original_open(self_path, *a, **kw)

        with patch.object(Path, "open", tracking_open):
            self.log.read(limit=3)

        self.assertTrue(
            any(str(c).endswith("events.jsonl") for c in open_calls),
            "Path.open() must be called for events.jsonl",
        )

    def test_early_stop_returns_exactly_limit_rows(self):
        """read() with limit=5 on a 100-event file must return exactly 5 rows."""
        _write_rows(self.log, 100)
        rows = self.log.read(limit=5)
        self.assertEqual(len(rows), 5)
        # The 5 rows must be the first 5 (indices 0..4).
        for i, row in enumerate(rows):
            self.assertEqual(row["index"], i)


# ---------------------------------------------------------------------------
# 3. Non-fatal OSError
# ---------------------------------------------------------------------------

class TestStreamReadOsError(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = _make_log(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_oserror_returns_empty_list(self):
        """An OSError during file open must return [] not raise."""
        self.log.path.write_text("valid line\n", encoding="utf-8")
        with patch.object(Path, "open", side_effect=OSError("permission denied")):
            rows = self.log.read()
        self.assertEqual(rows, [])


# ---------------------------------------------------------------------------
# 4. Source-text guards
# ---------------------------------------------------------------------------

class TestSourceContainsStreamRead(unittest.TestCase):
    SRC_TEXT = (ROOT / "src" / "event_log.py").read_text(encoding="utf-8")

    def test_open_used_not_read_text(self):
        """read() must use self.path.open(...) not self.path.read_text() for actual I/O."""
        # Extract just the code portion of read() (excluding the docstring) by
        # looking for the first 'if not self.path.exists()' line which is always
        # the first code statement, and checking from there.
        start = self.SRC_TEXT.find("def read(self,")
        next_def = self.SRC_TEXT.find("\n    def ", start + 1)
        read_body = self.SRC_TEXT[start:next_def] if next_def != -1 else self.SRC_TEXT[start:]
        # Strip the docstring: find the closing triple-quote after the def line.
        docstring_end = read_body.find('"""', read_body.find('"""') + 3) + 3
        code_portion = read_body[docstring_end:]
        # In the actual code portion (post-docstring), read_text must not appear.
        self.assertNotIn("read_text(", code_portion, "read() code body must not call read_text()")
        self.assertIn(".open(", code_portion, "read() must use .open() for streaming")

    def test_for_loop_over_fh(self):
        """read() must iterate the file handle directly (for line in fh)."""
        self.assertIn("for idx, line in enumerate(fh)", self.SRC_TEXT)

    def test_early_break_present(self):
        """read() must break out of the loop once limit is reached."""
        self.assertIn("break", self.SRC_TEXT)


if __name__ == "__main__":
    unittest.main()
