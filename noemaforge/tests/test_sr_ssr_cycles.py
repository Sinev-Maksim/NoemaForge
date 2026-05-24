#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_sr_ssr_cycles.py
Zone: release/package
Version: 0.31.13.alpha-patched1
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
# File: tests/test_sr_ssr_cycles.py
# Purpose: Unit-test SR and SSR reporting safeguards such as epoch immutability markers.
# Invoked by / imported from:
#   - unittest discovery
# Public API / entry functions:
#   - class SRCycleTests
#   - class SSRCycleTests
# Inputs:
#   - temporary packet directories and mocked helper functions
# Output formats / side effects:
#   - unittest assertions only
# AutoDoc: refreshed 2026-04-09 (manual)
# === End NoemaForge Autodoc File Header ===


import json
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(ROOT, 'src'))

import sr_cycle
import ssr_cycle


class SRCycleTests(unittest.TestCase):
    def test_sr_report_contains_epoch_immutability(self) -> None:
        with tempfile.TemporaryDirectory(prefix='noemaforge-sr-') as td:
            with mock.patch.object(sr_cycle, 'PACKETS_SR', os.path.join(td, 'sr')),                  mock.patch.object(sr_cycle, 'PACKETS_SURGEON', os.path.join(td, 'surgeon')),                  mock.patch.object(sr_cycle, 'PACKETS_SCARY', os.path.join(td, 'scary')),                  mock.patch.object(sr_cycle.epoch, 'current_epoch_id', return_value='E1'),                  mock.patch.object(sr_cycle.epoch, 'current_epoch_dir', return_value='/epochs/E1'),                  mock.patch.object(sr_cycle, 'sr_lite_run', return_value=('lite.json', {'counts': {}, 'sel_ok': True, 'recommendations': []})),                  mock.patch.object(sr_cycle.roadmap, 'export_report', return_value={'ok': True, 'report_path': 'rep.json', 'markdown_path': 'rep.md'}),                  mock.patch.object(sr_cycle, 'sel_append', return_value=None):
                rep = sr_cycle.run(max_events=10)
            with open(rep['sr_report'], 'r', encoding='utf-8') as f:
                obj = json.load(f)
            self.assertTrue(obj['epoch_immutable_ok'])
            self.assertIn('reflection_quality', obj)


class SSRCycleTests(unittest.TestCase):
    def test_ssr_report_contains_epoch_immutability(self) -> None:
        with tempfile.TemporaryDirectory(prefix='noemaforge-ssr-') as td:
            with mock.patch.object(ssr_cycle, 'PACKETS_SSR', os.path.join(td, 'ssr')),                  mock.patch.object(ssr_cycle, 'PACKETS_SCARY', os.path.join(td, 'scary')),                  mock.patch.object(ssr_cycle.epoch, 'current_epoch_id', return_value='E1'),                  mock.patch.object(ssr_cycle.epoch, 'current_epoch_dir', return_value='/epochs/E1'),                  mock.patch.object(ssr_cycle, '_today', return_value='2026-04-09'),                  mock.patch.object(ssr_cycle, '_read_sel', return_value=[]),                  mock.patch.object(ssr_cycle, '_list_quarantine', return_value=[]),                  mock.patch.object(ssr_cycle, 'sel_verify', return_value=True),                  mock.patch.object(ssr_cycle.roadmap, 'export_report', return_value={'ok': True, 'report_path': 'rep.json', 'markdown_path': 'rep.md'}),                  mock.patch.object(ssr_cycle, 'sel_append', return_value=None):
                rep = ssr_cycle.run(max_events=10)
            with open(rep['ssr_report'], 'r', encoding='utf-8') as f:
                obj = json.load(f)
            self.assertTrue(obj['epoch_immutable_ok'])
            self.assertIn('paranoia_quality', obj)


if __name__ == '__main__':
    unittest.main()
