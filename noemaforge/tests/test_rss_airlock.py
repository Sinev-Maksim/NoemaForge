#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_rss_airlock.py
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
# File: tests/test_rss_airlock.py
# Purpose: Validate RSS intake through WebGW+glove wrappers using mocked dependencies.
# Invoked by / imported from:
#   - unittest discovery
# Output formats / side effects:
#   - unittest assertions only
# AutoDoc: refreshed 2026-04-11 (manual)
# === End NoemaForge Autodoc File Header ===
import os, sys, tempfile, unittest
from unittest import mock
ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(ROOT, 'src'))
import rss_airlock

class RSSAirlockTests(unittest.TestCase):
    def test_ingest_feed_runs_webgw_and_glove(self) -> None:
        with tempfile.TemporaryDirectory(prefix='noemaforge-rss-') as td:
            inc = os.path.join(td, 'incident')
            os.makedirs(inc, exist_ok=True)
            with open(os.path.join(inc, 'glove_sanitized.txt'), 'w', encoding='utf-8') as f:
                f.write('Safe preview text from rss')
            with mock.patch.object(rss_airlock.webgateway, 'fetch_to_quarantine', return_value=(True, {'incident_id':'i1','incident_dir':inc}, 'ok')), \
                 mock.patch.object(rss_airlock.glove_runner, 'run_glove', return_value=(True, {'ok': True})):
                ok, payload, reason = rss_airlock.ingest_feed(feed_url='https://example.test/rss.xml', epoch_dir=td, actor={'role':'scary'}, trace_id='t1')
            self.assertTrue(ok)
            self.assertEqual(reason, 'ok')
            self.assertTrue(os.path.exists(payload['summary_path']))
            self.assertIn('Safe preview text', payload['safe_text_preview'])

if __name__ == '__main__':
    unittest.main()