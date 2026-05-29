#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_evaluation_gate_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Validate the executable EvaluationGate runtime smoke checks.
Inputs: Built-in gate fixtures and one intentionally broken fixture.
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
sys.path.insert(0, str(ROOT / "src"))

import evaluation_gate_runtime as egr
import production_ai_contracts as pac


class EvaluationGateRuntimeTests(unittest.TestCase):
    def test_default_gate_validation_covers_all_domains(self) -> None:
        report = egr.validate_evaluation_gate()

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(sorted(pac.CHANGE_DOMAINS), report["domain_coverage"])
        self.assertEqual([], report["missing_domains"])
        self.assertEqual(9, report["metrics"]["fixture_total"])
        self.assertEqual(9, report["metrics"]["fixture_passed"])
        self.assertEqual(0, report["metrics"]["fixture_failed"])

        blocked = {row["id"]: row for row in report["fixtures"] if not row["actual_ok"]}
        self.assertIn("router_missing_required_check_blocks", blocked)
        self.assertIn("check_missing:per_route_metrics", blocked["router_missing_required_check_blocks"]["failures"])
        self.assertIn("rag_below_threshold_blocks", blocked)
        self.assertIn("check_below_threshold:groundedness", blocked["rag_below_threshold_blocks"]["failures"])

    def test_gate_validation_blocks_unexpected_allow(self) -> None:
        report = egr.validate_evaluation_gate(
            fixtures=[
                {
                    "id": "bad_expectation",
                    "domain": "code",
                    "expected_ok": False,
                    "expected_failure": "check_missing:unit_tests",
                    "change": {"change_id": "code-ok", "domain": "code"},
                    "evidence": {
                        "artifact_uri": "reports/code.json",
                        "run_at": "2026-05-19T00:00:00Z",
                        "checks": [
                            {"id": "unit_tests", "status": "passed"},
                            {"id": "static_contract_scan", "status": "passed"},
                        ],
                    },
                }
            ]
        )

        self.assertFalse(report["ok"])
        self.assertIn("fixture_failed:bad_expectation", report["failures"])
        self.assertIn("domain_missing:rag", report["failures"])


if __name__ == "__main__":
    unittest.main()
