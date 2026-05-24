#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_ota_update_layer_qa.py
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-19
Modified: 2026-05-19
Purpose: QA-test OTA Update Layer discoverability through registry and canonical docs.
Inputs: Unified Registry, OTA policy and canonical documentation files.
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
sys.path.insert(0, str(PROJECT_ROOT))

import ota_update_layer_runtime as oalr
import unified_registry_runtime as urr
from ota import update_agent


class OTAUpdateLayerQATests(unittest.TestCase):
    def test_ota_update_layer_pack_is_registered_and_attached_to_pipeline(self) -> None:
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
        pack = entries.get("eval-pack:ota-update-layer-core:0.32.0")
        self.assertIsNotNone(pack)
        self.assertIn("configs/ota-update-layer.json", pack["refs"])
        self.assertIn("src/ota_update_layer_runtime.py", pack["refs"])
        self.assertIn("ota/update_agent.py", pack["refs"])
        self.assertIn("tests/test_ota_update_layer_performance.py", pack["refs"])

        pipeline = entries["pipeline:firstboot-model-selection:0.31.13.alpha-patched1"]
        self.assertIn("eval-pack:ota-update-layer-core:0.32.0", pipeline["eval_pack_refs"])

    def test_ota_update_layer_docs_policy_and_agent_are_discoverable(self) -> None:
        policy = oalr.load_policy(ROOT / "configs" / "ota-update-layer.json")
        self.assertEqual("OTAUpdateLayerPolicy", policy["kind"])
        self.assertTrue(policy["policy"]["require_staged_rollout"])
        self.assertTrue(policy["policy"]["forbid_activation_without_health_gate"])
        self.assertTrue(callable(update_agent.plan_update))

        for path in [
            PROJECT_ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("OTA_Update_Layer", text)

        for path in [
            PROJECT_ROOT / "docs" / "history" / "CHANGELOG.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("OTA_Update_Layer", text)
            self.assertIn("ota-update-layer-core", text)


if __name__ == "__main__":
    unittest.main()

