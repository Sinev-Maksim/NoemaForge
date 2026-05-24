#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_runtime_observer_cards_runtime.py
Zone: gui/control-plane
Version: 0.31.21.alpha
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate Runtime observer card contract and synthetic gateway/backend evidence.
Inputs: Workspace runtime-observer-cards policy and Admin GUI helper functions.
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
import production_ai_contracts as pac
import runtime_observer_cards_runtime as roc


class RuntimeObserverCardsRuntimeTests(unittest.TestCase):
    def test_workspace_runtime_observer_cards_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "runtime-observer-cards-policy.json"
        report = roc.validate_runtime_observer_cards_policy(
            roc.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(report["metrics"]["required_cards"], report["metrics"]["cards_in_source"])
        gate = pac.evaluate_gate(
            {"change_id": "runtime-observer-cards-core", "domain": "pipeline"},
            {
                "artifact_uri": "memory://runtime-observer-cards-core/report",
                "run_at": report["validated_at"],
                "checks": [
                    {"id": "pipeline_eval", "status": "pass"},
                    {"id": "rollback_plan", "status": "pass"},
                ],
            },
        )
        self.assertTrue(gate["ok"], gate)

    def test_admin_gui_builds_gateway_and_backend_cards(self) -> None:
        cards = ags.build_runtime_observer_cards(roc.synthetic_runtime_status())
        by_id = {card["id"]: card for card in cards}

        self.assertEqual("ok", by_id["gateway-service"]["status"])
        self.assertEqual("affirmed", by_id["gateway-socket"]["smoke_affirmation"])
        self.assertEqual("ok", by_id["main-backend-service"]["status"])
        self.assertEqual("main-local-test", by_id["main-model-manifest"]["state"])
        self.assertIn("device-policy", by_id)

    def test_missing_backend_socket_warns_without_claiming_affirmation(self) -> None:
        cards = ags.build_runtime_observer_cards(roc.synthetic_runtime_status(backend_active=False, sockets_present=True))
        by_id = {card["id"]: card for card in cards}

        self.assertEqual("warn", by_id["main-backend-service"]["status"])
        self.assertEqual("not_affirmed", by_id["main-backend-socket"]["smoke_affirmation"])


if __name__ == "__main__":
    unittest.main()
