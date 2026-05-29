#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_edge_tinyml_ota_pack_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate aggregate Edge/TinyML/OTA pack invariants.
Inputs: Workspace edge-tinyml-ota-pack policy and component policies.
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

import edge_tinyml_ota_pack_runtime as etop


class EdgeTinyMLOTAPackRuntimeTests(unittest.TestCase):
    def test_workspace_edge_tinyml_ota_pack_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "edge-tinyml-ota-pack-policy.json"
        report = etop.validate_edge_tinyml_ota_pack_policy(
            etop.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual("edge-tinyml-ota-pack-core", report["id"])
        self.assertEqual(6, report["metrics"]["components"])
        self.assertEqual(6, report["metrics"]["valid_components"])
        self.assertGreaterEqual(report["metrics"]["capabilities"], 20)

    def test_required_components_cover_full_pack_surface(self) -> None:
        policy = etop.load_policy(ROOT / "configs" / "edge-tinyml-ota-pack-policy.json")
        components = {item["id"]: item for item in policy["policy"]["required_components"]}

        self.assertEqual(
            {
                "sense-layer-edge-core",
                "tinyml-node-core",
                "gateway-inference-service-core",
                "edge-rules-engine-core",
                "ota-update-layer-core",
                "edge-reference-targets-core",
            },
            set(components),
        )
        self.assertIn("mqtt", components["sense-layer-edge-core"]["capabilities"])
        self.assertIn("serial", components["sense-layer-edge-core"]["capabilities"])
        self.assertIn("golden_vectors", components["tinyml-node-core"]["capabilities"])
        self.assertIn("manifest_only_model_loading", components["gateway-inference-service-core"]["capabilities"])
        self.assertIn("rollback_bundle", components["ota-update-layer-core"]["capabilities"])

    def test_component_validator_failure_is_reported(self) -> None:
        policy = etop.load_policy(ROOT / "configs" / "edge-tinyml-ota-pack-policy.json")
        broken = dict(policy)
        broken["policy"] = dict(policy["policy"])
        components = [dict(item) for item in policy["policy"]["required_components"]]
        components[0]["config"] = "noemaforge/configs/missing-sense-layer-edge.json"
        broken["policy"]["required_components"] = components

        report = etop.validate_edge_tinyml_ota_pack_policy(
            broken,
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            include_docs=False,
        )

        self.assertFalse(report["ok"])
        self.assertIn("component_config_missing:sense-layer-edge-core:noemaforge/configs/missing-sense-layer-edge.json", report["failures"])


if __name__ == "__main__":
    unittest.main()
