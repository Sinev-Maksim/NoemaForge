#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_edge_rules_engine_qa.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-19
Modified: 2026-05-19
Purpose: QA-test Edge Rules Engine discoverability through registry and canonical docs.
Inputs: Unified Registry, Edge Rules policy and canonical documentation files.
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

import edge_rules_engine_runtime as erer
import unified_registry_runtime as urr


class EdgeRulesEngineQATests(unittest.TestCase):
    def test_edge_rules_engine_pack_is_registered_and_attached_to_model(self) -> None:
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
        pack = entries.get("eval-pack:edge-rules-engine-core:0.32.1")
        self.assertIsNotNone(pack)
        self.assertIn("configs/edge-rules-engine-policy.json", pack["refs"])
        self.assertIn("src/edge_rules_engine_runtime.py", pack["refs"])
        self.assertIn("tests/test_edge_rules_engine_performance.py", pack["refs"])

        model = entries["model:model-registry-local:0.32.1"]
        self.assertIn("eval-pack:edge-rules-engine-core:0.32.1", model["eval_pack_refs"])

    def test_edge_rules_engine_docs_and_policy_are_discoverable(self) -> None:
        policy = erer.load_policy(ROOT / "configs" / "edge-rules-engine-policy.json")
        self.assertEqual("EdgeRulesEnginePolicy", policy["kind"])
        self.assertIn("whitebox_only", policy["policy"]["allowed_modes"])

        for path in [
            PROJECT_ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            PROJECT_ROOT / "docs" / "history" / "CHANGELOG.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("Edge_Rules_Engine", text)


if __name__ == "__main__":
    unittest.main()

