#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_public_showcase_guided_scenario_runtime.py
Zone: gui/control-plane
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Runtime-test the Admin GUI public showcase guided scenario contract.
Inputs: Public showcase policy, example scenario and Admin GUI server helper.
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

import admin_gui_server as ags
import public_showcase_guided_scenario_runtime as psg


class PublicShowcaseGuidedScenarioRuntimeTests(unittest.TestCase):
    def test_policy_validates_admin_gui_guided_scenario(self) -> None:
        policy_path = ROOT / "configs" / "public-showcase-guided-scenario-policy.json"
        report = psg.validate_public_showcase_guided_scenario_policy(
            psg.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )
        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(5, report["metrics"]["required_steps"])
        self.assertEqual(5, report["metrics"]["example_steps"])

    def test_admin_gui_scenario_is_local_first_and_reviewable(self) -> None:
        scenario = ags.build_public_showcase_scenario("ru")
        self.assertTrue(scenario["ok"])
        self.assertEqual("polished_admin_gui_guided_scenario", scenario["selection"])
        self.assertFalse(scenario["live_backend_demo_enabled"])
        self.assertFalse(scenario["requires_live_target"])
        self.assertFalse(scenario["requires_packaging"])
        self.assertTrue(scenario["safety"]["no_hidden_backend_start"])
        self.assertTrue(scenario["safety"]["no_auto_apply"])
        self.assertTrue(scenario["safety"]["final_target_replay_required"])
        self.assertEqual(
            ["health", "admin_greeting", "routed_pipeline", "dev_team_plan", "model_evolution_plan"],
            [step["id"] for step in scenario["steps"]],
        )


if __name__ == "__main__":
    unittest.main()
