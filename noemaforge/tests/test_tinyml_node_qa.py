#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_tinyml_node_qa.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-19
Modified: 2026-05-19
Purpose: QA-test TinyML Node discoverability through registry and canonical docs.
Inputs: Unified Registry, TinyML Node policy and canonical documentation files.
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

import tinyml_node_runtime as tnr
import unified_registry_runtime as urr


class TinyMLNodeQATests(unittest.TestCase):
    def test_tinyml_node_pack_is_registered_and_attached_to_model(self) -> None:
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
        pack = entries.get("eval-pack:tinyml-node-core:0.32.1")
        self.assertIsNotNone(pack)
        self.assertIn("configs/tinyml-node-policy.json", pack["refs"])
        self.assertIn("src/tinyml_node_runtime.py", pack["refs"])
        self.assertIn("tests/test_tinyml_node_performance.py", pack["refs"])
        self.assertIn("prelaunch/tinyml/golden_vectors/example_edge_model_vectors.jsonl", pack["refs"])

        model = entries["model:model-registry-local:0.32.1"]
        self.assertIn("eval-pack:tinyml-node-core:0.32.1", model["eval_pack_refs"])

    def test_tinyml_node_docs_and_policy_are_discoverable(self) -> None:
        policy = tnr.load_policy(ROOT / "configs" / "tinyml-node-policy.json")
        self.assertEqual("TinyMLNodePolicy", policy["kind"])
        self.assertTrue(policy["policy"]["require_golden_vectors"])
        self.assertTrue(policy["policy"]["forbid_direct_control_decisions"])

        for path in [
            PROJECT_ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("TinyML_Node", text)

        for path in [
            PROJECT_ROOT / "docs" / "history" / "CHANGELOG.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("TinyML_Node", text)
            self.assertIn("tinyml-node-core", text)


if __name__ == "__main__":
    unittest.main()

