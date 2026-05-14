#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_role_inventory_alignment.py
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
# File: tests/test_role_inventory_alignment.py
# Purpose: Verify role inventory normalization across flow catalog, tool policy, eval datasets, and administrator delegation.
# Invoked by / imported from:
#   - pytest discovery
# Output formats / side effects:
#   - unittest assertions only
# AutoDoc: refreshed 2026-04-30 (manual)
# === End NoemaForge Autodoc File Header ===

#!/usr/bin/env python3

import os
from pathlib import Path

import yaml

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), '..')))


def _load(name: str):
    return yaml.safe_load((ROOT / 'configs' / name).read_text(encoding='utf-8')) or {}


def test_flow_nodes_have_same_stream_policy_and_eval_coverage() -> None:
    flow = _load('flow-catalog.yaml')
    tool = _load('tool-policy.yaml')
    evals = _load('role-eval-datasets.yaml')
    roles = evals.get('roles') or {}
    streams = (tool.get('streams') or {})
    missing = []
    for stream_id, spec in (flow.get('flows') or {}).items():
        role_policy = (((streams.get(stream_id) or {}).get('roles')) or {})
        for node in (spec.get('nodes') or []):
            role = str((node or {}).get('role') or '')
            if not role:
                continue
            if role not in role_policy or f'{stream_id}/{role}' not in roles:
                missing.append(f'{stream_id}/{role}')
    assert not missing, missing


def test_administrator_delegation_targets_are_staffed_and_policy_covered() -> None:
    admin = _load('administrator-policy.yaml')
    tool = _load('tool-policy.yaml')
    evals = _load('role-eval-datasets.yaml')
    roles = evals.get('roles') or {}
    streams = tool.get('streams') or {}
    missing = []
    for targets in (admin.get('delegation') or {}).values():
        for target in targets or []:
            if '/' not in str(target):
                continue
            stream_id, role = str(target).split('/', 1)
            if f'{stream_id}/{role}' not in roles:
                missing.append(f'eval:{target}')
            if role not in (((streams.get(stream_id) or {}).get('roles')) or {}):
                missing.append(f'policy:{target}')
    assert not missing, missing


def test_missing_affirmations_from_previous_audit_are_present() -> None:
    aff = _load('role-affirmations.yaml')
    roles = aff.get('roles') or {}
    required = {'blender_artist','story_writer','researcher','budget_analyst','modeler','coach','diary_writer','photo_indexer','guard','video_editor'}
    assert required.issubset(set(roles.keys()))
