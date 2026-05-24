#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_tg_bot_runtime.py
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
# File: tests/test_tg_bot_runtime.py
# Purpose: Validate Telegram Bot API normalization and artifact writing with mocked HTTP.
# Invoked by / imported from:
#   - unittest discovery
# Output formats / side effects:
#   - unittest assertions only
# AutoDoc: refreshed 2026-04-11 (manual)
# === End NoemaForge Autodoc File Header ===
import io, json, os, sys, tempfile, unittest
from unittest import mock
ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(ROOT, 'src'))
import tg_bot_runtime

class TelegramBotRuntimeTests(unittest.TestCase):
    def test_fetch_and_ingest_updates(self) -> None:
        payload = {'ok': True, 'result': [{'update_id': 1, 'message': {'chat': {'id': 10, 'title': 'Chat'}, 'from': {'id': 20, 'username': 'alice'}, 'text': 'hello', 'date': 123}}]}
        class Resp(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self, *exc): return False
        with mock.patch('urllib.request.urlopen', return_value=Resp(json.dumps(payload).encode('utf-8'))):
            res = tg_bot_runtime.fetch_updates(policy_override={'enabled': True, 'token': '123:abc', 'base_url': 'https://api.telegram.org', 'timeout_sec': 1})
        self.assertTrue(res['ok'])
        with tempfile.TemporaryDirectory(prefix='noemaforge-tgbot-') as td:
            ing = tg_bot_runtime.ingest_updates(res['result'], td)
            self.assertEqual(ing['count'], 1)
            self.assertTrue(os.path.exists(ing['path']))

if __name__ == '__main__':
    unittest.main()