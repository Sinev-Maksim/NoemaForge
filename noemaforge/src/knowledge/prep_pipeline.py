#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/knowledge/prep_pipeline.py
Zone: release/package
Version: 0.32.1
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
# File: src/knowledge/prep_pipeline.py
# Zone: brain
# Purpose: Build long-form preprocessing plans for books: normalization, sentence labeling,
#   topic-adjacency grouping, split trees, and in-memory leaf chunk materialization.
# Callers: src/brainctl.py, future knowledge extraction pipelines, tests/test_prep_pipeline.py
# Inputs: raw txt/md books, PrepStore database, knowledge-policy prep_processing settings
# Outputs: prep-store metadata rows, normalized text artifact files, leaf chunk bodies in memory
# Side effects: reads source files, writes normalized text artifacts, mutates prep_index.sqlite
# Security notes:
#   - invariants: queue-first processing, plan-before-extraction, chunk bodies remain in memory only
#   - threats: accidental metadata reuse across checksum mismatch, unstable boundaries, provenance gaps
# === End NoemaForge Autodoc File Header ===

"""NoemaForge prep pipeline runtime.

This module implements the next functional B-track layer after the durable prep-store.
It intentionally stops before knowledge extraction and instead makes long-form sources
ready for downstream passage / claim building.

Execution order:
  1. Queue book (or lease next queue entry)
  2. Normalize text and persist a durable normalized text artifact
  3. Split into sentences with paragraph awareness
  4. Label each sentence with lightweight topic tags/signatures
  5. Build adjacency groups from topical continuity
  6. Build a split tree under a token budget
  7. Expose leaf chunk bodies *in memory* only
"""


import math
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Sequence, Tuple

from .policy import load_knowledge_policy
from .prep_store import PrepStore

STOPWORDS = {
    # English
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "he", "her", "his",
    "i", "in", "is", "it", "its", "of", "on", "or", "our", "she", "that", "the", "their", "them",
    "there", "they", "this", "to", "was", "we", "were", "will", "with", "you", "your", "into",
    "about", "after", "before", "than", "then", "when", "while", "where", "what", "which", "who",
    "whom", "why", "how", "can", "could", "would", "should", "may", "might", "must", "also",
    # Russian
    "и", "в", "во", "не", "что", "он", "на", "я", "с", "со", "как", "а", "то", "все", "она",
    "так", "его", "но", "да", "ты", "к", "у", "же", "вы", "за", "бы", "по", "только", "ее",
    "мне", "было", "вот", "от", "меня", "еще", "нет", "о", "из", "ему", "теперь", "когда", "даже",
    "ну", "вдруг", "ли", "если", "уже", "или", "ни", "быть", "был", "него", "до", "вас", "нибудь",
    "опять", "уж", "вам", "ведь", "там", "потом", "себя", "ничего", "ей", "может", "они", "тут",
    "где", "есть", "надо", "ней", "для", "мы", "тебя", "их", "чем", "была", "сам", "чтоб", "без",
    "будто", "чего", "раз", "тоже", "себе", "под", "будет", "ж", "тогда", "кто", "этот", "того",
}

SENTENCE_BOUNDARY_RE = re.compile(r'(?<=[.!?…])(?:["»”\'\)\]]*)\s+(?=[A-ZА-ЯЁ0-9])')
HEADING_RE = re.compile(r'^(#{1,6})\s+(.+?)\s*$', re.M)
CHAPTER_LINE_RE = re.compile(r'^\s*(?:chapter|глава)\b[^\n]*$', re.I | re.M)
TOKEN_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9_]+")
PARAGRAPH_SPLIT_RE = re.compile(r'\n\s*\n+')


def estimate_tokens(text: str, *, chars_per_token: int = 4) -> int:
    if not text:
        return 0
    cpt = max(1, int(chars_per_token))
    return max(1, math.ceil(len(text) / cpt))



def normalize_text(raw: str, *, canonicalization_profile: str = "default") -> str:
    txt = str(raw or "")
    txt = txt.replace("\ufeff", "")
    txt = txt.replace("\r\n", "\n").replace("\r", "\n")
    txt = txt.replace("\xa0", " ")
    txt = txt.replace("\t", "    ")
    txt = re.sub(r"[ \t]+\n", "\n", txt)
    txt = re.sub(r"\n{3,}", "\n\n", txt)
    if canonicalization_profile == "aggressive":
        txt = re.sub(r"[ ]{2,}", " ", txt)
    return txt.strip() + ("\n" if txt.strip() else "")



