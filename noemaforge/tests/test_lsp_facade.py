#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_lsp_facade.py
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
# File: tests/test_lsp_facade.py
# Purpose: Unit-test the offline LSP facade for diagnostics, symbols, and references.
# Invoked by / imported from:
#   - unittest discovery
# Public API / entry functions:
#   - class LSPFacadeTests
# Inputs:
#   - temporary source files created during test runtime
# Output formats / side effects:
#   - unittest assertions only
# AutoDoc: refreshed 2026-04-10 (manual)
# === End NoemaForge Autodoc File Header ===


import os
import sys
import tempfile
import unittest

ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(ROOT, 'src'))

import lsp_facade


class LSPFacadeTests(unittest.TestCase):
    def test_diagnostics_symbols_and_references(self) -> None:
        with tempfile.TemporaryDirectory(prefix='noemaforge-lsp-') as td:
            bad_py = os.path.join(td, 'bad.py')
            good_py = os.path.join(td, 'good.py')
            with open(bad_py, 'w', encoding='utf-8') as f:
                f.write('def broken(:\n    pass\n')
            with open(good_py, 'w', encoding='utf-8') as f:
                f.write('import os\n\nclass EpochGuard:\n    pass\n\ndef select_model():\n    return os.getcwd()\n')

            ok, diag, reason = lsp_facade.prepare_tool_action('lsp.diagnostics', {'root_paths': [td]})
            self.assertTrue(ok, reason)
            self.assertGreaterEqual(diag['count'], 1)
            self.assertTrue(any(item['path'].endswith('bad.py') for item in diag['diagnostics']))

            ok, syms, reason = lsp_facade.prepare_tool_action('lsp.symbols', {'root_paths': [td], 'query': 'Epoch'})
            self.assertTrue(ok, reason)
            self.assertEqual(syms['count'], 1)
            self.assertEqual(syms['symbols'][0]['kind'], 'class')

            ok, refs, reason = lsp_facade.prepare_tool_action('lsp.references', {'root_paths': [td], 'symbol': 'select_model'})
            self.assertTrue(ok, reason)
            self.assertGreaterEqual(refs['count'], 1)
            self.assertTrue(any(item['path'].endswith('good.py') for item in refs['references']))


if __name__ == '__main__':
    unittest.main()
