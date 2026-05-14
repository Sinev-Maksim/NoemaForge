#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_firstboot_orchestrator.py
Zone: release/package
Version: 0.31.13.alpha
Created: 2026-05-14
Modified: 2026-05-14
Purpose: Coordinate first-start model inventory, tournament, staffing and epoch safety checks.
Inputs: Command-line arguments, environment variables, package files and local NoemaForge runtime state as applicable.
Outputs: Structured command output, files, service state or UI state as documented by the caller.
Side effects: Limited to the documented NoemaForge paths, runtime state directories or systemd units used by this file.
Tests: Syntax validation plus the release setup selftest, consistency-audit and targeted smoke checks.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

# === NoemaForge Autodoc File Header ===
# File: tests/test_firstboot_orchestrator.py
# Purpose: Helper / validation script 'test_firstboot_orchestrator.py'.
# Invoked by / imported from:
#   - direct operator invocation or test discovery
# Public API / entry functions:
#   - module-level helpers / CLI entrypoint
# Inputs:
#   - local filesystem paths, command-line arguments, and NoemaForge runtime/install state
# Output formats / side effects:
#   - local JSON/YAML/text artifacts or process exit status
# AutoDoc: refreshed 2026-04-13 (manual)
# === End NoemaForge Autodoc File Header ===


import os
import sys
from pathlib import Path

ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(ROOT, 'src'))

import firstboot_orchestrator


def test_threshold_pass_true():
    assert firstboot_orchestrator._threshold_pass(
        {'pass_rate': 0.7, 'json_parse_rate': 0.9, 'quality_score': 0.6},
        {'pass_rate': 0.6, 'json_parse_rate': 0.8, 'quality_score': 0.55},
    )


def test_profile_available_missing_required(tmp_path: Path):
    ok, missing = firstboot_orchestrator._profile_available('x', {'x': {'available_when': [{'path': str(tmp_path / 'missing'), 'kind': 'file'}]}})
    assert ok is False
    assert missing


def test_discover_gguf_shortlist(tmp_path: Path):
    root = tmp_path / 'Vault' / 'models-gguf'
    root.mkdir(parents=True)
    (root / 'qwen.gguf').write_bytes(b'1')
    (root / 'phi.gguf').write_bytes(b'12')
    out = firstboot_orchestrator._discover_gguf(str(tmp_path / 'Vault'), include_download_mirror=False, shortlist=['phi'], candidate_limit=10)
    assert len(out) == 1
    assert out[0].endswith('phi.gguf')


def test_discover_gguf_filters_non_head_shards(tmp_path: Path):
    root = tmp_path / 'Vault' / 'models-gguf'
    root.mkdir(parents=True)
    (root / 'model-00001-of-00003.gguf').write_bytes(b'head')
    (root / 'model-00002-of-00003.gguf').write_bytes(b'tail')
    (root / 'model-00003-of-00003.gguf').write_bytes(b'tail')
    out = firstboot_orchestrator._discover_gguf(str(tmp_path / 'Vault'), candidate_limit=10)
    assert len(out) == 1
    assert out[0].endswith('model-00001-of-00003.gguf')
    assert '00002-of' not in out[0]
