#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_conflict_runtime.py
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
# File: tests/test_conflict_runtime.py
# Purpose: Implement the knowledge subsystem module 'conflict_runtime'.
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

from knowledge.prep_store import PrepStore
from knowledge.store import KnowledgeStore
from knowledge.extraction_pipeline import extract_book
from knowledge.prep_pipeline import analyze_book_path
from knowledge.conflict_runtime import detect_conflicts


def test_detect_conflicts_finds_polarity_mismatch(tmp_path: Path) -> None:
    prep = PrepStore(str(tmp_path / 'prep.sqlite'))
    kg = KnowledgeStore(str(tmp_path / 'kg.sqlite'))
    artifact_root = tmp_path / 'artifacts'
    book = tmp_path / 'book.md'
    book.write_text(
        '# Chapter 1\n\n'
        'From A01 follows B01 because the initial structure created by A01 determines which downstream branch remains valid.\n\n'
        'From A01 not follows B01 because the required anchor is missing in this counterexample.\n',
        encoding='utf-8',
    )
    analyzed = analyze_book_path(prep_store=prep, source_path=str(book), artifact_root=str(artifact_root), max_tokens_per_leaf=80)
    assert analyzed['ok'] is True
    rep = extract_book(prep_store=prep, store=kg, book_id=str(analyzed['book_id']), artifact_root=str(artifact_root), default_realm='science')
    assert rep['ok'] is True
    crep = detect_conflicts(store=kg, prep_store=prep, book_id=str(analyzed['book_id']))
    assert crep['ok'] is True
    assert crep['created_conflicts'] >= 1
