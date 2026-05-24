#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_signed_model_manifest_qa.py
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-19
Modified: 2026-05-19
Purpose: QA-test signed model manifest discoverability through registry and canonical docs.
Inputs: Unified Registry, signed manifest policy and canonical documentation files.
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

import signed_model_manifest_runtime as smmr
import unified_registry_runtime as urr


class SignedModelManifestQATests(unittest.TestCase):
    def test_signed_manifest_pack_is_registered_and_model_attached(self) -> None:
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
        pack = entries.get("eval-pack:signed-model-manifest-core:0.32.0")
        self.assertIsNotNone(pack)
        self.assertIn("configs/signed-model-manifest-policy.json", pack["refs"])
        self.assertIn("contracts/signed_model_manifest.schema.json", pack["refs"])
        self.assertIn("src/signed_model_manifest_runtime.py", pack["refs"])
        self.assertIn("tests/test_signed_model_manifest_performance.py", pack["refs"])

        model = entries["model:model-registry-local:0.31.13.alpha-patched1"]
        self.assertIn("eval-pack:signed-model-manifest-core:0.32.0", model["eval_pack_refs"])

    def test_signed_manifest_docs_and_policy_are_discoverable(self) -> None:
        policy = smmr.load_policy(ROOT / "configs" / "signed-model-manifest-policy.json")
        self.assertEqual("SignedModelManifestPolicy", policy["kind"])
        self.assertEqual("prelaunch/manifests/models/example_edge_model.manifest.json", policy["manifest_refs"][0]["ref"])

        for path in [
            PROJECT_ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            PROJECT_ROOT / "docs" / "history" / "CHANGELOG.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("Model_Manifest_And_Signing", text)


if __name__ == "__main__":
    unittest.main()

