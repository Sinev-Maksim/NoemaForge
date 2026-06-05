#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_audit_remediation_unit.py
Zone: tests
Version: 0.32.2
Created: 2026-06-04
Modified: 2026-06-04
Purpose: Unit tests for audit_remediation.py helper functions:
         _find_check, _create_packet, _notify_user, _nowz,
         _save_json, _save_text, and apply_on_missing_actions.
         All I/O is redirected to temporary directories; no seclog,
         taskqueue, or incidents modules needed.
Inputs: audit_remediation module functions.
Outputs: pytest/unittest pass/fail.
Side effects: Writes and removes files under tempfile.mkdtemp().
Tests: python3 -m unittest noemaforge/tests/test_audit_remediation_unit.py -v
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


def _install_stubs(tmpdir: str) -> None:
    """Install stubs for audit_remediation dependencies."""
    # platform_paths
    stub_pp = types.ModuleType("platform_paths")
    stub_paths = types.SimpleNamespace(
        root=Path(tmpdir),
        data_root=Path(tmpdir) / "data",
    )
    stub_pp.DEFAULT_PATHS = stub_paths
    sys.modules["platform_paths"] = stub_pp

    # seclog — just a no-op append
    stub_seclog = types.ModuleType("seclog")
    stub_seclog.append = lambda event: {}
    sys.modules["seclog"] = stub_seclog

    # taskqueue — optional; stub with enqueue_task
    stub_taskqueue = types.ModuleType("taskqueue")
    stub_taskqueue.load_policy = lambda: {}
    stub_taskqueue.enqueue_task = lambda **kwargs: {"task_id": "stub_task", **kwargs}
    sys.modules["taskqueue"] = stub_taskqueue

    # incidents — optional; stub with open_incident
    stub_incidents = types.ModuleType("incidents")
    stub_incidents.open_incident = lambda **kwargs: {"path": os.path.join(tmpdir, "incident.json")}
    sys.modules["incidents"] = stub_incidents


