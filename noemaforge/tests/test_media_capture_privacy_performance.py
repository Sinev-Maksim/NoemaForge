#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_media_capture_privacy_performance.py
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Performance-test bounded media capture privacy gate evaluation.
Inputs: Workspace media capture privacy policy and synthetic requests.
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
sys.path.insert(0, str(ROOT / "src"))

import media_capture_privacy_runtime as mcpr


class MediaCapturePrivacyPerformanceTests(unittest.TestCase):
    def test_synthetic_capture_gate_batch_runs_under_budget(self) -> None:
        policy = mcpr.load_policy(ROOT / "configs" / "media-capture-privacy-policy.json")
        result = mcpr.benchmark_media_capture_privacy(policy, iterations=1000)

        self.assertTrue(result["ok"], result)
        self.assertEqual(500, result["allowed"])
        self.assertEqual(500, result["blocked"])
        self.assertLess(result["elapsed_sec"], 2.0)


if __name__ == "__main__":
    unittest.main()
