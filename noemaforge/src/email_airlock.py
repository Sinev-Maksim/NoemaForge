#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/email_airlock.py
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
# File: src/email_airlock.py
# Purpose: Stage .eml content into a safe-summary airlock so email-like input can be reviewed without exposing raw prompt-injection text to executor roles.
# Invoked by / imported from:
#   - tests/test_email_airlock.py
# Public API / entry functions:
#   - parse_eml
#   - build_safe_summary
#   - intake_maildir
# Inputs:
#   - .eml files or Maildir-style directories.
# Output formats / side effects:
#   - JSON safe-summary artifacts and copied raw messages under the configured quarantine root.
# Security considerations:
#   - Uses PI scrubbing and redaction before emitting summaries.
#   - Keeps raw email isolated from the summary artifact.
# AutoDoc: refreshed 2026-04-11 (manual)
# === End NoemaForge Autodoc File Header ===


import email
import email.policy
import hashlib
import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Any, Dict, List

from pi_firewall import scan_and_scrub

DEFAULT_QUARANTINE_ROOT = '/var/lib/noemaforge/quarantine/email'
DEFAULT_SUMMARY_ROOT = '/workspace/outbox/email'


def _nowz() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _payload_text(msg: email.message.EmailMessage) -> str:
    if msg.is_multipart():
        parts: List[str] = []
        for part in msg.walk():
            if part.get_content_maintype() == 'multipart':
                continue
            ctype = str(part.get_content_type() or '').lower()
            if ctype == 'text/plain':
                try:
                    parts.append(part.get_content())
                except Exception:
                    continue
        return '\n'.join([p for p in parts if p]).strip()
    try:
        return str(msg.get_content() or '').strip()
    except Exception:
        return ''


def parse_eml(path: str) -> Dict[str, Any]:
    with open(path, 'rb') as f:
        msg = email.message_from_binary_file(f, policy=email.policy.default)
    text = _payload_text(msg)
    return {
        'path': str(path),
        'subject': str(msg.get('subject') or ''),
        'from': str(msg.get('from') or ''),
        'to': str(msg.get('to') or ''),
        'date': str(msg.get('date') or ''),
        'message_id': str(msg.get('message-id') or ''),
        'text': text,
    }


def build_safe_summary(path: str, *, quarantine_root: str = DEFAULT_QUARANTINE_ROOT, summary_root: str = DEFAULT_SUMMARY_ROOT) -> Dict[str, Any]:
    parsed = parse_eml(path)
    digest = hashlib.sha256(open(path, 'rb').read()).hexdigest()
    incident_id = f'email-{uuid.uuid4().hex[:12]}'
    incident_dir = os.path.join(quarantine_root, incident_id)
    os.makedirs(incident_dir, exist_ok=True)
    raw_copy = os.path.join(incident_dir, 'raw.eml')
    shutil.copy2(path, raw_copy)

    scrub = scan_and_scrub(parsed.get('text') or '', source=f'email:{os.path.basename(path)}')
    safe = {
        'ok': True,
        'incident_id': incident_id,
        'incident_dir': incident_dir,
        'source_path': str(path),
        'raw_copy': raw_copy,
        'sha256': digest,
        'created_at': _nowz(),
        'headers': {
            'subject': parsed.get('subject') or '',
            'from': parsed.get('from') or '',
            'to': parsed.get('to') or '',
            'date': parsed.get('date') or '',
            'message_id': parsed.get('message_id') or '',
        },
        'source': {
            'subject': parsed.get('subject') or '',
            'from': parsed.get('from') or '',
            'to': parsed.get('to') or '',
            'date': parsed.get('date') or '',
            'message_id': parsed.get('message_id') or '',
        },
        'scrub': {
            'pre': scrub.get('pre') or {},
            'post': scrub.get('post') or {},
        },
        'safe_summary': {
            'preview': str(scrub.get('scrubbed_text') or '')[:1500],
            'contains_injection_markers': bool(((scrub.get('pre') or {}).get('severity') or '').lower() not in ('', 'none')),
        },
    }
    os.makedirs(summary_root, exist_ok=True)
    summary_path = os.path.join(summary_root, incident_id + '.json')
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(safe, f, ensure_ascii=False, indent=2)
    safe['summary_path'] = summary_path
    with open(os.path.join(incident_dir, 'safe_summary.json'), 'w', encoding='utf-8') as f:
        json.dump(safe, f, ensure_ascii=False, indent=2)
    return safe


def intake_maildir(maildir_root: str, *, quarantine_root: str = DEFAULT_QUARANTINE_ROOT, summary_root: str = DEFAULT_SUMMARY_ROOT) -> Dict[str, Any]:
    root = Path(maildir_root)
    files = sorted([p for p in root.rglob('*') if p.is_file() and p.suffix.lower() in ('', '.eml')])
    processed: List[Dict[str, Any]] = []
    for p in files:
        processed.append(build_safe_summary(str(p), quarantine_root=quarantine_root, summary_root=summary_root))
    return {'ok': True, 'maildir_root': str(root), 'processed': len(processed), 'items': processed}
