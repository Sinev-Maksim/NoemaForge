#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_smarthome_local_control_qa.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test SmartHome Local Control discoverability through registry and canonical docs.
Inputs: Unified Registry, SmartHome policy and canonical documentation files.
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

import smarthome_local_control_runtime as shcr
import unified_registry_runtime as urr


class SmartHomeLocalControlQATests(unittest.TestCase):
    TODO_ITEM = (
        "Smart Home local-first control pack: plugs, switches, vacuums, "
        "cameras, sensors, local server, value your privacy."
    )
    CLOSURE = "Closed by `smarthome-local-control-core`"

    def test_smarthome_pack_is_registered_and_attached_to_pipeline(self) -> None:
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
        pack = entries.get("eval-pack:smarthome-local-control-core:0.32.1")
        self.assertIsNotNone(pack)
        self.assertIn("configs/smarthome-local-control-policy.json", pack["refs"])
        self.assertIn("src/smarthome_local_control_runtime.py", pack["refs"])
        self.assertIn("tests/test_smarthome_local_control_performance.py", pack["refs"])

        pipeline = entries["pipeline:firstboot-model-selection:0.32.1"]
        self.assertIn("eval-pack:smarthome-local-control-core:0.32.1", pipeline["eval_pack_refs"])
        self.assertIn("configs/smarthome-local-control-policy.json", pipeline["refs"])
        self.assertIn("src/smarthome_local_control_runtime.py", pipeline["refs"])

    def test_smarthome_docs_policy_and_changelog_are_discoverable(self) -> None:
        policy = shcr.load_policy(ROOT / "configs" / "smarthome-local-control-policy.json")
        self.assertEqual("SmartHomeLocalControlPolicy", policy["kind"])
        self.assertEqual("local_first_control_pack", policy["policy"]["activation_state"])
        self.assertFalse(policy["policy"]["privacy_controls"]["hidden_camera_capture_allowed"])
        self.assertTrue(policy["policy"]["governance_controls"]["emergency_pause_required"])

        report = shcr.validate_smarthome_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(report["ok"], report["failures"])

        for path in [
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "TODO.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("[x] Add local-first SmartHome pack", text)
            self.assertIn("[x] Add no-hidden-camera/no-hidden-microphone policy", text)
            self.assertIn("SmartHome Local Control", text)

        context = (ROOT / "docs" / "reference" / "PROJECT_CONTEXT.md").read_text(encoding="utf-8")
        self.assertIn("SmartHome Local Control", context)
        self.assertIn("smarthome-local-control-core", context)
        self.assertIn("visible privacy state", context)

        for path in [ROOT / "docs" / "history" / "CHANGELOG.md"]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("smarthome-local-control-core", text)
            self.assertIn("local-first device registry", text)

    def test_smarthome_local_first_roadmap_item_is_closed_in_canonical_docs(self) -> None:
        closed_line = f"- [x] {self.TODO_ITEM} {self.CLOSURE}"
        open_line = f"- [ ] {self.TODO_ITEM}"

        for path in [
            ROOT / "docs" / "TODO.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn(closed_line, text)
            self.assertNotIn(open_line, text)

        changelog = (ROOT / "docs" / "history" / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn(self.TODO_ITEM, changelog)
        self.assertIn("smarthome-local-control-core", changelog)


if __name__ == "__main__":
    unittest.main()

