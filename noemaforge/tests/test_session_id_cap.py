#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_session_id_cap.py
Zone: test
Version: 0.32.2
Created: 2026-05-30
Modified: 2026-05-30
Purpose: TDD tests for GET /api/session/current session_id parameter clamping.
  Verifies that session_id is truncated to 128 characters, that all-non-alphanumeric
  session_ids return HTTP 400, and that valid ids pass through unchanged.
  Prevents unbounded session-file proliferation via arbitrarily long or degenerate ids.
Inputs: admin_gui_server.AdminGuiHandler.do_GET (/api/session/current).
Outputs: test pass/fail.
Side effects: None (uses stubs only).
Tests: python noemaforge/tests/test_session_id_cap.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_SRC = Path(__file__).parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import admin_gui_server  # noqa: E402
from noemaforge_version import RUNTIME_VERSION  # noqa: E402


def _call_route(path: str):
    """Drive do_GET for /api/session/current and return (status, payload, calls)."""
    calls = []
    responses = []

    class ServerStub:
        def session_current(self, session_id: str = "default"):
            calls.append(session_id)
            return {"ok": True, "version": RUNTIME_VERSION, "session": {"session_id": session_id}}

    handler = object.__new__(admin_gui_server.AdminGuiHandler)
    handler.path = path
    handler.server = ServerStub()
    handler._send_json = lambda obj, status=200: responses.append((status, obj))
    admin_gui_server.AdminGuiHandler.do_GET(handler)
    return responses, calls


class TestSessionIdClamping(unittest.TestCase):
    """session_id is truncated to 128 characters in do_GET."""

    def test_short_id_passes_through_unchanged(self) -> None:
        """A normal short session_id is forwarded unchanged."""
        responses, calls = _call_route("/api/session/current?session_id=abc123")
        self.assertEqual(len(responses), 1)
        status, _ = responses[0]
        self.assertEqual(status, 200)
        self.assertEqual(calls, ["abc123"])

    def test_default_when_no_session_id_param(self) -> None:
        """No ?session_id= → 'default' is used."""
        responses, calls = _call_route("/api/session/current")
        status, _ = responses[0]
        self.assertEqual(status, 200)
        self.assertEqual(calls, ["default"])

    def test_long_id_clamped_to_128_chars(self) -> None:
        """A 10,000-character session_id is clamped to 128 characters."""
        long_id = "a" * 10_000
        responses, calls = _call_route(f"/api/session/current?session_id={long_id}")
        status, _ = responses[0]
        self.assertEqual(status, 200)
        self.assertEqual(len(calls[0]), 128)

    def test_exactly_128_chars_passes_through(self) -> None:
        """Exactly 128-character session_id is not truncated."""
        exact_id = "a" * 128
        responses, calls = _call_route(f"/api/session/current?session_id={exact_id}")
        status, _ = responses[0]
        self.assertEqual(status, 200)
        self.assertEqual(len(calls[0]), 128)

    def test_129_chars_truncated_to_128(self) -> None:
        """A 129-character session_id is truncated to 128."""
        over_id = "a" * 129
        responses, calls = _call_route(f"/api/session/current?session_id={over_id}")
        status, _ = responses[0]
        self.assertEqual(status, 200)
        self.assertEqual(len(calls[0]), 128)

    def test_clamped_id_is_prefix_of_original(self) -> None:
        """Clamped id is the first 128 characters of the original (newest chars not kept)."""
        id_200 = "b" * 100 + "c" * 100  # 200 chars: first 100 are 'b', next 100 are 'c'
        responses, calls = _call_route(f"/api/session/current?session_id={id_200}")
        sid = calls[0]
        self.assertEqual(len(sid), 128)
        self.assertTrue(sid.startswith("b"), "Should keep the first 128 chars (prefix)")


class TestSessionIdRejectNonAlphanumeric(unittest.TestCase):
    """session_id with no alphanumeric characters returns HTTP 400."""

    def test_all_dots_rejected(self) -> None:
        """'....' → 400."""
        responses, calls = _call_route("/api/session/current?session_id=....")
        self.assertEqual(len(responses), 1)
        status, payload = responses[0]
        self.assertEqual(status, 400)
        self.assertFalse(payload["ok"])
        self.assertEqual(calls, [])

    def test_all_dashes_rejected(self) -> None:
        """'----' → 400."""
        responses, calls = _call_route("/api/session/current?session_id=----")
        status, payload = responses[0]
        self.assertEqual(status, 400)
        self.assertFalse(payload["ok"])

    def test_mixed_special_no_alnum_rejected(self) -> None:
        """'...---...' → 400 (no alphanumeric)."""
        responses, calls = _call_route("/api/session/current?session_id=...---...")
        status, payload = responses[0]
        self.assertEqual(status, 400)
        self.assertFalse(payload["ok"])

    def test_error_message_is_descriptive(self) -> None:
        """400 response includes a descriptive error field."""
        responses, calls = _call_route("/api/session/current?session_id=...")
        _, payload = responses[0]
        self.assertIn("error", payload)
        self.assertIn("alphanumeric", payload["error"])

    def test_id_with_one_alnum_accepted(self) -> None:
        """'.a.' has an alphanumeric char → accepted (not rejected)."""
        responses, calls = _call_route("/api/session/current?session_id=.a.")
        status, _ = responses[0]
        self.assertEqual(status, 200)
        self.assertEqual(calls[0], ".a.")

    def test_id_with_underscore_only_rejected(self) -> None:
        """'___' has no alphanumeric char → 400."""
        responses, calls = _call_route("/api/session/current?session_id=___")
        status, payload = responses[0]
        self.assertEqual(status, 400)

    def test_numeric_only_id_accepted(self) -> None:
        """'12345' is alphanumeric → accepted."""
        responses, calls = _call_route("/api/session/current?session_id=12345")
        status, _ = responses[0]
        self.assertEqual(status, 200)
        self.assertEqual(calls[0], "12345")


class TestSourceContainsCapLogic(unittest.TestCase):
    """Source-text assertions for session_id clamping."""

    def setUp(self) -> None:
        src_path = Path(__file__).parent.parent / "src" / "admin_gui_server.py"
        self._src = src_path.read_text(encoding="utf-8")

    def test_128_clamp_in_source(self) -> None:
        """128-character clamp is present."""
        self.assertIn("[:128]", self._src)

    def test_alphanumeric_check_in_source(self) -> None:
        """re.search for alphanumeric is present."""
        self.assertIn("[A-Za-z0-9]", self._src)

    def test_400_returned_for_invalid_session_id(self) -> None:
        """status=400 return is present near session_id validation."""
        idx = self._src.index('"/api/session/current"')
        # Find the next route handler after this path check
        end = self._src.index("\n        if path ==", idx + 1)
        snippet = self._src[idx:end]
        self.assertIn("status=400", snippet)


if __name__ == "__main__":
    unittest.main()
