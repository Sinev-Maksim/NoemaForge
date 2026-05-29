#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_tts_runtime.py
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
# File: tests/test_tts_runtime.py
# Purpose: Validate the local TTS runtime and virtual-microphone backchannel helpers.
# Invoked by / imported from:
#   - unittest discovery
# Output formats / side effects:
#   - unittest assertions only
# AutoDoc: refreshed 2026-04-11 (manual)
# === End NoemaForge Autodoc File Header ===
import os, sys, tempfile, textwrap, unittest
ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(ROOT, 'src'))
import tts_runtime

class TTSRuntimeTests(unittest.TestCase):
    def _policy(self, td: str) -> dict:
        synth = os.path.join(td, 'fake_tts.py')
        inject = os.path.join(td, 'fake_inject.py')
        with open(synth, 'w', encoding='utf-8') as f:
            f.write(textwrap.dedent("""
                import os, struct, sys, wave
                out = sys.argv[1]
                os.makedirs(os.path.dirname(out), exist_ok=True)
                with wave.open(out, 'wb') as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(22050)
                    wf.writeframes(struct.pack('<h', 0) * 22050)
            """))
        with open(inject, 'w', encoding='utf-8') as f:
            f.write(textwrap.dedent("""
                import os, sys
                out = sys.argv[2]
                os.makedirs(os.path.dirname(out), exist_ok=True)
                with open(out, 'w', encoding='utf-8') as h:
                    h.write(sys.argv[1])
            """))
        return {
            'enabled': True,
            'artifacts_root': os.path.join(td, 'tts_artifacts'),
            'sessions_root': os.path.join(td, 'tts_sessions'),
            'synthesis': {
                'enabled': True,
                'backend_order': ['command'],
                'default_voice_id': 'administrator',
                'command': {'argv': [sys.executable, synth, '{output_path}']},
            },
            'backchannel': {
                'enabled': True,
                'backend_order': ['command'],
                'output_path': os.path.join(td, 'virtual_mic', 'last.txt'),
                'command': {'argv': [sys.executable, inject, '{audio_path}', '{output_path}']},
            },
        }

    def test_tts_backchannel_command_backend(self) -> None:
        with tempfile.TemporaryDirectory(prefix='noemaforge-tts-') as td:
            pol = self._policy(td)
            res = tts_runtime.tts_backchannel(text='Hello from NoemaForge', session_id='sess-1', policy_override=pol)
            self.assertTrue(os.path.exists(res['tts']['audio_path']))
            self.assertTrue(os.path.exists(res['backchannel']['output_path']))
            self.assertEqual(res['tts']['voice_id'], 'administrator')

    def test_prepare_tool_action(self) -> None:
        with tempfile.TemporaryDirectory(prefix='noemaforge-tts-') as td:
            pol = self._policy(td)
            ok, payload, reason = tts_runtime.prepare_tool_action('voice.tts_backchannel', {'text':'Status green', 'policy_override': pol}, policy_path='/tmp/missing.yaml')
            self.assertTrue(ok)
            self.assertEqual(reason, 'ok')
            self.assertIn('tts', payload)

if __name__ == '__main__':
    unittest.main()