#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_model_health_candidate_filter_performance.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Performance-test bounded failed-model candidate-map filtering validation.
Inputs: Synthetic candidate maps and model health registries.
Outputs: unittest assertions only.
Side effects: None.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import os
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, str(ROOT / "src"))

import model_health_candidate_filter_runtime as mhcf


def synthetic_candidate_map(role_count: int = 48) -> dict:
    roles = {}
    selected = []
    for index in range(role_count):
        model_id = f"good-model-{index}"
        selected.append(model_id)
        roles[f"role_{index}"] = {
            "selected": [{"model_id": model_id, "selection_status": "valid_measured", "score": 0.8}],
            "chosen": {"model_id": model_id, "selection_status": "valid_measured", "score": 0.8},
        }
    return {
        "kind": "RoleCandidateMap",
        "roles": roles,
        "unique_selected_model_ids": selected,
        "health_registry": "model-health-registry.json",
        "excluded_model_count": 24,
        "selection_diagnostics": {"no_candidates_reason": None},
    }


def synthetic_health_registry(excluded_count: int = 24) -> dict:
    return {
        "kind": "ModelHealthRegistry",
        "models": {
            f"bad-model-{index}": {
                "logical_model_id": f"bad-model-{index}",
                "health_state": "failed_runtime",
                "exclude_from_selection": True,
            }
            for index in range(excluded_count)
        },
    }


class ModelHealthCandidateFilterPerformanceTests(unittest.TestCase):
    def test_many_role_candidate_filter_checks_stay_bounded(self) -> None:
        candidate_map = synthetic_candidate_map()
        health = synthetic_health_registry()

        started = time.perf_counter()
        for _ in range(2000):
            report = mhcf.validate_filtered_candidate_map(candidate_map, health)
            self.assertTrue(report["ok"], report["failures"])
            self.assertEqual(0, report["metrics"]["selected_failed_model_count"])
        elapsed = time.perf_counter() - started

        self.assertLess(elapsed, 0.75)


if __name__ == "__main__":
    unittest.main()
