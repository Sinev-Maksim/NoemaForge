#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_typed_governance_track_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate typed governance dependency tracking across governance contract packs.
Inputs: Workspace Typed Governance Track policy and temporary broken fixtures.
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

import production_ai_contracts as pac
import typed_governance_track_runtime as tgtr


class TypedGovernanceTrackRuntimeTests(unittest.TestCase):
    def test_workspace_typed_governance_track_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "typed-governance-track.json"
        report = tgtr.validate_typed_governance_track_policy(
            tgtr.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(1, report["metrics"]["tracks"])
        self.assertEqual(1, report["metrics"]["passing_tracks"])
        self.assertEqual(8, report["metrics"]["contracts"])
        self.assertEqual(0, report["metrics"]["missing_refs"])

        gate = pac.evaluate_gate(
            {"change_id": "typed-governance-track-core", "domain": "pipeline"},
            tgtr.typed_governance_track_report_to_gate_evidence(
                report,
                artifact_uri="reports/typed-governance-track.json",
            ),
        )
        self.assertTrue(gate["ok"], gate)

    def test_track_dependency_after_stage_is_blocked(self) -> None:
        policy_path = ROOT / "configs" / "typed-governance-track.json"
        policy = tgtr.load_policy(policy_path)
        example_set = tgtr.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "typed_governance_track.example.json")
        broken_set = copy.deepcopy(example_set)
        broken_set["tracks"][0]["stages"][1]["depends_on"] = ["pipeline_rfc"]

        with patch.object(tgtr, "load_example_set", return_value=broken_set):
            report = tgtr.validate_typed_governance_track_policy(
                policy,
                project_root=PROJECT_ROOT,
                package_root=ROOT,
                policy_path=policy_path,
            )

        self.assertFalse(report["ok"])
        self.assertIn(
            "track_dependency_after_stage:typed-governance-track-main:sense_state_privacy:pipeline_rfc",
            report["failures"],
        )

    def test_missing_registry_eval_pack_attachment_is_blocked(self) -> None:
        policy_path = ROOT / "configs" / "typed-governance-track.json"
        policy = tgtr.load_policy(policy_path)
        broken_policy = copy.deepcopy(policy)
        broken_policy["policy"]["required_contracts"][6]["eval_pack_ref"] = "eval-pack:missing-research-packet:0.32.1"

        report = tgtr.validate_typed_governance_track_policy(
            broken_policy,
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertFalse(report["ok"])
        self.assertTrue(any(item.startswith("registry_eval_pack_missing:research_packet:") for item in report["failures"]))

    def test_contract_without_runtime_qa_and_performance_tests_is_blocked(self) -> None:
        policy_path = ROOT / "configs" / "typed-governance-track.json"
        policy = tgtr.load_policy(policy_path)
        broken_policy = copy.deepcopy(policy)
        broken_policy["policy"]["required_contracts"][0]["test_refs"] = ["tests/test_concept_frame_runtime.py"]

        report = tgtr.validate_typed_governance_track_policy(
            broken_policy,
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertFalse(report["ok"])
        self.assertIn("policy_contract_tests_incomplete:concept_frame", report["failures"])


if __name__ == "__main__":
    unittest.main()

