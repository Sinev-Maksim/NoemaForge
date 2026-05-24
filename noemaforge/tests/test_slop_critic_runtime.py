#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_slop_critic_runtime.py
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate Slop_Score and Critic_Stack contracts as advisory quality gates.
Inputs: Workspace Slop Critic policy and temporary broken fixtures.
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
from unittest.mock import patch

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import production_ai_contracts as pac
import slop_critic_runtime as scr


class SlopCriticRuntimeTests(unittest.TestCase):
    def test_workspace_slop_critic_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "slop-critic-policy.json"
        report = scr.validate_slop_critic_policy(
            scr.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(2, report["metrics"]["cases"])
        self.assertEqual(2, report["metrics"]["passing_cases"])
        self.assertEqual(2, report["metrics"]["scoring_cases"])
        self.assertEqual(2, report["metrics"]["passing_scoring_cases"])

        gate = pac.evaluate_gate(
            {"change_id": "slop-critic-governance-core", "domain": "pipeline"},
            scr.slop_critic_report_to_gate_evidence(report, artifact_uri="reports/slop-critic.json"),
        )
        self.assertTrue(gate["ok"], gate)

    def test_band_out_of_range_and_aggregate_mismatch_are_blocked(self) -> None:
        policy_path = ROOT / "configs" / "slop-critic-policy.json"
        policy = scr.load_policy(policy_path)
        example_set = scr.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "slop_critic.example.json")
        case = example_set["cases"][0]
        case["slop_score"]["bands"]["genericity"] = 1.2
        case["slop_score"]["aggregate_score"] = 0.99

        with patch.object(scr, "load_example_set", return_value=example_set):
            report = scr.validate_slop_critic_policy(
                policy,
                project_root=PROJECT_ROOT,
                package_root=ROOT,
                policy_path=policy_path,
            )

        self.assertFalse(report["ok"])
        self.assertIn("case_band_out_of_range:slop-critic-grounded-clean:genericity:1.2", report["failures"])
        self.assertIn("case_aggregate_mismatch:slop-critic-grounded-clean:0.99:0.285", report["failures"])

    def test_single_detector_truth_and_missing_critic_types_are_blocked(self) -> None:
        policy_path = ROOT / "configs" / "slop-critic-policy.json"
        policy = scr.load_policy(policy_path)
        example_set = scr.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "slop_critic.example.json")
        case = example_set["cases"][0]
        case["critic_stack"] = [case["critic_stack"][0]]
        case["detection_verdict"]["advisory"] = False
        case["detection_verdict"]["single_detector_decision"] = True
        case["finalization"]["final_without_critic_aggregation"] = True

        with patch.object(scr, "load_example_set", return_value=example_set):
            report = scr.validate_slop_critic_policy(
                policy,
                project_root=PROJECT_ROOT,
                package_root=ROOT,
                policy_path=policy_path,
            )

        self.assertFalse(report["ok"])
        self.assertIn("case_required_critics_missing:slop-critic-grounded-clean", report["failures"])
        self.assertIn("case_verdict_not_advisory:slop-critic-grounded-clean", report["failures"])
        self.assertIn("case_single_detector_truth_allowed:slop-critic-grounded-clean", report["failures"])
        self.assertIn("case_final_without_critics_allowed:slop-critic-grounded-clean", report["failures"])

    def test_score_text_artifact_flags_generic_unsupported_text_and_allows_grounded_text(self) -> None:
        policy = scr.load_policy(ROOT / "configs" / "slop-critic-policy.json")

        risky = scr.score_text_artifact(
            {
                "content": "This cutting-edge solution always works. This cutting-edge solution always works. It optimizes everything.",
                "evidence_refs": [],
                "provenance": {"present": False},
            },
            policy,
        )
        self.assertGreaterEqual(risky["slop_score"]["aggregate_score"], 0.6)
        self.assertEqual("escalate", risky["slop_score"]["action"])
        self.assertEqual("unknown", risky["detection_verdict"]["decision"])
        self.assertFalse(risky["detection_verdict"]["single_detector_decision"])

        grounded = scr.score_text_artifact(
            {
                "content": "The policy file declares advisory_by_default=true and requires text, provenance, and slop critics.",
                "evidence_refs": ["noemaforge/configs/slop-critic-policy.json"],
                "provenance": {"present": True, "manifest_ref": "prelaunch/governance/slop_critic.example.json"},
            },
            policy,
        )
        self.assertLessEqual(grounded["slop_score"]["aggregate_score"], 0.3)
        self.assertEqual("allow", grounded["slop_score"]["action"])
        self.assertEqual("clean", grounded["detection_verdict"]["decision"])


if __name__ == "__main__":
    unittest.main()
