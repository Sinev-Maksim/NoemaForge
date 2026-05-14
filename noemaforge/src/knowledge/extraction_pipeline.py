#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/knowledge/extraction_pipeline.py
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
# File: src/knowledge/extraction_pipeline.py
# Zone: brain
# Purpose: Build passages and claim provenance from durable prep-store leaf chunks and
#   publish them into the canonical hypergraph store with run-level trace metadata.
# Callers: src/brainctl.py, future grounded Administrator flows, tests/test_extraction_pipeline.py
# Inputs: PrepStore SQLite metadata, normalized text artifacts, KnowledgeStore SQLite, knowledge-policy extraction settings
# Outputs: Source/Passage/Claim/Evidence/Concept records in kg.sqlite and passage/claim origin rows in prep_index.sqlite
# Side effects: writes SQLite rows, reads normalized artifact files, updates book status during extraction
# Security notes:
#   - invariants: extraction consumes the precomputed chunk plan; claim publication requires provenance
#   - threats: unsupported claims, duplicate concepts, provenance drift on reruns
# === End NoemaForge Autodoc File Header ===

"""NoemaForge knowledge extraction runtime.

This module is the first runtime layer after the durable prep-store and prep planning
pipeline. It intentionally remains conservative: passages are built from leaf chunks,
and claims are extracted with deterministic heuristics so that provenance stays exact.

Design constraints:
- queue-first prep happens before extraction
- leaf chunk bodies are handled in memory only
- claims without provenance are never published
- reruns should be idempotent via stable IDs and OR REPLACE writes where possible
"""


import hashlib
import json
import re
from typing import Any, Dict, Iterable, List, Sequence

from .policy import load_knowledge_policy
from .prep_store import PrepStore
from .store import KnowledgeStore

TOKEN_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9_]+")
STOPWORDS = {
    "the", "and", "for", "that", "with", "this", "from", "into", "then", "when", "where",
    "which", "while", "every", "important", "book", "books", "chapter", "section", "from",
    "что", "это", "как", "для", "или", "при", "его", "её", "она", "они", "оно", "так",
    "когда", "если", "чтобы", "потом", "после", "над", "под", "надо", "очень", "есть",
}


