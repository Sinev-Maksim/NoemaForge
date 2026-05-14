#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/ics_import.py
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
# File: src/ics_import.py
# Purpose: Parse ICS calendar files into normalized NoemaForge learning/selfdev event records.
# Invoked by / imported from:
#   - src/selfdev_learning.py
#   - tests/test_workflow_modules.py
# Public API / entry functions:
#   - parse_ics_text
#   - import_ics_file
# Inputs:
#   - ICS text or path.
# Output formats / side effects:
#   - JSON event arrays when import_ics_file is used.
# AutoDoc: refreshed 2026-04-11 (manual)
# === End NoemaForge Autodoc File Header ===


import json
import os
from typing import Any, Dict, List


def _unfold(text: str) -> List[str]:
    lines = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    out: List[str] = []
    for line in lines:
        if line.startswith((' ', '\t')) and out:
            out[-1] += line[1:]
        else:
            out.append(line)
    return out


def parse_ics_text(text: str) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    cur: Dict[str, Any] | None = None
    for raw in _unfold(text or ''):
        line = raw.strip()
        if line == 'BEGIN:VEVENT':
            cur = {}
            continue
        if line == 'END:VEVENT':
            if cur is not None:
                events.append(cur)
            cur = None
            continue
        if cur is None or ':' not in line:
            continue
        key, value = line.split(':', 1)
        key = key.split(';', 1)[0].upper()
        cur[key] = value
    out: List[Dict[str, Any]] = []
    for ev in events:
        out.append({
            'uid': str(ev.get('UID') or ''),
            'summary': str(ev.get('SUMMARY') or ''),
            'description': str(ev.get('DESCRIPTION') or ''),
            'location': str(ev.get('LOCATION') or ''),
            'dtstart': str(ev.get('DTSTART') or ''),
            'dtend': str(ev.get('DTEND') or ''),
        })
    return out


def import_ics_file(path: str, out_path: str = '') -> Dict[str, Any]:
    text = open(path, 'r', encoding='utf-8', errors='replace').read()
    events = parse_ics_text(text)
    payload = {'ok': True, 'source_path': path, 'events': events}
    if out_path:
        os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        payload['out_path'] = out_path
    return payload
