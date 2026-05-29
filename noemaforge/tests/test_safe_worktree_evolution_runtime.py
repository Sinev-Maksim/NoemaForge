#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_safe_worktree_evolution_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-21
Modified: 2026-05-21
Purpose: Unit-test safe evolution worktree planning and contract validation.
Inputs: Safe worktree policy plus pipeline runtime helper functions.
Outputs: unittest assertions only.
Side effects: Creates temporary directories only.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import copy
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import pipeline_runtime as pr
import safe_worktree_evolution_runtime as swe


def _run(tmp: Path, pipeline_id: str = "evolution") -> dict:
    return {
        "run_id": "run-test",
        "pipeline_id": pipeline_id,
        "task_id": "patch review",
        "run_dir": str(tmp / "run"),
        "current_stage": "development",
    }


class SafeWorktreeEvolutionRuntimeTests(unittest.TestCase):
    def test_policy_validates_pipeline_runtime_contract(self) -> None:
        report = swe.validate_safe_worktree_evolution_policy(
            swe.load_policy(),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
        )
        self.assertTrue(report["ok"], report["failures"])
        summary = report["safe_worktree_evolution_summary"]
        self.assertEqual(4, summary["helper_count"])
        self.assertEqual(12, summary["controls_true"])
        self.assertTrue(summary["destination_guard"])
        self.assertTrue(summary["branch_guard"])

    def test_build_plan_defaults_to_safe_evolution_namespace_and_run_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            repo = tmp / "repo"
            repo.mkdir()
            (repo / ".git").mkdir()
            plan = pr.build_evolution_worktree_plan(_run(tmp), repo=str(repo), cwd=tmp)
            self.assertEqual("noemaforge/evolution/patch-review", plan["branch"])
            self.assertFalse(plan["applied"])
            self.assertTrue(plan["safety"]["destination_under_run_dir"])
            self.assertIn(str((tmp / "run" / "worktrees").resolve()), plan["path"])
            self.assertEqual(["git", "-C", str(repo.resolve()), "worktree", "add", "-B"], plan["command"][:6])

    def test_rejects_non_evolution_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            repo = tmp / "repo"
            repo.mkdir()
            (repo / ".git").mkdir()
            with self.assertRaises(SystemExit) as ctx:
                pr.build_evolution_worktree_plan(_run(tmp, pipeline_id="release_prep"), repo=str(repo), cwd=tmp)
            self.assertIn("worktree_requires_evolution_pipeline", str(ctx.exception))

    def test_rejects_path_escape_branch_escape_and_bad_base(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            repo = tmp / "repo"
            repo.mkdir()
            (repo / ".git").mkdir()
            run = _run(tmp)
            with self.assertRaises(SystemExit) as path_ctx:
                pr.build_evolution_worktree_plan(run, repo=str(repo), path="../../escape", cwd=tmp)
            self.assertIn("worktree_path_outside_run_dir", str(path_ctx.exception))
            with self.assertRaises(SystemExit) as branch_ctx:
                pr.build_evolution_worktree_plan(run, repo=str(repo), branch="feature/escape", cwd=tmp)
            self.assertIn("unsafe_branch_namespace", str(branch_ctx.exception))
            with self.assertRaises(SystemExit) as base_ctx:
                pr.build_evolution_worktree_plan(run, repo=str(repo), base="../main", cwd=tmp)
            self.assertIn("unsafe_base_ref", str(base_ctx.exception))

    def test_policy_rejects_weakened_apply_guard(self) -> None:
        policy = copy.deepcopy(swe.load_policy())
        policy["policy"]["controls"]["apply_requires_explicit_flag"] = False
        failures = swe._policy_failures(policy)
        self.assertIn("control_apply_requires_explicit_flag_not_true", failures)


if __name__ == "__main__":
    unittest.main()
