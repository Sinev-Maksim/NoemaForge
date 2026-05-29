#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_graph_gap_notice_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate Graph Gap Notice contract runtime behavior.
Inputs: Workspace Graph Gap Notice policy, grounded administrator sources and example set.
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

import graph_gap_notice_runtime as ggn
import production_ai_contracts as pac
from knowledge.grounded_administrator import answer_query


class EmptyStore:
    def get_claim(self, claim_id: str):
        return None


class EmptyPrep:
    def list_claim_origins(self, *, book_id: str):
        return []


class GraphGapNoticeRuntimeTests(unittest.TestCase):
    def test_workspace_graph_gap_notice_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "graph-gap-notice-policy.json"
        validation = ggn.validate_graph_gap_notice_policy(
            ggn.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(validation["ok"], validation["failures"])
        self.assertEqual(1, validation["metrics"]["scenarios"])
        self.assertEqual(1, validation["metrics"]["passing_scenarios"])
        self.assertGreaterEqual(validation["metrics"]["gap_followups"], 3)

        gate = pac.evaluate_gate(
            {"change_id": "graph-gap-notice-core", "domain": "rag"},
            ggn.graph_gap_notice_report_to_gate_evidence(validation, artifact_uri="reports/graph-gap-notice.json"),
        )
        self.assertTrue(gate["ok"], gate)

    def test_answer_query_graph_miss_returns_gap_notice_with_ingest_and_research(self) -> None:
        answer = answer_query(
            store=EmptyStore(),
            prep_store=EmptyPrep(),
            query="What does unmapped local graph topic mean?",
            book_id="book:fixture",
        )

        self.assertEqual("knowledge_gap_notice", answer["mode"])
        self.assertFalse(answer["grounded"])
        self.assertEqual([], answer["citations"])
        classified = set(ggn.classify_gap_followups(answer["followup"]))
        self.assertIn("ingest_relevant_source", classified)
        self.assertIn("propose_research", classified)

    def test_examples_reject_improvised_gap_answers(self) -> None:
        policy = ggn.load_policy(ROOT / "configs" / "graph-gap-notice-policy.json")
        examples = ggn.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "graph_gap_notice.example.json")
        blocked = set(policy["policy"]["blocked_answer_claims"])
        claims = {item["claim"] for item in examples["scenarios"][0]["rejected_answers"]}

        self.assertEqual(blocked, claims)
        self.assertEqual("knowledge_gap_notice", examples["scenarios"][0]["gap_answer"]["mode"])
        self.assertEqual([], examples["scenarios"][0]["gap_answer"]["citations"])


if __name__ == "__main__":
    unittest.main()
