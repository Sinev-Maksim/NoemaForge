#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_media_capture_privacy_qa.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test media capture privacy registration and documentation coverage.
Inputs: Unified Registry, media capture privacy policy and canonical documentation.
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

import media_capture_privacy_runtime as mcpr
import unified_registry_runtime as urr


class MediaCapturePrivacyQATests(unittest.TestCase):
    def test_media_capture_privacy_pack_is_registered(self) -> None:
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
        pack = entries.get("eval-pack:media-capture-privacy-core:0.32.2")
        self.assertIsNotNone(pack)
        self.assertIn("configs/media-capture-privacy-policy.json", pack["refs"])
        self.assertIn("contracts/media_capture_privacy.schema.json", pack["refs"])
        self.assertIn("src/media_capture_privacy_runtime.py", pack["refs"])
        self.assertIn("tests/test_media_capture_privacy_performance.py", pack["refs"])
        pipeline = entries["pipeline:firstboot-model-selection:0.32.2"]
        self.assertIn("eval-pack:media-capture-privacy-core:0.32.2", pipeline["eval_pack_refs"])
        self.assertIn("configs/media-capture-privacy-policy.json", pipeline["refs"])

    def test_docs_and_examples_name_the_privacy_boundary(self) -> None:
        policy = mcpr.load_policy(ROOT / "configs" / "media-capture-privacy-policy.json")
        report = mcpr.validate_media_capture_privacy_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(report["ok"], report["failures"])

        for path in [
            ROOT / "docs" / "README.md",
            ROOT / "docs" / "TODO.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "reference" / "PROJECT_CONTEXT.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("media-capture-privacy-core", text)
            self.assertIn("camera", text.lower())
            self.assertIn("microphone", text.lower())


if __name__ == "__main__":
    unittest.main()

