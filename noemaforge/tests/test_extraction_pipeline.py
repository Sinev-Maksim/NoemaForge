#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_extraction_pipeline.py
Zone: release/package
Version: 0.31.13.alpha
Created: 2026-05-14
Modified: 2026-05-14
Purpose: Manage NoemaForge pipeline catalog, runs, gates, artifacts and state.
Inputs: Command-line arguments, environment variables, package files and local NoemaForge runtime state as applicable.
Outputs: Structured command output, files, service state or UI state as documented by the caller.
Side effects: Limited to the documented NoemaForge paths, runtime state directories or systemd units used by this file.
Tests: Syntax validation plus the release setup selftest, consistency-audit and targeted smoke checks.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

# === NoemaForge Autodoc File Header ===
# File: tests/test_extraction_pipeline.py
# Zone: brain
# Purpose: Validate passage/claim extraction runtime on top of the prep-store and prep pipeline.
# Callers: pytest discovery
# Inputs: temporary prep/knowledge SQLite databases, temporary book files, temporary artifact roots
# Outputs: pytest assertions only
# Side effects: creates temporary SQLite databases and normalized artifact files
# Security notes:
#   - invariants: claims are published only with provenance and stable reruns keep origin counts stable
# === End NoemaForge Autodoc File Header ===


import os
import sys
from pathlib import Path

ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(ROOT, 'src'))

from knowledge.extraction_pipeline import extract_book, extract_next_book
from knowledge.prep_pipeline import analyze_book_path
from knowledge.prep_store import PrepStore
from knowledge.store import KnowledgeStore


def test_extract_book_builds_passages_claims_and_origins(tmp_path: Path):
    prep_db = tmp_path / 'prep.sqlite'
    kg_db = tmp_path / 'kg.sqlite'
    artifact_root = tmp_path / 'artifacts'
    book = tmp_path / 'book.md'
    book.write_text(
        '# Intro\n\n'
        'NoemaForge keeps provenance for every important statement. '
        'Administrator should answer from the graph, not improvise. '\
        'When evidence is missing, the system should say so clearly.\n',
        encoding='utf-8',
    )

    prep = PrepStore(str(prep_db))
    analyzed = analyze_book_path(prep_store=prep, source_path=str(book), artifact_root=str(artifact_root), max_tokens_per_leaf=25)
    assert analyzed['ok'] is True

    kg = KnowledgeStore(str(kg_db))
    rep = extract_book(prep_store=prep, store=kg, book_id=str(analyzed['book_id']), artifact_root=str(artifact_root), default_realm='science')
    assert rep['ok'] is True
    assert rep['created_passages'] >= 1
    assert rep['created_claims'] >= 2

    source = kg.get_source(str(rep['source_id']))
    assert source is not None
    origins = prep.list_claim_origins(book_id=str(analyzed['book_id']))
    assert len(origins) >= 2
    for origin in origins:
        addr = __import__('json').loads(origin['primary_address_json'])
        assert addr['source_id'] == rep['source_id']
        assert addr['book_id'] == analyzed['book_id']
        assert addr['passage_id']
        assert 'human_address' in addr
        claim = kg.get_claim(str(origin['claim_id']))
        assert claim is not None
        assert claim['extracted_from_passages']
        assert claim['supported_by_evidence']

    # Rerun should be idempotent for durable origin counts.
    rep2 = extract_book(prep_store=prep, store=kg, book_id=str(analyzed['book_id']), artifact_root=str(artifact_root), default_realm='science')
    assert rep2['ok'] is True
    assert len(prep.list_passage_origins(book_id=str(analyzed['book_id']))) == rep['created_passages']
    assert len(prep.list_claim_origins(book_id=str(analyzed['book_id']))) == rep['created_claims']


def test_extract_book_clause_fragment_claim_origin(tmp_path: Path):
    prep_db = tmp_path / 'prep.sqlite'
    kg_db = tmp_path / 'kg.sqlite'
    artifact_root = tmp_path / 'artifacts'
    book = tmp_path / 'long.txt'
    book.write_text(
        'This sentence is intentionally very long, with multiple clauses, and several commas, and more clauses, '
        'and repeated phrases, so that the planner is forced to split within a single sentence when the token budget is tiny.',
        encoding='utf-8',
    )
    prep = PrepStore(str(prep_db))
    analyzed = analyze_book_path(prep_store=prep, source_path=str(book), artifact_root=str(artifact_root), max_tokens_per_leaf=6)
    assert analyzed['ok'] is True
    kg = KnowledgeStore(str(kg_db))
    rep = extract_book(prep_store=prep, store=kg, book_id=str(analyzed['book_id']), artifact_root=str(artifact_root), default_realm='science')
    assert rep['ok'] is True
    claim_origins = prep.list_claim_origins(book_id=str(analyzed['book_id']))
    assert claim_origins
    # At least one claim should come from a fragment, not the full sentence span.
    sentences = {row['sentence_id']: row for row in prep.list_book_sentences(book_id=str(analyzed['book_id']))}
    assert any(
        str(origin['claim_mode']) == 'quoted'
        and origin['sentence_start_id'] == origin['sentence_end_id']
        and (
            int(origin['char_start'] or 0) != int(sentences[str(origin['sentence_start_id'])]['char_start'])
            or int(origin['char_end'] or 0) != int(sentences[str(origin['sentence_end_id'])]['char_end'])
        )
        for origin in claim_origins
    )


def test_extract_next_book_prefers_unextracted_priority_order(tmp_path: Path):
    prep_db = tmp_path / 'prep.sqlite'
    kg_db = tmp_path / 'kg.sqlite'
    artifact_root = tmp_path / 'artifacts'
    a = tmp_path / 'a.txt'
    b = tmp_path / 'b.txt'
    a.write_text('Lower priority prepared book. It still contains claims.', encoding='utf-8')
    b.write_text('Higher priority prepared book. It should be extracted first.', encoding='utf-8')

    prep = PrepStore(str(prep_db))
    ra = analyze_book_path(prep_store=prep, source_path=str(a), artifact_root=str(artifact_root), priority=50, queue_name='default')
    rb = analyze_book_path(prep_store=prep, source_path=str(b), artifact_root=str(artifact_root), priority=10, queue_name='default')
    assert ra['ok'] and rb['ok']

    kg = KnowledgeStore(str(kg_db))
    rep = extract_next_book(prep_store=prep, store=kg, artifact_root=str(artifact_root), default_realm='science')
    assert rep['ok'] is True
    assert rep['book_id'] == rb['book_id']
