#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_admin_smalltalk_route_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate Admin smalltalk conversation routing and no-pipeline regression behavior.
Inputs: Workspace admin-smalltalk-route policy and Admin runtimes.
Outputs: unittest assertions only.
Side effects: None.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import admin_runtime
import admin_smalltalk_route_runtime as asr


class AdminSmalltalkRouteRuntimeTests(unittest.TestCase):
    def test_workspace_admin_smalltalk_route_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "admin-smalltalk-route-policy.json"
        report = asr.validate_admin_smalltalk_route_policy(
            asr.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(2, report["metrics"]["script_reports"])
        self.assertEqual(2, report["metrics"]["valid_script_reports"])
        self.assertEqual(report["metrics"]["smalltalk_examples"], report["metrics"]["conversation_examples"])

    def test_smalltalk_decision_rewrites_greeting_to_conversation(self) -> None:
        for message in ["hello", "thanks", "спасибо", "как ты"]:
            with self.subTest(message=message):
                decision = asr.build_admin_smalltalk_decision(message)
                self.assertEqual("conversation", decision["mode"], decision)
                self.assertEqual("conversation", decision["route_id"], decision)
                self.assertFalse(decision["pipeline_id"], decision)
                self.assertFalse(decision["launches_pipeline"], decision)

    def test_explicit_control_request_does_not_use_conversation_route(self) -> None:
        for message in ["run public_mwp", "привет, запусти public_mwp", "hello start gui"]:
            with self.subTest(message=message):
                decision = asr.build_admin_smalltalk_decision(message)
                self.assertEqual("control", decision["mode"], decision)
                self.assertTrue(decision["explicit_control"], decision)

    def test_cli_execute_smalltalk_never_creates_pipeline_run(self) -> None:
        args = argparse.Namespace(
            root=str(ROOT),
            state=str(ROOT / "_tmp_admin_smalltalk_state"),
            evolution_state=str(ROOT / "_tmp_admin_smalltalk_evolution"),
            message="hello",
            text=[],
            locale="en",
            json=True,
            max_steps=0,
            time_budget_minutes=0,
            until_stop=False,
            execute=True,
            allow_degraded=False,
            dry_run=True,
            prepare_media=False,
            apply=False,
        )
        original = admin_runtime.create_pipeline_run

        def fail_pipeline_run(*_args, **_kwargs):
            raise AssertionError("smalltalk must not create a pipeline run")

        admin_runtime.create_pipeline_run = fail_pipeline_run
        stream = io.StringIO()
        try:
            with contextlib.redirect_stdout(stream):
                code = admin_runtime.cmd_message(args)
        finally:
            admin_runtime.create_pipeline_run = original

        payload = json.loads(stream.getvalue())
        self.assertEqual(0, code)
        self.assertEqual("conversation", payload["mode"], payload)
        self.assertEqual("conversation", payload["route"]["id"], payload)
        self.assertFalse(payload["executed"], payload)
        self.assertEqual([], payload["actions"], payload)
        self.assertFalse(payload["route"]["pipeline_id"], payload)


if __name__ == "__main__":
    unittest.main()
