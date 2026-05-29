#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_model_scorecards_expectations.py
Zone: release/package
Version: 0.32.2
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
# File: tests/test_model_scorecards_expectations.py
# Purpose: Unit-test JSON/schema/regex/numeric expectation helpers used during model pre-selection.
# Invoked by / imported from:
#   - unittest discovery
# Public API / entry functions:
#   - class ModelScorecardExpectationTests
# Inputs:
#   - in-memory expectation dictionaries and parsed JSON objects
# Output formats / side effects:
#   - unittest assertions only
# AutoDoc: refreshed 2026-04-09 (manual)
# === End NoemaForge Autodoc File Header ===


import os
import sys
import unittest

ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(ROOT, 'src'))

from model_scorecards import _check_expectations


class ModelScorecardExpectationTests(unittest.TestCase):
    def test_expectations_with_schema_regex_and_numeric(self) -> None:
        raw = '{"result": 323, "summary": "safe output", "policy": {"route": "scary"}}'
        expect = {
            'json': True,
            'regex': ['safe output'],
            'regex_not': ['token='],
            'keys': ['result', 'summary', 'policy'],
            'schema': {
                'type': 'object',
                'required': ['result', 'policy'],
                'properties': {
                    'result': {'type': 'integer'},
                    'policy': {'type': 'object', 'required': ['route']},
                },
            },
            'numeric': {'path': '$.result', 'equals': 323, 'tolerance': 0},
        }
        passed, checks, failures = _check_expectations(expect=expect, raw_text=raw, parsed_ok=True, parsed_obj={'result': 323, 'summary': 'safe output', 'policy': {'route': 'scary'}})
        self.assertTrue(passed, failures)
        self.assertTrue(checks['json'])
        self.assertTrue(checks['numeric']['ok'])


if __name__ == '__main__':
    unittest.main()
