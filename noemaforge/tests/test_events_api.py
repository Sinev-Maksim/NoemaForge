#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_events_api.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-27
Modified: 2026-05-27
Purpose: TDD tests for GET /api/events wired via event_log.py.
Inputs: EventLog, AdminGuiServer.events_api().
Outputs: unittest assertions only.
Side effects: None (temp dirs only).
Tests: python3 -m unittest noemaforge/tests/test_events_api.py -v
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
from event_log import EventLog
import admin_gui_server
from admin_gui_server import AdminGuiServer


class TestEventLogUnit(unittest.TestCase):
    """EventLog.read() returns list; append() creates readable rows."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="nf_events_test_")
        self.tmp_path = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_read_empty_log_returns_list(self) -> None:
        log = EventLog(self.tmp_path / "events")
        result = log.read()
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 0)

    def test_append_then_read_returns_event(self) -> None:
        log = EventLog(self.tmp_path / "events")
        log.append("test.event", {"key": "value"}, actor="test")
        rows = log.read()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["type"], "test.event")
        self.assertEqual(rows[0]["data"]["key"], "value")
        self.assertEqual(rows[0]["actor"], "test")

    def test_read_after_index_skips_earlier_rows(self) -> None:
        log = EventLog(self.tmp_path / "events")
        log.append("ev.first", {})
        log.append("ev.second", {})
        rows = log.read(after_index=1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["type"], "ev.second")

    def test_each_row_has_index_field(self) -> None:
        log = EventLog(self.tmp_path / "events")
        log.append("ev.a", {})
        log.append("ev.b", {})
        rows = log.read()
        for row in rows:
            self.assertIn("index", row)


class TestEventsApiMethod(unittest.TestCase):
    """AdminGuiServer.events_api() returns {ok, version, events}."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="nf_events_method_")
        self.tmp_path = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _make_server_stub(self) -> AdminGuiServer:
        log = EventLog(self.tmp_path / "events")
        obj = object.__new__(AdminGuiServer)
        obj.event_log = log
        return obj

    def test_events_api_ok_flag(self) -> None:
        srv = self._make_server_stub()
        result = srv.events_api()
        self.assertTrue(result["ok"])

    def test_events_api_includes_version(self) -> None:
        srv = self._make_server_stub()
        result = srv.events_api()
        self.assertEqual(result["version"], RUNTIME_VERSION)

    def test_events_api_has_events_list(self) -> None:
        srv = self._make_server_stub()
        result = srv.events_api()
        self.assertIn("events", result)
        self.assertIsInstance(result["events"], list)

    def test_events_api_respects_after_index(self) -> None:
        log = EventLog(self.tmp_path / "events")
        log.append("ev.a", {})
        log.append("ev.b", {})
        obj = object.__new__(AdminGuiServer)
        obj.event_log = log
        # after_index=0 → 2 events; after_index=1 → 1 event
        all_events = obj.events_api(after_index=0)["events"]
        tail_events = obj.events_api(after_index=1)["events"]
        self.assertEqual(len(all_events), 2)
        self.assertEqual(len(tail_events), 1)


class TestEventsApiRoute(unittest.TestCase):
    """GET /api/events must be registered in AdminGuiHandler.do_GET."""

    _source: str = ""

    @classmethod
    def setUpClass(cls) -> None:
        cls._source = (ROOT / "src" / "admin_gui_server.py").read_text(encoding="utf-8")

    def test_route_string_present_in_do_get(self) -> None:
        self.assertIn('"/api/events"', self._source)

    def test_events_api_method_called_in_do_get(self) -> None:
        self.assertIn("events_api(", self._source)

    def test_event_log_imported_or_instantiated(self) -> None:
        self.assertIn("EventLog", self._source)

    def test_event_log_in_init(self) -> None:
        self.assertIn("self.event_log", self._source)


if __name__ == "__main__":
    unittest.main()
