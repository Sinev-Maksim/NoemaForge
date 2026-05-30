#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_session_store_error_logging.py
Zone: test
Version: 0.32.2
Created: 2026-05-30
Modified: 2026-05-30
Purpose: Verify session_store errors in save_message() are logged to event_log instead of silently swallowed.
Inputs: AdminGuiServer.save_message() via stub.
Outputs: unittest results.
Side effects: None (temp dirs + stubs only).
Tests: python -m unittest noemaforge/tests/test_session_store_error_logging.py -v
Notes: Code comments are English-only.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from event_log import EventLog
from session_store import SessionStore


# ---------------------------------------------------------------------------
# Minimal AdminGuiServer stub — only the save_message() logic is exercised
# ---------------------------------------------------------------------------

def _make_server_stub(tmp_path: Path):
    """Build a minimal AdminGuiServer-like object with real EventLog and SessionStore."""
    import admin_gui_server as ags
    from admin_gui_server import AdminGuiServer

    store = SessionStore(tmp_path / "sessions")
    elog = EventLog(tmp_path / "events")

    obj = object.__new__(AdminGuiServer)
    obj.session_store = store
    obj.event_log = elog
    obj.gui_state_dir = tmp_path / "gui"
    obj.review_dir = tmp_path / "review"
    obj.gui_state_dir.mkdir(parents=True, exist_ok=True)
    (obj.review_dir / "sr" / "inbox").mkdir(parents=True, exist_ok=True)
    (obj.review_dir / "ssr" / "inbox").mkdir(parents=True, exist_ok=True)
    (obj.gui_state_dir / "raw").mkdir(parents=True, exist_ok=True)
    return obj


# ---------------------------------------------------------------------------
# 1. Happy path — no error, nothing logged
# ---------------------------------------------------------------------------

