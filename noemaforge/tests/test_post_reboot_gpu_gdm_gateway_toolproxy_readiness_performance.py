#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_post_reboot_gpu_gdm_gateway_toolproxy_readiness_performance.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-21
Modified: 2026-05-21
Purpose: Bounded regression-test post-reboot GPU/GDM/gateway/ToolProxy readiness validation runtime.
Inputs: Post-reboot composite readiness policy and example fixtures.
Outputs: unittest assertions only.
Side effects: None.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import post_reboot_gpu_gdm_gateway_toolproxy_readiness_runtime as prggt


class PostRebootGpuGdmGatewayToolproxyReadinessPerformanceTests(unittest.TestCase):
    def test_policy_validation_is_bounded_for_small_fixture(self) -> None:
        payload = prggt.load_policy()
        started = time.perf_counter()
        for _ in range(25):
            report = prggt.validate_post_reboot_gpu_gdm_gateway_toolproxy_readiness_policy(payload)
            self.assertTrue(report["ok"], report["failures"])
        elapsed = time.perf_counter() - started
        self.assertLess(elapsed, 2.0)


if __name__ == "__main__":
    unittest.main()
