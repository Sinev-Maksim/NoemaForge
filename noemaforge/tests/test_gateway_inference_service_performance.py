#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_gateway_inference_service_performance.py
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Performance-test Gateway Inference Service validation on a synthetic service catalog.
Inputs: Workspace policy expanded with hundreds of gateway services.
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
import time
import unittest
from pathlib import Path

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import gateway_inference_service_runtime as gisr


class GatewayInferenceServicePerformanceTests(unittest.TestCase):
    def test_synthetic_gateway_service_catalog_validates_under_budget(self) -> None:
        payload = copy.deepcopy(gisr.load_policy(ROOT / "configs" / "gateway-inference-service.json"))
        base_service = copy.deepcopy(payload["services"][0])
        payload["services"] = []
        for index in range(400):
            service = copy.deepcopy(base_service)
            service["id"] = f"gateway-inference-service-{index:04d}"
            payload["services"].append(service)

        started = time.perf_counter()
        report = gisr.validate_gateway_inference_service_policy(payload, project_root=PROJECT_ROOT, package_root=ROOT)
        elapsed = time.perf_counter() - started

        self.assertTrue(report["ok"], report["failures"][:5])
        self.assertEqual(400, report["metrics"]["services"])
        self.assertEqual(400, report["metrics"]["passing_services"])
        self.assertEqual(800, report["metrics"]["inference_endpoints"])
        self.assertEqual(400, report["metrics"]["mqtt_endpoints"])
        self.assertLess(elapsed, 5.0)


if __name__ == "__main__":
    unittest.main()
