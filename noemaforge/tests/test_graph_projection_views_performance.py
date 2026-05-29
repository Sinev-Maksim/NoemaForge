#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_graph_projection_views_performance.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Performance-test Graph Projection Views validation.
Inputs: Workspace Graph Projection Views policy and offline example graph.
Outputs: unittest assertions only.
Side effects: None.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import os
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import graph_projection_views_runtime as gpv


class GraphProjectionViewsPerformanceTests(unittest.TestCase):
    def test_graph_projection_boundary_refs_stay_canonical_and_bounded(self) -> None:
        policy = gpv.load_policy(ROOT / "configs" / "graph-projection-views-policy.json")
        refs = policy["policy"]["required_boundary_refs"]
        legacy_refs = {"README.md", "TODO.md", "noemaforge/TODO.md"}

        start = time.perf_counter()
        for _ in range(2500):
            canonical = all(ref.startswith(("docs/", "noemaforge/docs/")) for ref in refs)
            legacy_free = legacy_refs.isdisjoint(refs)
            bounded = len(refs) <= 12
        elapsed = time.perf_counter() - start

        self.assertTrue(canonical)
        self.assertTrue(legacy_free)
        self.assertTrue(bounded)
        self.assertLess(elapsed, 0.5)

    @unittest.skipIf(sys.platform == "win32", "wall-time threshold tuned for Linux/BigBro-BOS")
    def test_repeated_graph_projection_views_validation_stays_lightweight(self) -> None:
        policy = gpv.load_policy(ROOT / "configs" / "graph-projection-views-policy.json")
        start = time.perf_counter()
        for _ in range(8):
            report = gpv.validate_graph_projection_views_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        elapsed = time.perf_counter() - start

        self.assertTrue(report["ok"], report["failures"])
        self.assertLess(elapsed, 3.8)

    def test_projection_generation_for_larger_graph_stays_lightweight(self) -> None:
        graph = {
            "graph_ref": "hypergraph:perf:projection",
            "claims": [
                {
                    "id": f"claim:{idx}",
                    "title": f"Claim {idx}",
                    "summary": f"Projected claim {idx}",
                    "status": "supported" if idx % 3 else "uncertain",
                    "citations": [f"origin:{idx}"] if idx % 3 else [],
                    "task_context": [f"task:{idx}"] if idx % 5 == 0 else [],
                }
                for idx in range(240)
            ],
            "tasks": [{"id": f"task:{idx}", "title": f"Task {idx}", "status": "pending"} for idx in range(48)],
            "conflicts": [{"id": f"conflict:{idx}", "summary": f"Conflict {idx}", "status": "open"} for idx in range(24)],
        }
        start = time.perf_counter()
        for _ in range(10):
            projections = gpv.build_all_graph_projections(graph)
        elapsed = time.perf_counter() - start

        self.assertEqual({"conflict_review", "operator_summary", "task_context", "wiki_markdown"}, set(projections))
        self.assertLess(elapsed, 1.5)


if __name__ == "__main__":
    unittest.main()
