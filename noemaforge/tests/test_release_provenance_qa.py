#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_release_provenance_qa.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-21
Purpose: QA-test release provenance discoverability through registry and docs.
Inputs: Unified Registry, release provenance policy and canonical documentation files.
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

import release_provenance_runtime as rpr
import unified_registry_runtime as urr


class ReleaseProvenanceQATests(unittest.TestCase):
    def test_release_provenance_pack_is_registered_and_attached_to_pipeline(self) -> None:
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
        pack = entries.get("eval-pack:release-provenance-core:0.32.2")
        self.assertIsNotNone(pack)
        self.assertIn("configs/release-provenance-policy.json", pack["refs"])
        self.assertIn("contracts/release_provenance.schema.json", pack["refs"])
        self.assertIn("src/release_provenance_runtime.py", pack["refs"])
        self.assertIn("tests/test_release_provenance_performance.py", pack["refs"])

        pipeline = entries["pipeline:firstboot-model-selection:0.32.2"]
        self.assertIn("eval-pack:release-provenance-core:0.32.2", pipeline["eval_pack_refs"])
        self.assertIn("configs/release-provenance-policy.json", pipeline["refs"])
        self.assertIn("src/release_provenance_runtime.py", pipeline["refs"])

    def test_release_provenance_docs_policy_and_changelog_are_discoverable(self) -> None:
        policy = rpr.load_policy(ROOT / "configs" / "release-provenance-policy.json")
        self.assertEqual("ReleaseProvenancePolicy", policy["kind"])
        self.assertEqual("signed_release_provenance", policy["policy"]["activation_state"])
        self.assertIn("install_transcript", policy["policy"]["required_materials"])
        self.assertTrue(policy["policy"]["signing_controls"]["signature_required"])

        report = rpr.validate_release_provenance_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(report["ok"], report["failures"])

        for path in [
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "TODO.md",
            ROOT / "docs" / "onboarding" / "PUBLIC_MVP_CHECKLIST_0.30.0.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("[x] Signed release provenance.", text)
            self.assertIn("release-provenance-core", text)

        for path in [
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("release-provenance-core", text)
            self.assertIn("detached signatures", text)


if __name__ == "__main__":
    unittest.main()

