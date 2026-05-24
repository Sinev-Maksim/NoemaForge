#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_drive_state_qa.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-19
Modified: 2026-05-19
Purpose: QA-test Drive_State discoverability through registry and canonical docs.
Inputs: Unified Registry, Drive State policy and canonical documentation files.
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

import drive_state_runtime as dsr
import unified_registry_runtime as urr


class DriveStateQATests(unittest.TestCase):
    def test_drive_state_pack_is_registered_and_attached_to_pipeline(self) -> None:
        registry_path = ROOT / "configs" / "unified-registry.json"
        report = urr.validate_unified_registry(
            urr.load_registry(registry_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            registry_path=registry_path,
        )
        self.assertTrue(report["ok"], report["failures"])

        entries = {
            f"{entry['kind']}:{entry['id']}:{entry['version']}": entry
            for entry in report["normalized_registry"]["entries"]
        }
        pack = entries.get("eval-pack:drive-state-governance-core:0.32.1")
        self.assertIsNotNone(pack)
        self.assertIn("configs/drive-state-policy.json", pack["refs"])
        self.assertIn("src/drive_state_runtime.py", pack["refs"])
        self.assertIn("tests/test_drive_state_performance.py", pack["refs"])

        pipeline = entries["pipeline:firstboot-model-selection:0.32.1"]
        self.assertIn("eval-pack:drive-state-governance-core:0.32.1", pipeline["eval_pack_refs"])

    def test_drive_state_docs_policy_and_changelog_are_discoverable(self) -> None:
        policy = dsr.load_policy(ROOT / "configs" / "drive-state-policy.json")
        self.assertEqual("DriveStatePolicy", policy["kind"])
        self.assertEqual({"pressure", "fatigue", "urgency", "curiosity"}, set(policy["policy"]["signals"]))
        self.assertTrue(policy["policy"]["forbid_goal_rewrite"])

        report = dsr.validate_drive_state_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(report["ok"], report["failures"])

        for path in [
            PROJECT_ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("[x] Add bounded Drive_Adapter signals: pressure, fatigue, urgency, curiosity", text)
            self.assertIn("[x] Add bounded `Drive_State` adapter for pressure/fatigue/urgency/curiosity", text)

        for path in [
            PROJECT_ROOT / "docs" / "history" / "CHANGELOG.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("Drive_State / Drive_Adapter contract", text)
            self.assertIn("drive-state-governance-core", text)


if __name__ == "__main__":
    unittest.main()

