#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_orchestration_state.py
Zone: tests
Version: 0.32.2
Created: 2026-05-31
Modified: 2026-05-31
Purpose: Direct unit tests for orchestration_state functions:
           - nowz(): returns UTC ISO-8601 string ending in 'Z'.
           - _safe_int(): converts values to int safely (task-69 fix).
           - normalize_session_record(): normalises session dict fields,
             including safe handling of non-numeric selected_composite_top_n
             (bug where int("abc" or 0) raises ValueError was fixed in task-69).
           - normalize_job_record(): normalises job dict fields.
           - is_active_job(): correctly classifies job states.
         All functions were previously covered only via stubs in other tests;
         this file gives the real implementations their first direct coverage.
Inputs: orchestration_state from src/.
Outputs: pytest pass/fail.
Side effects: None (no I/O).
Tests: python3 -m unittest noemaforge/tests/test_orchestration_state.py -v
Notes: Code comments are English-only.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def _install_stubs() -> None:
    stub_ver = types.ModuleType("noemaforge_version")
    stub_ver.RUNTIME_VERSION = "0.32.2"
    sys.modules.setdefault("noemaforge_version", stub_ver)


_install_stubs()

from orchestration_state import (  # noqa: E402
    _safe_int,
    is_active_job,
    normalize_job_record,
    normalize_session_record,
    nowz,
    ACTIVE_JOB_STATES,
    FINAL_JOB_STATES,
)


class TestNowz(unittest.TestCase):
    """nowz() must return a UTC ISO-8601 timestamp ending in 'Z'."""

    def test_returns_string(self) -> None:
        result = nowz()
        self.assertIsInstance(result, str)

    def test_ends_with_z(self) -> None:
        result = nowz()
        self.assertTrue(result.endswith("Z"), f"nowz() must end with 'Z', got {result!r}")

    def test_contains_t_separator(self) -> None:
        result = nowz()
        self.assertIn("T", result, "nowz() must use ISO-8601 T separator")

    def test_no_microseconds(self) -> None:
        """nowz() truncates microseconds — format is YYYY-MM-DDTHH:MM:SSZ."""
        result = nowz()
        # Microseconds would appear as .NNNNNN before the Z
        self.assertNotIn(".", result, "nowz() must not include microseconds")

    def test_successive_calls_ordered(self) -> None:
        """Two successive nowz() calls must return timestamps in non-decreasing order."""
        t1 = nowz()
        t2 = nowz()
        self.assertLessEqual(t1, t2, "nowz() must return non-decreasing timestamps")


class TestSafeInt(unittest.TestCase):
    """_safe_int() must convert values to int without raising."""

    def test_int_passthrough(self) -> None:
        self.assertEqual(_safe_int(5), 5)
        self.assertEqual(_safe_int(0), 0)
        self.assertEqual(_safe_int(-3), -3)

    def test_float_truncated(self) -> None:
        self.assertEqual(_safe_int(3.9), 3)
        self.assertEqual(_safe_int(2.0), 2)

    def test_string_numeric(self) -> None:
        self.assertEqual(_safe_int("7"), 7)
        self.assertEqual(_safe_int("0"), 0)

    def test_non_numeric_string_returns_default(self) -> None:
        """Non-numeric strings must return the default, not raise ValueError."""
        self.assertEqual(_safe_int("abc"), 0)
        self.assertEqual(_safe_int("not-a-number", 99), 99)

    def test_none_returns_default(self) -> None:
        self.assertEqual(_safe_int(None), 0)
        self.assertEqual(_safe_int(None, 42), 42)

    def test_empty_string_returns_default(self) -> None:
        self.assertEqual(_safe_int(""), 0)

    def test_list_returns_default(self) -> None:
        self.assertEqual(_safe_int([1, 2, 3], -1), -1)