class TestAuditRemediationBase(unittest.TestCase):
    """Base class that sets up a tmpdir and stubs before each test."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        _install_stubs(self._tmpdir)
        # Reload audit_remediation so it picks up fresh stubs
        if "audit_remediation" in sys.modules:
            del sys.modules["audit_remediation"]
        import audit_remediation
        self.ar = audit_remediation
        # Patch module-level paths to use tmpdir
        self.ar.BASE = self._tmpdir
        self.ar.PACKETS_SURGEON = os.path.join(self._tmpdir, "packets", "surgeon")
        self.ar.PACKETS_SCARY = os.path.join(self._tmpdir, "packets", "scary")
        self.ar.INCIDENTS_DIR = os.path.join(self._tmpdir, "incidents", "daily_audit")
        self.ar.OUTBOX_NOTIF = os.path.join(self._tmpdir, "outbox", "notifications", "daily_audit")

    def tearDown(self) -> None:
        shutil.rmtree(self._tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Tests for _nowz()
# ---------------------------------------------------------------------------

class TestNowz(TestAuditRemediationBase):
    """_nowz() returns an ISO8601 UTC timestamp ending with Z."""

    def test_ends_with_z(self) -> None:
        ts = self.ar._nowz()
        self.assertTrue(ts.endswith("Z"), f"Expected Z suffix, got: {ts!r}")

    def test_is_string(self) -> None:
        self.assertIsInstance(self.ar._nowz(), str)

    def test_contains_date(self) -> None:
        ts = self.ar._nowz()
        # Should contain at least YYYY-MM-DD
        import re
        self.assertTrue(re.search(r"\d{4}-\d{2}-\d{2}", ts), f"No date found in: {ts!r}")


# ---------------------------------------------------------------------------
# Tests for _save_json() and _save_text()
# ---------------------------------------------------------------------------

class TestSaveHelpers(TestAuditRemediationBase):
    """_save_json and _save_text create directories and write files."""

    def test_save_json_creates_file(self) -> None:
        path = os.path.join(self._tmpdir, "sub", "file.json")
        self.ar._save_json(path, {"key": "value"})
        self.assertTrue(os.path.isfile(path))

    def test_save_json_creates_parent_dirs(self) -> None:
        path = os.path.join(self._tmpdir, "a", "b", "c", "data.json")
        self.ar._save_json(path, {"x": 1})
        self.assertTrue(os.path.isfile(path))

    def test_save_json_content_is_valid(self) -> None:
        path = os.path.join(self._tmpdir, "data.json")
        obj = {"list": [1, 2], "nested": {"ok": True}}
        self.ar._save_json(path, obj)
        with open(path, encoding="utf-8") as f:
            result = json.load(f)
        self.assertEqual(result["nested"]["ok"], True)

    def test_save_text_creates_file(self) -> None:
        path = os.path.join(self._tmpdir, "note.md")
        self.ar._save_text(path, "# Hello\n\nContent here.\n")
        self.assertTrue(os.path.isfile(path))

    def test_save_text_content_preserved(self) -> None:
        path = os.path.join(self._tmpdir, "text.md")
        content = "# Header\n\nText with unicode: привет\n"
        self.ar._save_text(path, content)
        with open(path, encoding="utf-8") as f:
            result = f.read()
        self.assertEqual(result, content)

    def test_save_text_creates_parent_dirs(self) -> None:
        path = os.path.join(self._tmpdir, "x", "y", "note.txt")
        self.ar._save_text(path, "hello")
        self.assertTrue(os.path.isfile(path))


# ---------------------------------------------------------------------------
# Tests for _find_check()
# ---------------------------------------------------------------------------

class TestFindCheck(TestAuditRemediationBase):
    """_find_check() locates a check by ID in the audit config."""

    def _make_cfg(self, checks):
        return {"checks": checks}

    def test_finds_matching_check(self) -> None:
        cfg = self._make_cfg([
            {"id": "daily_sla", "description": "SLA check"},
            {"id": "other_check", "description": "Other"},
        ])
        result = self.ar._find_check(cfg, "daily_sla")
        self.assertIsNotNone(result)
        self.assertEqual(result["description"], "SLA check")

    def test_returns_none_for_missing_id(self) -> None:
        cfg = self._make_cfg([{"id": "check_a"}])
        result = self.ar._find_check(cfg, "nonexistent")
        self.assertIsNone(result)

    def test_empty_checks_returns_none(self) -> None:
        cfg = {"checks": []}
        result = self.ar._find_check(cfg, "any_check")
        self.assertIsNone(result)

    def test_no_checks_key_returns_none(self) -> None:
        cfg = {}
        result = self.ar._find_check(cfg, "check_a")
        self.assertIsNone(result)

    def test_skips_non_dict_entries(self) -> None:
        """Non-dict entries in checks list are safely skipped."""
        cfg = self._make_cfg([
            "invalid_entry",
            None,
            42,
            {"id": "target_check"},
        ])
        result = self.ar._find_check(cfg, "target_check")
        self.assertIsNotNone(result)

    def test_strips_whitespace_from_id(self) -> None:
        """Check IDs with surrounding whitespace are matched."""
        cfg = self._make_cfg([{"id": "  spaced_check  "}])
        result = self.ar._find_check(cfg, "spaced_check")
        self.assertIsNotNone(result)

    def test_finds_second_check(self) -> None:
        """Returns the correct check when it is not the first in the list."""
        cfg = self._make_cfg([
            {"id": "first_check"},
            {"id": "second_check", "on_missing": []},
        ])
        result = self.ar._find_check(cfg, "second_check")
        self.assertIsNotNone(result)
        self.assertIn("on_missing", result)


# ---------------------------------------------------------------------------
# Tests for _create_packet()
# ---------------------------------------------------------------------------

class TestCreatePacket(TestAuditRemediationBase):
    """_create_packet() writes handoff packets to the correct directory."""

    def test_surgeon_packet_written_to_surgeon_dir(self) -> None:
        payload = {"kind": "DailyAuditHandoff", "check_id": "test_check"}
        path = self.ar._create_packet(to_role="surgeon", payload=payload)
        self.assertTrue(os.path.isfile(path), f"Packet file not found: {path}")
        self.assertIn("surgeon", path)

    def test_scary_packet_written_to_scary_dir(self) -> None:
        payload = {"kind": "DailyAuditHandoff", "check_id": "test_check"}
        path = self.ar._create_packet(to_role="scary", payload=payload)
        self.assertTrue(os.path.isfile(path), f"Packet file not found: {path}")
        self.assertIn("scary", path)

    def test_unknown_role_goes_to_scary_dir(self) -> None:
        """Unknown roles default to the scary directory."""
        payload = {"kind": "DailyAuditHandoff"}
        path = self.ar._create_packet(to_role="unknown", payload=payload)
        self.assertIn("scary", path)

    def test_packet_content_is_valid_json(self) -> None:
        payload = {"key": "value", "nested": {"ok": True}}
        path = self.ar._create_packet(to_role="surgeon", payload=payload)
        with open(path, encoding="utf-8") as f:
            result = json.load(f)
        self.assertEqual(result["key"], "value")

    def test_packet_filename_contains_timestamp(self) -> None:
        payload = {"kind": "test"}
        path = self.ar._create_packet(to_role="surgeon", payload=payload)
        filename = os.path.basename(path)
        # Timestamp format: YYYYMMDDTHHMMSSZ
        import re
        self.assertTrue(re.search(r"\d{8}T\d{6}Z", filename),
                        f"Timestamp not found in filename: {filename!r}")

    def test_multiple_packets_different_files(self) -> None:
        """Two calls create two separate files (due to timestamp)."""
        import time
        payload = {"kind": "DailyAuditHandoff"}
        path1 = self.ar._create_packet(to_role="surgeon", payload=payload)
        time.sleep(1.1)  # Ensure different timestamps
        path2 = self.ar._create_packet(to_role="surgeon", payload=payload)
        self.assertNotEqual(path1, path2)


# ---------------------------------------------------------------------------
# Tests for _notify_user()
# ---------------------------------------------------------------------------

class TestNotifyUser(TestAuditRemediationBase):
    """_notify_user() writes a markdown notification to the outbox."""

    def test_creates_notification_file(self) -> None:
        path = self.ar._notify_user(
            day="2026-06-04",
            check_id="daily_sla",
            missing=["task_001", "task_002"],
            in_progress=["task_003"],
            actions={"remediation_tasks_enqueued": 2},
        )
        self.assertTrue(os.path.isfile(path), f"Notification file not found: {path}")

    def test_file_contains_check_id(self) -> None:
        path = self.ar._notify_user(
            day="2026-06-04",
            check_id="my_check",
            missing=["task_x"],
            in_progress=[],
            actions={},
        )
        content = Path(path).read_text(encoding="utf-8")
        self.assertIn("my_check", content)

    def test_file_contains_missing_count(self) -> None:
        path = self.ar._notify_user(
            day="2026-06-04",
            check_id="sla_check",
            missing=["task_a", "task_b", "task_c"],
            in_progress=[],
            actions={},
        )
        content = Path(path).read_text(encoding="utf-8")
        self.assertIn("3", content)

    def test_file_contains_missing_task_ids(self) -> None:
        path = self.ar._notify_user(
            day="2026-06-04",
            check_id="check",
            missing=["task_special_001"],
            in_progress=[],
            actions={},
        )
        content = Path(path).read_text(encoding="utf-8")
        self.assertIn("task_special_001", content)

    def test_in_progress_items_listed(self) -> None:
        path = self.ar._notify_user(
            day="2026-06-04",
            check_id="check",
            missing=[],
            in_progress=["task_wip_01"],
            actions={},
        )
        content = Path(path).read_text(encoding="utf-8")
        self.assertIn("task_wip_01", content)

    def test_actions_listed(self) -> None:
        path = self.ar._notify_user(
            day="2026-06-04",
            check_id="check",
            missing=["t1"],
            in_progress=[],
            actions={"incident": "/tmp/incident.json"},
        )
        content = Path(path).read_text(encoding="utf-8")
        self.assertIn("incident", content)

    def test_empty_missing_zero_count(self) -> None:
        path = self.ar._notify_user(
            day="2026-06-04",
            check_id="check",
            missing=[],
            in_progress=[],
            actions={},
        )
        content = Path(path).read_text(encoding="utf-8")
        self.assertIn("0", content)

    def test_filename_includes_day_and_check(self) -> None:
        path = self.ar._notify_user(
            day="2026-06-04",
            check_id="daily_sla",
            missing=[],
            in_progress=[],
            actions={},
        )
        filename = os.path.basename(path)
        self.assertIn("2026-06-04", filename)
        self.assertIn("daily_sla", filename)


# ---------------------------------------------------------------------------
# Tests for apply_on_missing_actions()
# ---------------------------------------------------------------------------

class TestApplyOnMissingActions(TestAuditRemediationBase):
    """apply_on_missing_actions() applies configured remediation actions."""

    def _make_cfg(self, actions):
        return {
            "checks": [
                {
                    "id": "test_check",
                    "on_missing": actions,
                }
            ]
        }

    def test_returns_ok_true_for_empty_actions(self) -> None:
        cfg = self._make_cfg([])
        result = self.ar.apply_on_missing_actions(
            aud_cfg=cfg,
            check_id="test_check",
            day="2026-06-04",
            tz="UTC",
            missing=["t1"],
            in_progress=[],
        )
        self.assertTrue(result["ok"])

    def test_returns_check_id(self) -> None:
        cfg = self._make_cfg([])
        result = self.ar.apply_on_missing_actions(
            aud_cfg=cfg,
            check_id="my_check_id",
            day="2026-06-04",
            tz="UTC",
            missing=[],
            in_progress=[],
        )
        self.assertEqual(result["check_id"], "my_check_id")

    def test_returns_day(self) -> None:
        cfg = self._make_cfg([])
        result = self.ar.apply_on_missing_actions(
            aud_cfg=cfg,
            check_id="check",
            day="2026-06-04",
            tz="UTC",
            missing=[],
            in_progress=[],
        )
        self.assertEqual(result["day"], "2026-06-04")

    def test_notify_user_action_creates_notification(self) -> None:
        cfg = self._make_cfg([{"action": "notify_user"}])
        result = self.ar.apply_on_missing_actions(
            aud_cfg=cfg,
            check_id="test_check",
            day="2026-06-04",
            tz="UTC",
            missing=["task_001"],
            in_progress=[],
        )
        self.assertTrue(result["ok"])
        notif = result.get("artifacts", {}).get("notification", {})
        self.assertIn("path", notif, "notify_user action must create notification artifact")
        self.assertTrue(os.path.isfile(notif["path"]))

    def test_create_remediation_tasks_action(self) -> None:
        cfg = self._make_cfg([{"action": "create_remediation_tasks"}])
        result = self.ar.apply_on_missing_actions(
            aud_cfg=cfg,
            check_id="test_check",
            day="2026-06-04",
            tz="UTC",
            missing=["task_001", "task_002"],
            in_progress=[],
        )
        self.assertTrue(result["ok"])
        # remediation artifact must be present with tasks list
        remediation = result.get("artifacts", {}).get("remediation", {})
        self.assertIn("tasks", remediation)
        self.assertEqual(len(remediation["tasks"]), 2)

    def test_open_incident_action_creates_incident(self) -> None:
        cfg = self._make_cfg([{"action": "open_incident"}])
        result = self.ar.apply_on_missing_actions(
            aud_cfg=cfg,
            check_id="test_check",
            day="2026-06-04",
            tz="UTC",
            missing=["task_001"],
            in_progress=[],
        )
        self.assertTrue(result["ok"])
        incident = result.get("artifacts", {}).get("incident", {})
        self.assertIn("path", incident, "open_incident must create incident artifact")

    def test_handoff_packets_always_created_when_missing(self) -> None:
        """Handoff packets are created even when no on_missing actions are configured."""
        cfg = self._make_cfg([])
        result = self.ar.apply_on_missing_actions(
            aud_cfg=cfg,
            check_id="test_check",
            day="2026-06-04",
            tz="UTC",
            missing=["task_001"],
            in_progress=[],
        )
        handoff = result.get("artifacts", {}).get("handoff", {})
        self.assertIn("surgeon", handoff, "Surgeon packet must be created for missing tasks")
        self.assertIn("scary", handoff, "Scary packet must be created for missing tasks")

    def test_actions_list_populated(self) -> None:
        cfg = self._make_cfg([
            {"action": "notify_user"},
            {"action": "open_incident"},
        ])
        result = self.ar.apply_on_missing_actions(
            aud_cfg=cfg,
            check_id="test_check",
            day="2026-06-04",
            tz="UTC",
            missing=["task_001"],
            in_progress=[],
        )
        self.assertIn("notify_user", result["actions"])
        self.assertIn("open_incident", result["actions"])

    def test_unknown_check_id_returns_ok_with_empty_actions(self) -> None:
        """When check_id is not found in config, result is ok with empty actions."""
        cfg = {"checks": [{"id": "other_check"}]}
        result = self.ar.apply_on_missing_actions(
            aud_cfg=cfg,
            check_id="nonexistent_check",
            day="2026-06-04",
            tz="UTC",
            missing=["task_001"],
            in_progress=[],
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["actions"], [])

    def test_empty_aud_cfg_returns_ok(self) -> None:
        """Empty audit config does not crash."""
        result = self.ar.apply_on_missing_actions(
            aud_cfg={},
            check_id="check",
            day="2026-06-04",
            tz="UTC",
            missing=[],
            in_progress=[],
        )
        self.assertTrue(result["ok"])

    def test_nondict_action_entries_skipped(self) -> None:
        """Non-dict entries in on_missing are safely skipped."""
        cfg = self._make_cfg([
            "invalid_string",
            None,
            42,
            {"action": "notify_user"},
        ])
        result = self.ar.apply_on_missing_actions(
            aud_cfg=cfg,
            check_id="test_check",
            day="2026-06-04",
            tz="UTC",
            missing=["task_001"],
            in_progress=[],
        )
        self.assertTrue(result["ok"])
        self.assertIn("notify_user", result["actions"])

    def test_no_missing_empty_handoff_still_ok(self) -> None:
        """When no missing tasks, handoff packets may still be attempted."""
        cfg = self._make_cfg([])
        result = self.ar.apply_on_missing_actions(
            aud_cfg=cfg,
            check_id="test_check",
            day="2026-06-04",
            tz="UTC",
            missing=[],
            in_progress=[],
        )
        self.assertTrue(result["ok"])

    def test_actions_taken_key_present(self) -> None:
        cfg = self._make_cfg([{"action": "notify_user"}])
        result = self.ar.apply_on_missing_actions(
            aud_cfg=cfg,
            check_id="test_check",
            day="2026-06-04",
            tz="UTC",
            missing=["task_001"],
            in_progress=[],
        )
        self.assertIn("actions_taken", result)

    def test_multiple_missing_tasks_enqueued(self) -> None:
        """All missing task IDs are enqueued when create_remediation_tasks is set."""
        cfg = self._make_cfg([{"action": "create_remediation_tasks"}])
        result = self.ar.apply_on_missing_actions(
            aud_cfg=cfg,
            check_id="test_check",
            day="2026-06-04",
            tz="UTC",
            missing=["task_a", "task_b", "task_c"],
            in_progress=[],
        )
        remediation = result.get("artifacts", {}).get("remediation", {})
        self.assertEqual(len(remediation.get("tasks", [])), 3)

    def test_empty_task_ids_skipped_in_remediation(self) -> None:
        """Empty-string task IDs in missing are skipped."""
        cfg = self._make_cfg([{"action": "create_remediation_tasks"}])
        result = self.ar.apply_on_missing_actions(
            aud_cfg=cfg,
            check_id="test_check",
            day="2026-06-04",
            tz="UTC",
            missing=["task_valid", "", "  "],
            in_progress=[],
        )
        remediation = result.get("artifacts", {}).get("remediation", {})
        # Only "task_valid" should be enqueued; empty strings are skipped
        self.assertEqual(len(remediation.get("tasks", [])), 1)


# ---------------------------------------------------------------------------
# Tests for _open_incident() legacy fallback (when incidents module is None)
# ---------------------------------------------------------------------------

class TestOpenIncidentLegacyFallback(TestAuditRemediationBase):
    """_open_incident() creates a JSON file when incidents module is None."""

    def test_creates_json_file_without_incidents_module(self) -> None:
        # Remove incidents stub to simulate fallback
        orig = self.ar.incidents
        try:
            self.ar.incidents = None
            path = self.ar._open_incident(
                day="2026-06-04",
                check_id="test_check",
                tz="UTC",
                missing=["task_001"],
                in_progress=[],
                report_path="/tmp/report.json",
            )
            self.assertTrue(os.path.isfile(path), f"Legacy incident file not created: {path}")
            with open(path, encoding="utf-8") as f:
                obj = json.load(f)
            self.assertEqual(obj["kind"], "DailyAuditIncident")
            self.assertEqual(obj["check_id"], "test_check")
        finally:
            self.ar.incidents = orig

    def test_legacy_incident_has_severity_s2(self) -> None:
        orig = self.ar.incidents
        try:
            self.ar.incidents = None
            path = self.ar._open_incident(
                day="2026-06-04",
                check_id="check",
                tz="UTC",
                missing=["t1"],
                in_progress=[],
            )
            with open(path, encoding="utf-8") as f:
                obj = json.load(f)
            self.assertEqual(obj["severity"], "S2")
        finally:
            self.ar.incidents = orig

    def test_legacy_incident_includes_missing_tasks(self) -> None:
        orig = self.ar.incidents
        try:
            self.ar.incidents = None
            path = self.ar._open_incident(
                day="2026-06-04",
                check_id="check",
                tz="UTC",
                missing=["task_x", "task_y"],
                in_progress=[],
            )
            with open(path, encoding="utf-8") as f:
                obj = json.load(f)
            self.assertIn("task_x", obj["missing"])
            self.assertIn("task_y", obj["missing"])
        finally:
            self.ar.incidents = orig


if __name__ == "__main__":
    unittest.main()