#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_admin_llm_smalltalk_performance.py
Zone: gui/control-plane
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Performance-test bounded Admin smalltalk backend decision planning.
Inputs: Synthetic smalltalk and explicit control messages.
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
sys.path.insert(0, str(ROOT / "src"))

import admin_llm_smalltalk_runtime as als


class AdminLLMSmalltalkPerformanceTests(unittest.TestCase):
    def test_backend_decision_planning_stays_bounded_for_many_messages(self) -> None:
        messages = [
            f"hello there {index}" if index % 5 else f"run public_mwp {index}"
            for index in range(5000)
        ]

        started = time.perf_counter()
        decisions = [
            als.build_smalltalk_backend_decision(message, llm_available=bool(index % 2))
            for index, message in enumerate(messages)
        ]
        elapsed = time.perf_counter() - started

        self.assertEqual(5000, len(decisions))
        self.assertGreater(sum(1 for item in decisions if item["mode"] == "control"), 0)
        self.assertIn("llm_chat", {item["conversation_backend"] for item in decisions})
        self.assertIn("deterministic_fallback", {item["conversation_backend"] for item in decisions})
        self.assertLess(elapsed, 0.35, f"Admin smalltalk backend planning took {elapsed:.3f}s")


if __name__ == "__main__":
    unittest.main()
