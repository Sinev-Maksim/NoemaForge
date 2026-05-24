#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_dev_backlog_empty_policy_runtime.py
Zone: release/package
Version: 0.31.21.alpha
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate empty Dev backlog creates only a bounded seed self-optimization plan.
Inputs: Workspace dev-backlog-empty policy and Dev Team runtime.
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
from argparse import Namespace
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import dev_backlog_empty_policy_runtime as dbep
import dev_team_runtime as dtr


class DevBacklogEmptyPolicyRuntimeTests(unittest.TestCase):
    def test_workspace_dev_backlog_empty_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "dev-backlog-empty-policy.json"
        report = dbep.validate_dev_backlog_empty_policy(
            dbep.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertGreater(report["metrics"]["dev_team_chars"], 1000)
        self.assertGreater(report["metrics"]["seed_parser_chars"], 100)
        self.assertEqual(3, report["metrics"]["seed_actions"])

    def test_empty_backlog_creates_bounded_review_required_plan_only(self) -> None:
        fixture = dbep.build_empty_backlog_policy_fixture()
        plan = fixture["empty_plan"]

        self.assertTrue(plan["seed_created"], plan)
        self.assertEqual("draft_review_required", plan["plan_status"])
        self.assertFalse(plan["auto_apply"])
        self.assertFalse(plan["applied"])
        self.assertTrue(plan["requires_admin_approval"])
        self.assertEqual("plan_only_no_auto_apply", plan["execution_policy"])
        self.assertLessEqual(plan["improvement_budget"]["max_steps"], 5)
        self.assertLessEqual(plan["improvement_budget"]["time_budget_minutes"], 30)
        self.assertFalse(plan["improvement_budget"]["until_stop"])
        self.assertTrue(all(action["apply"] is False for action in plan["actions"]))

    def test_nonempty_dev_backlog_does_not_create_seed_plan(self) -> None:
        fixture = dbep.build_empty_backlog_policy_fixture()
        plan = fixture["nonempty_plan"]

        self.assertFalse(plan["seed_created"], plan)
        self.assertEqual("dev_backlog_not_empty", plan["reason"])
        self.assertFalse(plan["auto_apply"])
        self.assertFalse(plan["applied"])

    def test_seed_self_improvement_cli_writes_plan_artifact_without_apply(self) -> None:
        with tempfile.TemporaryDirectory(prefix="nfg-dev-backlog-empty-") as tmp:
            args = Namespace(
                state=tmp,
                backlog="",
                request="CLI fixture empty Dev backlog",
                max_steps=99,
                time_budget_minutes=999,
                json=True,
            )
            out = StringIO()
            with redirect_stdout(out):
                rc = dtr.cmd_seed_self_improvement_plan(args)
            plans = list(Path(tmp).glob("runs/dev_backlog_seed_*/seed-self-optimization-plan.json"))
            payload = json.loads(out.getvalue())

        self.assertEqual(0, rc)
        self.assertEqual(1, len(plans))
        self.assertTrue(payload["seed_created"], payload)
        self.assertFalse(payload["auto_apply"], payload)
        self.assertFalse(payload["applied"], payload)


if __name__ == "__main__":
    unittest.main()
