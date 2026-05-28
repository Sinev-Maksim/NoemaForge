#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_synthetic_book_and_grounded_admin.py
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
# File: tests/test_synthetic_book_and_grounded_admin.py
# Purpose: Helper / validation script 'test_synthetic_book_and_grounded_admin.py'.
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

from knowledge.synthetic_book import write_synthetic_book
from knowledge.prep_store import PrepStore
from knowledge.prep_pipeline import analyze_book_path
from knowledge.store import KnowledgeStore
from knowledge.extraction_pipeline import extract_book
from knowledge.grounded_administrator import answer_query
from knowledge.eval_runtime import evaluate_extraction_against_gold, evaluate_grounded_queries
from knowledge.error_learning import ErrorLearningStore


def test_synthetic_book_generation_and_grounded_answer(tmp_path: Path) -> None:
    synth_dir = tmp_path / 'synth'
    rep = write_synthetic_book(str(synth_dir))
    assert rep['ok'] is True
    book_path = Path(rep['book_path'])
    assert book_path.exists()
    assert Path(rep['gold_claims_path']).exists()
    assert Path(rep['gold_queries_path']).exists()

    prep = PrepStore(str(tmp_path / 'prep.sqlite'))
    analyzed = analyze_book_path(prep_store=prep, source_path=str(book_path), artifact_root=str(tmp_path / 'artifacts'), max_tokens_per_leaf=80)
    assert analyzed['ok'] is True

    kg = KnowledgeStore(str(tmp_path / 'kg.sqlite'))
    ex = extract_book(prep_store=prep, store=kg, book_id=str(analyzed['book_id']), artifact_root=str(tmp_path / 'artifacts'), default_realm='science')
    assert ex['ok'] is True
    assert ex['created_claims'] >= 40

    ans = answer_query(store=kg, prep_store=prep, query='What does the relation from A01 to B01 give the system, and why does A01 matter?', book_id=str(analyzed['book_id']), limit=5)
    assert ans['ok'] is True
    assert ans['grounded'] is True
    assert 'A01' in ans['answer']
    assert 'B01' in ans['answer']
    assert ans['citations']

    err = ErrorLearningStore(str(tmp_path / 'errors.sqlite'))
    run_id = err.start_run(component='claim_extractor_eval', book_id=str(analyzed['book_id']), profile_id='synthetic_book_eval')
    ev = evaluate_extraction_against_gold(store=kg, prep_store=prep, book_id=str(analyzed['book_id']), gold_claims_path=str(rep['gold_claims_path']), error_store=err, record_errors=True, run_id=run_id)
    err.finish_run(run_id=run_id, status='completed')
    assert ev['ok'] is True
    assert ev['recall'] >= 0.95
    assert ev['quality_score'] >= 0.70

    qev = evaluate_grounded_queries(store=kg, prep_store=prep, gold_queries_path=str(rep['gold_queries_path']), book_id=str(analyzed['book_id']), limit=5)
    assert qev['ok'] is True
    assert qev['quality_score'] >= 0.75
