#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_manifest_checksum_exclusion_qa.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-21
Modified: 2026-05-21
Purpose: QA-test manifest/checksum exclusion discoverability through registry and docs.
Inputs: Unified Registry, manifest checksum exclusion policy and canonical docs.
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

import manifest_checksum_exclusion_runtime as mcer
import unified_registry_runtime as urr

CLOSURE = "Closed by `manifest-checksum-exclusion-core`"


class ManifestChecksumExclusionQATests(unittest.TestCase):
    def test_pack_is_registered_with_manifest_and_docs_refs(self) -> None:
        registry_path = ROOT / "configs" / "unified-registry.json"
        report = urr.validate_unified_registry(
            urr.load_registry(registry_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            registry_path=registry_path,
        )
        manifest_failures = [
            item for item in report["failures"]
            if ":manifest-checksum-exclusion-core:" in item
        ]
        self.assertFalse(manifest_failures)

        entries = {
            f"{entry['kind']}:{entry['id']}:{entry['version']}": entry
            for entry in report["normalized_registry"]["entries"]
        }
        pack = entries.get("eval-pack:manifest-checksum-exclusion-core:0.32.1")
        self.assertIsNotNone(pack)
        self.assertIn("configs/manifest-checksum-exclusion-policy.json", pack["refs"])
        self.assertIn("contracts/manifest_checksum_exclusion.schema.json", pack["refs"])
        self.assertIn("src/manifest_checksum_exclusion_runtime.py", pack["refs"])
        self.assertIn("tests/test_manifest_checksum_exclusion_runtime.py", pack["refs"])
        self.assertIn("tests/test_manifest_checksum_exclusion_performance.py", pack["refs"])
        self.assertIn("docs/wiki/prelaunch/prelaunch-tooling.md", pack["refs"])

    def test_docs_changelog_and_policy_record_exclusion_rule(self) -> None:
        policy = mcer.load_policy(ROOT / "configs" / "manifest-checksum-exclusion-policy.json")
        report = mcer.validate_manifest_checksum_exclusion_policy(
            policy,
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            hash_source="git-index",
        )
        self.assertTrue(report["ok"], report["failures"][:10])
        self.assertIn("trash", policy["policy"]["excluded_dir_names"])
        self.assertIn("__pycache__", policy["policy"]["excluded_dir_names"])

        for path in [
            ROOT / "docs" / "README.md",
            ROOT / "docs" / "TODO.md",
            ROOT / "docs" / "reference" / "PROJECT_CONTEXT.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "wiki" / "prelaunch" / "prelaunch-tooling.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("manifest-checksum-exclusion-core", text, str(path))
            self.assertIn("trash", text, str(path))
            self.assertIn(CLOSURE, text, str(path))


if __name__ == "__main__":
    unittest.main()

