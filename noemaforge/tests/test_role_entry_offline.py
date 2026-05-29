#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_role_entry_offline.py
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
# File: tests/test_role_entry_offline.py
# Purpose: Verify that specialist roles emit deterministic offline work packets instead of placeholder text when llm.chat is unavailable.
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
sys.path.insert(0, os.path.join(ROOT, 'src'))

from roles import role_entry


class RoleEntryOfflineTests(unittest.TestCase):
    def test_offline_specialist_packet_has_expected_sections(self) -> None:
        ctx = {'stream_id': 'dev.work', 'project_id': 'proj-x'}
        out = role_entry._offline_specialist_content('python_dev', 'T-1', 'Add a checker step.', ctx)
        self.assertIn('## Objective', out)
        self.assertIn('## Working assumptions', out)
        self.assertIn('## Proposed steps', out)
        self.assertIn('## Expected deliverables', out)
        self.assertIn('## Verification', out)
        self.assertNotIn('placeholder', out.lower())


if __name__ == '__main__':
    unittest.main()