def _keywords(text: str, *, title_hint: str = "") -> List[str]:
    toks = [t.lower() for t in TOKEN_RE.findall((text or "") + " " + (title_hint or ""))]
    seen: List[str] = []
    for tok in toks:
        if len(tok) < 3 or tok in STOPWORDS:
            continue
        if tok not in seen:
            seen.append(tok)
    return seen[:8]



def label_sentence_topic(sentence_text: str, *, title_hint: str = "") -> Dict[str, Any]:
    keys = _keywords(sentence_text, title_hint=title_hint)
    if not keys:
        fallback = TOKEN_RE.findall(sentence_text or "")[:2]
        keys = [t.lower() for t in fallback] or ["misc"]
    topic_tags = keys[:4]
    signature = "|".join(sorted(topic_tags[:3]))
    confidence = min(0.98, 0.35 + 0.12 * len(topic_tags))
    if len(sentence_text.strip()) < 25:
        confidence = max(0.25, confidence - 0.10)
    return {
        "topic_tags": topic_tags,
        "topic_signature": signature,
        "topic_confidence": round(confidence, 4),
    }



def _topic_overlap(a: Sequence[str], b: Sequence[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / max(1, len(sa | sb))



def _find_paragraphs(text: str) -> List[Dict[str, Any]]:
    paras: List[Dict[str, Any]] = []
    pos = 0
    pno = 0
    for m in PARAGRAPH_SPLIT_RE.finditer(text):
        seg = text[pos:m.start()]
        if seg.strip():
            pno += 1
            paras.append({"paragraph_no": pno, "char_start": pos, "char_end": m.start(), "text": seg})
        pos = m.end()
    tail = text[pos:]
    if tail.strip():
        pno += 1
        paras.append({"paragraph_no": pno, "char_start": pos, "char_end": len(text), "text": tail})
    if not paras and text.strip():
        paras.append({"paragraph_no": 1, "char_start": 0, "char_end": len(text), "text": text})
    return paras



def _split_sentences(text: str, *, global_offset: int = 0) -> List[Tuple[int, int, str]]:
    out: List[Tuple[int, int, str]] = []
    last = 0
    for m in SENTENCE_BOUNDARY_RE.finditer(text):
        part = text[last:m.start()]
        if part.strip():
            local_start = last + (len(part) - len(part.lstrip()))
            local_end = m.start()
            out.append((global_offset + local_start, global_offset + local_end, part.strip()))
        last = m.end()
    tail = text[last:]
    if tail.strip():
        local_start = last + (len(tail) - len(tail.lstrip()))
        out.append((global_offset + local_start, global_offset + len(text), tail.strip()))
    return out



def _parse_structure(text: str) -> Dict[str, Any]:
    lines = text.splitlines(True)
    offsets: List[int] = []
    pos = 0
    for ln in lines:
        offsets.append(pos)
        pos += len(ln)

    headings: List[Dict[str, Any]] = []
    for i, line in enumerate(lines):
        ls = line.strip()
        if not ls:
            continue
        m = re.match(r'^(#{1,6})\s+(.+?)\s*$', ls)
        if m:
            headings.append({"offset": offsets[i], "level": len(m.group(1)), "title": m.group(2).strip(), "kind": "md"})
            continue
        if CHAPTER_LINE_RE.match(ls):
            headings.append({"offset": offsets[i], "level": 1, "title": ls, "kind": "chapter_line"})

    chapters: List[Dict[str, Any]] = []
    sections: List[Dict[str, Any]] = []
    if not headings:
        chapters.append({"chapter_no": 1, "chapter_title": "Book", "chapter_path": "1", "raw_char_start": 0, "raw_char_end": len(text)})
        sections.append({"chapter_no": 1, "chapter_path": "1", "section_path": "1", "section_title": "Book", "section_level": 1, "raw_char_start": 0, "raw_char_end": len(text)})
        return {"chapters": chapters, "sections": sections}

    chapter_starts = [h for h in headings if h["level"] == 1]
    if not chapter_starts or chapter_starts[0]["offset"] != 0:
        chapter_starts = [{"offset": 0, "level": 1, "title": "Book", "kind": "synthetic"}] + chapter_starts

    for idx, ch in enumerate(chapter_starts, start=1):
        ch_start = int(ch["offset"])
        ch_end = int(chapter_starts[idx]["offset"]) if idx < len(chapter_starts) else len(text)
        ch_path = str(idx)
        chapter = {"chapter_no": idx, "chapter_title": str(ch["title"]), "chapter_path": ch_path, "raw_char_start": ch_start, "raw_char_end": ch_end}
        chapters.append(chapter)
        local_heads = [h for h in headings if h["offset"] >= ch_start and h["offset"] < ch_end and h["level"] >= 2]
        if not local_heads:
            sections.append({
                "chapter_no": idx,
                "chapter_path": ch_path,
                "section_path": ch_path,
                "section_title": chapter["chapter_title"],
                "section_level": 1,
                "raw_char_start": ch_start,
                "raw_char_end": ch_end,
            })
            continue
        sec_counter = 0
        current_start = ch_start
        current_title = chapter["chapter_title"]
        for sh in local_heads:
            if sh["offset"] > current_start:
                sec_counter += 1
                sections.append({
                    "chapter_no": idx,
                    "chapter_path": ch_path,
                    "section_path": f"{ch_path}.{sec_counter}",
                    "section_title": current_title,
                    "section_level": 1,
                    "raw_char_start": current_start,
                    "raw_char_end": int(sh["offset"]),
                })
            current_start = int(sh["offset"])
            current_title = str(sh["title"])
        sec_counter += 1
        sections.append({
            "chapter_no": idx,
            "chapter_path": ch_path,
            "section_path": f"{ch_path}.{sec_counter}",
            "section_title": current_title,
            "section_level": 2,
            "raw_char_start": current_start,
            "raw_char_end": ch_end,
        })
    return {"chapters": chapters, "sections": sections}



def _resolve_owner(offset: int, records: Sequence[Dict[str, Any]], id_key: str) -> str | None:
    for rec in records:
        if int(rec.get("raw_char_start") or 0) <= offset < int(rec.get("raw_char_end") or 0):
            return str(rec.get(id_key) or "") or None
    return None



def _best_split_by_paragraph(sentences: Sequence[Dict[str, Any]], *, max_tokens: int) -> int:
    if len(sentences) < 2:
        return 0
    by_para: List[Tuple[int, int]] = []
    last_no = None
    start_idx = 0
    for idx, s in enumerate(sentences):
        pno = s.get("paragraph_no")
        if last_no is None:
            last_no = pno
            start_idx = idx
            continue
        if pno != last_no:
            by_para.append((start_idx, idx))
            start_idx = idx
            last_no = pno
    by_para.append((start_idx, len(sentences)))
    if len(by_para) <= 1:
        return 0
    totals = [sum(int(sentences[i].get("token_estimate") or 0) for i in range(a, b)) for a, b in by_para]
    best_idx = 0
    best_score = None
    for split_at in range(1, len(by_para)):
        left = sum(totals[:split_at])
        right = sum(totals[split_at:])
        score = max(left, right)
        if best_score is None or score < best_score:
            best_score = score
            best_idx = by_para[split_at][0]
    if best_score is None or best_score >= sum(totals):
        return 0
    return best_idx



def _split_single_sentence_by_clause(sentence: Dict[str, Any], *, max_tokens: int, clause_delimiters: Sequence[str], chars_per_token: int) -> List[Dict[str, Any]]:
    text = sentence["text"]
    if estimate_tokens(text, chars_per_token=chars_per_token) <= max_tokens:
        return [{
            "sentence_start_id": sentence["sentence_id"],
            "sentence_end_id": sentence["sentence_id"],
            "char_start": sentence["char_start"],
            "char_end": sentence["char_end"],
            "estimated_tokens": estimate_tokens(text, chars_per_token=chars_per_token),
            "boundary_mode": "sentence_span",
            "fragment_spec": {},
            "text": text,
        }]
    clause_chars = ''.join(re.escape(c) for c in clause_delimiters)
    splitter = re.compile(rf'(?<=[{clause_chars}])\s+') if clause_chars else None
    pieces: List[Tuple[int, int, str]] = []
    last = 0
    if splitter:
        for m in splitter.finditer(text):
            part = text[last:m.start()]
            if part.strip():
                local_start = last + (len(part) - len(part.lstrip()))
                pieces.append((local_start, m.start(), part.strip()))
            last = m.end()
    tail = text[last:]
    if tail.strip():
        local_start = last + (len(tail) - len(tail.lstrip()))
        pieces.append((local_start, len(text), tail.strip()))
    if len(pieces) <= 1:
        window_chars = max(32, max_tokens * chars_per_token)
        cur = 0
        while cur < len(text):
            end = min(len(text), cur + window_chars)
            pieces.append((cur, end, text[cur:end].strip()))
            cur = end
    out: List[Dict[str, Any]] = []
    for idx, (local_start, local_end, frag) in enumerate(pieces, start=1):
        if not frag:
            continue
        out.append({
            "sentence_start_id": sentence["sentence_id"],
            "sentence_end_id": sentence["sentence_id"],
            "char_start": int(sentence["char_start"]) + local_start,
            "char_end": int(sentence["char_start"]) + local_end,
            "estimated_tokens": estimate_tokens(frag, chars_per_token=chars_per_token),
            "boundary_mode": "clause_window",
            "fragment_spec": {"clause_index": idx, "fragment_count": len(pieces)},
            "text": frag,
        })
    return out



def _plan_sentence_range(sentences: Sequence[Dict[str, Any]], *, max_tokens: int, chars_per_token: int, paragraph_split_preference: bool, clause_split_enabled: bool, clause_delimiters: Sequence[str], split_depth: int = 0) -> Dict[str, Any]:
    total_tokens = sum(int(s.get("token_estimate") or 0) for s in sentences)
    node = {
        "sentence_start_id": str(sentences[0]["sentence_id"]),
        "sentence_end_id": str(sentences[-1]["sentence_id"]),
        "char_start": int(sentences[0]["char_start"]),
        "char_end": int(sentences[-1]["char_end"]),
        "estimated_tokens": total_tokens,
        "split_depth": split_depth,
        "split_strategy": "budget_check",
        "split_reason": "fits_budget" if total_tokens <= max_tokens else "over_budget",
        "boundary_mode": "sentence_span",
        "fragment_spec": {},
        "children": [],
        "chunk_quality_metrics": {
            "sentence_count": len(sentences),
            "budget_ratio": round(total_tokens / max(1, max_tokens), 4),
            "min_sentence_no": int(sentences[0]["sentence_no"]),
            "max_sentence_no": int(sentences[-1]["sentence_no"]),
        },
    }
    if total_tokens <= max_tokens:
        node["is_leaf"] = True
        return node
    if len(sentences) == 1:
        if clause_split_enabled:
            leaves = _split_single_sentence_by_clause(sentences[0], max_tokens=max_tokens, clause_delimiters=clause_delimiters, chars_per_token=chars_per_token)
            node["split_strategy"] = "clause_or_window"
            node["children"] = [{
                **leaf,
                "split_depth": split_depth + 1,
                "split_reason": "single_sentence_over_budget",
                "split_strategy": "clause_or_window",
                "chunk_quality_metrics": {
                    "sentence_count": 1,
                    "budget_ratio": round(int(leaf["estimated_tokens"]) / max(1, max_tokens), 4),
                    "fragment": True,
                },
                "is_leaf": True,
                "children": [],
            } for leaf in leaves]
            node["is_leaf"] = False
            return node
        node["is_leaf"] = True
        node["chunk_quality_metrics"]["oversized_leaf"] = True
        return node

    split_idx = 0
    strategy = "sentence_window"
    if paragraph_split_preference:
        split_idx = _best_split_by_paragraph(sentences, max_tokens=max_tokens)
        if split_idx:
            strategy = "paragraph_boundary"
    if not split_idx:
        running = 0
        target = max(1, math.floor(total_tokens / 2))
        for idx, s in enumerate(sentences[:-1], start=1):
            running += int(s.get("token_estimate") or 0)
            if running >= target:
                split_idx = idx
                break
        split_idx = split_idx or max(1, len(sentences) // 2)
    left = list(sentences[:split_idx])
    right = list(sentences[split_idx:])
    node["split_strategy"] = strategy
    node["split_reason"] = "over_budget_recursive"
    node["children"] = [
        _plan_sentence_range(left, max_tokens=max_tokens, chars_per_token=chars_per_token, paragraph_split_preference=paragraph_split_preference, clause_split_enabled=clause_split_enabled, clause_delimiters=clause_delimiters, split_depth=split_depth + 1),
        _plan_sentence_range(right, max_tokens=max_tokens, chars_per_token=chars_per_token, paragraph_split_preference=paragraph_split_preference, clause_split_enabled=clause_split_enabled, clause_delimiters=clause_delimiters, split_depth=split_depth + 1),
    ]
    node["is_leaf"] = False
    return node



def _walk_tree(node: Dict[str, Any]) -> Iterator[Dict[str, Any]]:
    yield node
    for child in node.get("children", []) or []:
        yield from _walk_tree(child)



def _flatten_leaves(node: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for n in _walk_tree(node):
        if n.get("is_leaf"):
            out.append(n)
    return out



def _persist_normalized_text(artifact_dir: str, normalized_text_artifact_id: str, text: str) -> str:
    out_dir = Path(artifact_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rel = f"normalized_text/{normalized_text_artifact_id}.txt"
    path = out_dir / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return rel



def analyze_book_path(
    *,
    prep_store: PrepStore,
    source_path: str,
    artifact_root: str,
    canonicalization_profile: str = "default",
    normalization_version: str = "norm-v1",
    queue_name: str = "default",
    priority: int = 100,
    book_title: str = "",
    max_tokens_per_leaf: int = 350,
    min_sentences_per_leaf: int = 1,
    sentence_token_chars_per_token: int = 4,
    paragraph_split_preference: bool = True,
    clause_split_enabled: bool = True,
    clause_delimiters: Sequence[str] = (",", ";", ":", "—", "–"),
    worker_id: str = "prep-analyze",
) -> Dict[str, Any]:
    rep = prep_store.enqueue_book_path(
        path=str(source_path),
        queue_name=str(queue_name),
        priority=int(priority),
        canonicalization_profile=str(canonicalization_profile),
        book_title=str(book_title or ""),
    )
    if not rep.get("ok"):
        return rep
    entry = prep_store.get_queue_entry(ingest_queue_entry_id=str(rep["ingest_queue_entry_id"])) or {}
    if str(entry.get("queue_status") or "") == "completed":
        out = prep_store.summarize_book(book_id=str(rep["book_id"]))
        out.update({"reused_analysis": True, "book_id": str(rep["book_id"]), "ingest_queue_entry_id": str(rep["ingest_queue_entry_id"])})
        return out
    if str(entry.get("queue_status") or "") == "queued":
        lease = prep_store.lease_next_queue_entry(queue_name=str(queue_name), worker_id=str(worker_id), lease_ttl_sec=900)
        if not lease.get("ok"):
            return lease
    return analyze_queue_entry(
        prep_store=prep_store,
        ingest_queue_entry_id=str(rep["ingest_queue_entry_id"]),
        artifact_root=str(artifact_root),
        normalization_version=str(normalization_version),
        max_tokens_per_leaf=int(max_tokens_per_leaf),
        min_sentences_per_leaf=int(min_sentences_per_leaf),
        sentence_token_chars_per_token=int(sentence_token_chars_per_token),
        paragraph_split_preference=bool(paragraph_split_preference),
        clause_split_enabled=bool(clause_split_enabled),
        clause_delimiters=list(clause_delimiters),
    )



def analyze_next_queue_entry(
    *,
    prep_store: PrepStore,
    artifact_root: str,
    queue_name: str = "default",
    worker_id: str = "prep-worker",
    lease_ttl_sec: int = 900,
    normalization_version: str = "norm-v1",
    max_tokens_per_leaf: int = 350,
    min_sentences_per_leaf: int = 1,
    sentence_token_chars_per_token: int = 4,
    paragraph_split_preference: bool = True,
    clause_split_enabled: bool = True,
    clause_delimiters: Sequence[str] = (",", ";", ":", "—", "–"),
) -> Dict[str, Any]:
    lease = prep_store.lease_next_queue_entry(queue_name=str(queue_name), worker_id=str(worker_id), lease_ttl_sec=int(lease_ttl_sec))
    if not lease.get("ok") or not lease.get("leased"):
        return lease
    return analyze_queue_entry(
        prep_store=prep_store,
        ingest_queue_entry_id=str(lease["entry"]["ingest_queue_entry_id"]),
        artifact_root=str(artifact_root),
        normalization_version=str(normalization_version),
        max_tokens_per_leaf=int(max_tokens_per_leaf),
        min_sentences_per_leaf=int(min_sentences_per_leaf),
        sentence_token_chars_per_token=int(sentence_token_chars_per_token),
        paragraph_split_preference=bool(paragraph_split_preference),
        clause_split_enabled=bool(clause_split_enabled),
        clause_delimiters=list(clause_delimiters),
    )



def analyze_queue_entry(
    *,
    prep_store: PrepStore,
    ingest_queue_entry_id: str,
    artifact_root: str,
    normalization_version: str = "norm-v1",
    max_tokens_per_leaf: int = 350,
    min_sentences_per_leaf: int = 1,
    sentence_token_chars_per_token: int = 4,
    paragraph_split_preference: bool = True,
    clause_split_enabled: bool = True,
    clause_delimiters: Sequence[str] = (",", ";", ":", "—", "–"),
) -> Dict[str, Any]:
    q = prep_store.get_queue_entry(ingest_queue_entry_id=str(ingest_queue_entry_id))
    if not q:
        return {"ok": False, "reason": "queue_entry_not_found", "ingest_queue_entry_id": str(ingest_queue_entry_id)}
    book = prep_store.get_book(book_id=str(q["book_id"]))
    if not book:
        return {"ok": False, "reason": "book_not_found", "book_id": str(q.get("book_id") or "")}

    src_path = str(book.get("source_path") or "")
    if not src_path or not os.path.exists(src_path):
        prep_store.mark_book_status(book_id=str(book["book_id"]), status="failed", error_code="source_missing", error_message=src_path)
        prep_store.complete_queue_entry(ingest_queue_entry_id=str(ingest_queue_entry_id), queue_status="failed")
        return {"ok": False, "reason": "source_missing", "path": src_path}

    raw = Path(src_path).read_text(encoding="utf-8")
    prep_store.mark_book_status(book_id=str(book["book_id"]), status="normalizing")
    norm_run = prep_store.start_processing_run(component="normalizer", book_id=str(book["book_id"]), profile_id=str(book.get("canonicalization_profile") or ""), code_version="0.27.9")
    try:
        normalized = normalize_text(raw, canonicalization_profile=str(book.get("canonicalization_profile") or "default"))
        rel = _persist_normalized_text(str(artifact_root), f"book_{book['book_id']}", normalized)
        art = prep_store.add_normalized_text_artifact(
            book_id=str(book["book_id"]),
            artifact_scope="book",
            text=normalized,
            normalization_version=str(normalization_version),
            canonicalization_profile=str(book.get("canonicalization_profile") or "default"),
            artifact_relpath=rel,
            artifact_encoding="utf-8",
        )
        prep_store.finish_processing_run(run_id=norm_run)
    except Exception as e:
        prep_store.finish_processing_run(run_id=norm_run, run_status="failed", error_code="normalization_error", error_message=str(e))
        prep_store.mark_book_status(book_id=str(book["book_id"]), status="failed", error_code="normalization_error", error_message=str(e))
        prep_store.complete_queue_entry(ingest_queue_entry_id=str(ingest_queue_entry_id), queue_status="failed")
        return {"ok": False, "reason": "normalization_error", "error": str(e)}

    structure = _parse_structure(normalized)
    chapter_ids_by_no: Dict[int, str] = {}
    section_records: List[Dict[str, Any]] = []
    for ch in structure["chapters"]:
        cid = prep_store.add_chapter(book_id=str(book["book_id"]), chapter_no=int(ch["chapter_no"]), chapter_title=str(ch["chapter_title"]), chapter_path=str(ch["chapter_path"]), raw_char_start=int(ch["raw_char_start"]), raw_char_end=int(ch["raw_char_end"]))
        chapter_ids_by_no[int(ch["chapter_no"])] = cid
        ch["chapter_id"] = cid
    for sec in structure["sections"]:
        sid = prep_store.add_section(book_id=str(book["book_id"]), chapter_id=str(chapter_ids_by_no[int(sec["chapter_no"])]), section_path=str(sec["section_path"]), section_title=str(sec["section_title"]), section_level=int(sec["section_level"]), raw_char_start=int(sec["raw_char_start"]), raw_char_end=int(sec["raw_char_end"]))
        sec["section_id"] = sid
        sec["chapter_id"] = str(chapter_ids_by_no[int(sec["chapter_no"])] )
        section_records.append(sec)

    prep_store.mark_book_status(book_id=str(book["book_id"]), status="labeling")
    split_run = prep_store.start_processing_run(component="sentence_splitter", book_id=str(book["book_id"]), profile_id="sentence_heuristic_v1", code_version="0.27.9")
    label_run = prep_store.start_processing_run(component="topic_labeler", book_id=str(book["book_id"]), profile_id="topic_heuristic_v1", code_version="0.27.9")

    sentence_rows: List[Dict[str, Any]] = []
    sentence_no = 0
    paragraphs = _find_paragraphs(normalized)
    for para in paragraphs:
        for s_start, s_end, s_text in _split_sentences(para["text"], global_offset=int(para["char_start"])):
            sentence_no += 1
            chapter_id = _resolve_owner(s_start, structure["chapters"], "chapter_id")
            section_id = _resolve_owner(s_start, section_records, "section_id")
            title_hint = ""
            for sec in section_records:
                if sec.get("section_id") == section_id:
                    title_hint = str(sec.get("section_title") or "")
                    break
            tok_est = estimate_tokens(s_text, chars_per_token=int(sentence_token_chars_per_token))
            sid = prep_store.add_sentence(
                book_id=str(book["book_id"]),
                chapter_id=chapter_id,
                section_id=section_id,
                normalized_text_artifact_id=str(art["normalized_text_artifact_id"]),
                sentence_no=sentence_no,
                paragraph_no=int(para["paragraph_no"]),
                char_start=int(s_start),
                char_end=int(s_end),
                text=s_text,
                token_estimate=tok_est,
            )
            label = label_sentence_topic(s_text, title_hint=title_hint)
            prep_store.add_sentence_topic_map(sentence_id=sid, labeling_run_id=str(label_run), topic_tags=label["topic_tags"], topic_signature=label["topic_signature"], topic_confidence=float(label["topic_confidence"]))
            sentence_rows.append({
                "sentence_id": sid,
                "sentence_no": sentence_no,
                "chapter_id": chapter_id,
                "section_id": section_id,
                "paragraph_no": int(para["paragraph_no"]),
                "char_start": int(s_start),
                "char_end": int(s_end),
                "token_estimate": tok_est,
                "text": s_text,
                **label,
            })
    prep_store.finish_processing_run(run_id=split_run)
    prep_store.finish_processing_run(run_id=label_run)

    prep_store.mark_book_status(book_id=str(book["book_id"]), status="chunk_planning")
    adj_run = prep_store.start_processing_run(component="adjacency_builder", book_id=str(book["book_id"]), profile_id="adjacency_v1", code_version="0.27.9")
    groups: List[List[Dict[str, Any]]] = []
    cur: List[Dict[str, Any]] = []
    cur_tags: List[str] = []
    for s in sentence_rows:
        if not cur:
            cur = [s]
            cur_tags = list(s["topic_tags"])
            continue
        same_scope = (s.get("chapter_id"), s.get("section_id")) == (cur[-1].get("chapter_id"), cur[-1].get("section_id"))
        overlap = _topic_overlap(cur_tags, s["topic_tags"])
        low_info = len(s["topic_tags"]) <= 1 or len(cur[-1]["topic_tags"]) <= 1
        if same_scope and (overlap >= 0.20 or low_info):
            cur.append(s)
            cur_tags = list(dict.fromkeys(cur_tags + list(s["topic_tags"])))
        else:
            groups.append(cur)
            cur = [s]
            cur_tags = list(s["topic_tags"])
    if cur:
        groups.append(cur)

    group_rows: List[Dict[str, Any]] = []
    for grp in groups:
        tags_union = list(dict.fromkeys(tag for row in grp for tag in row["topic_tags"]))
        overlaps = []
        for a, b in zip(grp, grp[1:]):
            overlaps.append(_topic_overlap(a["topic_tags"], b["topic_tags"]))
        cohesion = round(sum(overlaps) / max(1, len(overlaps)), 4) if overlaps else 1.0
        gid = prep_store.add_adjacency_group(
            book_id=str(book["book_id"]),
            chapter_id=str(grp[0].get("chapter_id") or "") or None,
            section_id=str(grp[0].get("section_id") or "") or None,
            built_run_id=str(adj_run),
            sentence_start_id=str(grp[0]["sentence_id"]),
            sentence_end_id=str(grp[-1]["sentence_id"]),
            topic_signature="|".join(sorted(tags_union[:3])),
            topic_tags_union=tags_union,
            cohesion_score=cohesion,
            estimated_tokens=sum(int(x.get("token_estimate") or 0) for x in grp),
        )
        prep_store.bind_adjacency_group(sentence_ids=[g["sentence_id"] for g in grp], adjacency_group_id=gid)
        group_rows.append({"adjacency_group_id": gid, "sentences": grp, "topic_tags_union": tags_union, "cohesion_score": cohesion})
    prep_store.finish_processing_run(run_id=adj_run)

    split_run = prep_store.start_processing_run(component="split_planner", book_id=str(book["book_id"]), profile_id="topic_adjacency_v1", code_version="0.27.9", thresholds={"max_tokens_per_leaf": int(max_tokens_per_leaf), "min_sentences_per_leaf": int(min_sentences_per_leaf)})
    leaf_no = 0
    split_node_count = 0
    for grp in group_rows:
        root = _plan_sentence_range(grp["sentences"], max_tokens=int(max_tokens_per_leaf), chars_per_token=int(sentence_token_chars_per_token), paragraph_split_preference=bool(paragraph_split_preference), clause_split_enabled=bool(clause_split_enabled), clause_delimiters=list(clause_delimiters), split_depth=0)
        def persist(node: Dict[str, Any], parent_id: str | None = None) -> None:
            nonlocal leaf_no, split_node_count
            split_node_count += 1
            metrics = dict(node.get("chunk_quality_metrics") or {})
            metrics.setdefault("topic_tags_union", grp["topic_tags_union"])
            sid = prep_store.add_split_node(
                book_id=str(book["book_id"]),
                chapter_id=str(grp["sentences"][0].get("chapter_id") or "") or None,
                section_id=str(grp["sentences"][0].get("section_id") or "") or None,
                built_run_id=str(split_run),
                parent_split_node_id=parent_id,
                adjacency_group_id=str(grp["adjacency_group_id"]),
                sentence_start_id=str(node["sentence_start_id"]),
                sentence_end_id=str(node["sentence_end_id"]),
                char_start=int(node.get("char_start")) if node.get("char_start") is not None else None,
                char_end=int(node.get("char_end")) if node.get("char_end") is not None else None,
                estimated_tokens=int(node.get("estimated_tokens") or 0),
                split_strategy=str(node.get("split_strategy") or ""),
                split_reason=str(node.get("split_reason") or ""),
                boundary_mode=str(node.get("boundary_mode") or "sentence_span"),
                fragment_spec=dict(node.get("fragment_spec") or {}),
                split_depth=int(node.get("split_depth") or 0),
                leaf_sequence_no=None,
                is_leaf=False,
                chunk_quality_metrics=metrics,
            )
            if node.get("is_leaf"):
                leaf_no += 1
                # store a leaf row under this parent for ordering clarity
                prep_store.add_split_node(
                    book_id=str(book["book_id"]),
                    chapter_id=str(grp["sentences"][0].get("chapter_id") or "") or None,
                    section_id=str(grp["sentences"][0].get("section_id") or "") or None,
                    built_run_id=str(split_run),
                    parent_split_node_id=sid,
                    adjacency_group_id=str(grp["adjacency_group_id"]),
                    sentence_start_id=str(node["sentence_start_id"]),
                    sentence_end_id=str(node["sentence_end_id"]),
                    char_start=int(node.get("char_start")) if node.get("char_start") is not None else None,
                    char_end=int(node.get("char_end")) if node.get("char_end") is not None else None,
                    estimated_tokens=int(node.get("estimated_tokens") or 0),
                    split_strategy=str(node.get("split_strategy") or "leaf"),
                    split_reason=str(node.get("split_reason") or "leaf"),
                    boundary_mode=str(node.get("boundary_mode") or "sentence_span"),
                    fragment_spec=dict(node.get("fragment_spec") or {}),
                    split_depth=int(node.get("split_depth") or 0) + 1,
                    leaf_sequence_no=leaf_no,
                    is_leaf=True,
                    chunk_quality_metrics=metrics,
                )
                return
            for child in node.get("children", []) or []:
                persist(child, sid)
        persist(root)
    prep_store.finish_processing_run(run_id=split_run)
    prep_store.mark_book_status(book_id=str(book["book_id"]), status="completed")
    prep_store.complete_queue_entry(ingest_queue_entry_id=str(ingest_queue_entry_id), queue_status="completed")
    summary = prep_store.summarize_book(book_id=str(book["book_id"]))
    summary.update({
        "ok": True,
        "book_id": str(book["book_id"]),
        "ingest_queue_entry_id": str(ingest_queue_entry_id),
        "normalized_text_artifact_id": str(art["normalized_text_artifact_id"]),
        "leaf_nodes": len(prep_store.list_leaf_nodes(book_id=str(book["book_id"]))),
        "split_node_count": int(summary.get("counts", {}).get("split_nodes", 0)),
    })
    return summary



def load_prep_processing_config(contracts_root: str = "/var/lib/noemaforge/contracts") -> Dict[str, Any]:
    kpol = load_knowledge_policy(str(contracts_root))
    prep_store_pol = (kpol.get("prep_store") or {}) if isinstance(kpol.get("prep_store"), dict) else {}
    prep_proc = (kpol.get("prep_processing") or {}) if isinstance(kpol.get("prep_processing"), dict) else {}
    base_dir = str(kpol.get("base_dir") or "/var/lib/noemaforge/kg")
    return {
        "db_path": str(prep_store_pol.get("db_path") or f"{base_dir}/prep_index.sqlite"),
        "artifact_root": str(prep_store_pol.get("artifact_dir") or f"{base_dir}/prep_artifacts"),
        "normalization_version": str(prep_proc.get("normalization_version") or "norm-v1"),
        "sentence_token_chars_per_token": int(prep_proc.get("sentence_token_chars_per_token") or 4),
        "max_tokens_per_leaf": int(prep_proc.get("max_tokens_per_leaf") or 350),
        "target_tokens_per_leaf": int(prep_proc.get("target_tokens_per_leaf") or 220),
        "min_sentences_per_leaf": int(prep_proc.get("min_sentences_per_leaf") or 1),
        "paragraph_split_preference": bool(prep_proc.get("paragraph_split_preference", True)),
        "clause_split_enabled": bool(prep_proc.get("clause_split_enabled", True)),
        "clause_delimiters": list(prep_proc.get("clause_delimiters") or [",", ";", ":", "—", "–"]),
    }


__all__ = [
    "PrepStore",
    "analyze_book_path",
    "analyze_next_queue_entry",
    "analyze_queue_entry",
    "estimate_tokens",
    "label_sentence_topic",
    "load_prep_processing_config",
    "normalize_text",
]
