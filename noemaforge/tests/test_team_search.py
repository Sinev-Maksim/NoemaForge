#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_team_search.py
Zone: release/package
Version: 0.32.1
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
# File: tests/test_team_search.py
# Purpose: Unit-test deterministic team-search helpers and state persistence.
# Invoked by / imported from:
#   - unittest discovery
# Public API / entry functions:
#   - class TeamSearchTests
# Inputs:
#   - temporary JSON scorecard directories created during test runtime
# Output formats / side effects:
#   - unittest assertions only
# AutoDoc: refreshed 2026-04-09 (manual)
# === End NoemaForge Autodoc File Header ===


import json
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(ROOT, 'src'))

import team_search


class TeamSearchTests(unittest.TestCase):
    def test_state_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory(prefix='noemaforge-team-search-') as td:
            state = {'k_current': 4, 'notes': ['ok']}
            team_search._save_team_search_state(td, 'dev.work', 'smoke', state)
            loaded = team_search._load_team_search_state(td, 'dev.work', 'smoke')
            self.assertEqual(loaded['k_current'], 4)
            self.assertEqual(loaded['notes'], ['ok'])

    def test_scorecard_exists(self) -> None:
        with tempfile.TemporaryDirectory(prefix='noemaforge-team-search-') as td:
            flow_dir = os.path.join(td, 'dev.work')
            os.makedirs(flow_dir, exist_ok=True)
            h = 'abc123'
            p = os.path.join(flow_dir, f'team__smoke__{h}.json')
            with open(p, 'w', encoding='utf-8') as f:
                json.dump({'role_models': {'dev': 'main'}}, f)
            self.assertTrue(team_search.scorecard_exists(td, 'dev.work', 'smoke', h))




    def test_coordinate_pick_avoids_failed_pairs(self) -> None:
        with tempfile.TemporaryDirectory(prefix='noemaforge-team-search-') as td:
            with mock.patch.object(team_search, '_models_seen_in_team_scorecards', return_value={'dev': set(), 'qa': set()}), \
                 mock.patch.object(team_search, '_team_role_run_counts', return_value={'dev': 0, 'qa': 0}):
                nxt = team_search._coordinate_pick_next_config(
                    team_scorecards_dir=td,
                    flow_id='dev.work',
                    suite='smoke',
                    role_ids=['dev', 'qa'],
                    role_candidates={'dev': ['bad-model', 'good-model'], 'qa': ['main']},
                    failed_role_models={'dev': {'bad-model'}},
                )
            self.assertIsNotNone(nxt)
            self.assertEqual(nxt['role_models']['dev'], 'good-model')

    def test_failed_role_models_uses_quality_metrics(self) -> None:
        with tempfile.TemporaryDirectory(prefix='noemaforge-team-search-') as td:
            model_dir = os.path.join(td, 'weak-model')
            os.makedirs(model_dir, exist_ok=True)
            p = os.path.join(model_dir, 'dev.work__dev__llm.json')
            with open(p, 'w', encoding='utf-8') as f:
                json.dump({'quality_metrics': {'stability_score': 0.2, 'step_success_rate': 0.3}}, f)
            failed = team_search._failed_role_models(td, 'dev.work', ['dev'], quality_floor=0.34, json_floor=0.34)
            self.assertIn('weak-model', failed.get('dev', set()))

if __name__ == '__main__':
    unittest.main()
