#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/honeykeys.py
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
# File: src/honeykeys.py
# Purpose: Issue and track per-run honeykeys so leaked fake credentials can be attributed and quarantined.
# Invoked by / imported from:
#   - src/toolproxy.py
#   - tests/test_honeykeys.py
# Public API / entry functions:
#   - issue_honeykey
#   - lookup_honeykey
#   - mark_leaked
#   - scan_text
# Inputs:
#   - state_dir, model_id, run_id, role, project_id, and leaked text.
# Output formats / side effects:
#   - JSON records under the honeykeys state directory.
# Security considerations:
#   - Generated values are fake markers only.
#   - Detection never requires exposing the original cleartext key to executor roles.
# AutoDoc: refreshed 2026-04-11 (manual)
# === End NoemaForge Autodoc File Header ===


import json
import os
import secrets
from typing import Any, Dict, List, Optional

DEFAULT_STATE_DIR = '/var/lib/noemaforge/honeykeys'


def _nowz() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _record_path(state_dir: str, key_id: str) -> str:
    return os.path.join(state_dir, 'issued', key_id + '.json')


def issue_honeykey(*, state_dir: str = DEFAULT_STATE_DIR, model_id: str, run_id: str, role: str, project_id: str, ttl_sec: int = 86400) -> Dict[str, Any]:
    key_id = 'hk-' + secrets.token_hex(8)
    value = f'noemaforge_hk_{model_id}_{secrets.token_urlsafe(18)}'
    rec = {
        'ok': True,
        'key_id': key_id,
        'value': value,
        'model_id': str(model_id or ''),
        'run_id': str(run_id or ''),
        'role': str(role or ''),
        'project_id': str(project_id or ''),
        'issued_at': _nowz(),
        'ttl_sec': int(ttl_sec),
        'status': 'issued',
        'leaks': [],
    }
    path = _record_path(state_dir, key_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(rec, f, ensure_ascii=False, indent=2)
    rec['path'] = path
    return rec


def _iter_records(state_dir: str) -> List[Dict[str, Any]]:
    root = os.path.join(state_dir, 'issued')
    out: List[Dict[str, Any]] = []
    if not os.path.isdir(root):
        return out
    for fn in sorted(os.listdir(root)):
        if not fn.endswith('.json'):
            continue
        try:
            with open(os.path.join(root, fn), 'r', encoding='utf-8') as f:
                obj = json.load(f)
            if isinstance(obj, dict):
                out.append(obj)
        except Exception:
            continue
    return out


def lookup_honeykey(*, state_dir: str = DEFAULT_STATE_DIR, leaked_value: str) -> Optional[Dict[str, Any]]:
    leaked = str(leaked_value or '').strip()
    if not leaked:
        return None
    for rec in _iter_records(state_dir):
        if str(rec.get('value') or '') == leaked:
            return rec
    return None


def scan_text(*, state_dir: str = DEFAULT_STATE_DIR, text: str) -> List[Dict[str, Any]]:
    hay = str(text or '')
    hits: List[Dict[str, Any]] = []
    for rec in _iter_records(state_dir):
        val = str(rec.get('value') or '')
        if val and val in hay:
            hits.append(rec)
    return hits


def mark_leaked(*, state_dir: str = DEFAULT_STATE_DIR, leaked_value: str, source: str = '') -> Dict[str, Any]:
    rec = lookup_honeykey(state_dir=state_dir, leaked_value=leaked_value)
    if not rec:
        return {'ok': False, 'reason': 'honeykey_not_found'}
    rec['status'] = 'leaked'
    leaks = rec.get('leaks') if isinstance(rec.get('leaks'), list) else []
    leaks.append({'at': _nowz(), 'source': str(source or '')})
    rec['leaks'] = leaks
    path = _record_path(state_dir, str(rec.get('key_id') or 'unknown'))
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(rec, f, ensure_ascii=False, indent=2)
    incident_dir = os.path.join(state_dir, 'incidents')
    os.makedirs(incident_dir, exist_ok=True)
    inc_path = os.path.join(incident_dir, str(rec.get('key_id') or 'unknown') + '.json')
    with open(inc_path, 'w', encoding='utf-8') as f:
        json.dump({'ok': True, 'record': rec}, f, ensure_ascii=False, indent=2)
    return {'ok': True, 'record': rec, 'incident_path': inc_path}
