#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_session_mode_history.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-27
Modified: 2026-05-27
Purpose: TDD tests for session mode persistence and message history sync via session_store.
Inputs: SessionStore, AdminGuiServer.session_mode(), AdminGuiServer.save_message().
Outputs: unittest assertions only.
Side effects: None (temp dirs only).
Tests: python3 -m unittest noemaforge/tests/test_session_mode_history.py -v
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from noemaforge_version import RUNTIME_VERSION
from session_store import SessionStore
import admin_gui_server
from admin_gui_server import AdminGuiServer


class TestSessionModeMethod(unittest.TestCase):
    """AdminGuiServer.session_mode() persists selected_mode via session_store."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="nf_mode_test_")
        self.tmp_path = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _make_server_stub(self) -> AdminGuiServer:
        store = SessionStore(self.tmp_path / "sessions")
        obj = object.__new__(AdminGuiServer)
        obj.session_store = store
        return obj

    def test_session_mode_returns_ok(self) -> None:
        srv = self._make_server_stub()
        result = srv.session_mode("normal")
        self.assertTrue(result["ok"])

    def test_session_mode_persists_to_store(self) -> None:
        srv = self._make_server_stub()
        srv.session_mode("fast")
        session = srv.session_store.load("default")
        self.assertEqual(session["selected_mode"], "fast")

    def test_session_mode_full_composite_stores_top_n(self) -> None:
        srv = self._make_server_stub()
        srv.session_mode("full_composite", composite_top_n=6)
        session = srv.session_store.load("default")
        self.assertEqual(session["selected_mode"], "full_composite")
        self.assertEqual(session["selected_composite_top_n"], 6)

    def test_session_mode_rejects_invalid_defaults_to_normal(self) -> None:
        srv = self._make_server_stub()
        srv.session_mode("invalid_mode_xyz")
        session = srv.session_store.load("default")
        self.assertEqual(session["selected_mode"], "normal")

    def test_session_mode_response_includes_session(self) -> None:
        srv = self._make_server_stub()
        result = srv.session_mode("full")
        self.assertIn("session", result)
        self.assertEqual(result["session"]["selected_mode"], "full")


class TestSessionModeRoute(unittest.TestCase):
    """POST /api/session/mode must be registered in AdminGuiHandler.do_POST."""

    _source: str = ""

    @classmethod
    def setUpClass(cls) -> None:
        cls._source = (ROOT / "src" / "admin_gui_server.py").read_text(encoding="utf-8")

    def test_post_route_session_mode_in_do_post(self) -> None:
        self.assertIn('"/api/session/mode"', self._source)

    def test_session_mode_method_called_in_do_post(self) -> None:
        self.assertIn("session_mode(", self._source)

    def test_session_store_imported(self) -> None:
        self.assertIn("SessionStore", self._source)

    def test_session_store_in_init(self) -> None:
        self.assertIn("self.session_store", self._source)


class TestSaveMessageSyncsSession(unittest.TestCase):
    """save_message() must also call session_store.append_message()."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="nf_savemsg_test_")
        self.tmp_path = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _make_server_stub(self) -> AdminGuiServer:
        store = SessionStore(self.tmp_path / "sessions")
        obj = object.__new__(AdminGuiServer)
        obj.session_store = store
        # save_message also needs gui_state_dir, data_root, review_dir
        obj.gui_state_dir = self.tmp_path / "gui"
        obj.gui_state_dir.mkdir(parents=True, exist_ok=True)
        obj.data_root = self.tmp_path / "data"
        obj.data_root.mkdir(parents=True, exist_ok=True)
        obj.review_dir = self.tmp_path / "review"
        (obj.review_dir / "sr" / "inbox").mkdir(parents=True, exist_ok=True)
        (obj.review_dir / "ssr" / "inbox").mkdir(parents=True, exist_ok=True)
        return obj

    def test_save_message_appends_to_session(self) -> None:
        srv = self._make_server_stub()
        srv.save_message("user", "Hello!")
        session = srv.session_store.load("default")
        self.assertEqual(len(session["messages"]), 1)
        self.assertEqual(session["messages"][0]["text"], "Hello!")

    def test_save_message_preserves_role_in_session(self) -> None:
        srv = self._make_server_stub()
        srv.save_message("user", "Hi")
        srv.save_message("model", "Hello there")
        session = srv.session_store.load("default")
        self.assertEqual(len(session["messages"]), 2)
        roles = [m["role"] for m in session["messages"]]
        self.assertIn("user", roles)
        self.assertIn("model", roles)

    def test_save_message_session_bounded_at_500(self) -> None:
        srv = self._make_server_stub()
        for i in range(10):
            srv.save_message("user", f"msg {i}")
        session = srv.session_store.load("default")
        # All 10 messages should be stored (well within 500 limit)
        self.assertEqual(len(session["messages"]), 10)


class TestAppJsSessionMode(unittest.TestCase):
    """Frontend app.js must persist mode and restore it on startup."""

    _appjs: str = ""

    @classmethod
    def setUpClass(cls) -> None:
        cls._appjs = (ROOT / "templates" / "pipeline-dashboard" / "app.js").read_text(encoding="utf-8")

    def test_app_js_posts_to_session_mode_on_continue(self) -> None:
        self.assertIn("/api/session/mode", self._appjs)

    def test_app_js_reads_selected_mode_from_session(self) -> None:
        self.assertIn("selected_mode", self._appjs)


if __name__ == "__main__":
    unittest.main()
