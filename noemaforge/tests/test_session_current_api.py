#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_session_current_api.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-27
Modified: 2026-05-27
Purpose: TDD tests for GET /api/session/current wired via session_store.py.
Inputs: SessionStore, AdminGuiServer.session_current().
Outputs: unittest assertions only.
Side effects: None (temp dirs only).
Tests: python3 -m pytest noemaforge/tests/test_session_current_api.py -v
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]          # noemaforge/
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

from noemaforge_version import RUNTIME_VERSION
from orchestration_state import normalize_session_record
from session_store import SessionStore
import admin_gui_server
from admin_gui_server import AdminGuiServer


class TestSessionStoreUnit(unittest.TestCase):
    """SessionStore.load() returns a properly normalized default record."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="nf_session_test_")
        self.tmp_path = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_load_creates_normalized_default_session(self) -> None:
        store = SessionStore(self.tmp_path / "sessions")
        session = store.load("default")

        self.assertEqual(session["session_id"], "default")
        self.assertEqual(session["selected_mode"], "normal")
        self.assertIsInstance(session["messages"], list)
        self.assertIsInstance(session["active_jobs"], list)
        self.assertIn("updated_at", session)
        self.assertIn("version", session)

    def test_load_persists_session_file(self) -> None:
        store = SessionStore(self.tmp_path / "sessions")
        store.load("default")
        self.assertTrue((self.tmp_path / "sessions" / "default.json").exists())

    def test_load_idempotent_second_call_returns_same_id(self) -> None:
        store = SessionStore(self.tmp_path / "sessions")
        s1 = store.load("default")
        s2 = store.load("default")
        self.assertEqual(s1["session_id"], s2["session_id"])


class TestSessionCurrentMethod(unittest.TestCase):
    """AdminGuiServer.session_current() returns {ok, version, session}."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="nf_session_method_")
        self.tmp_path = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _make_server_stub(self) -> AdminGuiServer:
        """Instantiate AdminGuiServer without socket binding, for unit testing."""
        store = SessionStore(self.tmp_path / "sessions")
        # Bypass __init__ (which binds a socket and checks dir layout) so we can
        # test only the session_current() method in isolation.
        obj = object.__new__(AdminGuiServer)
        obj.session_store = store
        return obj

    def test_session_current_has_ok_flag(self) -> None:
        srv = self._make_server_stub()
        result = srv.session_current()
        self.assertTrue(result["ok"])

    def test_session_current_includes_runtime_version(self) -> None:
        srv = self._make_server_stub()
        result = srv.session_current()
        self.assertEqual(result["version"], RUNTIME_VERSION)

    def test_session_current_embeds_normalized_session(self) -> None:
        srv = self._make_server_stub()
        result = srv.session_current()
        self.assertIn("session", result)
        session = result["session"]
        self.assertEqual(session["session_id"], "default")
        self.assertIn("selected_mode", session)
        self.assertIn("messages", session)
        self.assertIn("active_jobs", session)

    def test_session_current_repeated_calls_are_stable(self) -> None:
        srv = self._make_server_stub()
        r1 = srv.session_current()
        r2 = srv.session_current()
        self.assertEqual(r1["session"]["session_id"], r2["session"]["session_id"])
        self.assertEqual(r1["session"]["selected_mode"], r2["session"]["selected_mode"])


class TestSessionCurrentRoute(unittest.TestCase):
    """GET /api/session/current must be registered in AdminGuiHandler.do_GET."""

    _source: str = ""

    @classmethod
    def setUpClass(cls) -> None:
        cls._source = (ROOT / "src" / "admin_gui_server.py").read_text(encoding="utf-8")

    def test_route_string_present_in_do_get(self) -> None:
        self.assertIn('"/api/session/current"', self._source)

    def test_session_current_method_called_in_do_get(self) -> None:
        self.assertIn("session_current()", self._source)

    def test_session_store_imported_or_instantiated(self) -> None:
        self.assertIn("SessionStore", self._source)


if __name__ == "__main__":
    unittest.main()
