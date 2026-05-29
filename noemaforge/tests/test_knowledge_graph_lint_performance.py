#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_knowledge_graph_lint_performance.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Performance-test Knowledge Graph Lint validation.
Inputs: Workspace Knowledge Graph Lint policy and offline examples.
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

import knowledge_graph_lint_runtime as kgl


class KnowledgeGraphLintPerformanceTests(unittest.TestCase):
    def test_repeated_knowledge_graph_lint_validation_stays_lightweight(self) -> None:
        policy = kgl.load_policy(ROOT / "configs" / "knowledge-graph-lint-policy.json")
        start = time.perf_counter()
        for _ in range(8):
            report = kgl.validate_knowledge_graph_lint_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        elapsed = time.perf_counter() - start

        self.assertTrue(report["ok"], report["failures"])
        self.assertLess(elapsed, 3.8)


if __name__ == "__main__":
    unittest.main()
