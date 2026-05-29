#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_hypergraph_error_improvement_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate hypergraph error improvement runtime behavior.
Inputs: Workspace Hypergraph Error Improvement policy, SQL schema and offline example.
Outputs: unittest assertions only.
Side effects: Temporary SQLite database creation under pytest/unittest temp paths.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import hypergraph_error_improvement_runtime as hei
from knowledge.error_learning import ErrorLearningStore


class HypergraphErrorImprovementRuntimeTests(unittest.TestCase):
    def test_workspace_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "hypergraph-error-improvement-policy.json"
        validation = hei.validate_hypergraph_error_improvement_policy(
            hei.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(validation["ok"], validation["failures"])
        self.assertEqual(3, validation["metrics"]["stores"])
        self.assertGreaterEqual(validation["metrics"]["defect_classes"], 5)
        self.assertGreaterEqual(validation["metrics"]["approved_reuse_targets"], 2)
        self.assertGreaterEqual(validation["metrics"]["tracked_errors"], 5)
        self.assertGreaterEqual(validation["metrics"]["approved_retraining_deltas"], 1)
        self.assertGreaterEqual(validation["metrics"]["approved_regression_cases"], 1)

    def test_example_separates_source_and_pipeline_defects(self) -> None:
        examples = hei.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "hypergraph_error_improvement.example.json")
        plan = hei.build_improvement_loop(examples["scenarios"][0])

        self.assertTrue(plan["ok"], plan["failures"])
        self.assertEqual(1, plan["metrics"]["source_defects"])
        self.assertEqual(4, plan["metrics"]["pipeline_defects"])
        self.assertEqual(
            [
                "chunking_defect",
                "extraction_defect",
                "labeling_defect",
                "linking_defect",
                "source_defect",
            ],
            plan["metrics"]["defect_classes"],
        )
        for tracked in plan["tracked_errors"]:
            self.assertTrue(tracked["model_id"])
            self.assertTrue(tracked["run_id"])
            self.assertTrue(tracked["profile_id"])

    def test_existing_error_learning_store_tracks_run_model_and_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = ErrorLearningStore(str(Path(tmp) / "errors.sqlite"))
            self.assertTrue({"error_events", "corrections", "regression_cases"}.issubset(set(store.list_tables())))
            run_id = store.start_run(
                component="entity_linker",
                model_id="nf-entity-linker-local",
                profile_id="profile:linking:v1",
                run_id="run:test:linker",
            )
            error_id = store.add_error_event(
                run_id=run_id,
                component="entity_linker",
                error_type="wrong_entity_link",
                source_defect=False,
            )
            correction_id = store.add_correction(
                error_id=error_id,
                corrected_by="qa",
                correction_kind="entity_link",
                new_value={"entity_id": "concept:correct"},
                approved_for_training=True,
                approved_for_eval=True,
            )
            store.promote_regression_case(
                error_id=error_id,
                source_correction_id=correction_id,
                component="entity_linker",
                input_payload={"mention": "Noema"},
                expected_payload={"entity_id": "concept:correct"},
                promoted_by="qa",
            )
            store.promote_training_delta(
                error_id=error_id,
                correction_id=correction_id,
                target_model_family="entity_linker",
                delta_payload={"entity_id": "concept:correct"},
            )

            run = store.get_run(run_id)
            self.assertIsNotNone(run)
            self.assertEqual("nf-entity-linker-local", run["model_id"])
            self.assertEqual("profile:linking:v1", run["profile_id"])


if __name__ == "__main__":
    unittest.main()
