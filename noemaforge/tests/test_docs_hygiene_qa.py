#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_docs_hygiene_qa.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-19
Modified: 2026-05-21
Purpose: QA-test docs hygiene and active-file readability discoverability through registry and documentation indexes.
Inputs: Workspace docs hygiene policy, Unified Registry and docs README files.
Outputs: unittest assertions only.
Side effects: None.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import docs_hygiene_runtime as dhr
import unified_registry_runtime as urr


class DocsHygieneQATests(unittest.TestCase):
    def test_docs_hygiene_pack_is_discoverable_and_registered(self) -> None:
        policy_path = ROOT / "configs" / "docs-hygiene-policy.json"
        registry_path = ROOT / "configs" / "unified-registry.json"
        registry = urr.load_registry(registry_path)
        report = urr.validate_unified_registry(
            registry,
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            registry_path=registry_path,
        )
        self.assertTrue(report["ok"], report["failures"])

        entries = {
            f"{entry['kind']}:{entry['id']}:{entry['version']}": entry
            for entry in report["normalized_registry"]["entries"]
        }
        pack = entries.get("eval-pack:docs-hygiene-prelaunch:0.32.1")
        self.assertIsNotNone(pack)
        self.assertIn("configs/docs-hygiene-policy.json", pack["refs"])
        self.assertIn("contracts/docs_hygiene_policy.schema.json", pack["refs"])
        self.assertIn("src/docs_hygiene_runtime.py", pack["refs"])

        policy = dhr.load_policy(policy_path)
        self.assertEqual("DocsHygienePolicy", policy["kind"])
        self.assertIn("noemaforge/src/docs_hygiene_runtime.py", policy["refs"])

    def test_docs_index_names_the_executable_hygiene_gate(self) -> None:
        expected = "noemaforge/src/docs_hygiene_runtime.py"
        text = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")
        self.assertIn("docs-hygiene-policy.json", text)
        self.assertIn(expected, text)
        self.assertIn("active-file readability", text)


if __name__ == "__main__":
    unittest.main()

