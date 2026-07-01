#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_host_preflight.py
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
# File: tests/test_host_preflight.py
# Purpose: Validate bootstrap host-preflight reporting on a synthetic seed tree.
# Invoked by / imported from:
#   - unittest discovery
# Output formats / side effects:
#   - unittest assertions only
# AutoDoc: refreshed 2026-04-11 (manual)
# === End NoemaForge Autodoc File Header ===
import importlib.util, os, tempfile, unittest
from pathlib import Path
ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), '..'))
mod_path = os.path.join(ROOT, 'bootstrap', 'noemaforge-host-preflight.py')
spec = importlib.util.spec_from_file_location('noemaforge_host_preflight', mod_path)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)

class HostPreflightTests(unittest.TestCase):
    def test_collect_report(self) -> None:
        with tempfile.TemporaryDirectory(prefix='noemaforge-preflight-') as td:
            os.makedirs(os.path.join(td, 'src'), exist_ok=True)
            os.makedirs(os.path.join(td, 'configs'), exist_ok=True)
            os.makedirs(os.path.join(td, 'offline-apt', 'aptrepo'), exist_ok=True)
            root = Path(td)
            (root / 'src' / 'noemaforge-llm-gateway.go').write_text('package main', encoding='utf-8')
            (root / 'configs' / 'voice-backends-policy.yaml').write_text('enabled: false\n', encoding='utf-8')
            (root / 'configs' / 'tts-backends-policy.yaml').write_text('enabled: false\n', encoding='utf-8')
            (root / 'configs' / 'discord-bridge-policy.yaml').write_text('enabled: false\n', encoding='utf-8')
            (root / 'offline-apt' / 'aptrepo' / 'Packages').write_text('Package: demo\n', encoding='utf-8')
            rep = mod.collect_report(td)
            self.assertTrue(rep['checks']['seed_exists'])
            self.assertTrue(rep['checks']['gateway_source'])

if __name__ == '__main__':
    unittest.main()
