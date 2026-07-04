#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_admin_gui_task_state_payload.py
Zone: gui/control-plane
Version: 0.32.2
Created: 2026-07-04
Modified: 2026-07-04
Purpose: Validate Admin GUI task panel state payload for configured default tasks.
Inputs: Admin GUI task API helpers and taskqueue policy fixture.
Outputs: unittest assertions only.
Side effects: Temporary task store writes only.
Tests: python3 -m unittest noemaforge/tests/test_admin_gui_task_state_payload.py -v
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path


ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, str(ROOT / "src"))

from admin_gui_server import AdminGuiServer  # noqa: E402


class _FakeEventLog:
    def __init__(self) -> None:
        self.rows = []

    def append(self, event_type, data=None, *, actor="system", trace_id=""):
        row = {
            "type": event_type,
            "data": data or {},
            "actor": actor,
            "trace_id": trace_id,
        }
        self.rows.append(row)
        return row


def _build_server(tasks_dir: Path) -> AdminGuiServer:
    server = object.__new__(AdminGuiServer)
    server.root = ROOT
    server.tasks_dir = tasks_dir
    server._tasks_lock = threading.Lock()
    server.event_log = _FakeEventLog()
    server._last_task_state_reason = ""
    return server


class AdminGuiTaskStatePayloadTests(unittest.TestCase):
    def test_empty_task_store_exposes_expected_defaults_and_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            server = _build_server(Path(tmp) / "tasks")
            payload = server.tasks_list()

        self.assertTrue(payload["ok"])
        self.assertEqual([], payload["tasks"])
        self.assertEqual(
            "default_tasks_configured_not_materialized",
            payload["task_state"]["state_reason"],
        )
        self.assertGreater(payload["task_state"]["expected_default_task_count"], 0)
        self.assertEqual(
            payload["task_state"]["expected_default_task_count"],
            payload["task_state"]["missing_default_task_count"],
        )
        self.assertGreater(len(payload["expected_default_tasks"]), 0)
        self.assertIn("visible_note", payload["task_state"])
        self.assertEqual(
            payload["task_state"]["state_reason"],
            payload["summary"]["state_reason"],
        )

    def test_manual_refresh_preserves_payload_and_logs_reason_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            server = _build_server(Path(tmp) / "tasks")
            first = server.tasks_list()
            second = server.tasks_list()

            self.assertEqual(first["task_state"], second["task_state"])
            self.assertEqual(1, len(server.event_log.rows))
            self.assertEqual("admin_gui.task_state", server.event_log.rows[0]["type"])
            self.assertEqual(
                first["task_state"]["state_reason"],
                server.event_log.rows[0]["data"]["state_reason"],
            )

    def test_materialized_default_tasks_report_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            server = _build_server(Path(tmp) / "tasks")
            expected = server._expected_default_tasks()
            tasks = []
            for item in expected:
                tasks.append({
                    "task_id": item["task_id"],
                    "title": item["title"],
                    "category": item["category"],
                    "priority": 50,
                    "status": "pending",
                    "group_key": item["group_key"],
                })
            server._write_json(server.task_store_file(), {"tasks": tasks})

            payload = server.tasks_list()

        self.assertEqual("default_tasks_present", payload["task_state"]["state_reason"])
        self.assertEqual(0, payload["task_state"]["missing_default_task_count"])
        self.assertEqual(len(expected), payload["summary"]["pending"])


if __name__ == "__main__":
    unittest.main()
