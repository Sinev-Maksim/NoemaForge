#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_topic_adjacent_retrieval_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate Topic-Adjacent Retrieval contract runtime behavior.
Inputs: Workspace Topic-Adjacent Retrieval policy, prep pipeline/store sources and example set.
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

import production_ai_contracts as pac
import topic_adjacent_retrieval_runtime as tar


class TopicAdjacentRetrievalRuntimeTests(unittest.TestCase):
    def test_workspace_topic_adjacent_retrieval_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "topic-adjacent-retrieval-policy.json"
        validation = tar.validate_topic_adjacent_retrieval_policy(
            tar.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(validation["ok"], validation["failures"])
        self.assertEqual(1, validation["metrics"]["scenarios"])
        self.assertEqual(1, validation["metrics"]["passing_scenarios"])
        self.assertGreaterEqual(validation["metrics"]["locality_fields"], 5)

        gate = pac.evaluate_gate(
            {"change_id": "topic-adjacent-retrieval-core", "domain": "rag"},
            tar.topic_adjacent_retrieval_report_to_gate_evidence(validation, artifact_uri="reports/topic-adjacent-retrieval.json"),
        )
        self.assertTrue(gate["ok"], gate)

    def test_ranker_prefers_local_topic_adjacent_support_over_distant_same_label(self) -> None:
        result = tar.rank_topic_adjacent_candidates(
            [
                {
                    "chunk_id": "local-primary",
                    "chapter_id": "c1",
                    "section_id": "s1",
                    "topic_signature": "knowledge|administrator|provenance",
                    "coherence_score": 0.9,
                    "estimated_tokens": 100,
                    "adjacency_group_id": "adj:1",
                    "sentence_start_id": "1",
                },
                {
                    "chunk_id": "local-support",
                    "chapter_id": "c1",
                    "section_id": "s1",
                    "topic_signature": "knowledge|administrator|citation",
                    "coherence_score": 0.75,
                    "estimated_tokens": 70,
                    "adjacency_group_id": "adj:1",
                    "sentence_start_id": "2",
                },
                {
                    "chunk_id": "distant-same-label",
                    "chapter_id": "c9",
                    "section_id": "s1",
                    "topic_signature": "knowledge|administrator|citation",
                    "coherence_score": 0.99,
                    "estimated_tokens": 50,
                    "adjacency_group_id": "adj:9",
                    "sentence_start_id": "9",
                },
            ],
            query_signature="knowledge|administrator|provenance",
            max_tokens=200,
            locality_scope={"chapter_id": "c1", "section_id": "s1"},
        )

        self.assertEqual("local-primary", result["primary_chunk"]["chunk_id"])
        self.assertEqual(["local-support"], [item["chunk_id"] for item in result["adjacent_support_chunks"]])
        self.assertIn("outside chapter/section locality", {item["reason"] for item in result["rejected_chunks"]})

    def test_ranker_does_not_add_support_without_remaining_budget(self) -> None:
        result = tar.rank_topic_adjacent_candidates(
            [
                {
                    "chunk_id": "primary",
                    "chapter_id": "c1",
                    "section_id": "s1",
                    "topic_signature": "knowledge|administrator",
                    "coherence_score": 0.9,
                    "estimated_tokens": 150,
                    "adjacency_group_id": "adj:1",
                },
                {
                    "chunk_id": "support-too-large",
                    "chapter_id": "c1",
                    "section_id": "s1",
                    "topic_signature": "knowledge|administrator",
                    "coherence_score": 0.8,
                    "estimated_tokens": 100,
                    "adjacency_group_id": "adj:1",
                },
            ],
            query_signature="knowledge|administrator",
            max_tokens=180,
            locality_scope={"chapter_id": "c1", "section_id": "s1"},
        )

        self.assertEqual(["primary"], [item["chunk_id"] for item in result["selected_chunks"]])
        self.assertEqual(30, result["budget_remaining"])
        self.assertIn("token budget exceeded", {item["reason"] for item in result["rejected_chunks"]})

    def test_static_sources_expose_adjacency_metadata_not_fixed_windows(self) -> None:
        policy = tar.load_policy(ROOT / "configs" / "topic-adjacent-retrieval-policy.json")
        validation = tar.validate_topic_adjacent_retrieval_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)

        self.assertTrue(validation["ok"], validation["failures"])
        reports = {item["ref"]: item for item in validation["static"]["reports"]}
        self.assertTrue(reports["src/knowledge/prep_pipeline.py"]["ok"])
        self.assertTrue(reports["src/knowledge/prep_store.py"]["ok"])
        self.assertTrue(reports["docs/architecture/ARCHITECTURE.md"]["ok"])

    def test_example_rejects_blocked_retrieval_claims(self) -> None:
        policy = tar.load_policy(ROOT / "configs" / "topic-adjacent-retrieval-policy.json")
        examples = tar.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "topic_adjacent_retrieval.example.json")
        blocked = set(policy["policy"]["blocked_retrieval_claims"])
        claims = {item["claim"] for item in examples["scenarios"][0]["rejected_retrievals"]}

        self.assertEqual(blocked, claims)
        self.assertEqual("best_matching_coherent_chunk", examples["scenarios"][0]["retrieval_order"][0])
        self.assertEqual("adjacent_support_chunks_if_budget_remains", examples["scenarios"][0]["retrieval_order"][2])


if __name__ == "__main__":
    unittest.main()
