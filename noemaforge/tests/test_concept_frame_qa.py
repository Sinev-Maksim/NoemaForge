#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_concept_frame_qa.py
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-19
Modified: 2026-05-19
Purpose: QA-test Concept_Frame discoverability through registry and canonical docs.
Inputs: Unified Registry, Concept Frame policy and canonical documentation files.
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

import concept_frame_runtime as cfr
import unified_registry_runtime as urr


class ConceptFrameQATests(unittest.TestCase):
    def test_concept_frame_pack_is_registered_and_attached_to_pipeline(self) -> None:
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
        pack = entries.get("eval-pack:concept-frame-governance-core:0.32.0")
        self.assertIsNotNone(pack)
        self.assertIn("configs/concept-frame-policy.json", pack["refs"])
        self.assertIn("src/concept_frame_runtime.py", pack["refs"])
        self.assertIn("tests/test_concept_frame_performance.py", pack["refs"])

        pipeline = entries["pipeline:firstboot-model-selection:0.31.13.alpha-patched1"]
        self.assertIn("eval-pack:concept-frame-governance-core:0.32.0", pipeline["eval_pack_refs"])

    def test_concept_frame_docs_policy_and_changelog_are_discoverable(self) -> None:
        policy = cfr.load_policy(ROOT / "configs" / "concept-frame-policy.json")
        self.assertEqual("ConceptFramePolicy", policy["kind"])
        self.assertEqual({"admin", "architect"}, set(policy["policy"]["allowed_roles"]))

        report = cfr.validate_concept_frame_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(report["ok"], report["failures"])

        for path in [
            PROJECT_ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("[x] Add `Concept_Frame` schema for Admin/Architect", text)

        for path in [
            PROJECT_ROOT / "docs" / "history" / "CHANGELOG.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("Concept_Frame governance contract", text)
            self.assertIn("concept-frame-governance-core", text)


if __name__ == "__main__":
    unittest.main()

