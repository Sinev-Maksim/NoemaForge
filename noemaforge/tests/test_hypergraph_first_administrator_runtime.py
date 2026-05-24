#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_hypergraph_first_administrator_runtime.py
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate Hypergraph-First Administrator contract runtime behavior.
Inputs: Workspace Hypergraph-First Administrator policy, grounded administrator sources and example set.
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

import hypergraph_first_administrator_runtime as hfa
import production_ai_contracts as pac
from knowledge.grounded_administrator import answer_query


class RecordingStore:
    def __init__(self, events):
        self.events = events
        self.claims = {
            "claim:admin-hypergraph-first": {
                "text_normalized": "Administrator grounded knowledge starts from hypergraph provenance.",
                "confidence": 0.95,
                "about_concepts": ["Administrator", "hypergraph", "provenance"],
            }
        }

    def get_claim(self, claim_id: str):
        self.events.append(f"store.get_claim:{claim_id}")
        return self.claims.get(claim_id)


class RecordingPrep:
    def __init__(self, events, origins):
        self.events = events
        self.origins = origins

    def list_claim_origins(self, *, book_id: str):
        self.events.append(f"prep.list_claim_origins:{book_id}")
        return list(self.origins)


class HypergraphFirstAdministratorRuntimeTests(unittest.TestCase):
    def test_workspace_hypergraph_first_administrator_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "hypergraph-first-administrator-policy.json"
        validation = hfa.validate_hypergraph_first_administrator_policy(
            hfa.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(validation["ok"], validation["failures"])
        self.assertEqual(1, validation["metrics"]["scenarios"])
        self.assertEqual(1, validation["metrics"]["passing_scenarios"])
        self.assertGreaterEqual(validation["metrics"]["trace_fields"], 4)

        gate = pac.evaluate_gate(
            {"change_id": "hypergraph-first-administrator-core", "domain": "rag"},
            hfa.hypergraph_first_administrator_report_to_gate_evidence(validation, artifact_uri="reports/hypergraph-first-administrator.json"),
        )
        self.assertTrue(gate["ok"], gate)

    def test_answer_query_reads_claim_origins_before_claim_text(self) -> None:
        events = []
        prep = RecordingPrep(
            events,
            [
                {
                    "claim_id": "claim:admin-hypergraph-first",
                    "primary_address": {"human_address": "knowledge.hypergraph.yaml#success_signals[1]"},
                }
            ],
        )
        answer = answer_query(
            store=RecordingStore(events),
            prep_store=prep,
            query="How does Administrator use hypergraph provenance?",
            book_id="book:fixture",
        )

        self.assertEqual("prep.list_claim_origins:book:fixture", events[0])
        self.assertTrue(any(item.startswith("store.get_claim:") for item in events[1:]))
        self.assertEqual("grounded_answer", answer["mode"])
        self.assertTrue(answer["citations"])
        self.assertEqual("knowledge.hypergraph.yaml#success_signals[1]", answer["citations"][0]["human_address"])

    def test_fallback_trace_only_allows_docs_after_graph_miss(self) -> None:
        with_graph_hit = hfa.build_hypergraph_first_trace(graph_claim_origin_count=2, docs_fallback_requested=True)
        graph_miss = hfa.build_hypergraph_first_trace(graph_claim_origin_count=0, docs_fallback_requested=True)

        self.assertEqual("hypergraph_claim_origins", with_graph_hit["first_retrieval_surface"])
        self.assertFalse(with_graph_hit["fallback_allowed"])
        self.assertTrue(graph_miss["fallback_allowed"])

    def test_examples_reject_blocked_hypergraph_first_claims(self) -> None:
        policy = hfa.load_policy(ROOT / "configs" / "hypergraph-first-administrator-policy.json")
        examples = hfa.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "hypergraph_first_administrator.example.json")
        blocked = set(policy["policy"]["blocked_answer_claims"])
        claims = {item["claim"] for item in examples["scenarios"][0]["rejected_answers"]}

        self.assertEqual(blocked, claims)
        self.assertEqual("hypergraph_claim_origins", examples["scenarios"][0]["retrieval_order"][0])
        self.assertFalse(examples["scenarios"][0]["retrieval_trace"]["fallback_allowed"])


if __name__ == "__main__":
    unittest.main()
