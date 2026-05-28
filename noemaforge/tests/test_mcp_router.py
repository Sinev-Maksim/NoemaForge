#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_mcp_router.py
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
# File: tests/test_mcp_router.py
# Purpose: Unit-test the MCP router facade, local adapter execution, and envelope validation logic.
# Invoked by / imported from:
#   - unittest discovery
# Public API / entry functions:
#   - class MCPRouterTests
# Inputs:
#   - temporary catalog YAML files and issue JSON files created during test runtime
# Output formats / side effects:
#   - unittest assertions only
# AutoDoc: refreshed 2026-04-10 (manual)
# === End NoemaForge Autodoc File Header ===


import json
import os
import sys
import tempfile
import textwrap
import unittest

ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(ROOT, 'src'))

import mcp_router


class MCPRouterTests(unittest.TestCase):
    def _catalog_path(self) -> str:
        td = tempfile.mkdtemp(prefix='noemaforge-mcp-')
        docs_dir = os.path.join(td, 'docs')
        os.makedirs(docs_dir, exist_ok=True)
        with open(os.path.join(docs_dir, 'epochs.md'), 'w', encoding='utf-8') as f:
            f.write('Epoch immutability protects rollback safety.\n')
        issues_path = os.path.join(td, 'issues.json')
        with open(issues_path, 'w', encoding='utf-8') as f:
            json.dump([
                {'id': 'BRN-1', 'title': 'Epoch rollback', 'body': 'Rollback must stay targeted.', 'state': 'open', 'tags': ['epoch']},
                {'id': 'BRN-2', 'title': 'Voice import', 'body': 'Support sidecar transcript import.', 'state': 'triaged', 'tags': ['voice']},
            ], f)
        path = os.path.join(td, 'mcp-adapters.yaml')
        with open(path, 'w', encoding='utf-8') as f:
            f.write(textwrap.dedent(
                """
                apiVersion: noemaforge.mcp_adapters/v1
                kind: MCPAdapterCatalog
                enabled_by_default: true
                adapters:
                  - id: docs.search
                    title: Documentation search
                    mode: local
                    local_handler: docs_search
                    search_roots:
                      - docs
                    enabled: true
                  - id: issue.tracker
                    title: Issue tracker
                    mode: local
                    local_handler: issue_tracker
                    issues_path: issues.json
                    enabled: true
                  - id: remote.bundle
                    title: Remote bundle adapter
                    mode: bundle
                    bundle_id: mcp.bundle
                    enabled: true
                """
            ))
        return path

    def test_list_adapters(self) -> None:
        path = self._catalog_path()
        res = mcp_router.list_adapters(config_path=path, include_disabled=False)
        self.assertTrue(res['ok'])
        self.assertEqual(res['count'], 3)
        self.assertEqual(res['adapters'][0]['id'], 'docs.search')

    def test_build_call_envelope_for_bundle_adapter(self) -> None:
        path = self._catalog_path()
        ok, env, reason = mcp_router.build_call_envelope(
            adapter_id='remote.bundle',
            tool_name='search',
            args={'query': 'epoch immutability'},
            config_path=path,
        )
        self.assertTrue(ok, reason)
        self.assertEqual(env['adapter_id'], 'remote.bundle')
        self.assertEqual(env['tool_name'], 'search')
        self.assertEqual(env['input']['query'], 'epoch immutability')

    def test_docs_search_runtime_action(self) -> None:
        path = self._catalog_path()
        mode, payload, reason = mcp_router.runtime_action(
            'mcp.call',
            {'adapter_id': 'docs.search', 'tool_name': 'search', 'input': {'query': 'rollback safety'}},
            config_path=path,
        )
        self.assertEqual(mode, 'local_result', reason)
        self.assertEqual(payload['count'], 1)
        self.assertIn('epochs.md', payload['results'][0]['path'])

    def test_issue_tracker_runtime_action(self) -> None:
        path = self._catalog_path()
        mode, payload, reason = mcp_router.runtime_action(
            'mcp.call',
            {'adapter_id': 'issue.tracker', 'tool_name': 'search', 'input': {'query': 'voice'}},
            config_path=path,
        )
        self.assertEqual(mode, 'local_result', reason)
        self.assertEqual(payload['issues'][0]['id'], 'BRN-2')


if __name__ == '__main__':
    unittest.main()
