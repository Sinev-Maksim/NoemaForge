#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_pytest_suite_partition_qa.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test pytest suite partition contract discoverability through registry and docs.
Inputs: Unified Registry, pytest suite partition policy and canonical documentation files.
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

import pytest_suite_partition_runtime as pspr
import unified_registry_runtime as urr

CLOSURE = "Closed by `pytest-suite-partition-core`"
TODO_ITEM = "Investigate full monolithic pytest hang around pipeline runtime suite in this container; targeted tests pass."


class PytestSuitePartitionQATests(unittest.TestCase):
    def test_partition_pack_is_registered_and_attached_to_firstboot_pipeline(self) -> None:
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
        pack = entries.get("eval-pack:pytest-suite-partition-core:0.32.1")
        self.assertIsNotNone(pack)
        self.assertIn("configs/pytest-suite-partition-policy.json", pack["refs"])
        self.assertIn("contracts/pytest_suite_partition.schema.json", pack["refs"])
        self.assertIn("src/pytest_suite_partition_runtime.py", pack["refs"])
        self.assertIn("tests/test_pytest_suite_partition_runtime.py", pack["refs"])
        self.assertIn("tests/test_pytest_suite_partition_performance.py", pack["refs"])
        self.assertIn("docs/TODO.md", pack["refs"])
        self.assertIn("docs/backlog/ROADMAP_AND_TODO.md", pack["refs"])

        pipeline = entries["pipeline:firstboot-model-selection:0.32.1"]
        self.assertIn("eval-pack:pytest-suite-partition-core:0.32.1", pipeline["eval_pack_refs"])
        self.assertIn("configs/pytest-suite-partition-policy.json", pipeline["refs"])
        self.assertIn("src/pytest_suite_partition_runtime.py", pipeline["refs"])

    def test_policy_docs_and_changelog_record_closed_pytest_hang_item(self) -> None:
        policy = pspr.load_policy(ROOT / "configs" / "pytest-suite-partition-policy.json")
        report = pspr.validate_pytest_suite_partition_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(report["ok"], report["failures"])

        todo_text = (ROOT / "docs" / "TODO.md").read_text(encoding="utf-8")
        self.assertIn("pytest-suite-partition-core", todo_text)
        self.assertIn("monolithic pytest", todo_text)
        self.assertIn(CLOSURE, todo_text)

        backlog = (ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md").read_text(encoding="utf-8")
        self.assertEqual(0, backlog.count(f"- [ ] {TODO_ITEM}"))
        self.assertGreaterEqual(backlog.count(f"- [x] {TODO_ITEM}"), 2)
        self.assertIn(CLOSURE, backlog)

        for path in [
            ROOT / "docs" / "README.md",
            ROOT / "docs" / "reference" / "PROJECT_CONTEXT.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("pytest-suite-partition-core", text, str(path))
            self.assertIn("monolithic pytest", text, str(path))
            self.assertIn(CLOSURE, text, str(path))


if __name__ == "__main__":
    unittest.main()

