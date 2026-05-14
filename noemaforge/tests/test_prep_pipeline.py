#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_prep_pipeline.py
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
# File: tests/test_prep_pipeline.py
# Zone: brain
# Purpose: Validate the runtime prep pipeline for normalization, sentence/topic planning,
#   split-tree generation, and in-memory leaf chunk materialization.
# Callers: pytest discovery
# Inputs: temporary book files, temporary prep-store databases, artifact directories
# Outputs: pytest assertions only
# Side effects: creates temporary SQLite databases and normalized artifact files
# Security notes:
#   - invariants: queue-first processing and in-memory chunk bodies are exercised
# === End NoemaForge Autodoc File Header ===


import os
import sys
from pathlib import Path

ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(ROOT, 'src'))

from knowledge.prep_pipeline import analyze_book_path, analyze_next_queue_entry
from knowledge.prep_store import PrepStore


def test_prep_pipeline_markdown_book(tmp_path: Path):
    db = tmp_path / 'prep.sqlite'
    artifact_root = tmp_path / 'artifacts'
    book = tmp_path / 'book.md'
    book.write_text(
        '# Intro\n\n'
        'NoemaForge keeps provenance for every important statement. It builds durable metadata first. '\
        'Then it extracts knowledge in a later pass.\n\n'
        '## Grounded answers\n\n'
        'Administrator should answer from the graph, not improvise from thin air. '\
        'When the graph is missing evidence, the system should say so clearly.\n',
        encoding='utf-8',
    )

    store = PrepStore(str(db))
    rep = analyze_book_path(
        prep_store=store,
        source_path=str(book),
        artifact_root=str(artifact_root),
        canonicalization_profile='default',
        max_tokens_per_leaf=18,
    )
    assert rep['ok'] is True
    summary = store.summarize_book(book_id=rep['book_id'])
    assert summary['counts']['chapters'] >= 1
    assert summary['counts']['sections'] >= 1
    assert summary['counts']['sentences'] >= 4
    assert summary['counts']['sentence_topic_maps'] == summary['counts']['sentences']
    assert summary['counts']['adjacency_groups'] >= 1
    assert summary['counts']['leaf_nodes'] >= 1

    artifact = store.get_normalized_text_artifact(normalized_text_artifact_id=rep['normalized_text_artifact_id'])
    assert artifact is not None
    rel = str(artifact['artifact_relpath'])
    assert rel.startswith('normalized_text/')
    assert (artifact_root / rel).exists()

    leaves = list(store.iter_leaf_chunk_bodies(book_id=rep['book_id'], artifact_root=str(artifact_root)))
    assert leaves
    assert all(isinstance(item['text'], str) and item['text'].strip() for item in leaves)


def test_prep_pipeline_clause_splitting(tmp_path: Path):
    db = tmp_path / 'prep.sqlite'
    artifact_root = tmp_path / 'artifacts'
    book = tmp_path / 'long.txt'
    book.write_text(
        'This sentence is intentionally very long, with multiple clauses, and several commas, and more clauses, '\
        'and repeated phrases, so that the planner is forced to split within a single sentence when the token budget is tiny.',
        encoding='utf-8',
    )
    store = PrepStore(str(db))
    rep = analyze_book_path(
        prep_store=store,
        source_path=str(book),
        artifact_root=str(artifact_root),
        canonicalization_profile='default',
        max_tokens_per_leaf=6,
    )
    assert rep['ok'] is True
    leaves = list(store.iter_leaf_chunk_bodies(book_id=rep['book_id'], artifact_root=str(artifact_root)))
    assert len(leaves) >= 2
    assert any(item['boundary_mode'] in {'clause_window', 'char_span'} for item in leaves)
    assert all(item['text'].strip() for item in leaves)


def test_prep_pipeline_run_next_queue(tmp_path: Path):
    db = tmp_path / 'prep.sqlite'
    artifact_root = tmp_path / 'artifacts'
    a = tmp_path / 'a.txt'
    b = tmp_path / 'b.txt'
    a.write_text('Short book. Another line of text.', encoding='utf-8')
    b.write_text('Higher priority book. It should be processed first.', encoding='utf-8')

    store = PrepStore(str(db))
    store.enqueue_book_path(path=str(a), queue_name='default', priority=50, canonicalization_profile='default')
    store.enqueue_book_path(path=str(b), queue_name='default', priority=10, canonicalization_profile='default')

    rep = analyze_next_queue_entry(
        prep_store=store,
        artifact_root=str(artifact_root),
        queue_name='default',
        worker_id='w1',
        max_tokens_per_leaf=20,
    )
    assert rep['ok'] is True
    book = store.get_book(book_id=rep['book_id'])
    assert book is not None
    assert Path(str(book['source_path'])).name == 'b.txt'
