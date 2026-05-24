#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_knowledge_purpose_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate knowledge purpose artifact runtime behavior.
Inputs: Workspace Knowledge Purpose policy and offline example artifact.
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

import knowledge_purpose_runtime as kpr


class KnowledgePurposeRuntimeTests(unittest.TestCase):
    def test_workspace_knowledge_purpose_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "knowledge-purpose-policy.json"
        validation = kpr.validate_knowledge_purpose_policy(
            kpr.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(validation["ok"], validation["failures"])
        self.assertEqual(10, validation["metrics"]["artifact_fields"])
        self.assertEqual(3, validation["metrics"]["decision_stages"])
        self.assertEqual(1, validation["metrics"]["scenarios"])
        self.assertEqual(1, validation["metrics"]["passing_scenarios"])

    def test_purpose_decisions_cover_ingest_lint_and_review(self) -> None:
        examples = kpr.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "knowledge_purpose.example.json")
        scenario = examples["scenarios"][0]
        purpose = scenario["purpose_artifact"]

        results = [
            kpr.evaluate_knowledge_item_against_purpose(purpose, item["knowledge_item"], stage=item["stage"])
            for item in scenario["decisions"]
        ]

        self.assertEqual(["accept", "reject", "defer"], [item["decision"] for item in results])
        self.assertIn("topic_out_of_scope", results[1]["reasons"])
        self.assertIn("update_policy_review_required", results[2]["reasons"])

    def test_missing_scope_or_source_quality_never_silently_accepts(self) -> None:
        examples = kpr.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "knowledge_purpose.example.json")
        purpose = examples["scenarios"][0]["purpose_artifact"]
        result = kpr.evaluate_knowledge_item_against_purpose(
            purpose,
            {"id": "item:bad", "topic": "Unknown folklore", "source_quality": "manual_memory_only", "age_days": 1},
            stage="ingest",
        )

        self.assertEqual("reject", result["decision"])
        self.assertIn("source_quality_below_purpose_floor", result["reasons"])


if __name__ == "__main__":
    unittest.main()
