#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_safe_worktree_evolution_performance.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-21
Modified: 2026-05-21
Purpose: Bounded regression test for safe evolution worktree validation.
Inputs: Safe worktree policy and synthetic local worktree plans.
Outputs: unittest assertions only.
Side effects: Creates temporary directories only.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import pipeline_runtime as pr
import safe_worktree_evolution_runtime as swe


class SafeWorktreeEvolutionPerformanceTests(unittest.TestCase):
    def test_plan_builder_stays_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            repo = tmp / "repo"
            repo.mkdir()
            (repo / ".git").mkdir()
            run = {
                "run_id": "run-perf",
                "pipeline_id": "evolution",
                "task_id": "bounded",
                "run_dir": str(tmp / "run"),
            }
            started = time.perf_counter()
            plans = [
                pr.build_evolution_worktree_plan(run, repo=str(repo), branch=f"noemaforge/evolution/bounded-{idx}", cwd=tmp)
                for idx in range(300)
            ]
            elapsed = time.perf_counter() - started
            self.assertEqual(300, len(plans))
            self.assertTrue(all(item["safety"]["destination_under_run_dir"] for item in plans))
            self.assertLess(elapsed, 2.0)

    def test_policy_validation_stays_bounded(self) -> None:
        policy = swe.load_policy()
        started = time.perf_counter()
        reports = [
            swe.validate_safe_worktree_evolution_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
            for _ in range(20)
        ]
        elapsed = time.perf_counter() - started
        self.assertTrue(all(item["ok"] for item in reports), reports[-1]["failures"])
        self.assertLess(elapsed, 1.5)


if __name__ == "__main__":
    unittest.main()
