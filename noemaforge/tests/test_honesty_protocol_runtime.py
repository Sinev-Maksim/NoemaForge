#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_honesty_protocol_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Validate Honesty Protocol contracts for unknown, need-research and error-attribution states.
Inputs: Workspace Honesty Protocol policy and temporary broken fixtures.
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

import honesty_protocol_runtime as hpr
import production_ai_contracts as pac


class HonestyProtocolRuntimeTests(unittest.TestCase):
    def test_workspace_honesty_protocol_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "honesty-protocol-policy.json"
        report = hpr.validate_honesty_protocol_policy(
            hpr.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(3, report["metrics"]["cases"])
        self.assertEqual(3, report["metrics"]["passing_cases"])
        self.assertEqual(3, report["metrics"]["classification_cases"])
        self.assertEqual(3, report["metrics"]["passing_classification_cases"])
        self.assertEqual(0, report["metrics"]["missing_template_states"])

        gate = pac.evaluate_gate(
            {"change_id": "honesty-protocol-governance-core", "domain": "pipeline"},
            hpr.honesty_protocol_report_to_gate_evidence(report, artifact_uri="reports/honesty-protocol.json"),
        )
        self.assertTrue(gate["ok"], gate)

    def test_confident_unknown_is_blocked(self) -> None:
        policy_path = ROOT / "configs" / "honesty-protocol-policy.json"
        policy = hpr.load_policy(policy_path)
        example_set = hpr.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "honesty_protocol.example.json")
        case = example_set["cases"][0]
        case["confidence"] = 0.91

        with patch.object(hpr, "load_example_set", return_value=example_set):
            report = hpr.validate_honesty_protocol_policy(
                policy,
                project_root=PROJECT_ROOT,
                package_root=ROOT,
                policy_path=policy_path,
            )

        self.assertFalse(report["ok"])
        self.assertIn("case_uncertain_confidence_too_high:honesty-unknown-no-evidence:0.91", report["failures"])

    def test_fabricated_citations_blame_shift_and_missing_repair_are_blocked(self) -> None:
        policy_path = ROOT / "configs" / "honesty-protocol-policy.json"
        policy = hpr.load_policy(policy_path)
        example_set = hpr.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "honesty_protocol.example.json")
        case = example_set["cases"][0]
        case["response_template"]["user_message"] = "Source: https://example.invalid says it is true."
        case["response_template"]["repair_action"] = ""
        case["guards"]["fabricated_citations"] = True
        case["guards"]["blame_shift"] = True

        with patch.object(hpr, "load_example_set", return_value=example_set):
            report = hpr.validate_honesty_protocol_policy(
                policy,
                project_root=PROJECT_ROOT,
                package_root=ROOT,
                policy_path=policy_path,
            )

        self.assertFalse(report["ok"])
        self.assertIn("case_fabricated_citation_risk:honesty-unknown-no-evidence", report["failures"])
        self.assertIn("case_fabricated_citations_allowed:honesty-unknown-no-evidence", report["failures"])
        self.assertIn("case_blame_shift_allowed:honesty-unknown-no-evidence", report["failures"])
        self.assertIn("case_repair_action_missing:honesty-unknown-no-evidence", report["failures"])

    def test_classifier_emits_first_class_states_and_clips_uncertainty(self) -> None:
        policy = hpr.load_policy(ROOT / "configs" / "honesty-protocol-policy.json")

        unknown = hpr.classify_honesty_event({"trace_id": "trace:test:unknown", "confidence": 0.9, "evidence_refs": []}, policy)
        self.assertEqual("unknown", unknown["state"])
        self.assertLessEqual(unknown["confidence"], policy["policy"]["max_uncertain_confidence"])
        self.assertEqual("ask_clarification", unknown["response_template"]["next_action"])

        need_research = hpr.classify_honesty_event(
            {"trace_id": "trace:test:fresh", "confidence": 0.7, "freshness_required": True, "evidence_refs": ["docs/wiki/architecture/typed-control-plane-sense-critics-rfc-0.31.13.alpha-patched1.md"]},
            policy,
        )
        self.assertEqual("need_research", need_research["state"])
        self.assertEqual("request_research", need_research["response_template"]["next_action"])

        error = hpr.classify_honesty_event(
            {"trace_id": "trace:test:error", "confidence": 0.8, "error": {"class": "tool_error", "summary": "timeout"}},
            policy,
        )
        self.assertEqual("error_attribution", error["state"])
        self.assertEqual("tool_error", error["error_attribution"]["class"])
        self.assertEqual("correct_error", error["response_template"]["next_action"])


if __name__ == "__main__":
    unittest.main()
