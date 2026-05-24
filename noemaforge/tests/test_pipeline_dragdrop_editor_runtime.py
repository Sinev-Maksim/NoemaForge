#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_pipeline_dragdrop_editor_runtime.py
Zone: gui/control-plane
Version: 0.31.21.alpha
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate draft-only pipeline drag/drop editor runtime behavior.
Inputs: Pipeline drag/drop editor policy and Admin GUI draft normalization helper.
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
import pipeline_dragdrop_editor_runtime as pde
import production_ai_contracts as pac


class PipelineDragDropEditorRuntimeTests(unittest.TestCase):
    def test_workspace_pipeline_dragdrop_editor_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "pipeline-dragdrop-editor-policy.json"
        report = pde.validate_pipeline_dragdrop_editor_policy(
            pde.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(report["ok"], report["failures"])
        gate = pac.evaluate_gate(
            {"change_id": "pipeline-dragdrop-editor-core", "domain": "pipeline"},
            {
                "artifact_uri": "memory://pipeline-dragdrop-editor-core/report",
                "run_at": report["validated_at"],
                "checks": [
                    {"id": "pipeline_eval", "status": "pass"},
                    {"id": "rollback_plan", "status": "pass"},
                ],
            },
        )
        self.assertTrue(gate["ok"], gate)

    def test_stage_reorder_helper_is_deterministic(self) -> None:
        self.assertEqual(["plan", "intake", "review"], pde.move_stage(["intake", "plan", "review"], 0, 1))
        self.assertEqual(["intake", "plan", "review"], pde.move_stage(["intake", "plan", "review"], -1, 1))

    def test_admin_gui_normalizes_draft_without_activation(self) -> None:
        draft = ags.normalize_pipeline_editor_draft({"id": "Demo Pipeline", "stages": ["intake", "plan", "plan", "../bad", "review"]})
        self.assertEqual("drag_drop_pipeline_editor", draft["editor_mode"])
        self.assertEqual("draft_only", draft["activation_state"])
        self.assertTrue(draft["review_required"])
        self.assertEqual(["intake", "plan", "bad", "review"], draft["stages"])
        self.assertTrue(draft["draft_id"].startswith("draft_"))


if __name__ == "__main__":
    unittest.main()
