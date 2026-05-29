#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_prep_store.py
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
# File: tests/test_prep_store.py
# Purpose: Validate the durable prep-store runtime adapter, queue lifecycle, and JSONL roundtrip.
# Invoked by / imported from:
#   - direct operator invocation or test discovery
# Public API / entry functions:
#   - module-level pytest tests
# Inputs:
#   - temporary filesystem paths and NoemaForge prep-store SQLite databases
# Output formats / side effects:
#   - unittest / pytest assertions only
# AutoDoc: refreshed 2026-04-29 (manual)
# === End NoemaForge Autodoc File Header ===


import json
import os
import sys
from pathlib import Path

ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(ROOT, 'src'))

from knowledge.prep_store import PrepStore


def test_prep_store_queue_and_reuse(tmp_path: Path):
    db = tmp_path / 'prep.sqlite'
    book = tmp_path / 'book.txt'
    book.write_text('Chapter one.\n\nA short book.', encoding='utf-8')

    store = PrepStore(str(db))
    rep1 = store.enqueue_book_path(path=str(book), canonicalization_profile='default', queue_name='default')
    assert rep1['ok'] is True
    assert rep1['ingest_queue_position'] == 1
    assert rep1['can_reuse_metadata'] is False

    rep2 = store.enqueue_book_path(path=str(book), canonicalization_profile='default', queue_name='default')
    assert rep2['ok'] is True
    assert rep2['ingest_queue_position'] == 1
    assert rep2['can_reuse_metadata'] is True
    assert rep2['reusable_book']['book_id'] == rep1['book_id']
    assert rep2['reused_queue_entry'] is True

    queue = store.list_queue(queue_name='default')
    assert len(queue) == 1


def test_prep_store_export_import_roundtrip(tmp_path: Path):
    src_db = tmp_path / 'prep_src.sqlite'
    dst_db = tmp_path / 'prep_dst.sqlite'
    store = PrepStore(str(src_db))

    rep = store.enqueue_book(
        source_id='src1',
        source_path='/tmp/book.md',
        book_title='Book',
        book_checksum='abc123',
        canonicalization_profile='default',
    )
    book_id = rep['book_id']
    chapter_id = store.add_chapter(book_id=book_id, chapter_no=1, chapter_title='Intro', chapter_path='1')
    section_id = store.add_section(book_id=book_id, chapter_id=chapter_id, section_path='1.1', section_title='S1')
    art = store.add_normalized_text_artifact(
        book_id=book_id,
        chapter_id=chapter_id,
        section_id=section_id,
        artifact_scope='section',
        text='Hello world. Another sentence.',
        normalization_version='v1',
        canonicalization_profile='default',
    )
    run_id = store.start_processing_run(component='topic_labeler', book_id=book_id, model_id='m1')
    s1 = store.add_sentence(
        book_id=book_id,
        chapter_id=chapter_id,
        section_id=section_id,
        normalized_text_artifact_id=art['normalized_text_artifact_id'],
        sentence_no=1,
        char_start=0,
        char_end=11,
        text='Hello world.',
    )
    s2 = store.add_sentence(
        book_id=book_id,
        chapter_id=chapter_id,
        section_id=section_id,
        normalized_text_artifact_id=art['normalized_text_artifact_id'],
        sentence_no=2,
        char_start=13,
        char_end=30,
        text='Another sentence.',
    )
    store.add_sentence_topic_map(sentence_id=s1, labeling_run_id=run_id, topic_tags=['greeting'], topic_signature='greeting', topic_confidence=0.8)
    group_id = store.add_adjacency_group(book_id=book_id, chapter_id=chapter_id, section_id=section_id, built_run_id=run_id, sentence_start_id=s1, sentence_end_id=s2, topic_signature='greeting+other', topic_tags_union=['greeting', 'other'])
    leaf_id = store.add_split_node(book_id=book_id, chapter_id=chapter_id, section_id=section_id, built_run_id=run_id, adjacency_group_id=group_id, sentence_start_id=s1, sentence_end_id=s2, is_leaf=True, leaf_sequence_no=1, split_reason='fits_budget')
    store.record_passage_origin(passage_id='pass1', book_id=book_id, chapter_id=chapter_id, section_id=section_id, normalized_text_artifact_id=art['normalized_text_artifact_id'], split_leaf_id=leaf_id, sentence_start_id=s1, sentence_end_id=s2, char_start=0, char_end=30, quote_fingerprint='q1', extraction_run_id=run_id)
    store.record_claim_origin(claim_id='claim1', source_id='src1', book_id=book_id, chapter_id=chapter_id, section_id=section_id, normalized_text_artifact_id=art['normalized_text_artifact_id'], passage_id='pass1', split_leaf_id=leaf_id, sentence_start_id=s1, sentence_end_id=s2, char_start=0, char_end=30, primary_address={'book_id': book_id}, evidence_spans=[{'sentence_start_id': s1, 'sentence_end_id': s2}], claim_mode='extracted', quote_fingerprint='q1', extraction_run_id=run_id)
    store.finish_processing_run(run_id=run_id)

    out_dir = tmp_path / 'export'
    exp = store.export_jsonl(out_dir=str(out_dir))
    assert exp['ok'] is True
    assert (out_dir / 'books.jsonl').exists()
    meta = json.loads((out_dir / '_export_meta.json').read_text(encoding='utf-8'))
    assert meta['tables']['books'] == 1

    dst = PrepStore(str(dst_db))
    imp = dst.import_jsonl(in_dir=str(out_dir), merge='replace')
    assert imp['ok'] is True
    assert imp['tables']['claim_origins'] == 1
    queue = dst.list_queue(queue_name='default')
    assert len(queue) == 1


def test_prep_store_leasing(tmp_path: Path):
    db = tmp_path / 'prep.sqlite'
    store = PrepStore(str(db))
    store.enqueue_book(source_id='srcA', source_path='/tmp/a', book_title='A', book_checksum='a1', queue_name='default', priority=50)
    store.enqueue_book(source_id='srcB', source_path='/tmp/b', book_title='B', book_checksum='b1', queue_name='default', priority=10)
    rep = store.lease_next_queue_entry(queue_name='default', worker_id='w1', lease_ttl_sec=60)
    assert rep['ok'] is True
    assert rep['leased'] is True
    assert rep['entry']['priority'] == 10
    store.complete_queue_entry(ingest_queue_entry_id=rep['entry']['ingest_queue_entry_id'])
    q = store.list_queue(queue_name='default')
    statuses = {item['ingest_queue_entry_id']: item['queue_status'] for item in q}
    assert statuses[rep['entry']['ingest_queue_entry_id']] == 'completed'
