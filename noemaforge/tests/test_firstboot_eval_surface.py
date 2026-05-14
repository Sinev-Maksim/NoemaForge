#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_firstboot_eval_surface.py
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
# File: tests/test_firstboot_eval_surface.py
# Purpose: Helper / validation script 'test_firstboot_eval_surface.py'.
# Invoked by / imported from:
#   - pytest discovery or direct CLI/testing workflows
# Output formats / side effects:
#   - local JSON/YAML/text artifacts or process exit status
# AutoDoc: refreshed 2026-04-30 (manual)
# === End NoemaForge Autodoc File Header ===


import os
import sys
import yaml

ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(ROOT, 'src'))

from firstboot_eval import default_eval_surface


def test_firstboot_eval_surface_includes_administrator() -> None:
    surface = default_eval_surface()
    assert ('operator.admin', 'administrator') in surface
    assert ('system.guard', 'surgeon') in surface



def test_firstboot_eval_surface_matches_role_eval_catalog() -> None:
    with open(os.path.join(ROOT, 'configs', 'role-eval-datasets.yaml'), 'r', encoding='utf-8') as f:
        doc = yaml.safe_load(f) or {}
    expected = sorted(tuple(str(k).split('/', 1)) for k in (doc.get('roles') or {}).keys() if '/' in str(k))
    assert sorted(default_eval_surface()) == expected
