#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_package_dry_run_validation_qa.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test package dry-run validation discoverability through registry and docs.
Inputs: Unified Registry, package dry-run policy and canonical documentation files.
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

import package_dry_run_validation_runtime as pdvr
import unified_registry_runtime as urr


class PackageDryRunValidationQATests(unittest.TestCase):
    def test_package_dry_run_pack_is_registered_and_attached_to_pipeline(self) -> None:
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
        pack = entries.get("eval-pack:package-dry-run-validation-core:0.32.1")
        self.assertIsNotNone(pack)
        self.assertIn("configs/package-dry-run-validation-policy.json", pack["refs"])
        self.assertIn("contracts/package_dry_run_validation.schema.json", pack["refs"])
        self.assertIn("src/package_dry_run_validation_runtime.py", pack["refs"])
        self.assertIn("tests/test_package_dry_run_validation_performance.py", pack["refs"])

        pipeline = entries["pipeline:firstboot-model-selection:0.32.1"]
        self.assertIn("eval-pack:package-dry-run-validation-core:0.32.1", pipeline["eval_pack_refs"])
        self.assertIn("configs/package-dry-run-validation-policy.json", pipeline["refs"])
        self.assertIn("src/package_dry_run_validation_runtime.py", pipeline["refs"])

    def test_package_dry_run_docs_policy_and_changelog_are_discoverable(self) -> None:
        policy = pdvr.load_policy(ROOT / "configs" / "package-dry-run-validation-policy.json")
        self.assertEqual("PackageDryRunValidationPolicy", policy["kind"])
        self.assertEqual("install_uninstall_dry_run_tests", policy["policy"]["activation_state"])
        self.assertIn("--dry-run", policy["policy"]["required_setup_flags"])
        self.assertIn("--dry-run", policy["policy"]["required_uninstall_flags"])

        report = pdvr.validate_package_dry_run_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(report["ok"], report["failures"])

        for path in [
            PROJECT_ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            PROJECT_ROOT / "TODO.md",
            ROOT / "TODO.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("[x] Add install/uninstall dry-run tests to package validation.", text)
            self.assertIn("package-dry-run-validation-core", text)

        for path in [
            PROJECT_ROOT / "docs" / "history" / "CHANGELOG.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("package-dry-run-validation-core", text)
            self.assertIn("install/uninstall dry-run", text)


if __name__ == "__main__":
    unittest.main()

