#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_final_gui_scenario_replay_readiness_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-21
Modified: 2026-05-21
Purpose: Runtime-test the final Admin GUI scenario replay readiness contract.
Inputs: Final GUI scenario replay readiness policy and runtime validator.
Outputs: unittest assertions only.
Side effects: None.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import final_gui_scenario_replay_readiness_runtime as fgsr


class FinalGuiScenarioReplayReadinessRuntimeTests(unittest.TestCase):
    def test_policy_validation_passes_without_running_gui_or_target_actions(self) -> None:
        report = fgsr.validate_final_gui_scenario_replay_readiness_policy(fgsr.load_policy())
        self.assertTrue(report["ok"], report["failures"])
        summary = report["final_gui_scenario_replay_summary"]
        self.assertTrue(summary["completion_blocked"])
        self.assertTrue(summary["target_machine_required"])
        self.assertTrue(summary["operator_approval_required"])
        self.assertTrue(summary["safe_local_validator_only"])
        self.assertEqual("polished_admin_gui_guided_scenario", summary["required_showcase_id"])
        self.assertGreaterEqual(summary["target_command_count"], 15)
        self.assertIn("admin_greeting_transcript", report["evidence_requirements"])
        self.assertIn("routed_pipeline_response_json", report["evidence_requirements"])
        self.assertIn("dev_team_response_json", report["evidence_requirements"])
        self.assertIn("model_evolution_response_json", report["evidence_requirements"])
        self.assertIn("version_bump_guard_record", report["evidence_requirements"])

    def test_selected_showcase_must_remain_the_reviewed_public_scenario(self) -> None:
        broken = copy.deepcopy(fgsr.load_policy())
        broken["policy"]["required_showcase_id"] = "manual_admin_demo"
        failures = fgsr._policy_failures(broken)
        self.assertIn("policy_required_showcase_id_invalid", failures)

        broken = copy.deepcopy(fgsr.load_policy())
        for check in broken["policy"]["required_checks"]:
            if check["id"] == "target-baseline":
                check["commands"] = ["noemaforge public-showcase scenario --json"]
        failures = fgsr._policy_failures(broken)
        self.assertIn("check_required_showcase_missing:target-baseline:polished_admin_gui_guided_scenario", failures)

    def test_operator_approval_is_required_for_start_and_archive_steps(self) -> None:
        broken = copy.deepcopy(fgsr.load_policy())
        for check in broken["policy"]["required_checks"]:
            if check["id"] in {"admin-gui-start", "transcript-and-archive"}:
                check["requires_operator_approval"] = False
        failures = fgsr._policy_failures(broken)
        self.assertIn("check_operator_approval_required:admin-gui-start", failures)
        self.assertIn("check_operator_approval_required:transcript-and-archive", failures)

    def test_remote_or_browser_execution_path_is_rejected(self) -> None:
        broken = copy.deepcopy(fgsr.load_policy())
        for check in broken["policy"]["required_checks"]:
            if check["id"] == "admin-gui-start":
                check["commands"].append("browser open https://example.invalid")
        failures = fgsr._policy_failures(broken)
        self.assertIn("check_forbidden_token:admin-gui-start:https://", failures)
        self.assertIn("check_forbidden_token:admin-gui-start:browser", failures)

    def test_example_validation_and_gate_evidence_are_explicit(self) -> None:
        report = fgsr.validate_final_gui_scenario_replay_readiness_policy(fgsr.load_policy())
        example = fgsr.validate_example()
        self.assertTrue(example["ok"], example["failures"])
        evidence = fgsr.gate_evidence(report, artifact_uri="reports/final-gui-scenario-replay-readiness.json")
        self.assertEqual("final_gui_scenario_replay_readiness", evidence["gate"])
        self.assertEqual("passed", evidence["status"])
        self.assertEqual(report["metrics"], evidence["metrics"])


if __name__ == "__main__":
    unittest.main()
