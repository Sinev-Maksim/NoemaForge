#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_artifact_card_affordance_performance.py
Zone: release/package
Version: 0.31.21.alpha
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Performance-test bounded Admin GUI artifact-card affordance generation.
Inputs: Synthetic artifact cards.
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


class ArtifactCardAffordancePerformanceTests(unittest.TestCase):
    def test_artifact_affordance_generation_is_bounded(self) -> None:
        cards = [
            {"type": "model_selection_artifact", "label": f"plan-{index}.json", "path": f"/var/lib/noemaforge/model-selection/run-{index}/plan.json"}
            for index in range(1500)
        ]

        started = time.perf_counter()
        enriched = ags.enrich_artifact_cards(cards)
        elapsed = time.perf_counter() - started

        self.assertEqual(1500, len(enriched))
        self.assertIn("/api/artifacts/open", enriched[-1]["open_url"])
        self.assertIn("/api/artifacts/download", enriched[-1]["download_url"])
        self.assertLess(elapsed, 1.5, f"artifact affordance generation took {elapsed:.3f}s")


if __name__ == "__main__":
    unittest.main()
