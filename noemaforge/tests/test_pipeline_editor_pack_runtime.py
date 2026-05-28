#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_pipeline_editor_pack_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate Pipeline Editor pack draft edit/clone/review invariants.
Inputs: Workspace pipeline-editor-pack policy and pipeline catalog.
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

import pipeline_editor_pack_runtime as pepr
import pipeline_runtime


class PipelineEditorPackRuntimeTests(unittest.TestCase):
    def test_workspace_pipeline_editor_pack_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "pipeline-editor-pack-policy.json"
        report = pepr.validate_pipeline_editor_pack_policy(
            pepr.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual("pipeline-editor-pack-core", report["id"])
        self.assertGreater(report["metrics"]["operations"], 3)
        self.assertEqual(report["metrics"]["operations"], report["metrics"]["drag_drop_events"])

    def test_editor_draft_clones_as_new_pipeline_class_without_activation(self) -> None:
        policy = pepr.load_policy(ROOT / "configs" / "pipeline-editor-pack-policy.json")
        catalog = pipeline_runtime.load_pipeline_catalog(ROOT)
        draft = pepr.build_pipeline_editor_draft(
            catalog,
            source_id="evolution",
            new_pipeline_id="evolution_clone_for_review",
            operations=[
                {"op": "add_stage", "stage": "scary_preflight", "after": "intake"},
                {"op": "set_deliverable", "value": "pipeline_editor_manifest"},
            ],
        )

        self.assertEqual([], pepr.validate_pipeline_editor_draft(draft, policy["policy"]))
        self.assertEqual("draft_only", draft["status"])
        self.assertFalse(draft["auto_activate"])
        self.assertFalse(draft["applied"])
        self.assertEqual("operator_draft_clone", draft["clone"]["pipeline_class"])
        self.assertEqual("evolution", draft["source_pipeline_id"])
        self.assertEqual("evolution_clone_for_review", draft["new_pipeline_id"])
        self.assertNotEqual(draft["source_pipeline_id"], draft["new_pipeline_id"])

    def test_review_chain_and_drag_drop_events_are_required(self) -> None:
        policy = pepr.load_policy(ROOT / "configs" / "pipeline-editor-pack-policy.json")
        draft = pepr.build_pipeline_editor_fixture(package_root=ROOT)

        self.assertEqual(["Scary", "Architecture", "Admin"], draft["review_chain"])
        self.assertIn("scary_review", draft["clone"]["stages"])
        self.assertIn("architecture_review", draft["clone"]["stages"])
        self.assertIn("admin_review", draft["clone"]["stages"])
        self.assertTrue(all(event["event_type"] == "drag_drop_stage_edit" for event in draft["drag_drop_events"]))

        broken = dict(draft)
        broken["review_chain"] = ["Admin"]
        self.assertIn("draft_review_chain_invalid", pepr.validate_pipeline_editor_draft(broken, policy["policy"]))

    def test_bad_operation_is_rejected(self) -> None:
        policy = pepr.load_policy(ROOT / "configs" / "pipeline-editor-pack-policy.json")
        catalog = pipeline_runtime.load_pipeline_catalog(ROOT)
        draft = pepr.build_pipeline_editor_draft(
            catalog,
            source_id="evolution",
            new_pipeline_id="bad_clone",
            operations=[{"op": "activate", "stage": "merge_plan"}],
        )

        failures = pepr.validate_pipeline_editor_draft(draft, policy["policy"])
        self.assertIn("draft_operation_not_allowed:activate", failures)
        self.assertIn("drag_drop_event_operation_not_allowed:activate", failures)


if __name__ == "__main__":
    unittest.main()
