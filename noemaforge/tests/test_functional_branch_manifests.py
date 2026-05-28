#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_functional_branch_manifests.py
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
# File: tests/test_functional_branch_manifests.py
# Purpose: Validate Wiki-LLM-inspired functional branch manifests and their registry/schema alignment.
# Invoked by / imported from:
#   - pytest discovery
# Output formats / side effects:
#   - unittest assertions only
# AutoDoc: refreshed 2026-04-30 (manual)
# === End NoemaForge Autodoc File Header ===

#!/usr/bin/env python3

import json
import os
from pathlib import Path

import jsonschema
import yaml

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), '..')))


def test_branch_registry_and_manifests_validate() -> None:
    reg = yaml.safe_load((ROOT / 'configs' / 'functional-branches.yaml').read_text(encoding='utf-8')) or {}
    reg_schema = json.loads((ROOT / 'contracts' / 'functional_branches.schema.json').read_text(encoding='utf-8'))
    man_schema = json.loads((ROOT / 'contracts' / 'functional_branch_manifest.schema.json').read_text(encoding='utf-8'))
    jsonschema.Draft7Validator(reg_schema).validate(reg)
    for branch_id, spec in (reg.get('branches') or {}).items():
        path = ROOT / str((spec or {}).get('manifest') or '')
        assert path.exists(), str(path)
        doc = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
        jsonschema.Draft7Validator(man_schema).validate(doc)
        assert str(doc.get('branch_id') or '') == str(branch_id)
        assert str(doc.get('purpose') or '').strip()
        assert str(doc.get('why_it_exists') or '').strip()
