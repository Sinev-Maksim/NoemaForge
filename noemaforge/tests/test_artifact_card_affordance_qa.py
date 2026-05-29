#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_artifact_card_affordance_qa.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test artifact-card affordance registration and documentation coverage.
Inputs: Unified Registry, artifact-card affordance policy and canonical documentation.
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

import artifact_card_affordance_runtime as acar
import unified_registry_runtime as urr


class ArtifactCardAffordanceQATests(unittest.TestCase):
    def test_artifact_card_pack_is_registered(self) -> None:
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
        pack = entries.get("eval-pack:artifact-card-affordance-core:0.32.2")
        self.assertIsNotNone(pack)
        self.assertIn("configs/artifact-card-affordance-policy.json", pack["refs"])
        self.assertIn("src/artifact_card_affordance_runtime.py", pack["refs"])
        self.assertIn("templates/pipeline-dashboard/artifact-affordances.css", pack["refs"])
        pipeline = entries["pipeline:firstboot-model-selection:0.32.2"]
        self.assertIn("eval-pack:artifact-card-affordance-core:0.32.2", pipeline["eval_pack_refs"])
        self.assertIn("configs/artifact-card-affordance-policy.json", pipeline["refs"])

    def test_docs_and_examples_name_artifact_card_affordance_contract(self) -> None:
        policy = acar.load_policy(ROOT / "configs" / "artifact-card-affordance-policy.json")
        report = acar.validate_artifact_card_affordance_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(report["ok"], report["failures"])

        for path in [
            ROOT / "docs" / "README.md",
            ROOT / "docs" / "TODO.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "reference" / "PROJECT_CONTEXT.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("artifact-card-affordance-core", text)
            self.assertIn("artifact", text.lower())
            self.assertIn("download", text.lower())


if __name__ == "__main__":
    unittest.main()

