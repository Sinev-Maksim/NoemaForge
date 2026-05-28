#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_intent_router_eval.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-18
Modified: 2026-05-18
Purpose: Validate Admin intent-router eval pack execution and per-route metrics.
Inputs: Packaged intent-router eval pack.
Outputs: unittest assertions only.
Side effects: None.
Tests: unittest discovery.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import intent_router_eval


class IntentRouterEvalTests(unittest.TestCase):
    def test_pack_evaluates_with_per_route_metrics(self) -> None:
        pack = intent_router_eval.load_pack(ROOT / "configs" / "intent-router-eval-pack.json")
        report = intent_router_eval.evaluate_pack(pack, trace_id="trace-router-eval")
        self.assertTrue(report["ok"], report)
        self.assertEqual("trace-router-eval", report["trace_id"])
        self.assertEqual(1.0, report["metrics"]["pass_rate"])
        self.assertIn("code", report["metrics"]["per_route"])
        self.assertEqual(2, report["metrics"]["per_route"]["code"]["total"])
        self.assertIn("ask_clarification", report["metrics"]["per_abstention_action"])


if __name__ == "__main__":
    unittest.main()
