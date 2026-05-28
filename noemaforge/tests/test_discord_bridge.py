#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_discord_bridge.py
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
# File: tests/test_discord_bridge.py
# Purpose: Validate deterministic Discord bridge asset generation, command-backed worker lifecycle, and ToolProxy-facing local facade behavior.
# Invoked by / imported from:
#   - unittest discovery
# Public API / entry functions:
#   - class DiscordBridgeTests
# Inputs:
#   - temporary directories and fake backend scripts created during test runtime
# Output formats / side effects:
#   - unittest assertions only
# AutoDoc: refreshed 2026-04-10 (manual)
# === End NoemaForge Autodoc File Header ===


import os
import sys
import tempfile
import textwrap
import time
import unittest

ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(ROOT, 'src'))

import discord_bridge
import toolproxy


class DiscordBridgeTests(unittest.TestCase):
    def _policy(self, td: str) -> dict:
        worker = os.path.join(td, 'bridge_worker.py')
        with open(worker, 'w', encoding='utf-8') as f:
            f.write(textwrap.dedent("""
                import os
                import sys
                import time
                label = sys.argv[1]
                output = sys.argv[2]
                os.makedirs(os.path.dirname(output), exist_ok=True)
                with open(output, 'w', encoding='utf-8') as out:
                    out.write(label)
                time.sleep(30)
            """))
        return {
            'enabled': True,
            'sessions_root': os.path.join(td, 'sessions'),
            'artifacts_root': os.path.join(td, 'assets'),
            'capture': {
                'av_delay_ms': 200,
                'video': {
                    'enabled': True,
                    'backend_order': ['command'],
                    'output_path': os.path.join(td, 'video.out'),
                    'command': {
                        'argv': [sys.executable, worker, 'video', '{output_path}']
                    },
                },
                'audio': {
                    'enabled': True,
                    'backend_order': ['command'],
                    'output_path': os.path.join(td, 'audio.out'),
                    'delay_ms': 200,
                    'command': {
                        'argv': [sys.executable, worker, 'audio', '{output_path}']
                    },
                },
            },
            'processing': {
                'background': {
                    'enabled': True,
                    'backend_order': ['prompt_gradient_ppm'],
                    'width': 160,
                    'height': 90,
                },
                'mask': {
                    'enabled': True,
                    'backend_order': ['soft_center_mask_pgm'],
                    'width': 160,
                    'height': 90,
                    'blur_px': 10,
                },
            },
            'discord_client': {
                'recommended_video_device': '/dev/video10',
                'recommended_audio_source': 'noemaforge-discord.monitor',
                'launch_notes': ['Use Discord desktop for transport.'],
            },
        }

    def test_prepare_assets_builtin_generators(self) -> None:
        with tempfile.TemporaryDirectory(prefix='noemaforge-discord-assets-') as td:
            policy = self._policy(td)
            assets = discord_bridge.prepare_assets(
                background_prompt='neon control room',
                mask_prompt='portrait left',
                policy_override=policy,
            )
            self.assertTrue(os.path.exists(assets['manifest_path']))
            self.assertTrue(os.path.exists(assets['background']['path']))
            self.assertTrue(os.path.exists(assets['mask']['path']))
            self.assertEqual(assets['background']['format'], 'ppm')
            self.assertEqual(assets['mask']['format'], 'pgm')

    def test_start_status_stop_bridge_with_command_backends(self) -> None:
        with tempfile.TemporaryDirectory(prefix='noemaforge-discord-bridge-') as td:
            policy = self._policy(td)
            session = discord_bridge.start_bridge(
                background_prompt='aurora station',
                mask_prompt='portrait right',
                policy_override=policy,
            )
            self.assertTrue(os.path.exists(session['manifest_path']))
            self.assertEqual(len(session['workers']), 2)
            time.sleep(0.2)
            status = discord_bridge.bridge_status(manifest_path=session['manifest_path'], policy_override=policy)
            self.assertTrue(any(w.get('alive') for w in status['workers']))
            self.assertEqual(status['handoff_notes'][0], 'Use Discord desktop for transport.')
            stopped = discord_bridge.stop_bridge(manifest_path=session['manifest_path'], policy_override=policy)
            self.assertTrue(all(w.get('status') == 'stopped' for w in stopped['workers']))

    def test_toolproxy_facade_routes_discord_actions(self) -> None:
        with tempfile.TemporaryDirectory(prefix='noemaforge-discord-toolproxy-') as td:
            cfg = {'discord_bridge_policy_path': '/tmp/discord-bridge-policy.yaml', 'epoch': {'enabled': False}}
            policy = self._policy(td)
            mode, payload, reason = toolproxy._plugin_facade_or_args(
                cfg,
                'discord.assets.prepare',
                {'background_prompt': 'studio light', 'mask_prompt': 'portrait', 'policy_override': policy},
            )
            self.assertEqual(mode, 'local_result')
            self.assertEqual(reason, 'ok')
            self.assertTrue(os.path.exists(payload['manifest_path']))


if __name__ == '__main__':
    unittest.main()
