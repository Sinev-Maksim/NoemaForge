#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_save_message_single_append.py
Zone: test
Version: 0.32.2
Created: 2026-05-30
Modified: 2026-05-30
Purpose: TDD tests verifying that save_message() calls session_store.append_message()
  exactly once, with the full message dict (not a slim subset).
  Fixes the double-append bug where two separate calls were made: one slim-dict
  call immediately after _save_conversation(), and a second full-msg call at the
  end — doubling the session-store message count and halving the 500-message window.
Inputs: admin_gui_server.AdminGuiServer.save_message().
Outputs: test pass/fail.
Side effects: Creates and removes temporary directories.
Tests: python noemaforge/tests/test_save_message_single_append.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, patch

_SRC = Path(__file__).parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from admin_gui_server import AdminGuiServer  # noqa: E402
from session_store import SessionStore  # noqa: E402
from event_log import EventLog  # noqa: E402


def _make_server(td: Path) -> AdminGuiServer:
    """Minimal AdminGuiServer stub with real file I/O."""
    srv = object.__new__(AdminGuiServer)
    srv.data_root = td
    srv.gui_state_dir = td / "gui"
    srv.gui_state_dir.mkdir(parents=True, exist_ok=True)
    srv.jobs_dir = td / "jobs"
    srv.jobs_dir.mkdir(parents=True, exist_ok=True)
    srv.review_dir = td / "review"
    (srv.review_dir / "sr" / "inbox").mkdir(parents=True, exist_ok=True)
    (srv.review_dir / "ssr" / "inbox").mkdir(parents=True, exist_ok=True)
    srv.model_selection_state = td / "model_selection"
    srv.model_selection_state.mkdir(parents=True, exist_ok=True)
    srv.session_store = SessionStore(td / "sessions")
    srv.event_log = EventLog(td / "events")
    srv._state_lock = threading.Lock()
    return srv


class TestSaveMessageSingleAppend(unittest.TestCase):
    """save_message() must call session_store.append_message() exactly once."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.td = Path(self._td.name)
        self.srv = _make_server(self.td)

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_append_message_called_exactly_once(self) -> None:
        """Replacing session_store with a mock, save_message triggers exactly one call."""
        mock_ss = MagicMock(spec=SessionStore)
        self.srv.session_store = mock_ss
        self.srv.save_message("user", "hello")
        self.assertEqual(mock_ss.append_message.call_count, 1)

    def test_append_message_payload_has_full_msg_fields(self) -> None:
        """The single call passes the full message dict (has message_id, trace_id, etc.)."""
        mock_ss = MagicMock(spec=SessionStore)
        self.srv.session_store = mock_ss
        self.srv.save_message("user", "test payload")
        args, _ = mock_ss.append_message.call_args
        # args[0] is session_id, args[1] is the message payload
        _session_id, payload = args
        self.assertIn("message_id", payload)
        self.assertIn("trace_id", payload)
        self.assertIn("conversation_id", payload)
        self.assertIn("role", payload)
        self.assertIn("text", payload)
        self.assertIn("ts", payload)

    def test_append_message_slim_dict_not_sent(self) -> None:
        """The payload is NOT a minimal slim dict (missing message_id was the old bug)."""
        mock_ss = MagicMock(spec=SessionStore)
        self.srv.session_store = mock_ss
        self.srv.save_message("assistant", "response")
        args, _ = mock_ss.append_message.call_args
        _session_id, payload = args
        # A slim dict only had role/persona/text/intent/ts — no message_id
        self.assertIn("message_id", payload,
                      "Slim-dict bug: payload missing message_id (duplicate call was removed)")

    def test_append_message_session_id_is_default(self) -> None:
        """The call targets the 'default' session."""
        mock_ss = MagicMock(spec=SessionStore)
        self.srv.session_store = mock_ss
        self.srv.save_message("user", "check session id")
        args, _ = mock_ss.append_message.call_args
        session_id = args[0]
        self.assertEqual(session_id, "default")

    def test_multiple_save_messages_not_doubled(self) -> None:
        """Three save_message() calls → exactly three append_message() calls (not six)."""
        mock_ss = MagicMock(spec=SessionStore)
        self.srv.session_store = mock_ss
        for i in range(3):
            self.srv.save_message("user", f"msg {i}")
        self.assertEqual(mock_ss.append_message.call_count, 3)

    def test_save_message_with_real_session_store_no_duplicate(self) -> None:
        """Using the real SessionStore, save_message() adds exactly one message per call."""
        self.srv.save_message("user", "first")
        self.srv.save_message("assistant", "second")
        session = self.srv.session_store.load("default")
        messages = session.get("messages", [])
        self.assertEqual(len(messages), 2,
                         f"Expected 2 messages, got {len(messages)} (double-append bug?)")


class TestSourceNoDoubleAppend(unittest.TestCase):
    """Source-text assertions: the slim-dict call must not exist in admin_gui_server.py."""

    def setUp(self) -> None:
        src_path = Path(__file__).parent.parent / "src" / "admin_gui_server.py"
        self._src = src_path.read_text(encoding="utf-8")

    def test_slim_dict_call_removed(self) -> None:
        """The old slim-dict append_message call must not appear."""
        # Old signature: append_message("default", {"role": role, "persona": ...})
        self.assertNotIn(
            'append_message("default", {"role": role',
            self._src,
            "Slim-dict double-append call was not removed from save_message()",
        )

    def test_only_one_append_message_in_save_message(self) -> None:
        """save_message() body contains exactly one append_message reference."""
        start = self._src.index("def save_message(")
        # Find the next method def to bound the search
        next_def = self._src.index("\n    def ", start + 1)
        body = self._src[start:next_def]
        occurrences = body.count("append_message")
        self.assertEqual(occurrences, 1,
                         f"Expected 1 append_message call in save_message, found {occurrences}")

    def test_full_msg_append_present(self) -> None:
        """The full-msg call (append_message('default', msg)) is retained."""
        self.assertIn('append_message("default", msg)', self._src)

    def test_sync_comment_removed(self) -> None:
        """The stale 'Sync message into session store' comment is removed."""
        self.assertNotIn("Sync message into session store", self._src)


if __name__ == "__main__":
    unittest.main()
