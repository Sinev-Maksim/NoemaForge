#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_grounded_addresses.py
Zone: release/package
Version: 0.31.13.alpha-patched1
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
# File: tests/test_grounded_addresses.py
# Purpose: Verify that grounded Administrator citations expose human-readable provenance addresses.
# Invoked by / imported from:
#   - pytest discovery
# Output formats / side effects:
#   - unittest assertions only
# AutoDoc: refreshed 2026-04-30 (manual)
# === End NoemaForge Autodoc File Header ===

#!/usr/bin/env python3

import os
import sys
from pathlib import Path

ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(ROOT, 'src'))

from knowledge.synthetic_book import write_synthetic_book
from knowledge.prep_store import PrepStore
from knowledge.prep_pipeline import analyze_book_path
from knowledge.store import KnowledgeStore
from knowledge.extraction_pipeline import extract_book
from knowledge.grounded_administrator import answer_query


def test_grounded_citations_include_human_address(tmp_path: Path) -> None:
    rep = write_synthetic_book(str(tmp_path / 'synth'))
    prep = PrepStore(str(tmp_path / 'prep.sqlite'))
    analyzed = analyze_book_path(prep_store=prep, source_path=str(rep['book_path']), artifact_root=str(tmp_path / 'artifacts'), max_tokens_per_leaf=80)
    kg = KnowledgeStore(str(tmp_path / 'kg.sqlite'))
    extract_book(prep_store=prep, store=kg, book_id=str(analyzed['book_id']), artifact_root=str(tmp_path / 'artifacts'), default_realm='science')
    ans = answer_query(store=kg, prep_store=prep, query='Why does A01 matter and what follows from A01 to B01?', book_id=str(analyzed['book_id']))
    assert ans['citations']
    assert all(str(c.get('human_address') or '').strip() for c in ans['citations'])
