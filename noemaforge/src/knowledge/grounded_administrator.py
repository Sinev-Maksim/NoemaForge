#!/usr/bin/env python3
from __future__ import annotations

# === NoemaForge Autodoc File Header ===
# File: src/knowledge/grounded_administrator.py
# Purpose: Implement the knowledge subsystem module 'grounded_administrator'.
# Invoked by / imported from:
#   - pytest discovery or direct CLI/testing workflows
# Output formats / side effects:
#   - local JSON/YAML/text artifacts or process exit status
# AutoDoc: refreshed 2026-04-30 (manual)
# === End NoemaForge Autodoc File Header ===

# === NoemaForge File Header ===
# File: src/knowledge/grounded_administrator.py
# Zone: brain
# Purpose: Answer operator-facing administrator questions strictly from the canonical knowledge graph with provenance.
# Callers: src/brainctl.py, future voice/text front-door handlers, tests/test_synthetic_book_and_grounded_admin.py
# Inputs: KnowledgeStore, PrepStore, operator query string, grounded-administrator policy options
# Outputs: structured grounded answer JSON with citations or a knowledge-gap notice
# Side effects: none.
# Security notes:
#   - invariants: grounded answers cite claim origins; no claim without provenance is surfaced
#   - threats: returning unsupported claims, hiding uncertainty, or fabricating provenance
# === End NoemaForge File Header ===


import json
import re
from typing import Any, Dict, List, Sequence, Tuple

from .prep_store import PrepStore
from .store import KnowledgeStore

TOKEN_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9_]+")
STOPWORDS = {
    'the', 'and', 'for', 'with', 'that', 'from', 'this', 'into', 'what', 'does', 'give', 'why', 'how', 'when',
    'это', 'как', 'что', 'для', 'или', 'если', 'когда', 'почему', 'дает', 'даёт', 'его', 'её', 'это', 'так',
}


def _tokens(text: str) -> List[str]:
    out: List[str] = []
    for tok in TOKEN_RE.findall(str(text or '').lower()):
        if len(tok) < 2 or tok in STOPWORDS:
            continue
        out.append(tok)
    return out


def _overlap_score(query_tokens: Sequence[str], claim_text: str, concept_tokens: Sequence[str]) -> float:
    if not query_tokens:
        return 0.0
    hay = set(_tokens(claim_text)) | {str(x).lower() for x in concept_tokens if str(x).strip()}
    overlap = len([t for t in query_tokens if t in hay])
    if overlap <= 0:
        return 0.0
    exact_bonus = 0.15 if 'follows' in claim_text.lower() or 'следует' in claim_text.lower() else 0.0
    return float(overlap) + exact_bonus


def _human_address(origin: Dict[str, Any]) -> str:
    addr = origin.get('primary_address')
    if not addr:
        addr = origin.get('primary_address_json')
    if isinstance(addr, str):
        try:
            addr = json.loads(addr)
        except Exception:
            addr = {}
    return str((addr or {}).get('human_address') or '')


def collect_grounded_claims(
    *,
    store: KnowledgeStore,
    prep_store: PrepStore,
    query: str,
    book_id: str = '',
    limit: int = 5,
) -> List[Dict[str, Any]]:
    """Return the most relevant claims that have provenance."""
    q_tokens = _tokens(query)
    if not q_tokens:
        return []
    origins = prep_store.list_claim_origins(book_id=str(book_id or ''))
    if not origins:
        return []
    out: List[Tuple[float, Dict[str, Any]]] = []
    for origin in origins:
        cid = str(origin.get('claim_id') or '')
        if not cid:
            continue
        claim = store.get_claim(cid)
        if not claim:
            continue
        concepts = claim.get('about_concepts') or []
        score = _overlap_score(q_tokens, str(claim.get('text_normalized') or ''), concepts)
        if score <= 0.0:
            continue
        addr = _human_address(origin)
        rec = {
            'claim_id': cid,
            'score': score,
            'text': str(claim.get('text_normalized') or ''),
            'confidence': float(claim.get('confidence') or 0.0),
            'concepts': concepts,
            'human_address': addr,
            'origin': origin,
        }
        out.append((score, rec))
    out.sort(key=lambda x: (-x[0], str(x[1].get('claim_id') or '')))
    return [rec for _, rec in out[: max(1, int(limit))]]


def answer_query(
    *,
    store: KnowledgeStore,
    prep_store: PrepStore,
    query: str,
    book_id: str = '',
    limit: int = 5,
    max_citations: int = 4,
) -> Dict[str, Any]:
    claims = collect_grounded_claims(store=store, prep_store=prep_store, query=query, book_id=book_id, limit=limit)
    if not claims:
        return {
            'ok': True,
            'mode': 'knowledge_gap_notice',
            'query': str(query),
            'grounded': False,
            'answer': 'Local grounded knowledge does not currently contain a supported answer for this question.',
            'citations': [],
            'followup': ['Ingest a relevant source or ask for a narrower scope.', 'Propose research to add graph-backed evidence.'],
        }
    citations = []
    pieces: List[str] = []
    seen_text: set[str] = set()
    for item in claims[: max_citations]:
        txt = str(item['text']).strip()
        if txt in seen_text:
            continue
        seen_text.add(txt)
        pieces.append(txt)
        citations.append({
            'claim_id': item['claim_id'],
            'human_address': item['human_address'],
            'score': item['score'],
        })
    answer = ' '.join(pieces[:3]).strip()
    return {
        'ok': True,
        'mode': 'grounded_answer',
        'query': str(query),
        'grounded': True,
        'answer': answer,
        'citations': citations,
        'claims': claims,
        'followup': [],
    }
