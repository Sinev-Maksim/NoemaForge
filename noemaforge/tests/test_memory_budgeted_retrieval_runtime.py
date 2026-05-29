#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_memory_budgeted_retrieval_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate Memory-Budgeted Retrieval contract runtime behavior.
Inputs: Workspace Memory-Budgeted Retrieval policy, prep pipeline/store sources and example set.
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

import memory_budgeted_retrieval_runtime as mbr
import production_ai_contracts as pac


class MemoryBudgetedRetrievalRuntimeTests(unittest.TestCase):
    def test_workspace_memory_budgeted_retrieval_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "memory-budgeted-retrieval-policy.json"
        validation = mbr.validate_memory_budgeted_retrieval_policy(
            mbr.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(validation["ok"], validation["failures"])
        self.assertEqual(1, validation["metrics"]["scenarios"])
        self.assertEqual(1, validation["metrics"]["passing_scenarios"])
        self.assertGreaterEqual(validation["metrics"]["lineage_fields"], 6)

        gate = pac.evaluate_gate(
            {"change_id": "memory-budgeted-retrieval-core", "domain": "rag"},
            mbr.memory_budgeted_retrieval_report_to_gate_evidence(validation, artifact_uri="reports/memory-budgeted-retrieval.json"),
        )
        self.assertTrue(gate["ok"], gate)

    def test_planner_selects_highest_coherence_subchunks_before_support_neighbors(self) -> None:
        plan = mbr.plan_memory_budgeted_retrieval(
            chunk_chain={"chain_id": "chain:1", "estimated_tokens": 400},
            subchunks=[
                {"chunk_id": "low", "chunk_parent_id": "chain:1", "chunk_split_reason": "active_memory_budget", "leaf_sequence_no": 3, "coherence_score": 0.5, "estimated_tokens": 100},
                {"chunk_id": "high", "chunk_parent_id": "chain:1", "chunk_split_reason": "active_memory_budget", "leaf_sequence_no": 1, "coherence_score": 0.95, "estimated_tokens": 100},
                {"chunk_id": "mid", "chunk_parent_id": "chain:1", "chunk_split_reason": "active_memory_budget", "leaf_sequence_no": 2, "coherence_score": 0.8, "estimated_tokens": 90},
            ],
            support_neighbors=[
                {"chunk_id": "support", "coherence_score": 0.7, "estimated_tokens": 40},
            ],
            max_tokens=235,
        )

        self.assertEqual("highest_coherence_subchunks", plan["degradation_mode"])
        self.assertEqual(["high", "mid"], [item["chunk_id"] for item in plan["selected_subchunks"]])
        self.assertEqual(["support"], [item["chunk_id"] for item in plan["selected_support_neighbors"]])
        self.assertEqual(5, plan["budget_remaining"])
        self.assertTrue(plan["partial_context_notice"])

    def test_planner_rejects_support_neighbors_without_remaining_budget(self) -> None:
        plan = mbr.plan_memory_budgeted_retrieval(
            chunk_chain={"chain_id": "chain:1", "estimated_tokens": 300},
            subchunks=[
                {"chunk_id": "a", "chunk_parent_id": "chain:1", "chunk_split_reason": "active_memory_budget", "leaf_sequence_no": 1, "coherence_score": 0.9, "estimated_tokens": 100},
                {"chunk_id": "b", "chunk_parent_id": "chain:1", "chunk_split_reason": "active_memory_budget", "leaf_sequence_no": 2, "coherence_score": 0.8, "estimated_tokens": 90},
            ],
            support_neighbors=[
                {"chunk_id": "support-too-large", "coherence_score": 0.7, "estimated_tokens": 60},
            ],
            max_tokens=220,
        )

        self.assertEqual(["a", "b"], [item["chunk_id"] for item in plan["selected_subchunks"]])
        self.assertEqual([], plan["selected_support_neighbors"])
        self.assertEqual(30, plan["budget_remaining"])
        self.assertIn("token budget exceeded", {item["reason"] for item in plan["rejected_neighbors"]})

    def test_planner_rejects_subchunks_without_lineage(self) -> None:
        plan = mbr.plan_memory_budgeted_retrieval(
            chunk_chain={"chain_id": "chain:1", "estimated_tokens": 300},
            subchunks=[
                {"chunk_id": "missing-lineage", "coherence_score": 0.9, "estimated_tokens": 50},
            ],
            support_neighbors=[],
            max_tokens=100,
        )

        self.assertEqual([], plan["selected_subchunks"])
        self.assertIn("lineage fields missing", plan["rejected_subchunks"][0]["reason"])

    def test_examples_reject_blocked_degradation_claims(self) -> None:
        policy = mbr.load_policy(ROOT / "configs" / "memory-budgeted-retrieval-policy.json")
        examples = mbr.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "memory_budgeted_retrieval.example.json")
        blocked = set(policy["policy"]["blocked_retrieval_claims"])
        claims = {item["claim"] for item in examples["scenarios"][0]["rejected_plans"]}

        self.assertEqual(blocked, claims)
        self.assertEqual(["chunk:knowledge-admin:primary:a", "chunk:knowledge-admin:primary:b"], examples["scenarios"][0]["selected_subchunks"])
        self.assertEqual(["chunk:knowledge-admin:support:left"], examples["scenarios"][0]["selected_support_neighbors"])


if __name__ == "__main__":
    unittest.main()
