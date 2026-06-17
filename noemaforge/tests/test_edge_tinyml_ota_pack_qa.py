#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_edge_tinyml_ota_pack_qa.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test docs coverage for aggregate Edge/TinyML/OTA pack behavior.
Inputs: Workspace TODO, roadmap, changelog, release notes and edge-tinyml-ota-pack policy.
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

import edge_tinyml_ota_pack_runtime as etop


class EdgeTinyMLOTAPackQATests(unittest.TestCase):
    def test_policy_summary_and_docs_record_completed_pack_item(self) -> None:
        policy = etop.load_policy(ROOT / "configs" / "edge-tinyml-ota-pack-policy.json")
        report = etop.validate_edge_tinyml_ota_pack_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual("edge-tinyml-ota-pack-core", policy["id"])

        item = "Edge/TinyML/OTA pack: MQTT/serial, TinyML validation, gateway inference, rules, manifest signing and OTA rollback."
        _existing_docs = [p for p in [
            PROJECT_ROOT / "TODO.md",
            ROOT / "TODO.md",
            PROJECT_ROOT / "docs" / "TODO.md",
            ROOT / "docs" / "TODO.md",
            PROJECT_ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
        ] if p.exists()]
        assert _existing_docs, "no candidate documentation file exists"
        for path in _existing_docs:
            text = path.read_text(encoding="utf-8")
            self.assertIn(f"[x] {item}", text, str(path))
            self.assertIn("edge-tinyml-ota-pack-core", text, str(path))
            self.assertIn("offline aggregate contract", text, str(path))

    def test_changelog_release_notes_capture_edge_pack_contract(self) -> None:
        _existing_docs = [p for p in [
            PROJECT_ROOT / "CHANGELOG.md",
            PROJECT_ROOT / "RELEASE_NOTES.md",
            PROJECT_ROOT / "docs" / "history" / "CHANGELOG.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ] if p.exists()]
        assert _existing_docs, "no candidate documentation file exists"
        for path in _existing_docs:
            text = path.read_text(encoding="utf-8")
            self.assertIn("edge-tinyml-ota-pack-core", text, str(path))
            self.assertIn("Edge/TinyML/OTA pack: MQTT/serial, TinyML validation, gateway inference, rules, manifest signing and OTA rollback", text, str(path))
            self.assertIn("offline aggregate contract", text, str(path))


if __name__ == "__main__":
    unittest.main()
