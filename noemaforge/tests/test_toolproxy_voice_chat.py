#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_toolproxy_voice_chat.py
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
# File: tests/test_toolproxy_voice_chat.py
# Purpose: Validate ToolProxy's administrator voice chat turn helper without requiring a live LLM gateway.
# Invoked by / imported from:
#   - unittest discovery
# Public API / entry functions:
#   - class ToolProxyVoiceChatTests
# Inputs:
#   - temporary session directories and patched helper functions
# Output formats / side effects:
#   - unittest assertions only
# AutoDoc: refreshed 2026-04-10 (manual)
# === End NoemaForge Autodoc File Header ===


import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(ROOT, 'src'))

_IMPORT_ERROR: "str | None" = None
try:
    import toolproxy
except ImportError as _e:
    _IMPORT_ERROR = str(_e)
    toolproxy = None  # type: ignore[assignment]


@unittest.skipIf(_IMPORT_ERROR is not None, f"requires Linux modules: {_IMPORT_ERROR}")
class ToolProxyVoiceChatTests(unittest.TestCase):
    def test_voice_chat_turn_routes_to_assistant_role(self) -> None:
        cfg = {
            'llm_gateway': {'unix_socket': '/tmp/fake.sock'},
            'model_registry_path': '/tmp/missing-registry.json',
            'model_scorecards_dir': '/tmp/model-scorecards',
            'voice_backends_policy_path': '/tmp/voice-backends-policy.yaml',
            'epoch': {'enabled': False},
        }
        aff = {'default': {'title': 'Executor', 'affirmation': 'Stay precise.', 'rules': []}}
        pol = {
            'streams': {
                'operator.admin': {
                    'roles': {
                        'administrator': {'allow': ['llm.chat']},
                        'dev': {'allow': ['voice.chat_turn']},
                    }
                }
            }
        }
        cat = {'streams': {'operator.admin': {'roles': {'administrator': {}, 'dev': {}}}}}
        actor = {'role': 'dev', 'project_id': 'p', 'run_id': 'r'}

        with tempfile.TemporaryDirectory(prefix='noemaforge-toolproxy-voice-') as td:
            turn_payload = {
                'session_id': 'sess-1',
                'session_path': os.path.join(td, 'session.json'),
                'assistant_target': {
                    'alias': 'administrator',
                    'stream_id': 'operator.admin',
                    'role': 'administrator',
                    'max_turn_history': 8,
                },
                'assistant_system_prompt': 'Use operational language.',
                'messages': [{'role': 'user', 'content': 'hello'}],
                'transcript': 'hello',
                'transcript_artifact': {'artifact_path': os.path.join(td, 'transcript.json')},
            }
            with mock.patch.object(toolproxy.voice_ingest, 'build_chat_turn', return_value=turn_payload), \
                 mock.patch.object(toolproxy, '_prepare_llm_chat_request', side_effect=lambda cfg, aff, payload, stream_id, role, actor, trace_id: (True, dict(payload, model='main'), 'ok')), \
                 mock.patch.object(toolproxy, '_llm_chat', return_value=(True, {'choices': [{'message': {'content': 'hello human'}}], 'model': 'main'}, 'ok')):
                ok, result, reason = toolproxy._voice_chat_turn(cfg, aff, pol, cat, actor, 'trace-1', {'assistant_alias': 'administrator'})
            self.assertTrue(ok)
            self.assertEqual(reason, 'ok')
            self.assertEqual(result['assistant_target']['role'], 'administrator')
            self.assertEqual(result['assistant_text'], 'hello human')
            self.assertTrue(os.path.exists(result['session']['session_path']))


if __name__ == '__main__':
    unittest.main()
