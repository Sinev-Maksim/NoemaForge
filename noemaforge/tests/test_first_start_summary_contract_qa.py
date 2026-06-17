#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_first_start_summary_contract_qa.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test First Start Summary discoverability through registry and canonical docs.
Inputs: Unified Registry, first-start summary policy and canonical documentation files.
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

import first_start_summary_contract_runtime as fsscr
import unified_registry_runtime as urr


class FirstStartSummaryContractQATests(unittest.TestCase):
    def test_first_start_summary_pack_is_registered_and_attached_to_pipeline(self) -> None:
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
        pack = entries.get("eval-pack:first-start-summary-output-core:0.32.1")
        self.assertIsNotNone(pack)
        self.assertIn("configs/first-start-summary-policy.json", pack["refs"])
        self.assertIn("src/first_start_summary.py", pack["refs"])
        self.assertIn("src/first_start_summary_contract_runtime.py", pack["refs"])
        self.assertIn("tests/test_first_start_summary_contract_performance.py", pack["refs"])

        pipeline = entries["pipeline:firstboot-model-selection:0.32.1"]
        self.assertIn("eval-pack:first-start-summary-output-core:0.32.1", pipeline["eval_pack_refs"])
        self.assertIn("configs/first-start-summary-policy.json", pipeline["refs"])
        self.assertIn("src/first_start_summary.py", pipeline["refs"])

    def test_first_start_summary_docs_policy_and_changelog_are_discoverable(self) -> None:
        policy = fsscr.load_policy(ROOT / "configs" / "first-start-summary-policy.json")
        self.assertEqual("FirstStartSummaryPolicy", policy["kind"])
        self.assertEqual("grouped_run_summary", policy["policy"]["activation_state"])
        self.assertIn("PASS", policy["policy"]["required_markers"])
        self.assertIn("WARN", policy["policy"]["required_markers"])
        self.assertIn("FAIL", policy["policy"]["required_markers"])

        report = fsscr.validate_first_start_summary_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(report["ok"], report["failures"])

        for path in [p for p in [
            PROJECT_ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            PROJECT_ROOT / "TODO.md",
            ROOT / "TODO.md",
        ] if p.exists()]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("[x] Verify first-start summary output is grouped by run", text)
            self.assertIn("First Start Summary", text)

        for path in [p for p in [
            PROJECT_ROOT / "docs" / "history" / "CHANGELOG.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ] if p.exists()]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("first-start-summary-output-core", text)
            self.assertIn("PASS/WARN/FAIL", text)


if __name__ == "__main__":
    unittest.main()

