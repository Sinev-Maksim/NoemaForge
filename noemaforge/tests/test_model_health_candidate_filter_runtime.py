#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_model_health_candidate_filter_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate failed-runtime model exclusion from filtered role candidate maps.
Inputs: Synthetic role tournament state and model health candidate filter policy.
Outputs: unittest assertions only.
Side effects: Temporary files under unittest temp directories only.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import model_health_candidate_filter_runtime as mhcf
import production_ai_contracts as pac
import role_tournament as rt


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


class ModelHealthCandidateFilterRuntimeTests(unittest.TestCase):
    def test_policy_validates_and_maps_to_gate_evidence(self) -> None:
        policy_path = ROOT / "configs" / "model-health-candidate-filter-policy.json"
        report = mhcf.validate_model_health_candidate_filter_policy(
            mhcf.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
        )

        self.assertTrue(report["ok"], report["failures"])
        gate = pac.evaluate_gate(
            {"change_id": "model-health-candidate-filter-core", "domain": "model"},
            {
                "artifact_uri": "reports/model-health-candidate-filter.json",
                "run_at": "2026-05-20T00:00:00Z",
                "checks": [
                    {"id": "model_eval", "status": "passed" if report["ok"] else "failed"},
                    {"id": "safety_eval", "status": "passed"},
                ],
                "metrics": report["metrics"],
                "rollback": {"available": True},
                "approval": {"required": False},
            },
        )
        self.assertTrue(gate["ok"], gate)

    def test_role_tournament_filtered_map_excludes_failed_runtime_model(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            state = Path(raw)
            health = {
                "apiVersion": "noemaforge.modelhealth/v1",
                "kind": "ModelHealthRegistry",
                "models": {
                    "bad-model": {
                        "logical_model_id": "bad-model",
                        "health_state": "failed_runtime",
                        "exclude_from_selection": True,
                        "reason": "warmup_failed",
                    },
                    "good-model": {
                        "logical_model_id": "good-model",
                        "health_state": "healthy",
                        "exclude_from_selection": False,
                    },
                },
            }
            write_json(state / "model-health-registry.json", health)
            role_results = {
                "administrator": {
                    "role_key": "administrator",
                    "top_k": 2,
                    "results": [
                        {"model_id": "bad-model", "selection_status": "valid_measured", "score": 0.99, "avg_latency_ms": 1},
                        {"model_id": "good-model", "selection_status": "valid_measured", "score": 0.88, "avg_latency_ms": 2},
                    ],
                    "selected": [],
                    "not_selected": [],
                    "blocked": [],
                }
            }

            rt.finalize_results({"summary": {}}, role_results, [], str(state), selection_mode="normal")
            candidate_map = mhcf.load_json(state / "role-candidate-map.filtered.json")
            report = mhcf.validate_filtered_candidate_map(candidate_map, health)

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(["good-model"], report["selected_models"])
        self.assertEqual(1, report["metrics"]["excluded_model_count"])
        self.assertEqual(0, report["metrics"]["selected_failed_model_count"])

    def test_validator_rejects_failed_runtime_model_in_selected_pool(self) -> None:
        example = mhcf.load_json(PROJECT_ROOT / "prelaunch" / "governance" / "model_health_candidate_filter.example.json")
        candidate_map = copy.deepcopy(example["candidate_map"])
        health = example["model_health_registry"]
        candidate_map["roles"]["administrator"]["selected"].append({"model_id": "bad-model", "selection_status": "valid_measured", "score": 1.0})
        candidate_map["unique_selected_model_ids"].append("bad-model")

        report = mhcf.validate_filtered_candidate_map(candidate_map, health)

        self.assertFalse(report["ok"])
        self.assertIn("failed_model_selected:bad-model", report["failures"])


if __name__ == "__main__":
    unittest.main()
