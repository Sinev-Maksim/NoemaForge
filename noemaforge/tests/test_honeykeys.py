#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_honeykeys.py
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
# File: tests/test_honeykeys.py
# Purpose: Validate honeykey issuance, scanning, and leak incident recording.
# Invoked by / imported from:
#   - unittest discovery
# Output formats / side effects:
#   - unittest assertions only
# AutoDoc: refreshed 2026-04-11 (manual)
# === End NoemaForge Autodoc File Header ===
import os, sys, tempfile, unittest
ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(ROOT, 'src'))
import honeykeys

class HoneykeysTests(unittest.TestCase):
    def test_issue_scan_and_mark_leaked(self) -> None:
        with tempfile.TemporaryDirectory(prefix='noemaforge-hk-') as td:
            rec = honeykeys.issue_honeykey(state_dir=td, model_id='main', run_id='r1', role='dev', project_id='p1')
            hits = honeykeys.scan_text(state_dir=td, text='prefix ' + rec['value'] + ' suffix')
            self.assertEqual(len(hits), 1)
            leak = honeykeys.mark_leaked(state_dir=td, leaked_value=rec['value'], source='unit_test')
            self.assertTrue(leak['ok'])
            self.assertTrue(os.path.exists(leak['incident_path']))

if __name__ == '__main__':
    unittest.main()