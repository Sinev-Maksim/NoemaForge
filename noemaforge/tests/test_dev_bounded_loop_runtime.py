#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_dev_bounded_loop_runtime.py
Zone: release/package
Version: 0.31.21.alpha
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate bounded Dev Team loop plan/checkpoint/stop behavior.
Inputs: Workspace dev-bounded-loop policy and Dev Team runtime.
Outputs: unittest assertions only.
Side effects: Temporary test directories only.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from argparse import Namespace
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import dev_bounded_loop_runtime as dblp
import dev_team_runtime as dtr


class DevBoundedLoopRuntimeTests(unittest.TestCase):
    def test_workspace_dev_bounded_loop_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "dev-bounded-loop-policy.json"
        report = dblp.validate_dev_bounded_loop_policy(
            dblp.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertGreater(report["metrics"]["dev_team_chars"], 1000)
        self.assertGreater(report["metrics"]["plan_parser_chars"], 100)
        self.assertGreater(report["metrics"]["checkpoint_parser_chars"], 100)
        self.assertEqual(10, report["metrics"]["bounded_plan_steps"])

    def test_bounded_loop_plan_clamps_budget_and_never_applies(self) -> None:
        plan = dtr.build_bounded_dev_loop_plan(
            "Unit bounded loop fixture",
            max_steps=999,
            time_budget_minutes=999,
            until_stop=True,
            checkpoint_interval=99,
        )

        self.assertEqual("dev_team_bounded_loop", plan["mode"])
        self.assertEqual("draft_checkpoint_required", plan["plan_status"])
        self.assertEqual("plan_and_checkpoint_only_no_auto_apply", plan["execution_policy"])
        self.assertFalse(plan["auto_apply"])
        self.assertFalse(plan["applied"])
        self.assertTrue(plan["requires_admin_approval"])
        self.assertLessEqual(plan["improvement_budget"]["max_steps"], 10)
        self.assertLessEqual(plan["improvement_budget"]["time_budget_minutes"], 60)
        self.assertTrue(plan["improvement_budget"]["until_stop"])
        self.assertEqual(10, len(plan["steps"]))
        self.assertTrue(all(step["apply"] is False for step in plan["steps"]))
        self.assertTrue(all(step["checkpoint_required"] is True for step in plan["steps"]))

    def test_persisted_loop_writes_checkpoints_and_honors_stop(self) -> None:
        with tempfile.TemporaryDirectory(prefix="nfg-bounded-loop-") as tmp:
            plan = dtr.write_bounded_dev_loop_plan(
                Path(tmp),
                "Persisted bounded loop fixture",
                max_steps=3,
                time_budget_minutes=15,
                until_stop=True,
            )
            run_dir = Path(plan["run_dir"])
            first = dtr.advance_bounded_dev_loop_checkpoint(run_dir, observation="first checkpoint")
            stopped = dtr.advance_bounded_dev_loop_checkpoint(run_dir, stop_requested=True, observation="stop now")

            self.assertTrue((run_dir / "bounded-loop-plan.json").exists())
            self.assertTrue((run_dir / "checkpoint-000.json").exists())
            self.assertTrue((run_dir / "checkpoint-current.json").exists())
            self.assertTrue((run_dir / "stop-request.json").exists())

        self.assertEqual("running", first["status"])
        self.assertEqual(1, first["checkpoint_index"])
        self.assertEqual(1, first["current_step"])
        self.assertFalse(first["auto_apply"])
        self.assertFalse(first["applied"])
        self.assertEqual("stopped", stopped["status"])
        self.assertTrue(stopped["terminal"])
        self.assertTrue(stopped["stop_requested"])
        self.assertFalse(stopped["auto_apply"])
        self.assertFalse(stopped["applied"])

    def test_bounded_loop_cli_commands_write_reviewable_artifacts_without_apply(self) -> None:
        with tempfile.TemporaryDirectory(prefix="nfg-bounded-loop-cli-") as tmp:
            plan_args = Namespace(
                state=tmp,
                request="CLI bounded loop fixture",
                max_steps=99,
                time_budget_minutes=999,
                until_stop=True,
                checkpoint_interval=99,
                json=True,
            )
            out = StringIO()
            with redirect_stdout(out):
                plan_rc = dtr.cmd_bounded_loop_plan(plan_args)
            plan_payload = json.loads(out.getvalue())
            checkpoint_args = Namespace(
                run_dir=plan_payload["run_dir"],
                step_id="",
                observation="CLI stop checkpoint",
                stop=True,
                json=True,
            )
            checkpoint_out = StringIO()
            with redirect_stdout(checkpoint_out):
                checkpoint_rc = dtr.cmd_bounded_loop_checkpoint(checkpoint_args)
            checkpoint_payload = json.loads(checkpoint_out.getvalue())

        self.assertEqual(0, plan_rc)
        self.assertEqual(0, checkpoint_rc)
        self.assertEqual("dev_team_bounded_loop", plan_payload["mode"])
        self.assertFalse(plan_payload["auto_apply"])
        self.assertFalse(plan_payload["applied"])
        self.assertEqual("stopped", checkpoint_payload["status"])
        self.assertTrue(checkpoint_payload["stop_requested"])
        self.assertFalse(checkpoint_payload["auto_apply"])
        self.assertFalse(checkpoint_payload["applied"])


if __name__ == "__main__":
    unittest.main()
