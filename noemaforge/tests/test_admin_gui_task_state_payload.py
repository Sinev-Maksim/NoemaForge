#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_admin_gui_task_state_payload.py
Zone: gui/control-plane
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
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path


ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, str(ROOT / "src"))

from admin_gui_server import AdminGuiServer  # noqa: E402


DEFAULT_TASKQUEUE_POLICY = """\
apiVersion: noemaforge.taskqueue/v1
kind: TaskQueuePolicy
default_tasks:
  SELF_IMPROVE:
  - kind: module
    module: surgeon_auto
    priority_class: background
    group_key: default.self_improve.surgeon_auto
    cooldown_sec: 3600
  SECURITY:
  - kind: module
    module: scary_sweep
    priority_class: background
    group_key: default.security.scary_sweep
    cooldown_sec: 1800
"""


class _FakeEventLog:
    def __init__(self, *, fail: bool = False) -> None:
        self.rows = []
        self.fail = fail

    def append(self, event_type, data=None, *, actor="system", trace_id=""):
        if self.fail:
            raise RuntimeError("append failed")
        row = {
            "type": event_type,
            "data": data or {},
            "actor": actor,
            "trace_id": trace_id,
        }
        self.rows.append(row)
        return row


def _build_server(tmp: Path, *, policy_text: str | None = DEFAULT_TASKQUEUE_POLICY, event_log: _FakeEventLog | None = None) -> AdminGuiServer:
    root = tmp / "root"
    config_dir = root / "configs"
    config_dir.mkdir(parents=True, exist_ok=True)
    if policy_text is not None:
        (config_dir / "taskqueue-policy.yaml").write_text(policy_text, encoding="utf-8")
    server = object.__new__(AdminGuiServer)
    server.root = root
    server.tasks_dir = tmp / "tasks"
    server._tasks_lock = threading.Lock()
    server.event_log = event_log or _FakeEventLog()
    server._last_task_state_reason = ""
    server._expected_default_tasks_cache = None
    return server


class AdminGuiTaskStatePayloadTests(unittest.TestCase):
    def test_empty_task_store_exposes_expected_defaults_and_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            server = _build_server(Path(tmp))
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
            server = _build_server(Path(tmp))
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
            server = _build_server(Path(tmp))
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

    def test_missing_policy_reports_load_failure_not_no_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            server = _build_server(Path(tmp), policy_text=None)
            payload = server.tasks_list()

        self.assertEqual(
            "default_tasks_policy_unavailable",
            payload["task_state"]["state_reason"],
        )
        self.assertEqual("policy_missing", payload["task_state"]["default_tasks_load_status"])
        self.assertEqual(0, payload["task_state"]["expected_default_task_count"])

    def test_empty_default_tasks_report_no_defaults_configured(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            server = _build_server(Path(tmp), policy_text="default_tasks: {}\n")
            payload = server.tasks_list()

        self.assertEqual(
            "no_default_tasks_configured",
            payload["task_state"]["state_reason"],
        )
        self.assertEqual("ok", payload["task_state"]["default_tasks_load_status"])
        self.assertEqual(0, payload["task_state"]["expected_default_task_count"])

    def test_concurrent_reason_logging_deduplicates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            server = _build_server(Path(tmp))
            task_state = server._task_state_payload([])
            barrier = threading.Barrier(8)

            def record() -> None:
                barrier.wait()
                server._record_task_state_reason(task_state)

            threads = [threading.Thread(target=record) for _ in range(8)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

            self.assertEqual(1, len(server.event_log.rows))

    def test_event_log_append_failure_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            server = _build_server(Path(tmp), event_log=_FakeEventLog(fail=True))
            task_state = server._task_state_payload([])
            stderr = StringIO()

            with redirect_stderr(stderr):
                server._record_task_state_reason(task_state)

            self.assertIn("failed to log event", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
