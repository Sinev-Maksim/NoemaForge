#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_runtime_observer_cards_performance.py
Zone: gui/control-plane
Version: 0.31.21.alpha
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Performance-test bounded Runtime observer card construction.
Inputs: Synthetic Runtime status records.
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

import admin_gui_server as ags
import runtime_observer_cards_runtime as roc


class RuntimeObserverCardsPerformanceTests(unittest.TestCase):
    def test_runtime_observer_card_building_stays_bounded(self) -> None:
        statuses = [
            roc.synthetic_runtime_status(
                gateway_active=bool(index % 2),
                backend_active=bool(index % 3),
                sockets_present=bool(index % 5),
            )
            for index in range(5000)
        ]

        started = time.perf_counter()
        card_sets = [ags.build_runtime_observer_cards(status) for status in statuses]
        elapsed = time.perf_counter() - started

        self.assertEqual(5000, len(card_sets))
        self.assertTrue(all(len(cards) == 6 for cards in card_sets))
        self.assertLess(elapsed, 0.35, f"Runtime observer card building took {elapsed:.3f}s")


if __name__ == "__main__":
    unittest.main()
