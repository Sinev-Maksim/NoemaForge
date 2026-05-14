#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_runtime_placeholder_scan.py
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
# File: tests/test_runtime_placeholder_scan.py
# Purpose: Guard runtime source, config, bootstrap, and tool files against known placeholder regressions.
# Invoked by / imported from:
#   - unittest discovery
# Output formats / side effects:
#   - unittest assertions only
# AutoDoc: refreshed 2026-04-09 (manual)
# === End NoemaForge Autodoc File Header ===


import os
import sys
import unittest

ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(ROOT, 'tools', 'checker'))

import noemaforge_check


class RuntimePlaceholderScanTests(unittest.TestCase):
    def test_no_high_confidence_runtime_placeholders(self) -> None:
        step = noemaforge_check.check_runtime_placeholder_markers(ROOT)
        self.assertEqual(step.status, 'PASS', step.data)


if __name__ == '__main__':
    unittest.main()
