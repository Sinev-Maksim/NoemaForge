#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_first_start_summary_contract_performance.py
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Performance-test first-start summary validation on synthetic run catalogs.
Inputs: Workspace policy expanded with hundreds of first-start event runs.
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
from unittest.mock import patch

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import first_start_summary_contract_runtime as fsscr


class FirstStartSummaryContractPerformanceTests(unittest.TestCase):
    def test_synthetic_first_start_event_catalog_validates_under_budget(self) -> None:
        policy = fsscr.load_policy(ROOT / "configs" / "first-start-summary-policy.json")
        base_set = fsscr.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "first_start_summary.example.json")
        synthetic_set = copy.deepcopy(base_set)
        synthetic_set["events"] = []
        states = ["selection_ready_no_apply", "degraded_selected", "blocked_no_models"]
        for index in range(300):
            run_id = f"run-{index:03d}"
            state = states[index % len(states)]
            synthetic_set["events"].append({"ts": f"2026-05-20T01:{index % 60:02d}:00Z", "step": "start", "state": "running", "message": "run started", "extra": {"run_id": run_id}})
            synthetic_set["events"].append({"ts": f"2026-05-20T01:{index % 60:02d}:01Z", "step": "inventory", "state": "complete", "message": "inventory complete", "extra": {"selection_mode": "gui"}})
            synthetic_set["events"].append({"ts": f"2026-05-20T01:{index % 60:02d}:02Z", "step": "complete", "state": state, "message": "run complete", "extra": {"selection_mode": "gui"}})

        started = time.perf_counter()
        with patch.object(fsscr, "load_example_set", return_value=synthetic_set):
            report = fsscr.validate_first_start_summary_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        elapsed = time.perf_counter() - started

        self.assertTrue(report["ok"], report["failures"][:10])
        self.assertEqual(300, report["metrics"]["runs"])
        self.assertEqual(900, report["metrics"]["events"])
        self.assertEqual(3, report["metrics"]["markers_seen"])
        self.assertLess(elapsed, 5.0)


if __name__ == "__main__":
    unittest.main()
