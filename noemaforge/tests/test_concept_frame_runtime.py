#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_concept_frame_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Validate Concept_Frame contracts for Admin/Architect governance decisions.
Inputs: Workspace Concept Frame policy and temporary broken fixtures.
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
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import concept_frame_runtime as cfr
import production_ai_contracts as pac


class ConceptFrameRuntimeTests(unittest.TestCase):
    def test_workspace_concept_frame_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "concept-frame-policy.json"
        report = cfr.validate_concept_frame_policy(
            cfr.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(2, report["metrics"]["frames"])
        self.assertEqual(2, report["metrics"]["passing_frames"])
        self.assertEqual(1, report["metrics"]["admin_frames"])
        self.assertEqual(1, report["metrics"]["architect_frames"])
        self.assertEqual(1, report["metrics"]["dangerous_frames"])
        self.assertEqual(1, report["metrics"]["pipeline_rfc_required_frames"])
        self.assertEqual(0, report["metrics"]["missing_refs"])

        gate = pac.evaluate_gate(
            {"change_id": "concept-frame-governance-core", "domain": "pipeline"},
            cfr.concept_frame_report_to_gate_evidence(report, artifact_uri="reports/concept-frame.json"),
        )
        self.assertTrue(gate["ok"], gate)

    def test_dangerous_pipeline_frame_requires_approval_and_rfc(self) -> None:
        policy_path = ROOT / "configs" / "concept-frame-policy.json"
        payload = copy.deepcopy(cfr.load_policy(policy_path))
        frame_set = cfr.load_frame_set(PROJECT_ROOT / "prelaunch" / "governance" / "concept_frame.admin_architect.example.json")
        architect = frame_set["frames"][1]
        architect["gates"]["dangerous_action"] = False
        architect["gates"]["approval_required"] = False
        architect["gates"]["approval_refs"] = []
        architect["gates"]["pipeline_rfc_required"] = False
        architect["gates"]["pipeline_rfc_ref"] = ""

        with patch.object(cfr, "load_frame_set", return_value=frame_set):
            report = cfr.validate_concept_frame_policy(
                payload,
                project_root=PROJECT_ROOT,
                package_root=ROOT,
                policy_path=policy_path,
            )

        self.assertFalse(report["ok"])
        self.assertIn("frame_dangerous_action_not_marked:cf-architect-pipeline-rfc-boundary", report["failures"])
        self.assertIn("frame_approval_not_required_for_dangerous_action:cf-architect-pipeline-rfc-boundary", report["failures"])
        self.assertIn("frame_approval_refs_missing:cf-architect-pipeline-rfc-boundary", report["failures"])
        self.assertIn("frame_pipeline_rfc_not_required:cf-architect-pipeline-rfc-boundary", report["failures"])
        self.assertIn("frame_pipeline_rfc_ref_missing:cf-architect-pipeline-rfc-boundary", report["failures"])

    def test_frame_shape_requires_context_options_and_honesty_state(self) -> None:
        policy_path = ROOT / "configs" / "concept-frame-policy.json"
        payload = copy.deepcopy(cfr.load_policy(policy_path))
        frame_set = cfr.load_frame_set(PROJECT_ROOT / "prelaunch" / "governance" / "concept_frame.admin_architect.example.json")
        admin = frame_set["frames"][0]
        admin["trace_id"] = ""
        admin["context"] = {"summary": "", "source_refs": []}
        admin["options"] = []
        admin["recommendation"]["selected_option_id"] = "missing-option"
        admin["gates"]["honesty_state"] = ""

        with patch.object(cfr, "load_frame_set", return_value=frame_set):
            report = cfr.validate_concept_frame_policy(
                payload,
                project_root=PROJECT_ROOT,
                package_root=ROOT,
                policy_path=policy_path,
            )

        self.assertFalse(report["ok"])
        self.assertIn("frame_trace_id_invalid:cf-admin-model-selection-dry-run", report["failures"])
        self.assertIn("frame_context_summary_missing:cf-admin-model-selection-dry-run", report["failures"])
        self.assertIn("frame_context_source_refs_missing:cf-admin-model-selection-dry-run", report["failures"])
        self.assertIn("frame_options_missing:cf-admin-model-selection-dry-run", report["failures"])
        self.assertIn("frame_recommendation_option_invalid:cf-admin-model-selection-dry-run:missing-option", report["failures"])
        self.assertIn("frame_honesty_state_invalid:cf-admin-model-selection-dry-run:", report["failures"])


if __name__ == "__main__":
    unittest.main()
