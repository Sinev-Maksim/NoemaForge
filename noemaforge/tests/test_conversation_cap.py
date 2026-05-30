#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_conversation_cap.py
Zone: test
Version: 0.32.2
Created: 2026-05-30
Modified: 2026-05-30
Purpose: TDD tests for MAX_CONVERSATION_MESSAGES cap in AdminGuiServer._save_conversation().
  Verifies that conversation-current.json is trimmed to at most 1000 messages,
  that the most-recent messages are kept (oldest are dropped), and that the
  cap boundary is respected exactly.
Inputs: admin_gui_server.AdminGuiServer, admin_gui_server.MAX_CONVERSATION_MESSAGES.
Outputs: test pass/fail.
Side effects: Creates and removes temporary directories.
Tests: python noemaforge/tests/test_conversation_cap.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path

_SRC = Path(__file__).parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from admin_gui_server import AdminGuiServer, MAX_CONVERSATION_MESSAGES  # noqa: E402
from session_store import SessionStore  # noqa: E402
from event_log import EventLog  # noqa: E402


def _make_server(td: Path) -> AdminGuiServer:
    """Minimal AdminGuiServer stub wired with real file I/O and session/event stores."""
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


class TestMaxConversationMessagesConstant(unittest.TestCase):
    """MAX_CONVERSATION_MESSAGES is exported and has the expected value."""

    def test_constant_is_1000(self) -> None:
        self.assertEqual(MAX_CONVERSATION_MESSAGES, 1000)

    def test_constant_is_positive_int(self) -> None:
        self.assertIsInstance(MAX_CONVERSATION_MESSAGES, int)
        self.assertGreater(MAX_CONVERSATION_MESSAGES, 0)


class TestSaveConversationCap(unittest.TestCase):
    """_save_conversation() trims conv['messages'] to MAX_CONVERSATION_MESSAGES."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.td = Path(self._td.name)
        self.srv = _make_server(self.td)

    def tearDown(self) -> None:
        self._td.cleanup()

    def _make_conv(self, n: int) -> dict:
        """Build a conversation dict with n dummy messages."""
        return {
            "conversation_id": "conv_test",
            "created_at": "2026-05-30T00:00:00Z",
            "updated_at": "2026-05-30T00:00:00Z",
            "locale": "ru",
            "active_persona": "Admin",
            "pending_intent": None,
            "pending_payload": {},
            "messages": [{"message_id": f"msg_{i}", "text": f"msg {i}"} for i in range(n)],
            "artifacts": [],
            "jobs": [],
        }

    def test_below_cap_unchanged(self) -> None:
        """Fewer than MAX messages: all are preserved."""
        n = MAX_CONVERSATION_MESSAGES - 1
        conv = self._make_conv(n)
        self.srv._save_conversation(conv)
        saved = json.loads(self.srv.conversation_file().read_text(encoding="utf-8"))
        self.assertEqual(len(saved["messages"]), n)

    def test_at_cap_unchanged(self) -> None:
        """Exactly MAX messages: all are preserved."""
        conv = self._make_conv(MAX_CONVERSATION_MESSAGES)
        self.srv._save_conversation(conv)
        saved = json.loads(self.srv.conversation_file().read_text(encoding="utf-8"))
        self.assertEqual(len(saved["messages"]), MAX_CONVERSATION_MESSAGES)

    def test_above_cap_trimmed_to_max(self) -> None:
        """Exceeding MAX: messages trimmed to exactly MAX."""
        n = MAX_CONVERSATION_MESSAGES + 50
        conv = self._make_conv(n)
        self.srv._save_conversation(conv)
        saved = json.loads(self.srv.conversation_file().read_text(encoding="utf-8"))
        self.assertEqual(len(saved["messages"]), MAX_CONVERSATION_MESSAGES)

    def test_oldest_messages_dropped(self) -> None:
        """When trimmed, the oldest messages are dropped (newest kept)."""
        n = MAX_CONVERSATION_MESSAGES + 5
        conv = self._make_conv(n)
        self.srv._save_conversation(conv)
        saved = json.loads(self.srv.conversation_file().read_text(encoding="utf-8"))
        # Oldest messages (indices 0–4) must be gone; newest must remain.
        ids = [m["message_id"] for m in saved["messages"]]
        self.assertNotIn("msg_0", ids)
        self.assertNotIn("msg_4", ids)
        self.assertIn(f"msg_{n - 1}", ids)

    def test_newest_messages_kept(self) -> None:
        """The last MAX messages are always retained."""
        n = MAX_CONVERSATION_MESSAGES + 100
        conv = self._make_conv(n)
        self.srv._save_conversation(conv)
        saved = json.loads(self.srv.conversation_file().read_text(encoding="utf-8"))
        ids = [m["message_id"] for m in saved["messages"]]
        # The very last message must survive.
        self.assertIn(f"msg_{n - 1}", ids)
        # First message at the new boundary must survive.
        self.assertIn(f"msg_{n - MAX_CONVERSATION_MESSAGES}", ids)

    def test_empty_messages_list_no_error(self) -> None:
        """Empty messages list is saved without error."""
        conv = self._make_conv(0)
        self.srv._save_conversation(conv)
        saved = json.loads(self.srv.conversation_file().read_text(encoding="utf-8"))
        self.assertEqual(saved["messages"], [])

    def test_missing_messages_key_no_error(self) -> None:
        """conv without 'messages' key is saved without error."""
        conv = {
            "conversation_id": "conv_test",
            "created_at": "2026-05-30T00:00:00Z",
            "updated_at": "2026-05-30T00:00:00Z",
        }
        self.srv._save_conversation(conv)  # must not raise
        saved = json.loads(self.srv.conversation_file().read_text(encoding="utf-8"))
        self.assertIn("updated_at", saved)


class TestSourceContainsCapLogic(unittest.TestCase):
    """Source-text assertions: the constant and slice must appear in admin_gui_server.py."""

    def setUp(self) -> None:
        src_path = Path(__file__).parent.parent / "src" / "admin_gui_server.py"
        self._src = src_path.read_text(encoding="utf-8")

    def test_constant_defined(self) -> None:
        self.assertIn("MAX_CONVERSATION_MESSAGES = 1000", self._src)

    def test_cap_applied_in_save_conversation(self) -> None:
        self.assertIn("MAX_CONVERSATION_MESSAGES", self._src)
        # The slice must be present somewhere after _save_conversation definition.
        idx = self._src.index("def _save_conversation(")
        snippet = self._src[idx: idx + 600]
        self.assertIn("MAX_CONVERSATION_MESSAGES", snippet)

    def test_slice_trims_tail(self) -> None:
        """The trimming uses a negative-index slice to keep newest messages."""
        self.assertIn("[-MAX_CONVERSATION_MESSAGES:]", self._src)

    def test_constant_in_module_scope(self) -> None:
        """Constant is defined at module level (not inside a class or function)."""
        for line in self._src.splitlines():
            if line.startswith("MAX_CONVERSATION_MESSAGES"):
                self.assertIn("= 1000", line)
                return
        self.fail("MAX_CONVERSATION_MESSAGES not found at module level")


if __name__ == "__main__":
    unittest.main()
