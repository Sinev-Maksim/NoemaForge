#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_release_artifact_name_guard_qa.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-21
Modified: 2026-05-21
Purpose: QA-test release artifact name guard discoverability through registry and docs.
Inputs: Unified Registry, release artifact name guard policy and canonical docs.
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

import release_artifact_name_guard_runtime as rang
import unified_registry_runtime as urr

CLOSURE = "Closed by `release-artifact-name-guard-core`"


class ReleaseArtifactNameGuardQATests(unittest.TestCase):
    def test_pack_is_registered_with_policy_runtime_and_docs_refs(self) -> None:
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
        pack = entries.get("eval-pack:release-artifact-name-guard-core:0.32.2")
        self.assertIsNotNone(pack)
        self.assertIn("configs/release-artifact-name-guard-policy.json", pack["refs"])
        self.assertIn("contracts/release_artifact_name_guard.schema.json", pack["refs"])
        self.assertIn("src/release_artifact_name_guard_runtime.py", pack["refs"])
        self.assertIn("tests/test_release_artifact_name_guard_runtime.py", pack["refs"])
        self.assertIn("tests/test_release_artifact_name_guard_performance.py", pack["refs"])
        self.assertIn("docs/wiki/prelaunch/prelaunch-tooling.md", pack["refs"])

    def test_docs_changelog_and_policy_record_canonical_release_history_rule(self) -> None:
        policy = rang.load_policy(ROOT / "configs" / "release-artifact-name-guard-policy.json")
        report = rang.validate_release_artifact_name_guard_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(report["ok"], report["failures"][:10])
        self.assertEqual("noemaforge/docs/history/CHANGELOG.md", policy["policy"]["canonical_changelog_ref"])
        self.assertIn("RELEASE_NOTES_*", policy["policy"]["forbidden_filename_patterns"])

        for path in [
            ROOT / "docs" / "README.md",
            ROOT / "docs" / "TODO.md",
            ROOT / "docs" / "reference" / "PROJECT_CONTEXT.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "wiki" / "prelaunch" / "prelaunch-tooling.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("release-artifact-name-guard-core", text, str(path))
            self.assertIn("history/CHANGELOG.md", text, str(path))
            self.assertIn(CLOSURE, text, str(path))


if __name__ == "__main__":
    unittest.main()

