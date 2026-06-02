#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_manifest_checksum_exclusion_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-21
Modified: 2026-05-21
Purpose: Validate manifest/checksum exclusion policy and scanner behavior.
Inputs: Manifest checksum exclusion policy and synthetic path fixtures.
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
import production_ai_contracts as pac


class ManifestChecksumExclusionRuntimeTests(unittest.TestCase):
    def test_workspace_manifests_and_checksums_validate(self) -> None:
        policy = mcer.load_policy(ROOT / "configs" / "manifest-checksum-exclusion-policy.json")
        report = mcer.validate_manifest_checksum_exclusion_policy(
            policy,
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            hash_source="git-index",
        )

        self.assertTrue(report["ok"], report["failures"][:10])
        self.assertEqual(0, report["metrics"]["excluded_path_hits"])
        self.assertEqual(0, report["metrics"]["hash_mismatches"])
        self.assertGreater(report["metrics"]["project_active_files"], report["metrics"]["package_active_files"])

        gate = pac.evaluate_gate(
            {
                "change_id": "manifest-checksum-exclusion-core",
                "domain": "pipeline",
                "required_checks": ["manifest_checksum_exclusion", "rollback_plan"],
            },
            {
                "artifact_uri": "reports/manifest-checksum-exclusion.json",
                "run_at": "2026-05-21T00:00:00Z",
                "checks": [
                    {"id": "manifest_checksum_exclusion", "status": "passed" if report["ok"] else "failed"},
                    {"id": "rollback_plan", "status": "passed"},
                ],
            },
        )
        self.assertTrue(gate["ok"], gate)

    def test_excluded_parts_detect_trash_and_cache_paths(self) -> None:
        excluded = {"trash", "__pycache__", ".pytest_cache"}

        self.assertTrue(mcer._has_excluded_part("trash/run/file.json", excluded))
        self.assertTrue(mcer._has_excluded_part("noemaforge/src/__pycache__/x.pyc", excluded))
        self.assertFalse(mcer._has_excluded_part("noemaforge/src/runtime.py", excluded))


if __name__ == "__main__":
    unittest.main()
