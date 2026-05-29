#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_runtime_default_safety_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate default runtime safety invariants.
Inputs: Workspace runtime-default-safety policy, autostart policy and runtime scripts.
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

import production_ai_contracts as pac
import runtime_default_safety_runtime as rdsr
import team_member_runtime as tmrt


class RuntimeDefaultSafetyRuntimeTests(unittest.TestCase):
    def test_workspace_runtime_default_safety_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "runtime-default-safety-policy.json"
        validation = rdsr.validate_runtime_default_safety_policy(
            rdsr.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(validation["ok"], validation["failures"])
        self.assertEqual(1, validation["metrics"]["scenarios"])
        self.assertEqual(1, validation["metrics"]["passing_scenarios"])

        gate = pac.evaluate_gate(
            {"change_id": "runtime-default-safety-core", "domain": "pipeline"},
            rdsr.runtime_default_safety_report_to_gate_evidence(validation, artifact_uri="reports/runtime-default-safety.json"),
        )
        self.assertTrue(gate["ok"], gate)

    def test_autostart_policy_keeps_heavy_llm_manual_only(self) -> None:
        policy = rdsr.load_autostart_policy(ROOT / "configs" / "autostart-llm-policy.json")
        self.assertEqual(1, policy["invariant"]["max_active_llms"])
        self.assertEqual("switchable", policy["invariant"]["mode"])
        self.assertEqual("runtime_only", policy["modes"]["gui"]["default_llm_profile"])
        self.assertEqual("bootstrap_cpu_llm", policy["modes"]["wogui"]["default_llm_profile"])
        self.assertEqual("manual_only", policy["modes"]["gui"]["heavy_llm"])
        self.assertEqual("manual_only", policy["modes"]["wogui"]["heavy_llm"])
        self.assertFalse(policy["profiles"]["runtime_only"]["starts_llm"])
        self.assertTrue(policy["profiles"]["bootstrap_cpu_llm"]["cpu_only"])
        self.assertTrue(policy["profiles"]["bootstrap_cpu_llm"]["blocks_heavy_models"])
        self.assertTrue(policy["profiles"]["heavy_manual"]["requires_explicit_flag"])

    def test_runtime_policy_and_team_member_defaults_are_single_heavy_safe(self) -> None:
        pipeline_policy = rdsr.pipeline_policy_snapshot()
        self.assertEqual("switchable", pipeline_policy["runtime_invariant"]["mode"])
        self.assertEqual(1, pipeline_policy["runtime_invariant"]["max_active_llms"])
        self.assertEqual("conditional_safe_start_only", pipeline_policy["runtime_invariant"]["heavy_llm_autostart"])

        team_policy = tmrt.default_policy()
        self.assertEqual(1, team_policy["invariant"]["max_active_llms"])
        self.assertEqual("sequential", team_policy["invariant"]["default_execution"])

    def test_boot_scripts_reject_heavy_autostart_tokens(self) -> None:
        autostart_text = (ROOT / "tools" / "prep" / "noemaforge-autostart-safe.sh").read_text(encoding="utf-8")
        boot_mode_text = (ROOT / "tools" / "prep" / "noemaforge-boot-mode.sh").read_text(encoding="utf-8")
        self.assertIn("heavy LLM autostart is disabled", autostart_text)
        self.assertIn("heavy_llm=manual_only max_active_llms=1", autostart_text)
        self.assertIn("heavy LLM autostart is disabled", boot_mode_text)
        self.assertIn("Default profile: runtime_only", boot_mode_text)


if __name__ == "__main__":
    unittest.main()
