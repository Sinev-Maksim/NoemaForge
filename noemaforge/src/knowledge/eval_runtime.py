#!/usr/bin/env python3
from __future__ import annotations

# === NoemaForge Autodoc File Header ===
# File: src/knowledge/eval_runtime.py
# Purpose: Implement the knowledge subsystem module 'eval_runtime'.
# Invoked by / imported from:
#   - pytest discovery or direct CLI/testing workflows
# Output formats / side effects:
#   - local JSON/YAML/text artifacts or process exit status
# AutoDoc: refreshed 2026-04-30 (manual)
# === End NoemaForge Autodoc File Header ===

# === NoemaForge File Header ===
# File: src/knowledge/eval_runtime.py
# Zone: brain
# Purpose: Evaluate extracted claims and grounded answers against deterministic synthetic-book gold fixtures.
# Callers: src/brainctl.py, tests/test_synthetic_book_and_grounded_admin.py
# Inputs: KnowledgeStore, PrepStore, gold JSONL paths, optional ErrorLearningStore
# Outputs: evaluation summaries and optional error/regression records
# Side effects: may write error-learning SQLite rows when record_errors is enabled
# Security notes:
#   - invariants: evaluation must never mutate the canonical knowledge graph
#   - threats: silently accepting provenance-poor claims or mixing source defects with model/runtime errors
# === End NoemaForge File Header ===


import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .error_learning import ErrorLearningStore
from .grounded_administrator import answer_query
from .prep_store import PrepStore
from .store import KnowledgeStore


def _load_jsonl(path: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    with open(path, 'r', encoding='utf-8') as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            obj = json.loads(ln)
            if isinstance(obj, dict):
                out.append(obj)
    return out


def _norm(s: Any) -> str:
    return ' '.join(str(s or '').lower().split())


def _claim_is_chain_relevant(text: str) -> bool:
    t = _norm(text)
    import re
    return bool(re.search(r'\b[a-zа-яё]\d{2,}\b', t, flags=re.I))


def _match_gold_to_claim(gold: Dict[str, Any], claims: Sequence[Dict[str, Any]], origins: Sequence[Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    target_subs = [_norm(x) for x in gold.get('must_match_substrings') or []]
    for claim, origin in zip(claims, origins):
        text = _norm(claim.get('text_normalized') or claim.get('text') or '')
        if target_subs and not all(sub in text for sub in target_subs):
            continue
        return claim, origin
    return None, None


def evaluate_extraction_against_gold(
    *,
    store: KnowledgeStore,
    prep_store: PrepStore,
    book_id: str,
    gold_claims_path: str,
    error_store: Optional[ErrorLearningStore] = None,
    record_errors: bool = False,
    run_id: str = '',
) -> Dict[str, Any]:
    gold = _load_jsonl(gold_claims_path)
    origins = prep_store.list_claim_origins(book_id=str(book_id))
    claims = [store.get_claim(str(r.get('claim_id') or '')) or {} for r in origins]
    matches: List[Dict[str, Any]] = []
    misses: List[Dict[str, Any]] = []
    for g in gold:
        claim, origin = _match_gold_to_claim(g, claims, origins)
        if claim and origin:
            matches.append({'gold': g, 'claim_id': claim.get('claim_id'), 'origin': origin})
        else:
            misses.append(g)
            if record_errors and error_store is not None and run_id:
                error_store.add_error_event(
                    run_id=str(run_id),
                    component='claim_extractor',
                    error_type='missed_gold_claim',
                    severity='medium',
                    source_address={'book_id': str(book_id), 'chapter_no': g.get('chapter_no'), 'section_path': g.get('section_path')},
                    predicted_payload={'matched': False},
                    expected_payload=g,
                    source_defect=False,
                )
    matched_ids = {str(m['claim_id']) for m in matches}
    relevant_origins = []
    for r, c in zip(origins, claims):
        if _claim_is_chain_relevant(c.get('text_normalized') or c.get('text') or ''):
            relevant_origins.append(r)
    extras = [r for r in relevant_origins if str(r.get('claim_id') or '') not in matched_ids]
    if record_errors and error_store is not None and run_id:
        for origin in extras:
            claim = store.get_claim(str(origin.get('claim_id') or '')) or {}
            error_store.add_error_event(
                run_id=str(run_id),
                component='claim_extractor',
                error_type='extra_claim',
                severity='medium',
                source_address=(origin.get('primary_address') or origin.get('primary_address_json') or {}),
                object_kind='claim',
                object_id=str(origin.get('claim_id') or ''),
                predicted_payload={'claim_id': str(origin.get('claim_id') or ''), 'text': str(claim.get('text_normalized') or claim.get('text') or '')},
                expected_payload={'matched_gold': False},
                source_defect=False,
            )
    precision = float(len(matches)) / float(max(1, len(relevant_origins)))
    recall = float(len(matches)) / float(max(1, len(gold)))
    quality = round((precision + recall) / 2.0, 4)
    return {
        'ok': True,
        'book_id': str(book_id),
        'gold_claims': len(gold),
        'extracted_claims': len(origins),
        'matched_claims': len(matches),
        'missed_claims': len(misses),
        'extra_claims': len(extras),
        'precision_approx': round(precision, 4),
        'recall': round(recall, 4),
        'quality_score': quality,
        'misses': misses[:25],
    }


def evaluate_grounded_queries(
    *,
    store: KnowledgeStore,
    prep_store: PrepStore,
    gold_queries_path: str,
    book_id: str = '',
    limit: int = 5,
) -> Dict[str, Any]:
    gold = _load_jsonl(gold_queries_path)
    results: List[Dict[str, Any]] = []
    matched = 0
    for q in gold:
        rep = answer_query(store=store, prep_store=prep_store, query=str(q.get('query') or ''), book_id=str(book_id or ''), limit=int(limit))
        answer = _norm(rep.get('answer') or '')
        ok = all(_norm(x) in answer for x in (q.get('expected_ids') or []))
        if not ok:
            # fallback: citations or claims may still contain the ids
            hay = answer + ' ' + ' '.join(_norm(c.get('text') or '') for c in rep.get('claims') or [])
            ok = all(_norm(x) in hay for x in (q.get('expected_ids') or []))
        if ok:
            matched += 1
        results.append({'query': q.get('query'), 'ok': bool(ok), 'mode': rep.get('mode'), 'answer': rep.get('answer'), 'citations': rep.get('citations')})
    return {
        'ok': True,
        'queries': len(gold),
        'matched': matched,
        'quality_score': round(float(matched) / float(max(1, len(gold))), 4),
        'results': results,
    }
