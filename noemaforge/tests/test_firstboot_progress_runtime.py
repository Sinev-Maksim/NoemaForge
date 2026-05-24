#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_firstboot_progress_runtime.py
Zone: release/package
Version: 0.31.21.alpha
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate firstboot progress view rendering and policy checks.
Inputs: Firstboot Progress View policy and offline examples.
Outputs: unittest assertions only.
Side effects: None.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import firstboot_progress_runtime as fbp

class FirstbootProgressRuntimeTests(unittest.TestCase):
    def test_workspace_policy_validates(self) -> None:
        policy = fbp.load_policy(ROOT / "configs" / "firstboot-progress-view-policy.json")
        report = fbp.validate_firstboot_progress_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(8, report["metrics"]["phases"])
        self.assertEqual(1, report["metrics"]["examples"])
        self.assertEqual(len(policy["refs"]), report["metrics"]["resolved_refs"])

    def test_progress_view_renders_all_canonical_phases_and_next_actions(self) -> None:
        example = fbp.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "firstboot_progress_view.example.json")
        view = fbp.build_progress_view(example["events"], status=example["status"], staffing=example["staffing"])
        text = fbp.render_progress_text(view)
        self.assertEqual("FirstbootProgressView", view["kind"])
        self.assertEqual("reboot_pending", view["final_summary"]["current_phase"])
        self.assertGreaterEqual(view["final_summary"]["completed_phases"], 6)
        for phase_id in fbp.REQUIRED_PHASES:
            self.assertIn(phase_id, text)
        self.assertIn("FIRSTBOOT PROGRESS", text)
        self.assertIn("Next actions", text)

    def test_cli_validation_summary_uses_workspace_policy(self) -> None:
        raw = subprocess.check_output(
            [sys.executable, str(ROOT / "src" / "firstboot_progress_runtime.py"), "--validate", "--summary"],
            text=True,
            cwd=str(PROJECT_ROOT),
        )
        summary = json.loads(raw)
        self.assertTrue(summary["ok"], summary["failures"])
        self.assertEqual("firstboot-progress-view-core", summary["id"])


if __name__ == "__main__":
    unittest.main()
