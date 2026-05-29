#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_admin_llm_smalltalk_runtime.py
Zone: gui/control-plane
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate Admin GUI optional LLM smalltalk and deterministic fallback runtime behavior.
Inputs: Workspace admin-llm-smalltalk policy and Admin GUI server methods.
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

import admin_gui_server as ags
import admin_llm_smalltalk_runtime as als
import production_ai_contracts as pac


class AdminLLMSmalltalkRuntimeTests(unittest.TestCase):
    def test_workspace_admin_llm_smalltalk_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "admin-llm-smalltalk-policy.json"
        report = als.validate_admin_llm_smalltalk_policy(
            als.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(["deterministic_fallback", "llm_chat"], report["metrics"]["synthetic_backends"])
        gate = pac.evaluate_gate(
            {"change_id": "admin-llm-smalltalk-core", "domain": "pipeline"},
            {
                "artifact_uri": "memory://admin-llm-smalltalk-core/report",
                "run_at": report["validated_at"],
                "checks": [
                    {"id": "pipeline_eval", "status": "pass"},
                    {"id": "rollback_plan", "status": "pass"},
                ],
            },
        )
        self.assertTrue(gate["ok"], gate)

    def test_backend_decision_preserves_control_and_both_chat_backends(self) -> None:
        llm = als.build_smalltalk_backend_decision("hello", llm_available=True)
        fallback = als.build_smalltalk_backend_decision("hello", llm_available=False)
        control = als.build_smalltalk_backend_decision("run public_mwp", llm_available=True)

        self.assertEqual("conversation", llm["mode"])
        self.assertEqual("llm_chat", llm["conversation_backend"])
        self.assertEqual("conversation", fallback["mode"])
        self.assertEqual("deterministic_fallback", fallback["conversation_backend"])
        self.assertEqual("control", control["mode"])
        self.assertTrue(control["explicit_control"])
        self.assertFalse(control["conversation_backend"])

    def test_admin_gui_conversational_reply_reports_backend(self) -> None:
        class Dummy:
            def __init__(self, reply: str) -> None:
                self.reply = reply

            def try_llm_admin_reply(self, text: str, locale: str) -> str:
                return self.reply

            def fallback_conversation_reply(self, text: str, locale: str) -> str:
                return "fallback"

        llm = ags.AdminGuiServer.conversational_admin_reply(Dummy("from llm"), "hello", "en")
        fallback = ags.AdminGuiServer.conversational_admin_reply(Dummy(""), "hello", "en")

        self.assertEqual({"reply": "from llm", "backend": "llm_chat"}, llm)
        self.assertEqual({"reply": "fallback", "backend": "deterministic_fallback"}, fallback)

    def test_admin_gui_explicit_control_guard_runs_before_conversation(self) -> None:
        class GuardDummy:
            def _explicit_control_request(self, low: str) -> bool:
                return ags.AdminGuiServer._explicit_control_request(self, low)

        dummy = GuardDummy()
        self.assertTrue(ags.AdminGuiServer._explicit_control_request(dummy, "run public_mwp"))
        self.assertFalse(ags.AdminGuiServer._conversational(dummy, "run public_mwp"))
        self.assertFalse(ags.AdminGuiServer._explicit_control_request(dummy, "hello"))
        self.assertTrue(ags.AdminGuiServer._conversational(dummy, "hello"))


if __name__ == "__main__":
    unittest.main()
