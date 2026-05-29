#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_typed_governance_track_qa.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test Typed Governance Track discoverability through registry and canonical docs.
Inputs: Unified Registry, Typed Governance Track policy and canonical documentation files.
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

import typed_governance_track_runtime as tgtr
import unified_registry_runtime as urr


class TypedGovernanceTrackQATests(unittest.TestCase):
    def test_typed_governance_track_pack_is_registered_and_attached_to_pipeline(self) -> None:
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
        pack = entries.get("eval-pack:typed-governance-track-core:0.32.2")
        self.assertIsNotNone(pack)
        self.assertIn("configs/typed-governance-track.json", pack["refs"])
        self.assertIn("src/typed_governance_track_runtime.py", pack["refs"])
        self.assertIn("tests/test_typed_governance_track_performance.py", pack["refs"])

        pipeline = entries["pipeline:firstboot-model-selection:0.32.2"]
        self.assertIn("eval-pack:typed-governance-track-core:0.32.2", pipeline["eval_pack_refs"])
        self.assertIn("configs/typed-governance-track.json", pipeline["refs"])
        self.assertIn("src/typed_governance_track_runtime.py", pipeline["refs"])

    def test_typed_governance_track_docs_policy_and_changelog_are_discoverable(self) -> None:
        policy = tgtr.load_policy(ROOT / "configs" / "typed-governance-track.json")
        self.assertEqual("TypedGovernanceTrackPolicy", policy["kind"])
        self.assertTrue(policy["policy"]["require_dependency_order"])
        self.assertTrue(policy["policy"]["require_registry_attachment"])
        self.assertEqual("pipeline_rfc", policy["policy"]["required_stage_order"][-1])

        report = tgtr.validate_typed_governance_track_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(report["ok"], report["failures"])

        for path in [
            PROJECT_ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            PROJECT_ROOT / "TODO.md",
            ROOT / "TODO.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("[x] Track typed governance contracts", text)
            self.assertIn("Typed Governance Track", text)

        for path in [
            PROJECT_ROOT / "docs" / "history" / "CHANGELOG.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("typed-governance-track-core", text)
            self.assertIn("dependency-order and registry-attachment checks", text)


if __name__ == "__main__":
    unittest.main()

