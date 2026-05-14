#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/selfdev_learning.py
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
# File: src/selfdev_learning.py
# Purpose: Maintain a lightweight self-development tracker from inbox notes and optional imported calendar events.
# Invoked by / imported from:
#   - tests/test_workflow_modules.py
# Public API / entry functions:
#   - ingest_learning_items
#   - merge_calendar_events
#   - build_review_queue
# Inputs:
#   - selfdev inbox files and optional normalized ICS event payloads.
# Output formats / side effects:
#   - JSON state files and review queue artifacts.
# AutoDoc: refreshed 2026-04-11 (manual)
# === End NoemaForge Autodoc File Header ===


import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List


def _load_state(path: str) -> Dict[str, Any]:
    try:
        with open(path, 'r', encoding='utf-8') as f:
            obj = json.load(f)
        return obj if isinstance(obj, dict) else {'items': {}}
    except Exception:
        return {'items': {}}


def _save_state(path: str, obj: Dict[str, Any]) -> str:
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    return path


def ingest_learning_items(inbox_dir: str, state_path: str) -> Dict[str, Any]:
    state = _load_state(state_path)
    items = state.get('items') if isinstance(state.get('items'), dict) else {}
    for p in sorted(Path(inbox_dir).glob('*')):
        if not p.is_file() or p.suffix.lower() not in ('.txt', '.md', '.json'):
            continue
        txt = p.read_text(encoding='utf-8', errors='replace')
        digest = hashlib.sha256((str(p) + '|' + txt).encode('utf-8')).hexdigest()[:16]
        title = txt.splitlines()[0].strip() if txt.strip() else p.stem
        items[digest] = {
            'id': digest,
            'title': title or p.stem,
            'source_path': str(p),
            'body_preview': txt[:400],
            'state': 'new',
            'source_kind': 'file',
        }
    state['items'] = items
    _save_state(state_path, state)
    return {'ok': True, 'count': len(items), 'state_path': state_path}


def merge_calendar_events(state_path: str, events: List[Dict[str, Any]]) -> Dict[str, Any]:
    state = _load_state(state_path)
    items = state.get('items') if isinstance(state.get('items'), dict) else {}
    for event in (events or []):
        digest = hashlib.sha256(json.dumps(event, sort_keys=True).encode('utf-8')).hexdigest()[:16]
        items[digest] = {
            'id': digest,
            'title': str(event.get('summary') or 'Calendar event'),
            'source_kind': 'ics',
            'dtstart': str(event.get('dtstart') or ''),
            'dtend': str(event.get('dtend') or ''),
            'state': 'scheduled',
            'event': event,
        }
    state['items'] = items
    _save_state(state_path, state)
    return {'ok': True, 'count': len(items), 'state_path': state_path}


def build_review_queue(state_path: str, out_dir: str) -> Dict[str, Any]:
    state = _load_state(state_path)
    items = list((state.get('items') or {}).values()) if isinstance(state.get('items'), dict) else []
    items.sort(key=lambda x: (str(x.get('state') or ''), str(x.get('title') or '')))
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, 'selfdev_review_queue.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump({'ok': True, 'items': items}, f, ensure_ascii=False, indent=2)
    return {'ok': True, 'count': len(items), 'out_path': out_path}
