#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_yaml_inventory_readability_qa.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-21
Modified: 2026-05-21
Purpose: QA-test YAML inventory readability discoverability through registry and docs.
Inputs: Unified Registry, YAML inventory readability policy and canonical docs.
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

import unified_registry_runtime as urr
import yaml_inventory_readability_runtime as yirr

CLOSURE = "Closed by `yaml-inventory-readability-core`"


class YamlInventoryReadabilityQATests(unittest.TestCase):
    def test_pack_is_registered_with_docs_and_runtime_refs(self) -> None:
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
        pack = entries.get("eval-pack:yaml-inventory-readability-core:0.32.1")
        self.assertIsNotNone(pack)
        self.assertIn("configs/yaml-inventory-readability-policy.json", pack["refs"])
        self.assertIn("contracts/yaml_inventory_readability.schema.json", pack["refs"])
        self.assertIn("src/yaml_inventory_readability_runtime.py", pack["refs"])
        self.assertIn("tests/test_yaml_inventory_readability_runtime.py", pack["refs"])
        self.assertIn("tests/test_yaml_inventory_readability_performance.py", pack["refs"])
        self.assertIn("docs/wiki/prelaunch/prelaunch-tooling.md", pack["refs"])

    def test_docs_changelog_and_runtime_describe_scope(self) -> None:
        policy = yirr.load_policy(ROOT / "configs" / "yaml-inventory-readability-policy.json")
        report = yirr.validate_yaml_inventory_readability_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(report["ok"], report["failures"])

        runtime_text = (ROOT / "src" / "yaml_inventory_readability_runtime.py").read_text(encoding="utf-8")
        self.assertNotIn("import yaml", runtime_text)
        self.assertIn("not a full YAML semantic parser", runtime_text)

        for path in [
            ROOT / "docs" / "README.md",
            ROOT / "docs" / "TODO.md",
            ROOT / "docs" / "reference" / "PROJECT_CONTEXT.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "wiki" / "prelaunch" / "prelaunch-tooling.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("yaml-inventory-readability-core", text, str(path))
            self.assertIn("YAML", text, str(path))
            self.assertIn(CLOSURE, text, str(path))


if __name__ == "__main__":
    unittest.main()

