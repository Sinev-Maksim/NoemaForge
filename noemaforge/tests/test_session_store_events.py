#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_session_store_events.py
Zone: tests
Version: 0.32.2
Created: 2026-05-31
Modified: 2026-05-31
Purpose: Cover SessionStore.events() — the JSONL read-back path that feeds
         polling and SSE endpoints. Previously had zero test coverage.
Inputs: SessionStore from session_store.
Outputs: pytest pass/fail.
Side effects: Writes and removes files under tempfile.mkdtemp().
Tests: python3 -m unittest noemaforge/tests/test_session_store_events.py -v
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

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def _install_stubs() -> None:
    import noemaforge_version as real_version
    sys.modules.setdefault("noemaforge_version", real_version)

    stub_orch = types.ModuleType("orchestration_state")
    stub_orch.nowz = lambda: "2026-05-31T00:00:00Z"

    def _norm(r):
        r.setdefault("session_id", "default")
        r.setdefault("messages", [])
        r.setdefault("selected_mode", "normal")
        r.setdefault("selected_composite_top_n", 0)
        r.setdefault("active_jobs", [])
        return r

    stub_orch.normalize_session_record = _norm
    sys.modules.setdefault("orchestration_state", stub_orch)


_install_stubs()

from session_store import SessionStore  # noqa: E402


class TestSessionStoreEvents(unittest.TestCase):
    """SessionStore.events() — JSONL read-back, pagination, error tolerance."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.store = SessionStore(root=Path(self._tmpdir))

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    # ------------------------------------------------------------------
    # Basic read-back
    # ------------------------------------------------------------------

    def test_empty_when_no_events_file(self):
        """events() must return [] when session-events.jsonl does not exist."""
        result = self.store.events()
        self.assertEqual(result, [])

    def test_events_returned_after_load(self):
        """events() must return rows written by _append_event via load()."""
        self.store.load("default")  # triggers session.created event
        rows = self.store.events()
        self.assertGreater(len(rows), 0, "At least one event must be written by load()")
        self.assertIn("type", rows[0], "Each event row must have a 'type' key")

    def test_event_has_index_field(self):
        """events() must add 'index' field to each row (line number)."""
        self.store.load("default")
        rows = self.store.events()
        for row in rows:
            self.assertIn("index", row, "events() must inject 'index' field per row")
            self.assertIsInstance(row["index"], int)

    def test_events_contains_session_id(self):
        """events() rows must include the session_id field."""
        self.store.load("default")
        rows = self.store.events()
        for row in rows:
            self.assertIn("session_id", row)

    # ------------------------------------------------------------------
    # after_index pagination
    # ------------------------------------------------------------------

    def test_after_index_filters_earlier_rows(self):
        """events(after_index=N) must skip rows with index < N."""
        # Generate a few events
        self.store.load("default")
        self.store.update("default", x=1)
        self.store.update("default", y=2)

        all_rows = self.store.events()
        self.assertGreater(len(all_rows), 1, "Need >1 event for this test")

        # Fetch starting from row 1
        partial = self.store.events(after_index=1)
        self.assertEqual(len(partial), len(all_rows) - 1,
                         "after_index=1 must skip the first row")
        for row in partial:
            self.assertGreaterEqual(row["index"], 1)

    def test_after_index_zero_returns_all(self):
        """events(after_index=0) must return all rows."""
        self.store.load("default")
        self.store.update("default", k="v")
        all_from_0 = self.store.events(after_index=0)
        all_default = self.store.events()
        self.assertEqual(len(all_from_0), len(all_default))

    def test_after_index_beyond_end_returns_empty(self):
        """events(after_index=9999) must return [] when file has fewer rows."""
        self.store.load("default")
        result = self.store.events(after_index=9999)
        self.assertEqual(result, [])

    # ------------------------------------------------------------------
    # limit truncation
    # ------------------------------------------------------------------

    def test_limit_truncates_result(self):
        """events(limit=N) must return at most N rows."""
        # Write enough events
        self.store.load("default")
        for i in range(5):
            self.store.update("default", i=i)

        all_rows = self.store.events()
        self.assertGreater(len(all_rows), 2, "Need >2 events for this test")

        limited = self.store.events(limit=2)
        self.assertLessEqual(len(limited), 2, "limit=2 must return at most 2 rows")

    def test_limit_one_returns_first_event(self):
        """events(limit=1) must return the first (oldest) event."""
        self.store.load("default")
        self.store.update("default", second=True)
        one = self.store.events(limit=1)
        self.assertEqual(len(one), 1)
        self.assertEqual(one[0]["index"], 0)

    # ------------------------------------------------------------------
    # Malformed JSON tolerance
    # ------------------------------------------------------------------

    def test_malformed_lines_skipped(self):
        """events() must skip malformed JSON lines without raising."""
        # Write valid event then inject a corrupt line
        self.store.load("default")
        with self.store.events_path.open("a", encoding="utf-8") as fh:
            fh.write("NOT JSON\n")
        self.store.update("default", after_bad=True)

        rows = self.store.events()
        # Must return at least 2 valid rows (load + update), not crash
        self.assertGreaterEqual(len(rows), 2,
                                "Malformed line must be skipped; valid rows still returned")
        for row in rows:
            self.assertIn("type", row, "Returned rows must be valid event dicts")

    def test_empty_lines_skipped(self):
        """events() must skip empty/whitespace-only lines."""
        self.store.load("default")
        # Inject blank lines
        with self.store.events_path.open("a", encoding="utf-8") as f:
            f.write("\n\n   \n")
        self.store.update("default", after_blanks=True)

        rows = self.store.events()
        for row in rows:
            self.assertIn("type", row)

    # ------------------------------------------------------------------
    # Type field values
    # ------------------------------------------------------------------

    def test_load_emits_created_event(self):
        """load() on a new session must emit a 'session.created' event."""
        self.store.load("default")
        rows = self.store.events()
        types_seen = {r["type"] for r in rows}
        self.assertIn("session.created", types_seen)

    def test_update_emits_updated_event(self):
        """update() must emit a 'session.updated' event."""
        self.store.load("default")
        self.store.update("default", test=True)
        rows = self.store.events()
        types_seen = {r["type"] for r in rows}
        self.assertIn("session.updated", types_seen)

    def test_append_message_emits_message_event(self):
        """append_message() must emit a 'session.message' event."""
        self.store.load("default")
        self.store.append_message("default", {"role": "user", "content": "hello"})
        rows = self.store.events()
        types_seen = {r["type"] for r in rows}
        self.assertIn("session.message", types_seen)


if __name__ == "__main__":
    unittest.main()
