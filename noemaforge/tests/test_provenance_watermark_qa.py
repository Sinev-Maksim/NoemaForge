#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_provenance_watermark_qa.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test provenance/watermark discoverability through registry and canonical docs.
Inputs: Unified Registry, provenance/watermark policy and canonical documentation files.
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

import provenance_watermark_runtime as pwr
import unified_registry_runtime as urr


class ProvenanceWatermarkQATests(unittest.TestCase):
    def test_provenance_watermark_pack_is_registered_and_attached_to_pipeline(self) -> None:
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
        pack = entries.get("eval-pack:provenance-watermark-verdict-core:0.32.2")
        self.assertIsNotNone(pack)
        self.assertIn("configs/provenance-watermark-policy.json", pack["refs"])
        self.assertIn("src/provenance_watermark_runtime.py", pack["refs"])
        self.assertIn("tests/test_provenance_watermark_performance.py", pack["refs"])

        pipeline = entries["pipeline:firstboot-model-selection:0.32.2"]
        self.assertIn("eval-pack:provenance-watermark-verdict-core:0.32.2", pipeline["eval_pack_refs"])

    def test_provenance_watermark_docs_policy_and_changelog_are_discoverable(self) -> None:
        policy = pwr.load_policy(ROOT / "configs" / "provenance-watermark-policy.json")
        self.assertEqual("ProvenanceWatermarkPolicy", policy["kind"])
        self.assertEqual({"manifest", "signature", "watermark", "content_hash"}, set(policy["policy"]["hook_types"]))
        self.assertTrue(policy["policy"]["require_aggregated_detection_verdict"])

        report = pwr.validate_provenance_watermark_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(report["ok"], report["failures"])

        for path in [
            PROJECT_ROOT / "docs" / "ROADMAP.md",
            PROJECT_ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("[x] Add provenance/watermark hooks and aggregated Detection_Verdict", text)

        for path in [
            PROJECT_ROOT / "docs" / "history" / "CHANGELOG.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("provenance-watermark-verdict-core", text)
            self.assertIn("aggregated Detection_Verdict", text)


if __name__ == "__main__":
    unittest.main()

