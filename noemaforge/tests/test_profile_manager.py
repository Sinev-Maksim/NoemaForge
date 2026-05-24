#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_profile_manager.py
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
# File: tests/test_profile_manager.py
# Purpose: Validate operator profile listing and enable/disable toggles.
# Invoked by / imported from:
#   - unittest discovery
# Output formats / side effects:
#   - unittest assertions only
# AutoDoc: refreshed 2026-04-11 (manual)
# === End NoemaForge Autodoc File Header ===
import os, sys, tempfile, unittest, yaml
ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(ROOT, 'src'))
import profile_manager

class ProfileManagerTests(unittest.TestCase):
    def test_list_and_toggle_profiles(self) -> None:
        with tempfile.TemporaryDirectory(prefix='noemaforge-profiles-') as td:
            for fn in profile_manager.PROFILE_FILES.values():
                with open(os.path.join(td, fn), 'w', encoding='utf-8') as f:
                    yaml.safe_dump({'apiVersion':'x','kind':'Policy','enabled': False}, f, sort_keys=False)
            listed = profile_manager.list_profiles(td)
            self.assertEqual(set(listed.keys()), set(profile_manager.PROFILE_FILES.keys()))
            res = profile_manager.set_profile_enabled(td, 'voice', True)
            self.assertTrue(res['enabled'])
            snap = profile_manager.operator_status_snapshot(td)
            self.assertIn('voice', snap['enabled_profiles'])

if __name__ == '__main__':
    unittest.main()