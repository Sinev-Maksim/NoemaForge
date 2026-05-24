#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_gateway_inference_service_qa.py
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-19
Modified: 2026-05-19
Purpose: QA-test Gateway Inference Service discoverability through registry and canonical docs.
Inputs: Unified Registry, gateway inference policy and canonical documentation files.
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

import gateway_inference_service_runtime as gisr
import unified_registry_runtime as urr
from gateway.inference_service import app


class GatewayInferenceServiceQATests(unittest.TestCase):
    def test_gateway_inference_service_pack_is_registered_and_attached_to_model(self) -> None:
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
        pack = entries.get("eval-pack:gateway-inference-service-core:0.32.0")
        self.assertIsNotNone(pack)
        self.assertIn("configs/gateway-inference-service.json", pack["refs"])
        self.assertIn("src/gateway_inference_service_runtime.py", pack["refs"])
        self.assertIn("gateway/inference_service/app.py", pack["refs"])
        self.assertIn("tests/test_gateway_inference_service_performance.py", pack["refs"])

        model = entries["model:model-registry-local:0.31.13.alpha-patched1"]
        self.assertIn("eval-pack:gateway-inference-service-core:0.32.0", model["eval_pack_refs"])

    def test_gateway_inference_service_docs_policy_and_app_are_discoverable(self) -> None:
        policy = gisr.load_policy(ROOT / "configs" / "gateway-inference-service.json")
        self.assertEqual("GatewayInferenceServicePolicy", policy["kind"])
        self.assertTrue(policy["policy"]["require_manifest_only_model_loading"])
        self.assertIn({"kind": "health", "protocol": "rest", "method": "GET", "path": "/health"}, app.ENDPOINTS)

        for path in [
            PROJECT_ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("Gateway_Inference_Service", text)

        for path in [
            PROJECT_ROOT / "docs" / "history" / "CHANGELOG.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("Gateway_Inference_Service", text)
            self.assertIn("gateway-inference-service-core", text)


if __name__ == "__main__":
    unittest.main()

