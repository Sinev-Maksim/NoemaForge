from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pipeline_stage_transition_runtime as pstr


class PipelineStageTransitionRuntimeTests(unittest.TestCase):
    def test_policy_validation_passes_with_offline_scenario(self) -> None:
        report = pstr.validate_policy(ROOT / "configs" / "pipeline-stage-transition-policy.json")
        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(1, report["metrics"]["scenario_count"])
        self.assertGreaterEqual(report["metrics"]["required_commands"], 8)

    def test_policy_detects_missing_transition_command(self) -> None:
        payload = pstr.load_json(ROOT / "configs" / "pipeline-stage-transition-policy.json")
        broken = copy.deepcopy(payload)
        broken["policy"]["required_pipeline_commands"].remove("fail")
        failures = pstr._policy_failures(broken)
        self.assertIn("policy_required_command_missing:fail", failures)

    def test_invalid_stage_is_rejected_by_pause_and_fail(self) -> None:
        work = ROOT.parent / "trash" / "u"
        work.mkdir(parents=True, exist_ok=True)
        state = work / "s"
        run_id = "r"
        pstr._call_pipeline(["run", "public_mwp", "--task-id", "x", "--request", "invalid stage test", "--run-id", run_id, "--allow-existing"], state=state)
        pause_code, _, _, pause_err = pstr._call_pipeline(["pause", run_id, "--stage", "missing_stage"], state=state)
        fail_code, _, _, fail_err = pstr._call_pipeline(["fail", run_id, "--stage", "missing_stage"], state=state)
        self.assertNotEqual(0, pause_code)
        self.assertNotEqual(0, fail_code)
        self.assertIn("unknown stage", pause_err)
        self.assertIn("unknown stage", fail_err)


if __name__ == "__main__":
    unittest.main()
