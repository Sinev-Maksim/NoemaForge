#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_canonical_model_eval_matrix_readiness_performance.py
Zone: release/package
Version: 0.31.21.alpha
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Keep canonical CPU/GPU model matrix readiness checks bounded for local CI.
Inputs: Canonical model eval matrix readiness policy and runtime validator.
Outputs: unittest assertions only.
Side effects: None.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import canonical_model_eval_matrix_readiness_runtime as cmr


class CanonicalModelEvalMatrixReadinessPerformanceTests(unittest.TestCase):
    def test_readiness_validation_stays_bounded(self) -> None:
        payload = cmr.load_policy()
        start = time.perf_counter()
        reports = [cmr.validate_canonical_model_eval_matrix_readiness_policy(payload) for _ in range(25)]
        elapsed = time.perf_counter() - start
        self.assertTrue(all(report["ok"] for report in reports), reports[-1]["failures"])
        self.assertLess(elapsed, 2.0)


if __name__ == "__main__":
    unittest.main()
