#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/rss_airlock.py
Zone: release/package
Version: 0.32.2
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
# File: src/rss_airlock.py
# Purpose: Combine WebGW RSS intake with a glove-safe-summary pass so allowed feeds become quarantine artifacts plus deterministic safe summaries.
# Invoked by / imported from:
#   - tests/test_rss_airlock.py
# Public API / entry functions:
#   - ingest_feed
# Inputs:
#   - feed_url, epoch_dir, actor, trace_id, and optional policy overrides.
# Output formats / side effects:
#   - Quarantine incident directories populated by WebGW.
#   - Glove report/sanitized text files and a JSON safe-summary artifact.
# Security considerations:
#   - Uses WebGW for network intake and never returns raw feed payload to callers.
#   - Summary text is generated from glove-sanitized output only.
# AutoDoc: refreshed 2026-04-11 (manual)
# === End NoemaForge Autodoc File Header ===


import json
import os
from typing import Any, Dict, Tuple

import webgateway
import glove_runner


def _incident_dir_from_result(result: Dict[str, Any]) -> str:
    path = str(result.get('incident_dir') or '').strip()
    if path:
        return path
    incident_id = str(result.get('incident_id') or '').strip()
    if incident_id:
        return webgateway.incident_dir_for_id(incident_id)
    return ''


def ingest_feed(*, feed_url: str, epoch_dir: str, actor: Dict[str, Any], trace_id: str) -> Tuple[bool, Dict[str, Any], str]:
    ok, result, reason = webgateway.fetch_to_quarantine(
        epoch_dir=epoch_dir,
        actor=actor,
        trace_id=trace_id,
        url=str(feed_url or '').strip(),
        channel='rss',
    )
    if not ok:
        return ok, result, reason
    incident_dir = _incident_dir_from_result(result)
    if not incident_dir:
        return False, {'error': 'missing_incident_dir', 'result': result}, 'rss_missing_incident_dir'
    glove_ok, glove_result = glove_runner.run_glove(sandbox_policy={}, incident_dir=incident_dir, profile='rss_sanitize', languages='en,ru')
    if not glove_ok:
        return False, {'incident_dir': incident_dir, 'glove': glove_result}, 'rss_glove_failed'
    sanitized_path = os.path.join(incident_dir, 'glove_sanitized.txt')
    summary_path = os.path.join(incident_dir, 'rss_safe_summary.json')
    summary = {
        'ok': True,
        'incident_id': result.get('incident_id'),
        'incident_dir': incident_dir,
        'summary_path': summary_path,
        'glove_report_path': os.path.join(incident_dir, 'glove_report.json'),
        'sanitized_path': sanitized_path,
        'channel': 'rss',
        'safe_text_preview': '',
    }
    if os.path.exists(sanitized_path):
        txt = open(sanitized_path, 'r', encoding='utf-8', errors='replace').read()
        summary['safe_text_preview'] = txt[:1200]
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    return True, summary, 'ok'


def intake_feed(*, url: str, epoch_dir: str, actor: Dict[str, Any], trace_id: str) -> Dict[str, Any]:
    ok, payload, reason = ingest_feed(feed_url=url, epoch_dir=epoch_dir, actor=actor, trace_id=trace_id)
    if ok:
        return payload
    raise RuntimeError(reason)
