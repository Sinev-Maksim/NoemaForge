#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_validate_offline_apt.py
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
# File: tests/test_validate_offline_apt.py
# Purpose: Validate offline APT repository checks on a synthetic repo.
# Invoked by / imported from:
#   - unittest discovery
# Output formats / side effects:
#   - unittest assertions only
# AutoDoc: refreshed 2026-04-11 (manual)
# === End NoemaForge Autodoc File Header ===
import importlib.util, gzip, os, tempfile, unittest
ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), '..'))
mod_path = os.path.join(ROOT, 'tools', 'prep', 'validate_offline_apt.py')
spec = importlib.util.spec_from_file_location('validate_offline_apt', mod_path)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)

class ValidateOfflineAptTests(unittest.TestCase):
    def test_validate_repo(self) -> None:
        with tempfile.TemporaryDirectory(prefix='noemaforge-offline-apt-') as td:
            with gzip.open(os.path.join(td, 'Packages.gz'), 'wt', encoding='utf-8') as f:
                f.write('Package: demo\n')
            open(os.path.join(td, 'demo_1.0_amd64.deb'), 'wb').write(b'not-a-real-deb')
            rep = mod.validate_repo(td)
            self.assertTrue(rep['ok'])
            self.assertGreaterEqual(rep['deb_count'], 1)

if __name__ == '__main__':
    unittest.main()