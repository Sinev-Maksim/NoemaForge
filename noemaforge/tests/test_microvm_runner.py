#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_microvm_runner.py
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
# File: tests/test_microvm_runner.py
# Purpose: Verify that the microVM reference runner validates spec shape and emits structured contract diagnostics.
# Invoked by / imported from:
#   - unittest discovery
# Output formats / side effects:
#   - unittest assertions only
# AutoDoc: refreshed 2026-04-09 (manual)
# === End NoemaForge Autodoc File Header ===


import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), '..'))
MOD_PATH = os.path.join(ROOT, 'bootstrap', 'microvm', 'noemaforge-microvm-run.py')
spec = importlib.util.spec_from_file_location('noemaforge_microvm_run', MOD_PATH)
microvm = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(microvm)


class MicroVMRunnerTests(unittest.TestCase):
    def test_contract_validation_reports_missing_fields(self) -> None:
        with tempfile.TemporaryDirectory(prefix='noemaforge-microvm-') as td:
            spec_path = os.path.join(td, 'spec.json')
            with open(spec_path, 'w', encoding='utf-8') as f:
                json.dump({'argv': [], 'cwd': '/tmp', 'env': {}, 'quota': {}, 'mounts': {}, 'allow_network': False}, f)
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = microvm.main(['--spec', spec_path])
            self.assertEqual(rc, 0)
            obj = json.loads(buf.getvalue())
            self.assertEqual(obj['meta']['mode'], 'contract_validation')
            self.assertFalse(obj['meta']['spec_valid'])
            self.assertIn('cpu_time_sec', obj['meta']['quota_missing'])


if __name__ == '__main__':
    unittest.main()
