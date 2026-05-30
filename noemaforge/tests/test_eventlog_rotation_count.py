#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_eventlog_rotation_count.py
Zone: tests
Version: 0.32.2
Created: 2026-05-30
Modified: 2026-05-30
Purpose: Verify EventLog.status() exposes rotation_count so polling callers can
         detect log rotations and reset after_index to avoid the after-rotation
         blind spot.
Inputs: EventLog from event_log; temporary directories.
Outputs: pytest pass/fail.
Side effects: Writes and removes files under tempfile.mkdtemp().
Tests: python3 -m unittest noemaforge/tests/test_eventlog_rotation_count.py -v
Notes: Code comments are English-only.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Minimal stubs
# ---------------------------------------------------------------------------

def _install_stubs() -> None:
    stub_ver = types.ModuleType("noemaforge_version")
    stub_ver.RUNTIME_VERSION = "0.32.2"
    sys.modules.setdefault("noemaforge_version", stub_ver)

    stub_orch = types.ModuleType("orchestration_state")
    stub_orch.nowz = lambda: "2026-05-30T00:00:00Z"
    sys.modules.setdefault("orchestration_state", stub_orch)


_install_stubs()

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from event_log import EventLog, MAX_EVENT_LINES, _MAX_ARCHIVE_DEPTH, _ROTATION_SIZE_FAST_PATH  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_log(root: Path) -> EventLog:
    return EventLog(root=root)