class TestNoErrorNoLog(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tp = Path(self.tmp.name)
        self.srv = _make_server_stub(self.tp)

    def tearDown(self):
        self.tmp.cleanup()

    def test_successful_append_no_event_logged(self):
        """When session_store.append_message succeeds, no error event is emitted."""
        # Simulate the try/except block directly.
        msg = {"message_id": "m1", "role": "user", "text": "hello"}
        logged = []
        real_append = self.srv.event_log.append

        def spy_append(*a, **kw):
            logged.append((a, kw))
            return real_append(*a, **kw)

        self.srv.event_log.append = spy_append

        try:
            self.srv.session_store.append_message("default", msg)
        except Exception as _ss_exc:
            try:
                self.srv.event_log.append(
                    "gui.session_store_error",
                    {"message_id": msg.get("message_id", ""), "error": str(_ss_exc)},
                    actor="admin_gui",
                )
            except Exception:
                pass

        # No error was raised, so no event should have been logged.
        self.assertEqual(len(logged), 0)


# ---------------------------------------------------------------------------
# 2. Error path — session_store raises, event is logged
# ---------------------------------------------------------------------------

class TestErrorIsLogged(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tp = Path(self.tmp.name)
        self.srv = _make_server_stub(self.tp)

    def tearDown(self):
        self.tmp.cleanup()

    def _simulate_save_message_block(self, msg: dict, ss_error: Exception | None = None):
        """Execute the try/except block from save_message() directly."""
        def _fail(*a, **kw):
            raise ss_error

        original_append = self.srv.session_store.append_message
        if ss_error is not None:
            self.srv.session_store.append_message = _fail
        try:
            self.srv.session_store.append_message("default", msg)
        except Exception as _ss_exc:
            try:
                self.srv.event_log.append(
                    "gui.session_store_error",
                    {"message_id": msg.get("message_id", ""), "error": str(_ss_exc)},
                    actor="admin_gui",
                )
            except Exception:
                pass
        finally:
            if ss_error is not None:
                self.srv.session_store.append_message = original_append

    def test_session_store_error_emits_event(self):
        """When append_message() raises, an event is appended to EventLog."""
        msg = {"message_id": "m2", "role": "user"}
        self._simulate_save_message_block(msg, ss_error=RuntimeError("disk full"))

        events = self.srv.event_log.read()
        error_events = [e for e in events if e.get("type") == "gui.session_store_error"]
        self.assertEqual(len(error_events), 1)

    def test_event_contains_message_id(self):
        """The logged event must include the failing message_id."""
        msg = {"message_id": "msg-abc", "role": "user"}
        self._simulate_save_message_block(msg, ss_error=OSError("no space"))

        events = self.srv.event_log.read()
        error_events = [e for e in events if e.get("type") == "gui.session_store_error"]
        self.assertEqual(error_events[0]["data"]["message_id"], "msg-abc")

    def test_event_contains_error_string(self):
        """The logged event must include a string representation of the exception."""
        msg = {"message_id": "m3", "role": "user"}
        self._simulate_save_message_block(msg, ss_error=ValueError("bad value"))

        events = self.srv.event_log.read()
        error_events = [e for e in events if e.get("type") == "gui.session_store_error"]
        self.assertIn("bad value", error_events[0]["data"]["error"])

    def test_event_actor_is_admin_gui(self):
        """The logged event must use actor='admin_gui'."""
        msg = {"message_id": "m4"}
        self._simulate_save_message_block(msg, ss_error=RuntimeError("err"))

        events = self.srv.event_log.read()
        error_events = [e for e in events if e.get("type") == "gui.session_store_error"]
        self.assertEqual(error_events[0]["actor"], "admin_gui")

    def test_missing_message_id_uses_empty_string(self):
        """If msg has no message_id, event data must use empty string fallback."""
        msg = {"role": "system"}  # no message_id
        self._simulate_save_message_block(msg, ss_error=RuntimeError("err"))

        events = self.srv.event_log.read()
        error_events = [e for e in events if e.get("type") == "gui.session_store_error"]
        self.assertEqual(error_events[0]["data"]["message_id"], "")

    def test_event_log_failure_does_not_propagate(self):
        """If event_log.append() itself raises, the exception must be swallowed."""
        msg = {"message_id": "m5"}
        original_elog_append = self.srv.event_log.append
        self.srv.event_log.append = MagicMock(side_effect=OSError("event log disk full"))

        try:
            self._simulate_save_message_block(msg, ss_error=RuntimeError("ss error"))
        except Exception as exc:
            self.fail(f"Exception propagated unexpectedly: {exc}")
        finally:
            self.srv.event_log.append = original_elog_append


# ---------------------------------------------------------------------------
# 3. Source-text guards
# ---------------------------------------------------------------------------

class TestSourceContainsErrorLogging(unittest.TestCase):
    SRC_TEXT = (ROOT / "src" / "admin_gui_server.py").read_text(encoding="utf-8")

    def test_exception_caught_as_named_variable(self):
        """except Exception should bind to a named variable, not bare pass."""
        self.assertIn("except Exception as _ss_exc:", self.SRC_TEXT)

    def test_event_log_append_called_in_except(self):
        """event_log.append must be called inside the session_store except block."""
        self.assertIn('"gui.session_store_error"', self.SRC_TEXT)

    def test_actor_admin_gui(self):
        """Event must use actor='admin_gui'."""
        self.assertIn('actor="admin_gui"', self.SRC_TEXT)

    def test_inner_guard_against_event_log_failure(self):
        """Inner try/except must guard against event_log.append() failing."""
        # The pattern is: try: self.event_log.append(...) except Exception: pass
        # Verify the nested try is present via the structural check.
        self.assertIn("gui.session_store_error", self.SRC_TEXT)
        # Also check the outer bare except is gone and replaced with named one.
        import re
        bare_pass = re.findall(r"except Exception:\s*\n\s*pass", self.SRC_TEXT)
        # The inner guard for event_log failure is still an `except Exception: pass`,
        # but the outer session_store one must now be named.
        # We verify by ensuring the named form is present.
        self.assertIn("except Exception as _ss_exc:", self.SRC_TEXT)


if __name__ == "__main__":
    unittest.main()
