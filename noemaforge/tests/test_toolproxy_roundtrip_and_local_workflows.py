#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_toolproxy_roundtrip_and_local_workflows.py
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
# File: tests/test_toolproxy_roundtrip_and_local_workflows.py
# Purpose: Validate ToolProxy roundtrip helpers and local workflow facades.
# Invoked by / imported from:
#   - unittest discovery
# Output formats / side effects:
#   - unittest assertions only
# AutoDoc: refreshed 2026-04-11 (manual)
# === End NoemaForge Autodoc File Header ===
import os, sqlite3, sys, tempfile, unittest
from unittest import mock
ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(ROOT, 'src'))
import toolproxy

class ToolProxyRoundtripTests(unittest.TestCase):
    def test_voice_chat_roundtrip_merges_tts_result(self) -> None:
        cfg = {'tts_backends_policy_path': '/tmp/tts.yaml', 'epoch': {'enabled': False}}
        with mock.patch.object(toolproxy, '_voice_chat_turn', return_value=(True, {'assistant_text':'hello', 'session': {'session_id':'s1'}}, 'ok')), \
             mock.patch.object(toolproxy.tts_runtime, 'tts_backchannel', return_value={'tts': {'audio_path': '/tmp/a.wav'}, 'backchannel': {'output_path': '/tmp/out'}}):
            ok, payload, reason = toolproxy._voice_chat_roundtrip(cfg, {}, {}, {}, {'role':'dev'}, 't1', {})
        self.assertTrue(ok)
        self.assertEqual(reason, 'ok')
        self.assertIn('tts', payload)

    def test_local_workflow_facades(self) -> None:
        cfg = {'profiles_root': '/tmp', 'epoch': {'enabled': False}, 'honeykeys': {'enabled': False}}
        with tempfile.TemporaryDirectory(prefix='noemaforge-toolproxy-local-') as td:
            import yaml
            for fn in ('voice-backends-policy.yaml','tts-backends-policy.yaml','discord-bridge-policy.yaml','web-gateway-policy.yaml','local-gateway-policy.yaml'):
                with open(os.path.join(td, fn), 'w', encoding='utf-8') as f:
                    yaml.safe_dump({'apiVersion':'x','kind':'Policy','enabled': False}, f, sort_keys=False)
            cfg['profiles_root'] = td
            mode, payload, reason = toolproxy._plugin_facade_or_args(cfg, 'operator.status', {})
            self.assertEqual(mode, 'local_result')
            self.assertEqual(reason, 'ok')
            self.assertIn('profiles', payload)

            db = os.path.join(td, 'tg.sqlite')
            con = sqlite3.connect(db)
            con.execute('CREATE TABLE messages(chat_id TEXT, msg_id INTEGER, date TEXT, sender TEXT, text_clean TEXT)')
            con.execute('CREATE TABLE links(chat_id TEXT, msg_id INTEGER, url TEXT)')
            con.execute('INSERT INTO messages VALUES(?,?,?,?,?)', ('c1',1,'2026-01-01','a','hello http://x'))
            con.execute('INSERT INTO links VALUES(?,?,?)', ('c1',1,'http://x'))
            con.commit(); con.close()
            mode, payload, reason = toolproxy._plugin_facade_or_args(cfg, 'tg.channel.curate', {'index_db': db, 'out_dir': os.path.join(td, 'tg_out')})
            self.assertEqual(mode, 'local_result')
            self.assertEqual(payload['count'], 1)

if __name__ == '__main__':
    unittest.main()