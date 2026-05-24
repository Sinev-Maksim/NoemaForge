from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pipeline_stage_transition_runtime as pstr


class PipelineStageTransitionPerformanceTests(unittest.TestCase):
    def test_transition_validation_stays_bounded(self) -> None:
        started = time.perf_counter()
        report = pstr.validate_policy(ROOT / "configs" / "pipeline-stage-transition-policy.json")
        elapsed = time.perf_counter() - started
        self.assertTrue(report["ok"], report["failures"])
        self.assertLess(elapsed, 5.0)
        self.assertLessEqual(report["metrics"]["scenario_count"], 2)


if __name__ == "__main__":
    unittest.main()
