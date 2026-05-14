#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_team_scorecards_quality.py
Zone: release/package
Version: 0.31.13.alpha
Created: 2026-05-14
Modified: 2026-05-14
Purpose: Provide NoemaForge release functionality for the packaged local runtime.
Inputs: Command-line arguments, environment variables, package files and local NoemaForge runtime state as applicable.
Outputs: Structured command output, files, service state or UI state as documented by the caller.
Side effects: Limited to the documented NoemaForge paths, runtime state directories or systemd units used by this file.
Tests: Syntax validation plus the release setup selftest, consistency-audit and targeted smoke checks.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations


# === NoemaForge Autodoc File Header ===
# File: tests/test_team_scorecards_quality.py
# Purpose: Unit-test derived stability and hallucination metrics for team scorecards.
# Invoked by / imported from:
#   - unittest discovery
# Public API / entry functions:
#   - class TeamScorecardQualityTests
# Inputs:
#   - in-memory team scorecard case results
# Output formats / side effects:
#   - unittest assertions only
# AutoDoc: refreshed 2026-04-09 (manual)
# === End NoemaForge Autodoc File Header ===


import os
import sys
import unittest

ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(ROOT, 'src'))

from team_scorecards import _quality_metrics


class TeamScorecardQualityTests(unittest.TestCase):
    def test_quality_metrics_capture_variance_and_risk(self) -> None:
        results = [
            {
                'steps': [
                    {'ok': True, 'reason': 'ok'},
                    {'ok': False, 'reason': 'gateway_error'},
                ],
                'judge': {'ok': True, 'raw': {'missing': ['qa'], 'notes': ['possible hallucination']}}
            },
            {
                'steps': [
                    {'ok': True, 'reason': 'ok_nonjson'},
                ],
                'judge': {'ok': False, 'raw': {'missing': [], 'notes': ['unsupported claim']}}
            },
        ]
        metrics = _quality_metrics(results, [0.9, 0.4])
        self.assertGreater(metrics['score_variance'], 0.0)
        self.assertLess(metrics['stability_score'], 1.0)
        self.assertGreater(metrics['hallucination_risk'], 0.0)
        self.assertEqual(metrics['judge_failures'], 1)


if __name__ == '__main__':
    unittest.main()
