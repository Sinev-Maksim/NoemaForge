#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/profile_manager.py
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
# File: src/profile_manager.py
# Purpose: Read and toggle rollout-gated profile files so an operator face can inspect and enable supported runtime profiles without manual YAML editing.
# Invoked by / imported from:
#   - src/ui_snapshot.py
#   - tests/test_profile_manager.py
# Public API / entry functions:
#   - list_profiles
#   - set_profile_enabled
#   - operator_status_snapshot
# Inputs:
#   - config_root and profile identifiers.
# Output formats / side effects:
#   - JSON-compatible dictionaries; optional YAML writes when toggling a profile.
# Security considerations:
#   - Only edits top-level enabled flags for known profile files.
#   - Never touches epoch manifests or arbitrary config paths.
# AutoDoc: refreshed 2026-04-11 (manual)
# === End NoemaForge Autodoc File Header ===


import os
from typing import Any, Dict

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None  # type: ignore

PROFILE_FILES = {
    'voice': 'voice-backends-policy.yaml',
    'tts': 'tts-backends-policy.yaml',
    'av_bridge': 'discord-bridge-policy.yaml',
    'webgw': 'web-gateway-policy.yaml',
    'localgw': 'local-gateway-policy.yaml',
}


def _read_yaml(path: str) -> Dict[str, Any]:
    if not path or not os.path.exists(path) or yaml is None:
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            obj = yaml.safe_load(f) or {}
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _write_yaml(path: str, payload: Dict[str, Any]) -> str:
    if yaml is None:
        raise RuntimeError('yaml_unavailable')
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        yaml.safe_dump(payload, f, allow_unicode=True, sort_keys=False)
    return path


def list_profiles(config_root: str) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for profile_id, filename in PROFILE_FILES.items():
        path = os.path.join(config_root, filename)
        doc = _read_yaml(path)
        out[profile_id] = {
            'profile_id': profile_id,
            'path': path,
            'exists': os.path.exists(path),
            'enabled': bool(doc.get('enabled')) if isinstance(doc, dict) else False,
            'kind': str(doc.get('kind') or ''),
            'apiVersion': str(doc.get('apiVersion') or ''),
        }
    return out


def set_profile_enabled(config_root: str, profile_id: str, enabled: bool) -> Dict[str, Any]:
    filename = PROFILE_FILES.get(str(profile_id or '').strip())
    if not filename:
        raise RuntimeError('unknown_profile')
    path = os.path.join(config_root, filename)
    doc = _read_yaml(path)
    if not isinstance(doc, dict) or not doc:
        raise RuntimeError('profile_missing_or_invalid')
    doc['enabled'] = bool(enabled)
    _write_yaml(path, doc)
    return {'ok': True, 'profile_id': profile_id, 'path': path, 'enabled': bool(enabled)}


def operator_status_snapshot(config_root: str) -> Dict[str, Any]:
    profs = list_profiles(config_root)
    enabled = sorted([k for k, v in profs.items() if bool(v.get('enabled'))])
    disabled = sorted([k for k, v in profs.items() if not bool(v.get('enabled'))])
    return {
        'profiles': profs,
        'enabled_profiles': enabled,
        'disabled_profiles': disabled,
        'ready_count': len(enabled),
        'total_count': len(profs),
    }
