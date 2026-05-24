#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_model_selection_datasets.py
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-14
Modified: 2026-05-14
Purpose: Create and manage model-selection plans and epoch candidate artifacts.
Inputs: Command-line arguments, environment variables, package files and local NoemaForge runtime state as applicable.
Outputs: Structured command output, files, service state or UI state as documented by the caller.
Side effects: Limited to the documented NoemaForge paths, runtime state directories or systemd units used by this file.
Tests: Syntax validation plus the release setup selftest, consistency-audit and targeted smoke checks.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

# === NoemaForge Autodoc File Header ===
# File: tests/test_model_selection_datasets.py
# Purpose: Helper / validation script 'test_model_selection_datasets.py'.
# Invoked by / imported from:
#   - pytest discovery or direct CLI/testing workflows
# Output formats / side effects:
#   - local JSON/YAML/text artifacts or process exit status
# AutoDoc: refreshed 2026-04-30 (manual)
# === End NoemaForge Autodoc File Header ===


import os
import sys
from pathlib import Path

ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(ROOT, 'src'))

from model_scorecards import load_eval_suite, _select_cases


def test_administrator_grounded_book_cases_are_loaded() -> None:
    doc = load_eval_suite(os.path.join(ROOT, 'configs'))
    cases = _select_cases(doc, suite='full', cap='llm', stream_id='operator.admin', role='administrator')
    ids = {str(c.get('id') or '') for c in cases if isinstance(c, dict)}
    assert 'administrator_book_chain_extract_v1' in ids
    assert 'administrator_book_chain_grounded_answer_v1' in ids



def test_role_eval_coverage_depth_is_not_shallow_for_operational_roles() -> None:
    import yaml
    with open(os.path.join(ROOT, 'configs', 'role-eval-datasets.yaml'), 'r', encoding='utf-8') as f:
        role_doc = yaml.safe_load(f) or {}
    doc = load_eval_suite(os.path.join(ROOT, 'configs'))
    shallow = []
    for key in sorted((role_doc.get('roles') or {}).keys()):
        if '/' not in str(key):
            continue
        stream_id, role = str(key).split('/', 1)
        cases = _select_cases(doc, suite=str((role_doc['roles'][key] or {}).get('suite') or 'smoke'), cap='llm', stream_id=stream_id, role=role)
        if len(cases) < 2:
            shallow.append(f'{key}:{len(cases)}')
    assert not shallow, shallow