def _norm_ws(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()



def _hash_text(text: str, *, alg: str = "sha256") -> str:
    return hashlib.new(str(alg), _norm_ws(text).encode("utf-8")).hexdigest()



def _stable_id(prefix: str, *parts: Any) -> str:
    payload = "||".join(str(p) for p in parts)
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()
    return f"{prefix}:{digest}"



def _slug(label: str) -> str:
    toks = [t.lower() for t in TOKEN_RE.findall(str(label or ""))]
    if not toks:
        return "misc"
    return "-".join(toks[:6])



def _token_words(text: str) -> List[str]:
    return [t.lower() for t in TOKEN_RE.findall(str(text or ""))]



def _claimworthy(text: str, *, min_chars: int, min_words: int) -> bool:
    t = _norm_ws(text)
    if len(t) < int(min_chars):
        return False
    if len(_token_words(t)) < int(min_words):
        return False
    if t.endswith("?"):
        return False
    if re.fullmatch(r"[#=\-\s]+", t):
        return False
    return True



def _auto_concept_labels(text: str, *, topic_tags: Sequence[str] = (), max_labels: int = 3, min_len: int = 4) -> List[str]:
    out: List[str] = []
    for tag in list(topic_tags or []):
        v = _norm_ws(tag)
        if len(v) >= int(min_len) and v.lower() not in STOPWORDS and v not in out:
            out.append(v)
        if len(out) >= int(max_labels):
            return out
    for tok in _token_words(text):
        if len(tok) < int(min_len) or tok in STOPWORDS:
            continue
        if tok not in out:
            out.append(tok)
        if len(out) >= int(max_labels):
            break
    return out





def _relation_pairs(text: str) -> List[tuple[str, str]]:
    out: List[tuple[str, str]] = []
    for m in re.finditer(r'from\s+([A-Za-z]\d{2,})\s+follows\s+([A-Za-z]\d{2,})', str(text or ''), flags=re.I):
        out.append((m.group(1).upper(), m.group(2).upper()))
    for m in re.finditer(r'из\s+([A-Za-zА-ЯЁ]\d{2,})\s+следует\s+([A-Za-zА-ЯЁ]\d{2,})', str(text or ''), flags=re.I):
        out.append((m.group(1).upper(), m.group(2).upper()))
    return out

def _resolve_titles(prep_store: PrepStore, *, book_id: str) -> Dict[str, Dict[str, str]]:
    chapters = {str(r["chapter_id"]): str(r.get("chapter_title") or "") for r in prep_store.list_book_chapters(book_id=str(book_id))}
    sections = {str(r["section_id"]): str(r.get("section_title") or "") for r in prep_store.list_book_sections(book_id=str(book_id))}
    return {"chapters": chapters, "sections": sections}



def _build_address(*, book: Dict[str, Any], chapter_title: str, section_title: str, chapter_id: str | None, section_id: str | None,
                   normalized_text_artifact_id: str, sentence_start_id: str, sentence_end_id: str, char_start: int, char_end: int, passage_id: str, split_leaf_id: str | None) -> Dict[str, Any]:
    return {
        "source_id": str(book.get("source_id") or ""),
        "source_path": str(book.get("source_path") or ""),
        "book_id": str(book.get("book_id") or ""),
        "book_title": str(book.get("book_title") or "") or str(book.get("source_path") or ""),
        "chapter_id": str(chapter_id or "") or None,
        "chapter_title": str(chapter_title or "") or None,
        "section_id": str(section_id or "") or None,
        "section_title": str(section_title or "") or None,
        "normalized_text_artifact_id": str(normalized_text_artifact_id),
        "sentence_start_id": str(sentence_start_id),
        "sentence_end_id": str(sentence_end_id),
        "char_start": int(char_start),
        "char_end": int(char_end),
        "passage_id": str(passage_id),
        "split_leaf_id": str(split_leaf_id or "") or None,
        "human_address": " / ".join([
            x for x in [
                str(book.get("book_title") or "") or str(book.get("source_path") or ""),
                str(chapter_title or "") if chapter_title else "",
                str(section_title or "") if section_title and section_title != chapter_title else "",
                f"chars {int(char_start)}-{int(char_end)}",
            ] if x
        ]),
    }



def _claim_candidates_for_leaf(*, prep_store: PrepStore, leaf: Dict[str, Any], artifact_root: str, min_claim_chars: int, min_claim_words: int) -> List[Dict[str, Any]]:
    rows = prep_store.list_sentences_between(
        sentence_start_id=str(leaf["sentence_start_id"]),
        sentence_end_id=str(leaf["sentence_end_id"]),
        artifact_root=str(artifact_root),
    )
    if not rows:
        txt = _norm_ws(str(leaf.get("text") or ""))
        if not _claimworthy(txt, min_chars=min_claim_chars, min_words=min_claim_words):
            return []
        return [{
            "text": txt,
            "sentence_start_id": str(leaf["sentence_start_id"]),
            "sentence_end_id": str(leaf["sentence_end_id"]),
            "char_start": int(leaf.get("char_start") or 0),
            "char_end": int(leaf.get("char_end") or 0),
            "claim_mode": "quoted",
            "topic_tags": [],
        }]

    # Fragment case: char-span/clause window does not align with the full sentence span.
    if str(leaf.get("boundary_mode") or "sentence_span") != "sentence_span":
        txt = _norm_ws(str(leaf.get("text") or ""))
        if not _claimworthy(txt, min_chars=min_claim_chars, min_words=min_claim_words):
            return []
        return [{
            "text": txt,
            "sentence_start_id": str(leaf["sentence_start_id"]),
            "sentence_end_id": str(leaf["sentence_end_id"]),
            "char_start": int(leaf.get("char_start") or rows[0]["char_start"]),
            "char_end": int(leaf.get("char_end") or rows[-1]["char_end"]),
            "claim_mode": "quoted",
            "topic_tags": [],
        }]

    out: List[Dict[str, Any]] = []
    if len(rows) == 1:
        row = rows[0]
        full_start = int(row.get("char_start") or 0)
        full_end = int(row.get("char_end") or 0)
        leaf_start = int(leaf.get("char_start") if leaf.get("char_start") is not None else full_start)
        leaf_end = int(leaf.get("char_end") if leaf.get("char_end") is not None else full_end)
        txt = _norm_ws(str(leaf.get("text") or row.get("text") or ""))
        if _claimworthy(txt, min_chars=min_claim_chars, min_words=min_claim_words):
            out.append({
                "text": txt,
                "sentence_start_id": str(row["sentence_id"]),
                "sentence_end_id": str(row["sentence_id"]),
                "char_start": leaf_start,
                "char_end": leaf_end,
                "claim_mode": "quoted",
                "topic_tags": [],
            })
        return out

    for row in rows:
        txt = _norm_ws(str(row.get("text") or ""))
        if not _claimworthy(txt, min_chars=min_claim_chars, min_words=min_claim_words):
            continue
        out.append({
            "text": txt,
            "sentence_start_id": str(row["sentence_id"]),
            "sentence_end_id": str(row["sentence_id"]),
            "char_start": int(row.get("char_start") or 0),
            "char_end": int(row.get("char_end") or 0),
            "claim_mode": "quoted",
            "topic_tags": [],
        })
    if out:
        return out

    agg = _norm_ws(str(leaf.get("text") or ""))
    if _claimworthy(agg, min_chars=min_claim_chars, min_words=min_claim_words):
        out.append({
            "text": agg,
            "sentence_start_id": str(leaf["sentence_start_id"]),
            "sentence_end_id": str(leaf["sentence_end_id"]),
            "char_start": int(leaf.get("char_start") or rows[0]["char_start"]),
            "char_end": int(leaf.get("char_end") or rows[-1]["char_end"]),
            "claim_mode": "aggregated",
            "topic_tags": [],
        })
    return out



def load_extraction_config(contracts_root: str = "/var/lib/noemaforge/contracts") -> Dict[str, Any]:
    pol = load_knowledge_policy(str(contracts_root))
    ext = (pol.get("extraction") or {}) if isinstance(pol.get("extraction"), dict) else {}
    return {
        "default_realm": str(ext.get("default_realm") or ""),
        "passage_profile_id": str(ext.get("passage_profile_id") or "passage_builder_v1"),
        "claim_profile_id": str(ext.get("claim_profile_id") or "claim_sentence_v1"),
        "min_claim_chars": int(ext.get("min_claim_chars") or 24),
        "min_claim_words": int(ext.get("min_claim_words") or 4),
        "create_evidence_objects": bool(ext.get("create_evidence_objects", True)),
        "create_lineage_links": bool(ext.get("create_lineage_links", True)),
        "auto_concepts_enabled": bool(ext.get("auto_concepts_enabled", True)),
        "max_auto_concepts_per_claim": int(ext.get("max_auto_concepts_per_claim") or 3),
        "concept_min_token_len": int(ext.get("concept_min_token_len") or 4),
        "quote_fingerprint_alg": str(ext.get("quote_fingerprint_alg") or "sha256"),
    }



def extract_book(
    *,
    prep_store: PrepStore,
    store: KnowledgeStore,
    book_id: str,
    artifact_root: str,
    default_realm: str = "",
    passage_profile_id: str = "passage_builder_v1",
    claim_profile_id: str = "claim_sentence_v1",
    min_claim_chars: int = 24,
    min_claim_words: int = 4,
    create_evidence_objects: bool = True,
    create_lineage_links: bool = True,
    auto_concepts_enabled: bool = True,
    max_auto_concepts_per_claim: int = 3,
    concept_min_token_len: int = 4,
    quote_fingerprint_alg: str = "sha256",
    created_by: str = "brainctl-kg-extract",
) -> Dict[str, Any]:
    book = prep_store.get_book(book_id=str(book_id))
    if not book:
        return {"ok": False, "reason": "book_not_found", "book_id": str(book_id)}
    leaves = list(prep_store.iter_leaf_chunk_bodies(book_id=str(book_id), artifact_root=str(artifact_root)))
    if not leaves:
        return {"ok": False, "reason": "no_leaf_chunks", "book_id": str(book_id)}

    titles = _resolve_titles(prep_store, book_id=str(book_id))
    source_id = str(book.get("source_id") or "")
    if not source_id:
        return {"ok": False, "reason": "source_id_missing", "book_id": str(book_id)}

    store.add_source(
        source_id=source_id,
        type="file",
        metadata={
            "path": str(book.get("source_path") or ""),
            "book_id": str(book_id),
            "book_title": str(book.get("book_title") or ""),
            "language": str(book.get("language") or ""),
            "edition": str(book.get("edition") or ""),
            "book_checksum": str(book.get("book_checksum") or ""),
            "book_checksum_alg": str(book.get("book_checksum_alg") or "sha256"),
            "canonicalization_profile": str(book.get("canonicalization_profile") or "default"),
        },
        primary_realm=str(default_realm or ""),
        version_info=f"prep:{book.get('canonicalization_profile') or 'default'}",
        created_by=str(created_by),
    )

    prep_store.mark_book_status(book_id=str(book_id), status="extracting")
    passage_run = prep_store.start_processing_run(
        component="passage_builder",
        book_id=str(book_id),
        profile_id=str(passage_profile_id),
        code_version="0.27.11",
        thresholds={"artifact_root": str(artifact_root)},
    )
    claim_run = prep_store.start_processing_run(
        component="claim_extractor",
        book_id=str(book_id),
        profile_id=str(claim_profile_id),
        code_version="0.27.11",
        thresholds={"min_claim_chars": int(min_claim_chars), "min_claim_words": int(min_claim_words)},
    )

    created_passages = 0
    created_claims = 0
    created_evidence = 0
    created_concepts = 0
    created_links = 0
    try:
        for leaf in leaves:
            passage_text = _norm_ws(str(leaf.get("text") or ""))
            if not passage_text:
                continue
            passage_id = _stable_id("passage", book_id, leaf.get("split_node_id"), leaf.get("char_start"), leaf.get("char_end"))
            chapter_id = None
            section_id = None
            sentence_rows = prep_store.list_sentences_between(
                sentence_start_id=str(leaf["sentence_start_id"]),
                sentence_end_id=str(leaf["sentence_end_id"]),
                artifact_root=str(artifact_root),
            )
            if sentence_rows:
                chapter_id = str(sentence_rows[0].get("chapter_id") or "") or None
                section_id = str(sentence_rows[0].get("section_id") or "") or None
            chapter_title = titles["chapters"].get(str(chapter_id or ""), "")
            section_title = titles["sections"].get(str(section_id or ""), "")
            anchor = {
                "kind": "prep_leaf",
                "book_id": str(book_id),
                "split_leaf_id": str(leaf.get("split_node_id") or ""),
                "normalized_text_artifact_id": str(leaf.get("normalized_text_artifact_id") or ""),
                "sentence_start_id": str(leaf.get("sentence_start_id") or ""),
                "sentence_end_id": str(leaf.get("sentence_end_id") or ""),
                "char_start": int(leaf.get("char_start") or 0),
                "char_end": int(leaf.get("char_end") or 0),
                "boundary_mode": str(leaf.get("boundary_mode") or "sentence_span"),
                "trace_level": "L4",
            }
            store.add_passage(
                passage_id=str(passage_id),
                source_id=str(source_id),
                anchor=anchor,
                text=passage_text,
                realm_override=str(default_realm or ""),
                created_by=str(created_by),
            )
            prep_store.record_passage_origin(
                passage_id=str(passage_id),
                book_id=str(book_id),
                chapter_id=chapter_id,
                section_id=section_id,
                normalized_text_artifact_id=str(leaf.get("normalized_text_artifact_id") or ""),
                split_leaf_id=str(leaf.get("split_node_id") or ""),
                sentence_start_id=str(leaf.get("sentence_start_id") or ""),
                sentence_end_id=str(leaf.get("sentence_end_id") or ""),
                char_start=int(leaf.get("char_start") or 0),
                char_end=int(leaf.get("char_end") or 0),
                quote_fingerprint=_hash_text(passage_text, alg=quote_fingerprint_alg),
                extraction_run_id=str(passage_run),
                trace_level="L4",
                trace_completeness_score=0.94,
            )
            created_passages += 1

            claim_candidates = _claim_candidates_for_leaf(
                prep_store=prep_store,
                leaf=leaf,
                artifact_root=str(artifact_root),
                min_claim_chars=int(min_claim_chars),
                min_claim_words=int(min_claim_words),
            )
            for cand in claim_candidates:
                claim_text = _norm_ws(str(cand.get("text") or ""))
                if not claim_text:
                    continue
                claim_id = _stable_id("claim", passage_id, cand.get("char_start"), cand.get("char_end"), claim_text)
                address = _build_address(
                    book=book,
                    chapter_title=chapter_title,
                    section_title=section_title,
                    chapter_id=chapter_id,
                    section_id=section_id,
                    normalized_text_artifact_id=str(leaf.get("normalized_text_artifact_id") or ""),
                    sentence_start_id=str(cand.get("sentence_start_id") or ""),
                    sentence_end_id=str(cand.get("sentence_end_id") or ""),
                    char_start=int(cand.get("char_start") or 0),
                    char_end=int(cand.get("char_end") or 0),
                    passage_id=str(passage_id),
                    split_leaf_id=str(leaf.get("split_node_id") or ""),
                )
                evidence_spans = [{
                    "kind": "text_span",
                    "normalized_text_artifact_id": str(leaf.get("normalized_text_artifact_id") or ""),
                    "sentence_start_id": str(cand.get("sentence_start_id") or ""),
                    "sentence_end_id": str(cand.get("sentence_end_id") or ""),
                    "char_start": int(cand.get("char_start") or 0),
                    "char_end": int(cand.get("char_end") or 0),
                    "quote_fingerprint": _hash_text(claim_text, alg=quote_fingerprint_alg),
                }]
                concept_ids: List[str] = []
                if bool(auto_concepts_enabled):
                    for label in _auto_concept_labels(claim_text, topic_tags=list(cand.get("topic_tags") or []), max_labels=int(max_auto_concepts_per_claim), min_len=int(concept_min_token_len)):
                        cid = f"concept:auto:{_slug(label)}"
                        store.upsert_auto_concept(
                            concept_id=str(cid),
                            label=str(label),
                            definition_passage_id=str(passage_id),
                            realms=[str(default_realm)] if str(default_realm or "").strip() else [],
                            introduced_in=str(source_id),
                            created_by=str(created_by),
                        )
                        concept_ids.append(str(cid))
                        created_concepts += 1
                evidence_ids: List[str] = []
                if bool(create_evidence_objects):
                    evidence_id = _stable_id("evidence", claim_id, address["char_start"], address["char_end"], address["passage_id"])
                    store.add_evidence(
                        evidence_id=str(evidence_id),
                        kind="text_span",
                        strength=0.95 if str(cand.get("claim_mode") or "quoted") == "quoted" else 0.82,
                        source_refs=[address],
                        support_passages=[{"passage_id": str(passage_id), "quote_fingerprint": evidence_spans[0]["quote_fingerprint"]}],
                        realm_context={"book_id": str(book_id), "chapter_id": chapter_id, "section_id": section_id},
                        notes="auto-extracted from prep leaf chunk",
                        created_by=str(created_by),
                    )
                    evidence_ids.append(str(evidence_id))
                    created_evidence += 1
                store.add_claim(
                    claim_id=str(claim_id),
                    text_normalized=claim_text,
                    about_concepts=concept_ids,
                    realm_context={"book_id": str(book_id), "chapter_id": chapter_id, "section_id": section_id},
                    status="hypothesis",
                    confidence=0.93 if str(cand.get("claim_mode") or "quoted") == "quoted" else 0.75,
                    extracted_from_passages=[str(passage_id)],
                    supported_by_evidence=evidence_ids,
                    counterclaims=[],
                    created_by=str(created_by),
                )
                prep_store.record_claim_origin(
                    claim_id=str(claim_id),
                    source_id=str(source_id),
                    book_id=str(book_id),
                    chapter_id=chapter_id,
                    section_id=section_id,
                    normalized_text_artifact_id=str(leaf.get("normalized_text_artifact_id") or ""),
                    passage_id=str(passage_id),
                    split_leaf_id=str(leaf.get("split_node_id") or ""),
                    sentence_start_id=str(cand.get("sentence_start_id") or ""),
                    sentence_end_id=str(cand.get("sentence_end_id") or ""),
                    char_start=int(cand.get("char_start") or 0),
                    char_end=int(cand.get("char_end") or 0),
                    primary_address=address,
                    evidence_spans=evidence_spans,
                    claim_mode=str(cand.get("claim_mode") or "quoted"),
                    quote_fingerprint=evidence_spans[0]["quote_fingerprint"],
                    extraction_run_id=str(claim_run),
                    trace_level="L4",
                    trace_completeness_score=0.96,
                )
                if bool(create_lineage_links):
                    store.add_lineage_link(
                        lineage_id=_stable_id("lineage", claim_id, passage_id, address["char_start"], address["char_end"]),
                        child_kind="claim",
                        child_id=str(claim_id),
                        relation_type="extracted_from_passage",
                        parents=[{"kind": "passage", "id": str(passage_id)}],
                        declared_derivation={"claim_mode": str(cand.get("claim_mode") or "quoted"), "profile_id": str(claim_profile_id)},
                        computed_checks={"quote_fingerprint": evidence_spans[0]["quote_fingerprint"], "book_checksum": str(book.get("book_checksum") or "")},
                        support_passages=[{"passage_id": str(passage_id), "char_start": address["char_start"], "char_end": address["char_end"]}],
                        confidence=0.96,
                        realm_context={"book_id": str(book_id), "chapter_id": chapter_id, "section_id": section_id},
                        created_by=str(created_by),
                    )
                for aid, bid in _relation_pairs(claim_text):
                    for label in (aid, bid):
                        cid = f"concept:auto:{_slug(label)}"
                        store.upsert_auto_concept(
                            concept_id=str(cid),
                            label=str(label),
                            definition_passage_id=str(passage_id),
                            realms=[str(default_realm)] if str(default_realm or "").strip() else [],
                            introduced_in=str(source_id),
                            created_by=str(created_by),
                        )
                        if cid not in concept_ids:
                            concept_ids.append(cid)
                    store.add_link(
                        link_id=_stable_id("link", aid, bid, "follows"),
                        from_kind="concept",
                        from_id=f"concept:auto:{_slug(aid)}",
                        to_kind="concept",
                        to_id=f"concept:auto:{_slug(bid)}",
                        link_type="follows",
                        conditions={"auto": True, "claim_id": str(claim_id)},
                        created_by=str(created_by),
                    )
                    created_links += 1
                for cid in concept_ids:
                    store.add_link(
                        link_id=_stable_id("link", claim_id, cid, "about"),
                        from_kind="claim",
                        from_id=str(claim_id),
                        to_kind="concept",
                        to_id=str(cid),
                        link_type="about",
                        conditions={"auto": True},
                        created_by=str(created_by),
                    )
                    created_links += 1
                created_claims += 1
        prep_store.finish_processing_run(run_id=str(passage_run))
        prep_store.finish_processing_run(run_id=str(claim_run))
        prep_store.mark_book_status(book_id=str(book_id), status="completed")
    except Exception as e:
        prep_store.finish_processing_run(run_id=str(passage_run), run_status="failed", error_code="passage_builder_error", error_message=str(e))
        prep_store.finish_processing_run(run_id=str(claim_run), run_status="failed", error_code="claim_extractor_error", error_message=str(e))
        prep_store.mark_book_status(book_id=str(book_id), status="failed", error_code="extraction_error", error_message=str(e))
        return {"ok": False, "reason": "extraction_error", "book_id": str(book_id), "error": str(e)}

    summary = prep_store.summarize_book(book_id=str(book_id))
    summary.update({
        "ok": True,
        "book_id": str(book_id),
        "source_id": str(source_id),
        "created_passages": int(created_passages),
        "created_claims": int(created_claims),
        "created_evidence": int(created_evidence),
        "created_concepts": int(created_concepts),
        "created_links": int(created_links),
        "passage_run_id": str(passage_run),
        "claim_run_id": str(claim_run),
    })
    return summary



def extract_next_book(
    *,
    prep_store: PrepStore,
    store: KnowledgeStore,
    artifact_root: str,
    default_realm: str = "",
    passage_profile_id: str = "passage_builder_v1",
    claim_profile_id: str = "claim_sentence_v1",
    min_claim_chars: int = 24,
    min_claim_words: int = 4,
    create_evidence_objects: bool = True,
    create_lineage_links: bool = True,
    auto_concepts_enabled: bool = True,
    max_auto_concepts_per_claim: int = 3,
    concept_min_token_len: int = 4,
    quote_fingerprint_alg: str = "sha256",
    created_by: str = "brainctl-kg-extract",
) -> Dict[str, Any]:
    ready = prep_store.list_books_ready_for_extraction(limit=50)
    for book in ready:
        if int(book.get("leaf_count") or 0) <= 0:
            continue
        if int(book.get("passage_count") or 0) > 0 and int(book.get("claim_count") or 0) > 0:
            continue
        return extract_book(
            prep_store=prep_store,
            store=store,
            book_id=str(book["book_id"]),
            artifact_root=str(artifact_root),
            default_realm=str(default_realm),
            passage_profile_id=str(passage_profile_id),
            claim_profile_id=str(claim_profile_id),
            min_claim_chars=int(min_claim_chars),
            min_claim_words=int(min_claim_words),
            create_evidence_objects=bool(create_evidence_objects),
            create_lineage_links=bool(create_lineage_links),
            auto_concepts_enabled=bool(auto_concepts_enabled),
            max_auto_concepts_per_claim=int(max_auto_concepts_per_claim),
            concept_min_token_len=int(concept_min_token_len),
            quote_fingerprint_alg=str(quote_fingerprint_alg),
            created_by=str(created_by),
        )
    return {"ok": True, "reason": "no_ready_books", "extracted": False}


__all__ = [
    "extract_book",
    "extract_next_book",
    "load_extraction_config",
]
