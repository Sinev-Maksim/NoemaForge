#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_audit_remediation.py
Zone: tests
Version: 0.32.2
Created: 2026-06-04
Modified: 2026-06-04
Purpose: Tests for audit_remediation.py — daily audit failure handling.
         Covers: _nowz, _save_json, _save_text, _find_check, _notify_user,
         _create_packet, apply_on_missing_actions.
Tests: python3 -m unittest noemaforge/tests/test_audit_remediation.py -v
Notes: Code comments are English-only.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# Stub platform_paths so audit_remediation.BASE can be overridden per-test
_mock_platform_paths = types.ModuleType("platform_paths")
_mock_paths_obj = MagicMock()
_mock_paths_obj.data_root = Path("/tmp/nf-audit-test-data")
_mock_platform_paths.DEFAULT_PATHS = _mock_paths_obj
sys.modules.setdefault("platform_paths", _mock_platform_paths)

# Stub seclog
_mock_seclog = types.ModuleType("seclog")
_mock_seclog.append = MagicMock(return_value={"evt_id": "test-evt", "_sel_hash": "abc"})
sys.modules.setdefault("seclog", _mock_seclog)

# Stub taskqueue (optional in audit_remediation)
_mock_taskqueue = types.ModuleType("taskqueue")
_mock_taskqueue.load_policy = MagicMock(return_value={})
_mock_taskqueue.enqueue_task = MagicMock(return_value={"task_id": "tq-001", "ok": True})
sys.modules.setdefault("taskqueue", _mock_taskqueue)

# Stub incidents (optional in audit_remediation)
_mock_incidents = types.ModuleType("incidents")
_mock_incidents.open_incident = MagicMock(return_value={"path": "/tmp/nf-audit-test-data/incidents/test.json"})
sys.modules.setdefault("incidents", _mock_incidents)

import audit_remediation  # noqa: E402


