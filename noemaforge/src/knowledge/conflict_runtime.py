#!/usr/bin/env python3
from __future__ import annotations

# === NoemaForge Autodoc File Header ===
# File: src/knowledge/conflict_runtime.py
# Purpose: Implement the knowledge subsystem module 'conflict_runtime'.
# Invoked by / imported from:
#   - pytest discovery or direct CLI/testing workflows
# Output formats / side effects:
#   - local JSON/YAML/text artifacts or process exit status
# AutoDoc: refreshed 2026-04-30 (manual)
# === End NoemaForge Autodoc File Header ===

# === NoemaForge File Header ===
# File: src/knowledge/conflict_runtime.py
# Zone: brain
# Purpose: Detect simple polarity conflicts between extracted claims and publish Conflict objects.
# Callers: src/brainctl.py, future maintenance workflows, tests/test_conflict_runtime.py
# Inputs: KnowledgeStore, PrepStore, optional book filter.
# Outputs: Conflict records in kg.sqlite and a structured report.
# Side effects: writes conflict rows only.
# Security notes:
#   - invariants: conflict detection is conservative and only publishes unresolved conflicts
#   - threats: over-linking unrelated claims if signatures are too broad
# === End NoemaForge File Header ===


import hashlib
import re
from typing import Any, Dict, List, Tuple

from .prep_store import PrepStore
from .store import KnowledgeStore

_NEG_RE = re.compile(r'\b(?:not|never|cannot|no|не|нет|никогда)\b', re.I)
_PAIR_RE = re.compile(r'\b([A-Za-z]\d{2,})\b.*?\b([A-Za-z]\d{2,})\b')


def _pair_key(text: str) -> str:
    m = _PAIR_RE.search(str(text or ''))
    if not m:
        return ''
    a, b = m.group(1).upper(), m.group(2).upper()
    return f'{a}->{b}'


def _is_negative(text: str) -> bool:
    return bool(_NEG_RE.search(str(text or '')))


def detect_conflicts(*, store: KnowledgeStore, prep_store: PrepStore, book_id: str = '', created_by: str = 'brainctl-kg-conflicts') -> Dict[str, Any]:
    origins = prep_store.list_claim_origins(book_id=str(book_id or ''))
    grouped: Dict[str, List[Tuple[Dict[str, Any], Dict[str, Any]]]] = {}
    for origin in origins:
        claim = store.get_claim(str(origin.get('claim_id') or ''))
        if not claim:
            continue
        key = _pair_key(str(claim.get('text_normalized') or ''))
        if not key:
            continue
        grouped.setdefault(key, []).append((claim, origin))
    created: List[str] = []
    for key, pairs in grouped.items():
        positives = [(c, o) for c, o in pairs if not _is_negative(c.get('text_normalized') or '')]
        negatives = [(c, o) for c, o in pairs if _is_negative(c.get('text_normalized') or '')]
        if not positives or not negatives:
            continue
        for pc, po in positives:
            for nc, no in negatives:
                cid = 'conflict:' + hashlib.sha1(f'{pc["claim_id"]}|{nc["claim_id"]}|{key}'.encode('utf-8')).hexdigest()
                store.add_conflict(
                    conflict_id=cid,
                    entity_a=str(pc['claim_id']),
                    entity_b=str(nc['claim_id']),
                    incompatibility_type='polarity_conflict',
                    realm_context={'book_id': str(book_id or ''), 'pair_key': key},
                    status='Unresolved',
                    confidence=0.66,
                    unresolved_reason='automatic_polarity_mismatch',
                    decision_trace='heuristic_conflict_detector_v1',
                    created_by=str(created_by),
                )
                created.append(cid)
    return {'ok': True, 'book_id': str(book_id or ''), 'created_conflicts': len(created), 'conflict_ids': created}