class TestNormalizeSessionRecord(unittest.TestCase):
    """normalize_session_record() must normalise all fields."""

    def _norm(self, record: dict) -> dict:
        return normalize_session_record(record)

    def test_empty_record_gets_defaults(self) -> None:
        result = self._norm({})
        self.assertEqual(result["session_id"], "default")
        self.assertEqual(result["selected_mode"], "normal")
        self.assertEqual(result["selected_composite_top_n"], 0)
        self.assertEqual(result["messages"], [])
        self.assertEqual(result["active_jobs"], [])
        self.assertIsInstance(result["last_route"], dict)
        self.assertEqual(result["last_event_index"], 0)
        self.assertIn("updated_at", result)
        self.assertIn("version", result)

    def test_session_id_preserved(self) -> None:
        result = self._norm({"session_id": "user-42"})
        self.assertEqual(result["session_id"], "user-42")

    def test_selected_mode_preserved(self) -> None:
        for mode in ("fast", "normal", "full", "full_composite"):
            result = self._norm({"selected_mode": mode})
            self.assertEqual(result["selected_mode"], mode)

    def test_composite_top_n_integer(self) -> None:
        result = self._norm({"selected_composite_top_n": 5})
        self.assertEqual(result["selected_composite_top_n"], 5)

    def test_composite_top_n_string_numeric(self) -> None:
        """'5' as a string must be converted to int 5, not raise."""
        result = self._norm({"selected_composite_top_n": "5"})
        self.assertEqual(result["selected_composite_top_n"], 5)

    def test_composite_top_n_non_numeric_string_defaults(self) -> None:
        """Non-numeric string must fall back to 0 without raising ValueError.

        This is the task-69 bug: int('abc' or 0) raises ValueError because
        'abc' is truthy so the 'or' returns 'abc', then int('abc') raises.
        _safe_int() fixes this by catching the exception.
        """
        # Must NOT raise — this was the bug before task-69
        result = self._norm({"selected_composite_top_n": "abc"})
        self.assertEqual(result["selected_composite_top_n"], 0)

    def test_last_event_index_non_numeric_defaults(self) -> None:
        """Non-numeric last_event_index must fall back to 0 without raising."""
        result = self._norm({"last_event_index": "bad"})
        self.assertEqual(result["last_event_index"], 0)

    def test_messages_list_preserved(self) -> None:
        msgs = [{"role": "user", "text": "hi"}]
        result = self._norm({"messages": msgs})
        self.assertEqual(len(result["messages"]), 1)

    def test_messages_none_becomes_empty_list(self) -> None:
        result = self._norm({"messages": None})
        self.assertEqual(result["messages"], [])

    def test_active_jobs_list_preserved(self) -> None:
        jobs = [{"job_id": "j1"}]
        result = self._norm({"active_jobs": jobs})
        self.assertEqual(len(result["active_jobs"]), 1)

    def test_last_route_dict_preserved(self) -> None:
        route = {"intent": "admin_chat", "score": 0.9}
        result = self._norm({"last_route": route})
        self.assertEqual(result["last_route"], route)

    def test_last_route_non_dict_becomes_empty(self) -> None:
        result = self._norm({"last_route": "not-a-dict"})
        self.assertEqual(result["last_route"], {})

    def test_updated_at_always_set(self) -> None:
        result = self._norm({})
        self.assertTrue(result["updated_at"].endswith("Z"))

    def test_version_always_set(self) -> None:
        result = self._norm({})
        self.assertEqual(result["version"], "0.32.2")


class TestNormalizeJobRecord(unittest.TestCase):
    """normalize_job_record() must normalise all fields."""

    def _norm(self, record: dict) -> dict:
        return normalize_job_record(record)

    def test_empty_record_gets_defaults(self) -> None:
        result = self._norm({})
        self.assertEqual(result["job_id"], "")
        self.assertEqual(result["kind"], "unknown")
        self.assertEqual(result["status"], "queued")
        self.assertEqual(result["lock_key"], "")
        self.assertIsInstance(result["progress"], dict)
        self.assertEqual(result["artifacts"], [])

    def test_job_id_preserved(self) -> None:
        result = self._norm({"job_id": "job-123"})
        self.assertEqual(result["job_id"], "job-123")

    def test_status_preserved(self) -> None:
        for status in ("queued", "running", "done", "failed", "cancelled"):
            result = self._norm({"status": status})
            self.assertEqual(result["status"], status)

    def test_progress_dict_preserved(self) -> None:
        prog = {"current": 3, "total": 10, "label": "processing"}
        result = self._norm({"progress": prog})
        self.assertEqual(result["progress"], prog)

    def test_progress_non_dict_replaced_with_default(self) -> None:
        result = self._norm({"progress": "50%"})
        self.assertIsInstance(result["progress"], dict)
        self.assertIn("current", result["progress"])

    def test_artifacts_list_preserved(self) -> None:
        artifacts = [{"path": "/tmp/out.json"}]
        result = self._norm({"artifacts": artifacts})
        self.assertEqual(result["artifacts"], artifacts)

    def test_created_at_defaults_to_nowz(self) -> None:
        result = self._norm({})
        self.assertTrue(result["created_at"].endswith("Z"))

    def test_version_set(self) -> None:
        result = self._norm({})
        self.assertEqual(result["version"], "0.32.2")


class TestIsActiveJob(unittest.TestCase):
    """is_active_job() must return True only for active states."""

    def test_active_states_return_true(self) -> None:
        for status in ACTIVE_JOB_STATES:
            with self.subTest(status=status):
                self.assertTrue(is_active_job({"status": status}))

    def test_final_states_return_false(self) -> None:
        for status in FINAL_JOB_STATES:
            with self.subTest(status=status):
                self.assertFalse(is_active_job({"status": status}))

    def test_unknown_status_returns_false(self) -> None:
        self.assertFalse(is_active_job({"status": "unknown_state"}))

    def test_missing_status_returns_false(self) -> None:
        self.assertFalse(is_active_job({}))

    def test_none_status_returns_false(self) -> None:
        self.assertFalse(is_active_job({"status": None}))


if __name__ == "__main__":
    unittest.main()
