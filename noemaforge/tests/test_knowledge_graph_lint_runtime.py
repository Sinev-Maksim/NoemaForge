#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_knowledge_graph_lint_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate knowledge graph lint runtime behavior.
Inputs: Workspace Knowledge Graph Lint policy and offline example graph.
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

import knowledge_graph_lint_runtime as kgl


class KnowledgeGraphLintRuntimeTests(unittest.TestCase):
    def test_workspace_knowledge_graph_lint_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "knowledge-graph-lint-policy.json"
        validation = kgl.validate_knowledge_graph_lint_policy(
            kgl.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(validation["ok"], validation["failures"])
        self.assertEqual(5, validation["metrics"]["finding_types"])
        self.assertEqual(2, validation["metrics"]["loop_targets"])
        self.assertEqual(2, validation["metrics"]["target_roles"])
        self.assertEqual(1, validation["metrics"]["passing_scenarios"])

    def test_lint_detects_all_required_maintenance_findings(self) -> None:
        examples = kgl.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "knowledge_graph_lint.example.json")
        graph = examples["scenarios"][0]["graph"]

        report = kgl.lint_knowledge_graph(graph, stale_after_days=45, weak_bridge_strength_below=0.5)
        finding_types = {item["type"] for item in report["findings"]}

        self.assertEqual(
            {"orphan_concept", "unsupported_claim", "stale_passage", "unresolved_conflict", "weak_realm_bridge"},
            finding_types,
        )
        self.assertIn("Administrator", report["metrics"]["target_roles"])
        self.assertIn("Surgeon", report["metrics"]["target_roles"])
        self.assertIn("prestart", report["metrics"]["loop_targets"])
        self.assertIn("scheduled_maintenance", report["metrics"]["loop_targets"])
        self.assertEqual(len(report["findings"]), len(report["maintenance_work"]))

    def test_clean_graph_has_no_maintenance_findings(self) -> None:
        graph = {
            "graph_ref": "hypergraph:clean",
            "concepts": [{"id": "concept:admin", "labels": ["Admin"]}],
            "claims": [
                {
                    "id": "claim:ok",
                    "status": "supported",
                    "concept_ids": ["concept:admin"],
                    "passage_refs": ["passage:ok"],
                    "citations": ["source:ok"],
                }
            ],
            "passages": [{"id": "passage:ok", "age_days": 1, "claim_ids": ["claim:ok"]}],
            "conflicts": [{"id": "conflict:closed", "status": "resolved"}],
            "realm_bridges": [{"id": "bridge:ok", "strength": 0.9, "evidence_refs": ["source:ok"]}],
        }

        report = kgl.lint_knowledge_graph(graph)
        self.assertTrue(report["ok"], report)
        self.assertEqual([], report["findings"])


if __name__ == "__main__":
    unittest.main()
