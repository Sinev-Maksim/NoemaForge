#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_gateway_inference_service_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Validate Gateway Inference Service contracts and manifest-only loading.
Inputs: Workspace Gateway Inference Service policy and local service skeleton.
Outputs: unittest assertions only.
Side effects: None.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import copy
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT))

import gateway_inference_service_runtime as gisr
import production_ai_contracts as pac
from gateway.inference_service import app, model_loader


class GatewayInferenceServiceRuntimeTests(unittest.TestCase):
    def test_workspace_gateway_inference_service_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "gateway-inference-service.json"
        report = gisr.validate_gateway_inference_service_policy(
            gisr.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(1, report["metrics"]["services"])
        self.assertEqual(1, report["metrics"]["passing_services"])
        self.assertEqual(5, report["metrics"]["endpoints"])
        self.assertEqual(2, report["metrics"]["inference_endpoints"])
        self.assertEqual(4, report["metrics"]["rest_endpoints"])
        self.assertEqual(1, report["metrics"]["mqtt_endpoints"])
        self.assertEqual(1, report["metrics"]["manifest_loaded_services"])
        self.assertEqual(0, report["metrics"]["direct_control_decision_services"])
        self.assertEqual(0, report["metrics"]["missing_refs"])

        gate = pac.evaluate_gate(
            {"change_id": "gateway-inference-service-core", "domain": "model"},
            gisr.gateway_inference_report_to_gate_evidence(report, artifact_uri="reports/gateway-inference-service.json"),
        )
        self.assertTrue(gate["ok"], gate)

    def test_service_skeleton_uses_manifest_loaded_model_state(self) -> None:
        manifest = PROJECT_ROOT / "prelaunch" / "manifests" / "models" / "example_edge_model.manifest.json"
        state = app.load_state(manifest)

        self.assertEqual("signed_manifest", state["model"]["source"])
        self.assertTrue(app.handle_rest("/health", state=state)["ok"])
        self.assertTrue(app.handle_rest("/ready", state=state)["ok"])
        self.assertEqual(1, app.handle_rest("/metrics", state=state)["gateway_inference_manifest_loads_total"])
        self.assertTrue(app.handle_rest("/infer", {"temperature_c": 20.0}, state=state)["ok"])
        self.assertTrue(app.handle_mqtt("noemaforge/gateway/infer", {"temperature_c": 20.0}, state=state)["ok"])

        with self.assertRaisesRegex(ValueError, "direct_model_path_forbidden"):
            model_loader.load_model(model_path="models/raw.onnx")

    def test_manifest_only_loading_and_control_endpoints_are_enforced(self) -> None:
        policy_path = ROOT / "configs" / "gateway-inference-service.json"
        payload = copy.deepcopy(gisr.load_policy(policy_path))
        service = payload["services"][0]
        service["model_source"] = "direct_path"
        service["direct_model_path"] = "models/raw.onnx"
        service["signed_model_manifest_ref"] = "prelaunch/manifests/models/missing.manifest.json"
        service["direct_control_decisions"] = True
        service["endpoints"] = [
            endpoint for endpoint in service["endpoints"] if endpoint.get("path") != "/ready"
        ]

        report = gisr.validate_gateway_inference_service_policy(
            payload,
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertFalse(report["ok"])
        self.assertIn("service_model_source_not_allowed:gateway-floor-inference-shadow:direct_path", report["failures"])
        self.assertIn("service_direct_model_path_present:gateway-floor-inference-shadow", report["failures"])
        self.assertIn("service_manifest_missing:gateway-floor-inference-shadow:prelaunch/manifests/models/missing.manifest.json", report["failures"])
        self.assertIn("service_direct_control_decision_enabled:gateway-floor-inference-shadow", report["failures"])
        self.assertIn("service_ready_endpoint_missing:gateway-floor-inference-shadow", report["failures"])


if __name__ == "__main__":
    unittest.main()