def _write_rotation_content(log: EventLog) -> bytes:
    """Write enough JSONL lines to trigger rotation on the next _maybe_rotate call."""
    line = (json.dumps({"event": "test", "data": "x" * 80}) + "\n").encode("utf-8")
    count = max(MAX_EVENT_LINES + 1, (_ROTATION_SIZE_FAST_PATH // len(line)) + 1)
    content = line * count
    log.path.write_bytes(content)
    return content


# ===========================================================================
# Section 1 — status() initial state
# ===========================================================================

class TestStatusInitialState(unittest.TestCase):
    """status() must return valid fields even before any appends or rotation."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._root = Path(self._tmpdir)
        self.log = _make_log(self._root)

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_rotation_count_starts_at_zero(self):
        """A fresh EventLog must report rotation_count=0."""
        s = self.log.status()
        self.assertEqual(s["rotation_count"], 0)

    def test_status_has_required_keys(self):
        """status() must return rotation_count, current_size_bytes, path."""
        s = self.log.status()
        self.assertIn("rotation_count", s)
        self.assertIn("current_size_bytes", s)
        self.assertIn("path", s)

    def test_current_size_bytes_zero_before_append(self):
        """current_size_bytes must be 0 before any data is written."""
        s = self.log.status()
        self.assertEqual(s["current_size_bytes"], 0)

    def test_path_points_to_events_jsonl(self):
        """path must be the absolute path of the live events file."""
        s = self.log.status()
        self.assertTrue(s["path"].endswith("events.jsonl"))

    def test_current_size_grows_after_append(self):
        """current_size_bytes must increase after append()."""
        self.log.append("test.event", {})
        s = self.log.status()
        self.assertGreater(s["current_size_bytes"], 0)


# ===========================================================================
# Section 2 — rotation_count increments on rotation
# ===========================================================================

class TestRotationCountIncrements(unittest.TestCase):
    """rotation_count must increment by 1 each time _maybe_rotate truncates the file."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._root = Path(self._tmpdir)
        self.log = _make_log(self._root)

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_rotation_count_increments_after_rotate(self):
        """After _maybe_rotate() truncates the file, rotation_count must be 1."""
        _write_rotation_content(self.log)
        with self.log._lock:
            self.log._maybe_rotate()
        s = self.log.status()
        self.assertEqual(s["rotation_count"], 1)

    def test_rotation_count_increments_twice_on_two_rotations(self):
        """Two successful rotations must yield rotation_count=2."""
        _write_rotation_content(self.log)
        with self.log._lock:
            self.log._maybe_rotate()
        # Write again and rotate again
        _write_rotation_content(self.log)
        with self.log._lock:
            self.log._maybe_rotate()
        s = self.log.status()
        self.assertEqual(s["rotation_count"], 2)

    def test_rotation_count_not_incremented_when_shift_fails(self):
        """If _shift_archives() fails, rotation_count must not increment."""
        _write_rotation_content(self.log)
        with patch.object(self.log, "_shift_archives", return_value=False):
            with self.log._lock:
                self.log._maybe_rotate()
        s = self.log.status()
        self.assertEqual(s["rotation_count"], 0)

    def test_rotation_count_not_incremented_below_threshold(self):
        """rotation_count must not change when the file is below rotation thresholds."""
        self.log.append("small.event", {})
        with self.log._lock:
            self.log._maybe_rotate()
        s = self.log.status()
        self.assertEqual(s["rotation_count"], 0)

    def test_size_drops_to_zero_after_rotation(self):
        """After rotation the live file must be truncated to 0 bytes."""
        _write_rotation_content(self.log)
        with self.log._lock:
            self.log._maybe_rotate()
        s = self.log.status()
        self.assertEqual(s["current_size_bytes"], 0)


# ===========================================================================
# Section 3 — polling pattern: reset after_index on rotation change
# ===========================================================================

class TestAfterIndexResetPattern(unittest.TestCase):
    """Simulate the recommended caller pattern: detect rotation and reset after_index."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._root = Path(self._tmpdir)
        self.log = _make_log(self._root)

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_caller_misses_events_after_rotation_without_reset(self):
        """A caller that does NOT reset after_index misses events after a rotation."""
        # Write and read some events
        for i in range(5):
            self.log.append("pre.event", {"i": i})
        rows = self.log.read(after_index=0, limit=100)
        after_index = rows[-1]["index"] + 1  # = 5 (next unread line)

        # Rotate the log
        _write_rotation_content(self.log)
        with self.log._lock:
            self.log._maybe_rotate()

        # Write new events into the now-empty log
        for i in range(3):
            self.log.append("post.event", {"i": i})

        # Caller with stale after_index=5 sees NO rows because the file only has 3 lines
        rows_stale = self.log.read(after_index=after_index, limit=100)
        self.assertEqual(len(rows_stale), 0,
                         "Caller with stale after_index should miss events after rotation")

    def test_caller_sees_events_after_rotation_with_reset(self):
        """A caller that DOES reset after_index=0 on rotation sees all new events."""
        # Write and read some events
        for i in range(5):
            self.log.append("pre.event", {"i": i})
        rows = self.log.read(after_index=0, limit=100)
        after_index = rows[-1]["index"] + 1
        last_rotation = self.log.status()["rotation_count"]

        # Rotate the log
        _write_rotation_content(self.log)
        with self.log._lock:
            self.log._maybe_rotate()

        # Write new events
        for i in range(3):
            self.log.append("post.event", {"i": i})

        # Caller detects rotation and resets after_index
        s = self.log.status()
        if s["rotation_count"] != last_rotation:
            after_index = 0  # reset

        rows_fresh = self.log.read(after_index=after_index, limit=100)
        self.assertEqual(len(rows_fresh), 3,
                         "Caller that resets after_index on rotation must see all new events")
        for i, row in enumerate(rows_fresh):
            self.assertEqual(row["data"]["i"], i)

    def test_rotation_count_is_stable_without_rotation(self):
        """rotation_count must remain unchanged across multiple reads without rotation."""
        for i in range(10):
            self.log.append("event", {"i": i})
        s1 = self.log.status()
        _ = self.log.read(after_index=0)
        s2 = self.log.status()
        self.assertEqual(s1["rotation_count"], s2["rotation_count"])


# ===========================================================================
# Section 4 — source-level check: status() is documented in class docstring
# ===========================================================================

class TestDocumentationPresent(unittest.TestCase):
    """Verify that the after-rotation blind spot is documented in the source."""

    def _get_source(self) -> str:
        src_path = _SRC / "event_log.py"
        return src_path.read_text(encoding="utf-8")

    def test_status_method_mentioned_in_class_docstring(self):
        """Class docstring must mention status() as the mitigation mechanism."""
        source = self._get_source()
        # Find the class docstring
        class_start = source.index("class EventLog:")
        docstring_end = source.index('"""', source.index('"""', class_start) + 3) + 3
        class_doc = source[class_start:docstring_end]
        self.assertIn("status()", class_doc,
                      "Class docstring must mention status() as the rotation detection method")

    def test_rotation_count_documented_in_read_docstring(self):
        """read() docstring must document the after-rotation blind spot."""
        source = self._get_source()
        read_def = source.index("def read(self,")
        # Find the docstring for read()
        doc_start = source.index('"""', read_def)
        doc_end = source.index('"""', doc_start + 3) + 3
        read_doc = source[doc_start:doc_end]
        self.assertIn("after_index", read_doc)
        self.assertIn("rotation", read_doc.lower())

    def test_rotation_count_in_status_docstring(self):
        """status() docstring must document rotation_count semantics."""
        source = self._get_source()
        status_def = source.index("def status(self)")
        doc_start = source.index('"""', status_def)
        doc_end = source.index('"""', doc_start + 3) + 3
        status_doc = source[doc_start:doc_end]
        self.assertIn("rotation_count", status_doc)


if __name__ == "__main__":
    unittest.main()
