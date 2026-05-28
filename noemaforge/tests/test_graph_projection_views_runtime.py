#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_graph_projection_views_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate graph-derived projection view runtime behavior.
Inputs: Workspace Graph Projection Views policy and example graph.
Outputs: unittest assertions only.
Side effects: None.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import graph_projection_views_runtime as gpv
import production_ai_contracts as pac


class GraphProjectionViewsRuntimeTests(unittest.TestCase):
    def test_workspace_graph_projection_views_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "graph-projection-views-policy.json"
        validation = gpv.validate_graph_projection_views_policy(
            gpv.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(validation["ok"], validation["failures"])
        self.assertEqual(4, validation["metrics"]["projection_types"])
        self.assertEqual(1, validation["metrics"]["scenarios"])
        self.assertEqual(1, validation["metrics"]["passing_scenarios"])

        gate = pac.evaluate_gate(
            {"change_id": "graph-projection-views-core", "domain": "rag"},
            gpv.graph_projection_views_report_to_gate_evidence(validation, artifact_uri="reports/graph-projection-views.json"),
        )
        self.assertTrue(gate["ok"], gate)

    def test_projection_builder_marks_views_as_derived_not_canonical(self) -> None:
        examples = gpv.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "graph_projection_views.example.json")
        graph = examples["scenarios"][0]["source_graph"]

        wiki = gpv.build_graph_projection(graph, "wiki_markdown")
        operator = gpv.build_graph_projection(graph, "operator_summary")
        conflict = gpv.build_graph_projection(graph, "conflict_review")

        self.assertTrue(wiki["generated_from_graph"])
        self.assertTrue(wiki["not_source_of_truth"])
        self.assertTrue(wiki["source_graph_digest"].startswith("sha256:"))
        self.assertIn("claim-origin:grounded-admin:001", wiki["citations"])
        self.assertIn("Grounded Administrator", wiki["markdown"])
        self.assertGreaterEqual(len(operator["uncertain"]), 1)
        self.assertEqual(1, conflict["open_conflict_count"])

    def test_projection_artifact_writer_exports_all_b3_views(self) -> None:
        examples = gpv.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "graph_projection_views.example.json")
        graph = examples["scenarios"][0]["source_graph"]

        with tempfile.TemporaryDirectory(prefix="nfg-graph-projections-") as tmp:
            report = gpv.write_projection_artifacts(graph, tmp)
            written = report["written"]

            self.assertEqual({"wiki_markdown", "operator_summary", "task_context", "conflict_review"}, set(written))
            self.assertTrue(Path(written["wiki_markdown"]).exists())
            self.assertTrue(Path(written["operator_summary"]).exists())
            self.assertTrue(Path(written["task_context"]).exists())
            self.assertTrue(Path(written["conflict_review"]).exists())
            self.assertTrue(Path(report["manifest"]).exists())
            wiki_text = Path(written["wiki_markdown"]).read_text(encoding="utf-8")
            self.assertIn("not source of truth", wiki_text)
            self.assertEqual(gpv.graph_digest(graph), report["manifest_payload"]["source_graph_digest"])

    def test_projection_digest_changes_when_graph_changes(self) -> None:
        examples = gpv.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "graph_projection_views.example.json")
        graph = examples["scenarios"][0]["source_graph"]
        changed = dict(graph)
        changed["claims"] = list(graph["claims"]) + [{"id": "claim:new", "title": "New", "summary": "New graph fact.", "status": "supported", "citations": ["origin:new"]}]

        self.assertNotEqual(gpv.graph_digest(graph), gpv.graph_digest(changed))


if __name__ == "__main__":
    unittest.main()
