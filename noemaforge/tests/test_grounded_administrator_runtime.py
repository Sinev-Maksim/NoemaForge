#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_grounded_administrator_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate Grounded Administrator contract runtime behavior.
Inputs: Workspace Grounded Administrator policy, knowledge manifest, RAG policies and example set.
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

import grounded_administrator_runtime as gar
import production_ai_contracts as pac
from knowledge.grounded_administrator import answer_query


class FakeStore:
    def __init__(self) -> None:
        self.claims = {
            "claim:admin-grounded": {
                "text_normalized": "A01 shows the Administrator should answer from graph-backed provenance.",
                "confidence": 0.92,
                "about_concepts": ["A01", "Administrator", "provenance"],
            }
        }

    def get_claim(self, claim_id: str):
        return self.claims.get(claim_id)


class FakePrep:
    def __init__(self, origins):
        self.origins = origins

    def list_claim_origins(self, *, book_id: str):
        return list(self.origins)


class GroundedAdministratorRuntimeTests(unittest.TestCase):
    def test_workspace_grounded_administrator_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "grounded-administrator-policy.json"
        validation = gar.validate_grounded_administrator_policy(
            gar.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(validation["ok"], validation["failures"])
        self.assertEqual(1, validation["metrics"]["scenarios"])
        self.assertEqual(1, validation["metrics"]["passing_scenarios"])
        self.assertGreaterEqual(validation["metrics"]["citation_fields"], 3)

        gate = pac.evaluate_gate(
            {"change_id": "grounded-administrator-core", "domain": "rag"},
            gar.grounded_administrator_report_to_gate_evidence(validation, artifact_uri="reports/grounded-administrator.json"),
        )
        self.assertTrue(gate["ok"], gate)

    def test_answer_query_requires_claim_origin_and_human_address(self) -> None:
        prep = FakePrep(
            [
                {
                    "claim_id": "claim:admin-grounded",
                    "primary_address": {"human_address": "knowledge.hypergraph.yaml#success_signals[1]"},
                }
            ]
        )
        answer = answer_query(
            store=FakeStore(),
            prep_store=prep,
            query="Why should Administrator answer with A01 provenance?",
            book_id="book:fixture",
        )

        self.assertTrue(answer["grounded"], answer)
        self.assertEqual("grounded_answer", answer["mode"])
        self.assertIn("graph-backed provenance", answer["answer"])
        self.assertTrue(answer["citations"])
        self.assertEqual("knowledge.hypergraph.yaml#success_signals[1]", answer["citations"][0]["human_address"])

    def test_answer_query_emits_gap_notice_when_graph_has_no_claim(self) -> None:
        answer = answer_query(
            store=FakeStore(),
            prep_store=FakePrep([]),
            query="unmapped default knowledge surface topic",
            book_id="book:fixture",
        )

        self.assertFalse(answer["grounded"], answer)
        self.assertEqual("knowledge_gap_notice", answer["mode"])
        self.assertEqual([], answer["citations"])
        self.assertTrue(any("Ingest" in item for item in answer["followup"]))

    def test_examples_keep_hypergraph_first_order_and_gap_followups(self) -> None:
        policy = gar.load_policy(ROOT / "configs" / "grounded-administrator-policy.json")
        examples = gar.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "grounded_administrator.example.json")
        validation = gar.validate_grounded_administrator_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)

        self.assertTrue(validation["ok"], validation["failures"])
        scenario = examples["scenarios"][0]
        self.assertEqual(["hypergraph_claims", "graph_neighbors"], scenario["retrieval_order"][:2])
        self.assertEqual("grounded_answer", scenario["supported_answer"]["mode"])
        self.assertEqual("knowledge_gap_notice", scenario["gap_answer"]["mode"])
        self.assertIn("ingest_relevant_source", scenario["gap_answer"]["followup"])


if __name__ == "__main__":
    unittest.main()
