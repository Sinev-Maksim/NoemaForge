#!/usr/bin/env python3
from __future__ import annotations

# === NoemaForge Autodoc File Header ===
# File: src/knowledge/synthetic_book.py
# Purpose: Implement the knowledge subsystem module 'synthetic_book'.
# Invoked by / imported from:
#   - pytest discovery or direct CLI/testing workflows
# Output formats / side effects:
#   - local JSON/YAML/text artifacts or process exit status
# AutoDoc: refreshed 2026-04-30 (manual)
# === End NoemaForge Autodoc File Header ===

# === NoemaForge File Header ===
# File: src/knowledge/synthetic_book.py
# Zone: brain
# Purpose: Generate a synthetic two-chapter book plus gold claims/query fixtures for hypergraph and model-selection tests.
# Callers: src/brainctl.py, tests/test_synthetic_book_and_grounded_admin.py, manual dataset generation.
# Inputs: output directory and generation parameters.
# Outputs: markdown book text, gold JSONL/JSON manifests, and role-eval case suggestions.
# Side effects: writes local files only.
# Security notes:
#   - offline-only synthetic corpus, no external dependencies.
#   - designed to be deterministic so checksums stay stable across runs.
# === End NoemaForge File Header ===


import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List

PAGE_WORD_TARGET = 260
PAGES_PER_CHAPTER = 10
SECTIONS_PER_CHAPTER = 10

A_TOPICS = [
    ('anchor signal', 'a stable initiating cue that keeps later actions aligned'),
    ('path contract', 'a rule set that constrains movement through a process'),
    ('focus lattice', 'a structure that keeps attention attached to the active task'),
    ('memory hinge', 'a short retained pattern that lets the next step reconnect to context'),
    ('proof spine', 'the ordered line of reasons that carries an argument safely forward'),
    ('dialogue compass', 'a guide that keeps a conversation pointed at a declared goal'),
    ('queue rhythm', 'the predictable cadence that keeps work from colliding in the pipeline'),
    ('safety lens', 'a frame that exposes hazards before a risky action is executed'),
    ('bridge token', 'a compact marker used to bind one state transition to the next'),
    ('review knot', 'a deliberate checkpoint where evidence and intent are compared'),
]

B_TOPICS = [
    ('guided branch', 'a derived step that opens only the path consistent with the anchor'),
    ('verified route', 'a downstream path that stays inside the contract and can be checked'),
    ('stable output', 'a result that remains coherent because focus did not drift'),
    ('context return', 'the ability to recover the correct thread after interruption'),
    ('defensible conclusion', 'an output that can be justified line by line from prior support'),
    ('clarified request', 'a user-facing formulation that removes ambiguity before execution'),
    ('balanced throughput', 'work that keeps moving without starving urgent items'),
    ('risk boundary', 'an execution edge beyond which actions must be slowed or stopped'),
    ('state continuity', 'a preserved handoff from one stage to the following stage'),
    ('audited decision', 'a choice that remains inspectable after it has been applied'),
]


def _word_count(text: str) -> int:
    return len([w for w in str(text).replace('\n', ' ').split(' ') if w.strip()])


def _pad_to_target(text: str, *, target_words: int, seed: int) -> str:
    filler_sentences = [
        'This paragraph repeats the core relation in varied language so the extractor sees both local detail and stable thematic continuity.',
        'The narrator restates the operational purpose, the observed effect, and the reason the relation matters to later tasks.',
        'A careful reader can trace how the initial condition constrains the later branch, why the resulting benefit is not accidental, and where the evidence sits in the section.',
        'The synthetic prose intentionally stays explicit: it names the concept, states the consequence, and explains the utility of the connection.',
        'Because the chapter is used for evaluation, every section contains grounded statements that can be quoted back with a concrete address.',
    ]
    out = text.strip()
    idx = 0
    while _word_count(out) < target_words:
        out += '\n\n' + filler_sentences[(seed + idx) % len(filler_sentences)]
        idx += 1
    return out.strip() + '\n'


def _make_section(chapter_no: int, section_no: int, global_no: int) -> Dict[str, Any]:
    a_label, a_desc_seed = A_TOPICS[(global_no - 1) % len(A_TOPICS)]
    b_label, b_desc_seed = B_TOPICS[(global_no - 1) % len(B_TOPICS)]
    aid = f'A{global_no:02d}'
    bid = f'B{global_no:02d}'
    a_desc = f'{aid} is the {a_label} of this section; it is described as {a_desc_seed}.'
    follows = f'From {aid} follows {bid}, because the initial structure created by {aid} determines which downstream branch remains valid.'
    b_desc = f'{bid} is the {b_label}; it is described as {b_desc_seed}.'
    relation = f'The relation from {aid} to {bid} gives the system a practical gain: it turns intention into a traceable next step without losing context.'
    body = f"## Section {chapter_no}.{section_no}: {aid} and {bid}\n\n" \
        f"{a_desc} The section opens by stating that the chapter treats {aid} as the stable origin of the later movement. " \
        f"It adds that a reader can identify {aid} by watching which promise remains unchanged while the surrounding details vary.\n\n" \
        f"{follows} The chapter does not present this as metaphor alone; it says that the sequence can be audited because the transition is explicit and local. " \
        f"By restating the dependency in plain language, the text makes the causal bridge visible instead of leaving it implied.\n\n" \
        f"{b_desc} The narrative then says that {bid} is valuable only when it can be pointed back to the origin. " \
        f"In other words, the chapter insists that the downstream state is not free-floating but inherits meaning from the anchor.\n\n" \
        f"{relation} The final part of the section explains that this matters for grounded work: a person can later ask what changed, what stayed fixed, and which sentence proved the connection. " \
        f"That combination of explicit naming, directed consequence, and practical utility is repeated on purpose so evaluation can measure both extraction and grounded answering."
    target = PAGE_WORD_TARGET
    padded = _pad_to_target(body, target_words=target, seed=global_no)
    return {
        'chapter_no': chapter_no,
        'section_no': section_no,
        'a_id': aid,
        'b_id': bid,
        'a_description': a_desc,
        'follows_claim': follows,
        'b_description': b_desc,
        'relation_value': relation,
        'text': padded,
        'query': f'What does the relation from {aid} to {bid} give the system, and why does {aid} matter?',
    }


