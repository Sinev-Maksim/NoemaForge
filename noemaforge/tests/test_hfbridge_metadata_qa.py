#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_hfbridge_metadata_qa.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test HFBridge discoverability through registry and canonical docs.
Inputs: Unified Registry, HFBridge policy and canonical documentation files.
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

import hfbridge_metadata_runtime as hmr
import unified_registry_runtime as urr


class HFBridgeMetadataQATests(unittest.TestCase):
    def test_hfbridge_pack_is_registered_and_attached_to_pipeline(self) -> None:
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
        pack = entries.get("eval-pack:hfbridge-metadata-core:0.32.1")
        self.assertIsNotNone(pack)
        self.assertIn("configs/hfbridge-metadata-policy.json", pack["refs"])
        self.assertIn("src/hfbridge_metadata_runtime.py", pack["refs"])
        self.assertIn("tests/test_hfbridge_metadata_performance.py", pack["refs"])

        pipeline = entries["pipeline:firstboot-model-selection:0.32.1"]
        self.assertIn("eval-pack:hfbridge-metadata-core:0.32.1", pipeline["eval_pack_refs"])
        self.assertIn("configs/hfbridge-metadata-policy.json", pipeline["refs"])
        self.assertIn("src/hfbridge_metadata_runtime.py", pipeline["refs"])

    def test_hfbridge_docs_policy_and_changelog_are_discoverable(self) -> None:
        policy = hmr.load_policy(ROOT / "configs" / "hfbridge-metadata-policy.json")
        self.assertEqual("HFBridgeMetadataPolicy", policy["kind"])
        self.assertEqual("metadata_first_read_mostly", policy["policy"]["activation_state"])
        self.assertIn("weight_download", policy["policy"]["blocked_operations"])

        report = hmr.validate_hfbridge_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(report["ok"], report["failures"])

        _existing_docs = [p for p in [
            PROJECT_ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            PROJECT_ROOT / "TODO.md",
            ROOT / "TODO.md",
        ] if p.exists()]
        assert _existing_docs, "no candidate documentation file exists"
        for path in _existing_docs:
            text = path.read_text(encoding="utf-8")
            self.assertIn("[x] Keep HFBridge metadata-first/read-mostly", text)
            self.assertIn("HFBridge Metadata", text)
            self.assertIn("metadata-first", text)

        _existing_docs = [p for p in [
            PROJECT_ROOT / "docs" / "history" / "CHANGELOG.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ] if p.exists()]
        assert _existing_docs, "no candidate documentation file exists"
        for path in _existing_docs:
            text = path.read_text(encoding="utf-8")
            self.assertIn("hfbridge-metadata-core", text)
            self.assertIn("read-mostly", text)


if __name__ == "__main__":
    unittest.main()