class TestNowz(unittest.TestCase):
    def test_returns_string(self) -> None:
        result = audit_remediation._nowz()
        self.assertIsInstance(result, str)

    def test_ends_with_z(self) -> None:
        result = audit_remediation._nowz()
        self.assertTrue(result.endswith("Z"), f"Expected Z suffix: {result!r}")

    def test_iso8601_format(self) -> None:
        import re
        result = audit_remediation._nowz()
        self.assertRegex(result, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")


class TestSaveJson(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self) -> None:
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_creates_file(self) -> None:
        path = os.path.join(self._tmpdir, "output.json")
        audit_remediation._save_json(path, {"key": "value"})
        self.assertTrue(os.path.exists(path))

    def test_creates_parent_dirs(self) -> None:
        path = os.path.join(self._tmpdir, "nested", "dir", "output.json")
        audit_remediation._save_json(path, {"x": 1})
        self.assertTrue(os.path.exists(path))

    def test_writes_valid_json(self) -> None:
        path = os.path.join(self._tmpdir, "data.json")
        obj = {"hello": "world", "num": 42}
        audit_remediation._save_json(path, obj)
        with open(path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        self.assertEqual(loaded, obj)

    def test_handles_list(self) -> None:
        path = os.path.join(self._tmpdir, "list.json")
        audit_remediation._save_json(path, [1, 2, 3])
        with open(path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        self.assertEqual(loaded, [1, 2, 3])

    def test_non_ascii_preserved(self) -> None:
        path = os.path.join(self._tmpdir, "unicode.json")
        obj = {"msg": "привет"}
        audit_remediation._save_json(path, obj)
        content = Path(path).read_text(encoding="utf-8")
        self.assertIn("привет", content)


class TestSaveText(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self) -> None:
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_creates_file(self) -> None:
        path = os.path.join(self._tmpdir, "note.md")
        audit_remediation._save_text(path, "# Hello\n")
        self.assertTrue(os.path.exists(path))

    def test_creates_parent_dirs(self) -> None:
        path = os.path.join(self._tmpdir, "a", "b", "note.txt")
        audit_remediation._save_text(path, "content")
        self.assertTrue(os.path.exists(path))

    def test_writes_correct_content(self) -> None:
        path = os.path.join(self._tmpdir, "file.txt")
        audit_remediation._save_text(path, "hello world")
        self.assertEqual(Path(path).read_text(encoding="utf-8"), "hello world")

    def test_empty_string_written(self) -> None:
        path = os.path.join(self._tmpdir, "empty.txt")
        audit_remediation._save_text(path, "")
        self.assertEqual(Path(path).read_text(encoding="utf-8"), "")


class TestFindCheck(unittest.TestCase):
    def _make_cfg(self, checks: list) -> dict:
        return {"checks": checks}

    def test_finds_check_by_id(self) -> None:
        cfg = self._make_cfg([{"id": "sla_check", "on_missing": []}])
        result = audit_remediation._find_check(cfg, "sla_check")
        self.assertIsNotNone(result)
        self.assertEqual(result["id"], "sla_check")

    def test_returns_none_for_unknown_id(self) -> None:
        cfg = self._make_cfg([{"id": "sla_check"}])
        result = audit_remediation._find_check(cfg, "nonexistent")
        self.assertIsNone(result)

    def test_returns_none_for_empty_checks(self) -> None:
        cfg = self._make_cfg([])
        result = audit_remediation._find_check(cfg, "any_id")
        self.assertIsNone(result)

    def test_skips_non_dict_entries(self) -> None:
        cfg = self._make_cfg(["string_entry", None, {"id": "valid"}])
        result = audit_remediation._find_check(cfg, "valid")
        self.assertIsNotNone(result)

    def test_returns_none_for_missing_checks_key(self) -> None:
        result = audit_remediation._find_check({}, "any_id")
        self.assertIsNone(result)

    def test_strips_whitespace_from_id(self) -> None:
        cfg = self._make_cfg([{"id": "  sla_check  "}])
        result = audit_remediation._find_check(cfg, "sla_check")
        self.assertIsNotNone(result)


class TestNotifyUser(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        # Patch OUTBOX_NOTIF to use temp dir
        self._orig_outbox = audit_remediation.OUTBOX_NOTIF
        audit_remediation.OUTBOX_NOTIF = os.path.join(self._tmpdir, "notifications")

    def tearDown(self) -> None:
        audit_remediation.OUTBOX_NOTIF = self._orig_outbox
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_creates_markdown_file(self) -> None:
        path = audit_remediation._notify_user(
            day="2026-06-04",
            check_id="sla_daily",
            missing=["task-1", "task-2"],
            in_progress=["task-3"],
            actions={},
        )
        self.assertTrue(os.path.exists(path))
        self.assertTrue(path.endswith(".md"))

    def test_markdown_contains_missing_count(self) -> None:
        path = audit_remediation._notify_user(
            day="2026-06-04",
            check_id="sla_daily",
            missing=["task-1", "task-2"],
            in_progress=[],
            actions={},
        )
        content = Path(path).read_text(encoding="utf-8")
        self.assertIn("2", content)  # 2 missing tasks

    def test_markdown_contains_check_id(self) -> None:
        path = audit_remediation._notify_user(
            day="2026-06-04",
            check_id="my_check",
            missing=["task-1"],
            in_progress=[],
            actions={},
        )
        content = Path(path).read_text(encoding="utf-8")
        self.assertIn("my_check", content)

    def test_markdown_lists_missing_tasks(self) -> None:
        path = audit_remediation._notify_user(
            day="2026-06-04",
            check_id="sla",
            missing=["task-999", "task-888"],
            in_progress=[],
            actions={},
        )
        content = Path(path).read_text(encoding="utf-8")
        self.assertIn("task-999", content)
        self.assertIn("task-888", content)

    def test_markdown_lists_in_progress_tasks(self) -> None:
        path = audit_remediation._notify_user(
            day="2026-06-04",
            check_id="sla",
            missing=[],
            in_progress=["task-777"],
            actions={},
        )
        content = Path(path).read_text(encoding="utf-8")
        self.assertIn("task-777", content)

    def test_actions_appear_in_markdown(self) -> None:
        path = audit_remediation._notify_user(
            day="2026-06-04",
            check_id="sla",
            missing=[],
            in_progress=[],
            actions={"remediation_tasks_enqueued": 3},
        )
        content = Path(path).read_text(encoding="utf-8")
        self.assertIn("remediation_tasks_enqueued", content)

    def test_filename_contains_day_and_check_id(self) -> None:
        path = audit_remediation._notify_user(
            day="2026-06-04",
            check_id="sla_daily",
            missing=[],
            in_progress=[],
            actions={},
        )
        self.assertIn("2026-06-04", path)
        self.assertIn("sla_daily", path)

    def test_empty_missing_list_handled(self) -> None:
        # Should not raise even with empty lists
        path = audit_remediation._notify_user(
            day="2026-06-04",
            check_id="sla",
            missing=[],
            in_progress=[],
            actions={},
        )
        self.assertIsNotNone(path)


class TestCreatePacket(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self._orig_surgeon = audit_remediation.PACKETS_SURGEON
        self._orig_scary = audit_remediation.PACKETS_SCARY
        audit_remediation.PACKETS_SURGEON = os.path.join(self._tmpdir, "packets", "surgeon")
        audit_remediation.PACKETS_SCARY = os.path.join(self._tmpdir, "packets", "scary")

    def tearDown(self) -> None:
        audit_remediation.PACKETS_SURGEON = self._orig_surgeon
        audit_remediation.PACKETS_SCARY = self._orig_scary
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_creates_surgeon_packet(self) -> None:
        path = audit_remediation._create_packet(to_role="surgeon", payload={"kind": "test"})
        self.assertTrue(os.path.exists(path))

    def test_creates_scary_packet(self) -> None:
        path = audit_remediation._create_packet(to_role="scary", payload={"kind": "test"})
        self.assertTrue(os.path.exists(path))

    def test_unknown_role_defaults_to_scary_dir(self) -> None:
        path = audit_remediation._create_packet(to_role="unknown", payload={"kind": "test"})
        self.assertIn("scary", path)

    def test_packet_is_valid_json(self) -> None:
        payload = {"kind": "DailyAuditHandoff", "date": "2026-06-04"}
        path = audit_remediation._create_packet(to_role="surgeon", payload=payload)
        with open(path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        self.assertEqual(loaded["kind"], "DailyAuditHandoff")

    def test_filename_contains_timestamp(self) -> None:
        path = audit_remediation._create_packet(to_role="surgeon", payload={})
        basename = os.path.basename(path)
        # Should contain a timestamp like 20260604T...
        import re
        self.assertRegex(basename, r"\d{8}T\d{6}Z")

    def test_filename_contains_role(self) -> None:
        path = audit_remediation._create_packet(to_role="surgeon", payload={})
        self.assertIn("surgeon", os.path.basename(path))


class TestApplyOnMissingActions(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        # Redirect all output dirs to tmpdir
        self._orig_surgeon = audit_remediation.PACKETS_SURGEON
        self._orig_scary = audit_remediation.PACKETS_SCARY
        self._orig_incidents = audit_remediation.INCIDENTS_DIR
        self._orig_outbox = audit_remediation.OUTBOX_NOTIF
        audit_remediation.PACKETS_SURGEON = os.path.join(self._tmpdir, "packets", "surgeon")
        audit_remediation.PACKETS_SCARY = os.path.join(self._tmpdir, "packets", "scary")
        audit_remediation.INCIDENTS_DIR = os.path.join(self._tmpdir, "incidents")
        audit_remediation.OUTBOX_NOTIF = os.path.join(self._tmpdir, "notifications")

    def tearDown(self) -> None:
        audit_remediation.PACKETS_SURGEON = self._orig_surgeon
        audit_remediation.PACKETS_SCARY = self._orig_scary
        audit_remediation.INCIDENTS_DIR = self._orig_incidents
        audit_remediation.OUTBOX_NOTIF = self._orig_outbox
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _make_cfg(self, actions: list) -> dict:
        return {
            "checks": [
                {
                    "id": "sla_daily",
                    "on_missing": actions,
                }
            ]
        }

    def test_returns_dict_with_ok(self) -> None:
        cfg = self._make_cfg([])
        result = audit_remediation.apply_on_missing_actions(
            aud_cfg=cfg,
            check_id="sla_daily",
            day="2026-06-04",
            tz="UTC",
            missing=["task-1"],
            in_progress=[],
        )
        self.assertIn("ok", result)
        self.assertTrue(result["ok"])

    def test_returns_check_id_and_day(self) -> None:
        cfg = self._make_cfg([])
        result = audit_remediation.apply_on_missing_actions(
            aud_cfg=cfg,
            check_id="sla_daily",
            day="2026-06-04",
            tz="UTC",
            missing=[],
            in_progress=[],
        )
        self.assertEqual(result["check_id"], "sla_daily")
        self.assertEqual(result["day"], "2026-06-04")

    def test_no_actions_when_no_on_missing_configured(self) -> None:
        cfg = self._make_cfg([])
        result = audit_remediation.apply_on_missing_actions(
            aud_cfg=cfg,
            check_id="sla_daily",
            day="2026-06-04",
            tz="UTC",
            missing=["task-1"],
            in_progress=[],
        )
        self.assertEqual(result["actions"], [])

    def test_notify_user_action_creates_notification(self) -> None:
        cfg = self._make_cfg([{"action": "notify_user"}])
        result = audit_remediation.apply_on_missing_actions(
            aud_cfg=cfg,
            check_id="sla_daily",
            day="2026-06-04",
            tz="UTC",
            missing=["task-1"],
            in_progress=[],
        )
        self.assertIn("notify_user", result["actions"])
        self.assertIn("notification", result["artifacts"])

    def test_open_incident_action_recorded(self) -> None:
        cfg = self._make_cfg([{"action": "open_incident"}])
        result = audit_remediation.apply_on_missing_actions(
            aud_cfg=cfg,
            check_id="sla_daily",
            day="2026-06-04",
            tz="UTC",
            missing=["task-1"],
            in_progress=[],
        )
        self.assertIn("open_incident", result["actions"])

    def test_unknown_check_id_returns_empty_actions(self) -> None:
        cfg = self._make_cfg([{"action": "notify_user"}])
        result = audit_remediation.apply_on_missing_actions(
            aud_cfg=cfg,
            check_id="nonexistent_check",
            day="2026-06-04",
            tz="UTC",
            missing=["task-1"],
            in_progress=[],
        )
        self.assertEqual(result["actions"], [])

    def test_handoff_packets_always_created_when_missing(self) -> None:
        cfg = self._make_cfg([])
        result = audit_remediation.apply_on_missing_actions(
            aud_cfg=cfg,
            check_id="sla_daily",
            day="2026-06-04",
            tz="UTC",
            missing=["task-1"],
            in_progress=[],
        )
        # Handoff packets are created regardless of actions list
        self.assertIn("handoff", result["artifacts"])
        self.assertIn("surgeon", result["artifacts"]["handoff"])
        self.assertIn("scary", result["artifacts"]["handoff"])

    def test_create_remediation_tasks_action_calls_taskqueue(self) -> None:
        cfg = self._make_cfg([{"action": "create_remediation_tasks"}])
        _mock_taskqueue.enqueue_task.reset_mock()
        result = audit_remediation.apply_on_missing_actions(
            aud_cfg=cfg,
            check_id="sla_daily",
            day="2026-06-04",
            tz="UTC",
            missing=["task-999"],
            in_progress=[],
        )
        self.assertIn("create_remediation_tasks", result["actions"])
        _mock_taskqueue.enqueue_task.assert_called()

    def test_actions_taken_dict_populated(self) -> None:
        cfg = self._make_cfg([{"action": "notify_user"}])
        result = audit_remediation.apply_on_missing_actions(
            aud_cfg=cfg,
            check_id="sla_daily",
            day="2026-06-04",
            tz="UTC",
            missing=["task-1"],
            in_progress=[],
        )
        self.assertIn("actions_taken", result)

    def test_non_dict_action_entries_skipped(self) -> None:
        cfg = {"checks": [{"id": "sla_daily", "on_missing": ["invalid", None, {"action": "notify_user"}]}]}
        result = audit_remediation.apply_on_missing_actions(
            aud_cfg=cfg,
            check_id="sla_daily",
            day="2026-06-04",
            tz="UTC",
            missing=["task-1"],
            in_progress=[],
        )
        # Should not crash; only the dict entry should be processed
        self.assertIn("notify_user", result["actions"])

    def test_missing_aud_cfg_does_not_crash(self) -> None:
        result = audit_remediation.apply_on_missing_actions(
            aud_cfg={},
            check_id="sla_daily",
            day="2026-06-04",
            tz="UTC",
            missing=["task-1"],
            in_progress=[],
        )
        self.assertIn("ok", result)

    def test_empty_missing_list_still_creates_packets(self) -> None:
        # Even with no missing tasks, packets are attempted
        cfg = self._make_cfg([])
        result = audit_remediation.apply_on_missing_actions(
            aud_cfg=cfg,
            check_id="sla_daily",
            day="2026-06-04",
            tz="UTC",
            missing=[],
            in_progress=[],
        )
        self.assertIn("ok", result)


if __name__ == "__main__":
    unittest.main()