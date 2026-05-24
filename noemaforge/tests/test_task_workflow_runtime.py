#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_task_workflow_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate task add/edit/prioritize/block/complete through Admin chat and API.
Inputs: Workspace task-workflow policy and Admin GUI server runtime.
Outputs: unittest assertions only.
Side effects: None.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import task_workflow_runtime as twr


class TaskWorkflowRuntimeTests(unittest.TestCase):
    def test_workspace_task_workflow_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "task-workflow-policy.json"
        report = twr.validate_task_workflow_policy(
            twr.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(1, report["metrics"]["source_reports"])
        self.assertEqual(1, report["metrics"]["valid_source_reports"])
        self.assertEqual(2, report["metrics"]["task_count"])

    def test_api_task_workflow_persists_edit_priority_block_and_complete(self) -> None:
        sequence = twr.build_task_workflow_sequence(package_root=ROOT)
        api = sequence["api"]

        self.assertTrue(all(api[step]["ok"] for step in ["create", "edit", "prioritize", "block", "complete"]))
        self.assertEqual("API edited task", api["edit"]["task"]["title"])
        self.assertEqual(90, api["prioritize"]["task"]["priority"])
        self.assertEqual("blocked", api["block"]["task"]["status"])
        self.assertEqual("completed", api["complete"]["task"]["status"])

    def test_admin_chat_task_workflow_persists_edit_priority_block_and_complete(self) -> None:
        sequence = twr.build_task_workflow_sequence(package_root=ROOT)
        chat = sequence["chat"]

        self.assertTrue(all(chat[step]["ok"] for step in ["create", "edit", "prioritize", "block", "complete"]))
        self.assertEqual("Проверить Admin task flow через чат", chat["edit"]["task"]["title"])
        self.assertEqual(95, chat["prioritize"]["task"]["priority"])
        self.assertEqual("blocked", chat["block"]["task"]["status"])
        self.assertEqual("completed", chat["complete"]["task"]["status"])


if __name__ == "__main__":
    unittest.main()
