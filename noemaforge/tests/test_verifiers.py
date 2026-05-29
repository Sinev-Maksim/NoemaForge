#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_verifiers.py
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
# File: tests/test_verifiers.py
# Purpose: Verify that the verifier runtime supports the configured catalog and basic payload classes.
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

import verifiers


class VerifierRuntimeTests(unittest.TestCase):
    def test_catalog_types_are_supported(self) -> None:
        listed = verifiers.list_verifiers(os.path.join(ROOT, 'configs'))
        self.assertIn('qa', listed)
        self.assertTrue(set(listed.values()).issubset(verifiers.SUPPORTED_TYPES))

    def test_manifest_verifier(self) -> None:
        result = verifiers.verify('manifest', {'manifest': {'items': ['x']}}, epoch_dir=os.path.join(ROOT, 'configs'))
        self.assertTrue(result['ok'], result)

    def test_coverage_verifier(self) -> None:
        payload = {'expected_inputs': ['a', 'b'], 'observed_inputs': ['a', 'b']}
        result = verifiers.verify('coverage', payload, epoch_dir=os.path.join(ROOT, 'configs'))
        self.assertTrue(result['ok'], result)

    def test_sumcheck_verifier(self) -> None:
        payload = {'expected': 10, 'actual': 10}
        result = verifiers.verify('sumcheck', payload, epoch_dir=os.path.join(ROOT, 'configs'))
        self.assertTrue(result['ok'], result)


if __name__ == '__main__':
    unittest.main()
