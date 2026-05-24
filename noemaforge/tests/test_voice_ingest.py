#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_voice_ingest.py
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
# File: tests/test_voice_ingest.py
# Purpose: Unit-test deterministic voice staging, live command backends, transcript import, and session artifact creation.
# Invoked by / imported from:
#   - unittest discovery
# Public API / entry functions:
#   - class VoiceIngestTests
# Inputs:
#   - temporary audio/text files and fake backend scripts created during test runtime
# Output formats / side effects:
#   - unittest assertions only
# AutoDoc: refreshed 2026-04-10 (manual)
# === End NoemaForge Autodoc File Header ===


import base64
import json
import os
import sys
import tempfile
import textwrap
import unittest

ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(ROOT, 'src'))

import voice_ingest


class VoiceIngestTests(unittest.TestCase):
    def _command_policy(self, td: str, *, with_stt: bool = True) -> dict:
        recorder = os.path.join(td, 'fake_recorder.py')
        with open(recorder, 'w', encoding='utf-8') as f:
            f.write(textwrap.dedent('''
                import struct, sys, wave
                path = sys.argv[1]
                rate = int(float(sys.argv[2]))
                channels = int(sys.argv[3])
                seconds = max(1, int(float(sys.argv[4])))
                frames = rate * seconds
                with wave.open(path, 'wb') as wf:
                    wf.setnchannels(channels)
                    wf.setsampwidth(2)
                    wf.setframerate(rate)
                    silence = struct.pack('<h', 0) * frames * channels
                    wf.writeframes(silence)
            '''))
        transcriber = os.path.join(td, 'fake_transcriber.py')
        with open(transcriber, 'w', encoding='utf-8') as f:
            f.write(textwrap.dedent('''
                import json, os, sys
                audio_path = sys.argv[1]
                out_json = sys.argv[2]
                payload = {
                    'text': 'hello administrator from live stt',
                    'language': 'en',
                    'segments': [{'start': 0.0, 'end': 1.0, 'text': 'hello administrator from live stt'}],
                    'audio_seen': os.path.basename(audio_path),
                }
                with open(out_json, 'w', encoding='utf-8') as f:
                    json.dump(payload, f)
            '''))
        policy = {
            'enabled': True,
            'microphone': {
                'enabled': True,
                'backend_order': ['command'],
                'sample_rate_hz': 16000,
                'channels': 1,
                'max_seconds': 1,
                'command': {
                    'argv': [sys.executable, recorder, '{output_path}', '{sample_rate_hz}', '{channels}', '{duration_sec}']
                },
            },
            'stt': {
                'enabled': with_stt,
                'backend_order': ['command'],
                'default_language': 'en',
                'command': {
                    'argv': [sys.executable, transcriber, '{audio_path}', '{output_json_path}'],
                    'result_mode': 'json_file',
                },
            },
            'assistant': {
                'default_alias': 'administrator',
                'history_root': os.path.join(td, 'sessions'),
                'max_turn_history': 8,
            },
            'assistant_targets': {
                'administrator': {
                    'stream_id': 'operator.admin',
                    'role': 'administrator',
                    'title': 'NoemaForge Administrator',
                    'system_preamble': 'Be short and operational.',
                }
            },
        }
        return policy

    def test_capture_and_manual_transcript(self) -> None:
        with tempfile.TemporaryDirectory(prefix='noemaforge-voice-') as td:
            audio = os.path.join(td, 'sample.wav')
            with open(audio, 'wb') as f:
                f.write(b'RIFF....WAVEfmt ')

            inbox = os.path.join(td, 'inbox')
            outbox = os.path.join(td, 'outbox')
            cap = voice_ingest.capture(audio_path=audio, note='memo', inbox_root=inbox)
            self.assertTrue(os.path.exists(cap['captured_path']))
            self.assertTrue(os.path.exists(cap['manifest_path']))

            tr = voice_ingest.transcribe(
                manifest_path=cap['manifest_path'],
                transcript_text='hello world',
                outbox_root=outbox,
            )
            self.assertEqual(tr['status'], 'complete')
            self.assertTrue(os.path.exists(tr['artifact_path']))
            self.assertTrue(os.path.exists(tr['transcript_path']))

    def test_capture_from_inline_bytes_and_sidecar_import(self) -> None:
        with tempfile.TemporaryDirectory(prefix='noemaforge-voice-') as td:
            inbox = os.path.join(td, 'inbox')
            outbox = os.path.join(td, 'outbox')
            cap = voice_ingest.capture(
                audio_bytes_b64=base64.b64encode(b'RIFF....WAVEfmt ').decode('ascii'),
                filename='memo.wav',
                inbox_root=inbox,
            )
            sidecar = os.path.splitext(cap['captured_path'])[0] + '.txt'
            with open(sidecar, 'w', encoding='utf-8') as f:
                f.write('remember the canary gate\n')
            tr = voice_ingest.transcribe(manifest_path=cap['manifest_path'], outbox_root=outbox)
            self.assertEqual(tr['status'], 'complete')
            self.assertEqual(tr['mode'], 'sidecar_import')
            self.assertTrue(os.path.exists(tr['transcript_path']))

    def test_auto_capture_preserves_original_sidecar_lookup(self) -> None:
        with tempfile.TemporaryDirectory(prefix='noemaforge-voice-') as td:
            audio = os.path.join(td, 'memo.wav')
            with open(audio, 'wb') as f:
                f.write(b'RIFF....WAVEfmt ')
            with open(os.path.splitext(audio)[0] + '.txt', 'w', encoding='utf-8') as f:
                f.write('from original sidecar')
            res = voice_ingest.transcribe(audio_path=audio, inbox_root=os.path.join(td, 'inbox'), outbox_root=os.path.join(td, 'outbox'))
            self.assertEqual(res['status'], 'complete')
            self.assertEqual(res['mode'], 'sidecar_import')

    def test_deferred_transcription_request(self) -> None:
        with tempfile.TemporaryDirectory(prefix='noemaforge-voice-') as td:
            audio = os.path.join(td, 'sample.wav')
            with open(audio, 'wb') as f:
                f.write(b'RIFF....WAVEfmt ')
            res = voice_ingest.transcribe(audio_path=audio, inbox_root=os.path.join(td, 'ibox'), outbox_root=os.path.join(td, 'obox'))
            self.assertEqual(res['status'], 'queued')
            self.assertTrue(os.path.exists(res['job_path']))

    def test_capture_live_with_command_backend(self) -> None:
        with tempfile.TemporaryDirectory(prefix='noemaforge-voice-live-') as td:
            policy = self._command_policy(td, with_stt=False)
            cap = voice_ingest.capture_live(
                max_seconds=1,
                inbox_root=os.path.join(td, 'inbox'),
                policy_override=policy,
                backend='command',
            )
            self.assertTrue(os.path.exists(cap['captured_path']))
            self.assertTrue(cap['source_mode'].startswith('microphone:command'))
            self.assertGreater(cap['size_bytes'], 32)

    def test_transcribe_live_with_command_backend(self) -> None:
        with tempfile.TemporaryDirectory(prefix='noemaforge-voice-live-') as td:
            policy = self._command_policy(td)
            res = voice_ingest.transcribe_live(
                from_microphone=True,
                max_seconds=1,
                inbox_root=os.path.join(td, 'inbox'),
                outbox_root=os.path.join(td, 'outbox'),
                policy_override=policy,
                backend='command',
            )
            self.assertEqual(res['status'], 'complete')
            self.assertEqual(res['mode'], 'live_stt')
            self.assertEqual(res['backend'], 'command')
            self.assertTrue(os.path.exists(res['transcript_path']))
            self.assertIn('hello administrator', res['transcript_preview'])

    def test_build_chat_turn_and_update_session(self) -> None:
        with tempfile.TemporaryDirectory(prefix='noemaforge-voice-chat-') as td:
            policy = self._command_policy(td)
            turn = voice_ingest.build_chat_turn(
                args={'transcript_text': 'status please', 'assistant_alias': 'administrator'},
                policy_override=policy,
                outbox_root=os.path.join(td, 'outbox'),
            )
            self.assertEqual(turn['assistant_target']['role'], 'administrator')
            self.assertEqual(turn['messages'][-1]['content'], 'status please')
            session = voice_ingest.update_chat_session(
                session_path=turn['session_path'],
                session_id=turn['session_id'],
                assistant_target=turn['assistant_target'],
                transcript_text=turn['transcript'],
                llm_result={'choices': [{'message': {'content': 'All systems nominal.'}}]},
                transcript_artifact=turn['transcript_artifact'],
            )
            self.assertEqual(session['assistant_role'], 'administrator')
            self.assertEqual(session['messages'][-1]['content'], 'All systems nominal.')
            self.assertEqual(voice_ingest.extract_assistant_text({'choices': [{'message': {'content': 'ok'}}]}), 'ok')
            self.assertTrue(os.path.exists(turn['session_path']))
            with open(turn['session_path'], 'r', encoding='utf-8') as f:
                persisted = json.load(f)
            self.assertEqual(persisted['turns'][-1]['assistant_text'], 'All systems nominal.')


if __name__ == '__main__':
    unittest.main()
