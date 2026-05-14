#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_firstboot_status.py
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
# File: tests/test_firstboot_status.py
# Purpose: Helper / validation script 'test_firstboot_status.py'.
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


import json
import os
import sys
from pathlib import Path

ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(ROOT, 'src'))

import firstboot_status


def test_firstboot_status_roundtrip(tmp_path: Path):
    status = tmp_path / 'firstboot-status.json'
    events = tmp_path / 'firstboot-events.jsonl'
    firstboot_status.mark_started(str(status), str(events), share_root='/share', vault_root='/vault')
    firstboot_status.mark_step(str(status), str(events), step='eval', state='running', message='hello', extra={'n': 1})
    firstboot_status.mark_finished(str(status), str(events), state='done', message='bye')
    obj = json.loads(status.read_text(encoding='utf-8'))
    assert obj['state'] == 'done'
    lines = events.read_text(encoding='utf-8').strip().splitlines()
    assert len(lines) == 3
