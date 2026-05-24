#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_default_model_runtime_policy_runtime.py
Zone: release/package
Version: 0.31.21.alpha
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate the default CPU-safe model runtime policy with GPU-on-demand escalation.
Inputs: Workspace default model runtime policy, device policy, model profiles and Admin GUI source.
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

import default_model_runtime_policy as dmrp
import production_ai_contracts as pac


class DefaultModelRuntimePolicyRuntimeTests(unittest.TestCase):
    def test_workspace_default_model_runtime_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "default-model-runtime-policy.json"
        validation = dmrp.validate_default_model_runtime_policy(
            dmrp.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(validation["ok"], validation["failures"])
        self.assertEqual(2, validation["metrics"]["examples"])
        self.assertEqual(2, validation["metrics"]["passing_examples"])

        gate = pac.evaluate_gate(
            {"change_id": "default-model-runtime-policy-core", "domain": "pipeline"},
            dmrp.default_model_runtime_policy_report_to_gate_evidence(validation, artifact_uri="reports/default-model-runtime-policy.json"),
        )
        self.assertTrue(gate["ok"], gate)

    def test_runtime_device_policy_defaults_to_cpu_safe(self) -> None:
        device = dmrp.load_json(ROOT / "configs" / "runtime-device-policy.json")
        self.assertEqual("cpu_safe_always_on_with_gpu_on_demand", device["decision"])
        self.assertEqual("cpu", device["default"])
        self.assertEqual("cpu_safe", device["always_on_policy"])
        self.assertEqual("explicit_on_demand", device["gpu_policy"])
        self.assertFalse(device["gpu_autostart_enabled"])
        self.assertFalse(device["heavy_gpu_autostart"])
        self.assertEqual(1, device["max_active_heavy_workers"])

    def test_model_profiles_keep_minimal_cpu_and_gpu_on_demand(self) -> None:
        profiles = dmrp.load_json(ROOT / "configs" / "model-profiles.json")
        self.assertIn("CPU-safe", profiles["minimal"]["description"])
        self.assertEqual(0, profiles["minimal"]["vram_gib_min"])
        self.assertEqual(1, profiles["minimal"]["max_active_llms"])
        self.assertEqual("explicit_gpu_on_demand", profiles["gpu-heavy"]["default_runtime"])
        self.assertIn("GPU-on-demand", profiles["gpu-heavy"]["description"])
        self.assertIn("Never always-on", profiles["gpu-heavy"]["description"])
        self.assertEqual(1, profiles["gpu-heavy"]["max_active_llms"])

    def test_admin_gui_default_device_policy_is_cpu_safe(self) -> None:
        source = (ROOT / "src" / "admin_gui_server.py").read_text(encoding="utf-8")
        self.assertIn('"policy": "cpu"', source)
        self.assertIn("cpu_safe_always_on_with_gpu_on_demand", source)
        self.assertIn('"gpu_policy": "explicit_on_demand"', source)
        self.assertIn('"max_active_heavy_workers": 1', source)


if __name__ == "__main__":
    unittest.main()
