#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_provenance_watermark_runtime.py
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate provenance/watermark hook and Detection_Verdict contracts.
Inputs: Workspace provenance/watermark policy and temporary broken fixtures.
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
import provenance_watermark_runtime as pwr


class ProvenanceWatermarkRuntimeTests(unittest.TestCase):
    def test_workspace_provenance_watermark_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "provenance-watermark-policy.json"
        report = pwr.validate_provenance_watermark_policy(
            pwr.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(2, report["metrics"]["cases"])
        self.assertEqual(2, report["metrics"]["passing_cases"])
        self.assertEqual(3, report["metrics"]["scoring_cases"])
        self.assertEqual(3, report["metrics"]["passing_scoring_cases"])

        gate = pac.evaluate_gate(
            {"change_id": "provenance-watermark-verdict-core", "domain": "pipeline"},
            pwr.provenance_watermark_report_to_gate_evidence(report, artifact_uri="reports/provenance-watermark.json"),
        )
        self.assertTrue(gate["ok"], gate)

    def test_single_detector_truth_and_missing_aggregation_are_blocked(self) -> None:
        policy_path = ROOT / "configs" / "provenance-watermark-policy.json"
        policy = pwr.load_policy(policy_path)
        example_set = pwr.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "provenance_watermark.example.json")
        case = example_set["cases"][0]
        case["aggregated_detection_verdict"]["advisory"] = False
        case["aggregated_detection_verdict"]["single_detector_decision"] = True
        case["aggregated_detection_verdict"]["aggregated_from"] = ["watermark_signal"]
        case["finalization"]["final_without_critic_aggregation"] = True

        with patch.object(pwr, "load_example_set", return_value=example_set):
            report = pwr.validate_provenance_watermark_policy(
                policy,
                project_root=PROJECT_ROOT,
                package_root=ROOT,
                policy_path=policy_path,
            )

        self.assertFalse(report["ok"])
        self.assertIn("case_verdict_not_advisory:provenance-watermark-clean-local", report["failures"])
        self.assertIn("case_single_detector_truth_allowed:provenance-watermark-clean-local", report["failures"])
        self.assertIn("case_required_signal_inputs_missing:provenance-watermark-clean-local", report["failures"])
        self.assertIn("case_final_without_critics_allowed:provenance-watermark-clean-local", report["failures"])

    def test_missing_hooks_and_verdict_mismatch_are_blocked(self) -> None:
        policy_path = ROOT / "configs" / "provenance-watermark-policy.json"
        policy = pwr.load_policy(policy_path)
        example_set = pwr.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "provenance_watermark.example.json")
        case = example_set["cases"][0]
        case["artifact"]["hooks"] = [{"type": "watermark", "status": "verified"}]
        case["aggregated_detection_verdict"]["risk_score"] = 0.99
        case["aggregated_detection_verdict"]["decision"] = "advisory_manipulated"

        with patch.object(pwr, "load_example_set", return_value=example_set):
            report = pwr.validate_provenance_watermark_policy(
                policy,
                project_root=PROJECT_ROOT,
                package_root=ROOT,
                policy_path=policy_path,
            )

        self.assertFalse(report["ok"])
        self.assertIn("case_required_hooks_missing:provenance-watermark-clean-local", report["failures"])
        self.assertIn("case_risk_score_mismatch:provenance-watermark-clean-local:0.99:0.0", report["failures"])
        self.assertIn("case_decision_mismatch:provenance-watermark-clean-local:advisory_manipulated:clean", report["failures"])

    def test_aggregate_detection_verdict_escalates_mismatch_and_allows_clean(self) -> None:
        policy = pwr.load_policy(ROOT / "configs" / "provenance-watermark-policy.json")

        risky = pwr.aggregate_detection_verdict(
            {
                "source_manifest_ref": "prelaunch/governance/slop_critic.example.json",
                "signature": {"present": True, "verified": False},
                "watermark": {"present": False, "verified": False, "confidence": 0.1},
                "consistency": {"content_hash_match": False, "manifest_subject_match": False},
                "hooks": [
                    {"type": "manifest", "status": "present"},
                    {"type": "signature", "status": "failed"},
                    {"type": "watermark", "status": "absent"},
                    {"type": "content_hash", "status": "failed"},
                ],
            },
            policy,
        )
        verdict = risky["aggregated_detection_verdict"]
        self.assertGreaterEqual(verdict["risk_score"], 0.7)
        self.assertEqual("escalate", verdict["action"])
        self.assertEqual("advisory_manipulated", verdict["decision"])
        self.assertFalse(verdict["single_detector_decision"])

        clean = pwr.aggregate_detection_verdict(
            {
                "source_manifest_ref": "prelaunch/governance/slop_critic.example.json",
                "signature": {"present": True, "verified": True},
                "watermark": {"present": True, "verified": True, "confidence": 0.95},
                "consistency": {"content_hash_match": True, "manifest_subject_match": True},
                "hooks": [
                    {"type": "manifest", "status": "verified"},
                    {"type": "signature", "status": "verified"},
                    {"type": "watermark", "status": "verified"},
                    {"type": "content_hash", "status": "verified"},
                ],
            },
            policy,
        )
        verdict = clean["aggregated_detection_verdict"]
        self.assertEqual(0.0, verdict["risk_score"])
        self.assertEqual("allow", verdict["action"])
        self.assertEqual("clean", verdict["decision"])


if __name__ == "__main__":
    unittest.main()
