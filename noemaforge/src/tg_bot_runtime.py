#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/tg_bot_runtime.py
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
# File: src/tg_bot_runtime.py
# Purpose: Provide a policy-gated Telegram Bot API poller and update normalizer that can feed the same downstream safety path as export-based Telegram intake.
# Invoked by / imported from:
#   - tests/test_tg_bot_runtime.py
# Public API / entry functions:
#   - fetch_updates
#   - normalize_update
#   - ingest_updates
# Inputs:
#   - Bot token, base URL, and optional local policy overrides.
# Output formats / side effects:
#   - JSON update spool artifacts and normalized update dictionaries.
# Security considerations:
#   - Network access is optional and policy-gated.
#   - Normalization emits only message metadata and text fields needed for downstream quarantine/workflow handling.
# AutoDoc: refreshed 2026-04-11 (manual)
# === End NoemaForge Autodoc File Header ===


import json
import os
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None  # type: ignore

DEFAULT_POLICY_PATH = '/opt/noemaforge/configs/tg-bot-policy.yaml'


def _default_policy() -> Dict[str, Any]:
    return {
        'apiVersion': 'noemaforge.tgbot/v1',
        'kind': 'TelegramBotPolicy',
        'enabled': False,
        'base_url': 'https://api.telegram.org',
        'token': '',
        'timeout_sec': 15,
        'outbox_dir': '/workspace/outbox/tg_bot',
    }


def _load_policy(policy_path: str = DEFAULT_POLICY_PATH, policy_override: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    base = _default_policy()
    doc: Dict[str, Any] = {}
    if policy_path and os.path.exists(policy_path) and yaml is not None:
        try:
            with open(policy_path, 'r', encoding='utf-8') as f:
                loaded = yaml.safe_load(f) or {}
            if isinstance(loaded, dict):
                doc = loaded
        except Exception:
            doc = {}
    out = dict(base)
    out.update(doc)
    if isinstance(policy_override, dict):
        out.update(policy_override)
    return out


def fetch_updates(*, offset: int = 0, policy_path: str = DEFAULT_POLICY_PATH, policy_override: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    pol = _load_policy(policy_path=policy_path, policy_override=policy_override)
    if not bool(pol.get('enabled')):
        raise RuntimeError('tg_bot_disabled')
    token = str(pol.get('token') or '').strip()
    if not token:
        raise RuntimeError('tg_bot_missing_token')
    base_url = str(pol.get('base_url') or 'https://api.telegram.org').rstrip('/')
    query = urllib.parse.urlencode({'offset': int(offset), 'timeout': int(pol.get('timeout_sec') or 15)})
    url = f"{base_url}/bot{token}/getUpdates?{query}"
    with urllib.request.urlopen(url, timeout=float(pol.get('timeout_sec') or 15) + 5.0) as resp:
        data = json.loads(resp.read().decode('utf-8'))
    return data if isinstance(data, dict) else {'ok': False, 'result': []}


def normalize_update(update: Dict[str, Any]) -> Dict[str, Any]:
    msg = (update or {}).get('message') or (update or {}).get('channel_post') or {}
    chat = msg.get('chat') or {}
    sender = msg.get('from') or {}
    text = str(msg.get('text') or msg.get('caption') or '').strip()
    return {
        'update_id': update.get('update_id'),
        'chat_id': chat.get('id'),
        'chat_title': chat.get('title') or chat.get('username') or '',
        'sender': sender.get('username') or sender.get('first_name') or '',
        'sender_id': sender.get('id'),
        'date': msg.get('date'),
        'text': text,
        'has_text': bool(text),
    }


def ingest_updates(updates: List[Dict[str, Any]], out_dir: str) -> Dict[str, Any]:
    os.makedirs(out_dir, exist_ok=True)
    normalized = [normalize_update(u) for u in (updates or [])]
    path = os.path.join(out_dir, 'tg_bot_updates.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({'ok': True, 'updates': normalized}, f, ensure_ascii=False, indent=2)
    return {'ok': True, 'count': len(normalized), 'path': path, 'updates': normalized}
