#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_sense_layer_edge_qa.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-19
Modified: 2026-05-19
Purpose: QA-test Sense Layer Edge discoverability through registry and canonical docs.
Inputs: Unified Registry, Sense Layer Edge policy and canonical documentation files.
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
sys.path.insert(0, str(PROJECT_ROOT))

import sense_layer_edge_runtime as sler
import unified_registry_runtime as urr
from sense.edge import metrics_schema


class SenseLayerEdgeQATests(unittest.TestCase):
    def test_sense_layer_edge_pack_is_registered_and_attached_to_pipeline(self) -> None:
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
        pack = entries.get("eval-pack:sense-layer-edge-core:0.32.2")
        self.assertIsNotNone(pack)
        self.assertIn("configs/sense-layer-edge.json", pack["refs"])
        self.assertIn("src/sense_layer_edge_runtime.py", pack["refs"])
        self.assertIn("sense/edge/mqtt_adapter.py", pack["refs"])
        self.assertIn("tests/test_sense_layer_edge_performance.py", pack["refs"])

        pipeline = entries["pipeline:firstboot-model-selection:0.32.2"]
        self.assertIn("eval-pack:sense-layer-edge-core:0.32.2", pipeline["eval_pack_refs"])

    def test_sense_layer_edge_docs_policy_and_schema_are_discoverable(self) -> None:
        policy = sler.load_policy(ROOT / "configs" / "sense-layer-edge.json")
        self.assertEqual("SenseLayerEdgePolicy", policy["kind"])
        self.assertTrue(policy["policy"]["require_explicit_source_trust"])
        self.assertEqual({"trusted", "simulated", "unverified"}, metrics_schema.TRUST_LEVELS)

        for path in [
            PROJECT_ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("Sense_Layer.Edge", text)

        for path in [
            PROJECT_ROOT / "docs" / "history" / "CHANGELOG.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("Sense_Layer.Edge", text)
            self.assertIn("sense-layer-edge-core", text)


if __name__ == "__main__":
    unittest.main()