def build_synthetic_book(*, chapters: int = 2, sections_per_chapter: int = SECTIONS_PER_CHAPTER) -> Dict[str, Any]:
    sections: List[Dict[str, Any]] = []
    global_no = 1
    chapter_texts: List[str] = []
    for ch in range(1, chapters + 1):
        parts = [f'# Chapter {ch}: Structured Consequences\n']
        intro = (
            f'This chapter is part of a synthetic evaluation book. It uses repeated but meaningful structures so NoemaForge can test '
            f'topic-adjacency chunking, grounded extraction, and provenance-aware answering. Each section names an A concept, explains it, '
            f'states that B follows from A, describes B, and then explains what the relation from A to B gives the system.\n'
        )
        parts.append(_pad_to_target(intro, target_words=PAGE_WORD_TARGET, seed=ch * 100))
        for sec in range(1, sections_per_chapter + 1):
            info = _make_section(chapter_no=ch, section_no=sec, global_no=global_no)
            sections.append(info)
            parts.append(info['text'])
            global_no += 1
        chapter_texts.append('\n\n'.join(parts).strip() + '\n')
    full_text = '\n\n'.join(chapter_texts).strip() + '\n'
    checksum = hashlib.sha256(full_text.encode('utf-8')).hexdigest()
    manifest = {
        'book_title': 'Synthetic Book of Directed Claims',
        'chapters': chapters,
        'sections_per_chapter': sections_per_chapter,
        'book_checksum': checksum,
        'book_checksum_alg': 'sha256',
        'page_word_target': PAGE_WORD_TARGET,
        'pages_per_chapter_approx': PAGES_PER_CHAPTER,
        'sections': len(sections),
    }
    return {
        'book_text': full_text,
        'manifest': manifest,
        'sections': sections,
        'gold_claims': _gold_claims_from_sections(sections, manifest=manifest),
        'gold_queries': _gold_queries_from_sections(sections),
    }


def _gold_claims_from_sections(sections: List[Dict[str, Any]], *, manifest: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for sec in sections:
        chapter = int(sec['chapter_no'])
        section_path = f'{chapter}.{sec["section_no"]}'
        for kind, text in [
            ('a_description', sec['a_description']),
            ('follows', sec['follows_claim']),
            ('b_description', sec['b_description']),
            ('relation_value', sec['relation_value']),
        ]:
            out.append({
                'book_checksum': manifest['book_checksum'],
                'chapter_no': chapter,
                'section_path': section_path,
                'a_id': sec['a_id'],
                'b_id': sec['b_id'],
                'claim_kind': kind,
                'text': text,
                'must_match_substrings': [sec['a_id'], sec['b_id']] if kind == 'follows' else [sec['a_id']] if kind.startswith('a_') else [sec['b_id']] if kind.startswith('b_') else [sec['a_id'], sec['b_id'], 'gives'],
            })
    return out


def _gold_queries_from_sections(sections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for sec in sections[: min(8, len(sections))]:
        out.append({
            'query': sec['query'],
            'expected_claim_substrings': [sec['relation_value'], sec['follows_claim']],
            'expected_ids': [sec['a_id'], sec['b_id']],
        })
    return out


def write_synthetic_book(out_dir: str) -> Dict[str, Any]:
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    built = build_synthetic_book()
    book_path = root / 'synthetic_book.md'
    gold_claims_path = root / 'gold_claims.jsonl'
    gold_queries_path = root / 'gold_queries.jsonl'
    manifest_path = root / 'manifest.json'
    book_path.write_text(built['book_text'], encoding='utf-8')
    with gold_claims_path.open('w', encoding='utf-8') as f:
        for row in built['gold_claims']:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')
    with gold_queries_path.open('w', encoding='utf-8') as f:
        for row in built['gold_queries']:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')
    manifest_path.write_text(json.dumps(built['manifest'], ensure_ascii=False, indent=2), encoding='utf-8')
    return {
        'ok': True,
        'out_dir': str(root),
        'book_path': str(book_path),
        'gold_claims_path': str(gold_claims_path),
        'gold_queries_path': str(gold_queries_path),
        'manifest_path': str(manifest_path),
        'book_checksum': built['manifest']['book_checksum'],
        'sections': built['manifest']['sections'],
    }
