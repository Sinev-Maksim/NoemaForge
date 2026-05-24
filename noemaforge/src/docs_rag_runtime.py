#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/docs_rag_runtime.py
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Build and query a deterministic local docs/wiki RAG index with citations.
Inputs: Local Markdown/TODO/context files under a NoemaForge project root.
Outputs: JSON-compatible index, search and grounded-answer artifacts.
Side effects: None unless run as a CLI, which writes JSON to stdout.
Tests: noemaforge/tests/test_docs_rag_runtime.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


API_VERSION = "noemaforge.docs-rag/v1"
INDEX_KIND = "DocsRAGIndex"
SEARCH_KIND = "DocsRAGSearchResult"
ANSWER_KIND = "DocsRAGAnswer"
INDEX_VERSION = "docs-rag-v1"

DEFAULT_INCLUDE_GLOBS = [
    "docs/wiki/**/*.md",
    "docs/architecture/**/*.md",
    "docs/backlog/**/*.md",
    "docs/quality/**/*.md",
    "TODO.md",
    "context.md",
]

DEFAULT_MAX_CHARS_PER_DOC = 12000
DEFAULT_TOP_K = 5
DEFAULT_MAX_CITATIONS = 4

TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_\-']*|[а-яё0-9][а-яё0-9_\-']*", re.IGNORECASE)
HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*$")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n{2,}")

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "do",
    "does",
    "for",
    "from",
    "how",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "the",
    "to",
    "what",
    "with",
    "и",
    "в",
    "во",
    "для",
    "как",
    "на",
    "о",
    "по",
    "что",
}


def _nowz() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _normalize_text(value: Any) -> str:
    return unicodedata.normalize("NFKC", str(value or "")).lower()


def _tokens(value: Any) -> List[str]:
    text = _normalize_text(value)
    return [token for token in TOKEN_RE.findall(text) if token and token not in STOPWORDS]


def _relative_source_ref(path: Path, root: Path) -> str:
    resolved_root = root.resolve()
    try:
        rel = path.resolve().relative_to(resolved_root)
    except ValueError:
        rel = path.relative_to(root)
    return rel.as_posix()


def _iter_doc_paths(root: Path, include_globs: Sequence[str]) -> Iterable[Path]:
    seen = set()
    for pattern in include_globs:
        for path in root.glob(pattern):
            if not path.is_file():
                continue
            if path.suffix.lower() not in {".md", ".txt"}:
                continue
            ref = _relative_source_ref(path, root)
            if ref in seen:
                continue
            seen.add(ref)
            yield path


def _extract_title(path: Path, text: str) -> str:
    for line in text.splitlines():
        match = HEADING_RE.match(line)
        if match:
            return match.group(1).strip()
    return path.stem.replace("-", " ").replace("_", " ").strip().title()


def _extract_sections(text: str) -> List[str]:
    sections: List[str] = []
    for line in text.splitlines():
        match = HEADING_RE.match(line)
        if match:
            sections.append(match.group(1).strip())
    return sections


def _squash(value: str) -> str:
    return " ".join(str(value or "").split())


def _trim(value: str, limit: int) -> str:
    text = _squash(value)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def build_docs_index(
    root: Path | str,
    include_globs: Optional[Sequence[str]] = None,
    *,
    max_chars_per_doc: int = DEFAULT_MAX_CHARS_PER_DOC,
) -> Dict[str, Any]:
    """Return a deterministic JSON-compatible index over local documentation."""

    root_path = Path(root).resolve()
    globs = list(include_globs or DEFAULT_INCLUDE_GLOBS)
    docs: List[Dict[str, Any]] = []

    for path in sorted(_iter_doc_paths(root_path, globs), key=lambda item: _relative_source_ref(item, root_path)):
        raw = path.read_text(encoding="utf-8", errors="replace")
        text = raw[: max(0, int(max_chars_per_doc))]
        if not text.strip():
            continue
        token_list = _tokens(text)
        docs.append(
            {
                "source_ref": _relative_source_ref(path, root_path),
                "title": _extract_title(path, text),
                "text": text,
                "token_count": len(token_list),
                "section_count": len(_extract_sections(text)),
                "sections": _extract_sections(text)[:20],
            }
        )

    return {
        "apiVersion": API_VERSION,
        "kind": INDEX_KIND,
        "id": "docs-wiki-context",
        "index_version": INDEX_VERSION,
        "created_at": _nowz(),
        "root": str(root_path),
        "include_globs": globs,
        "max_chars_per_doc": int(max_chars_per_doc),
        "stats": {
            "documents": len(docs),
            "tokens": sum(int(doc.get("token_count") or 0) for doc in docs),
        },
        "docs": docs,
    }


def _query_phrases(tokens: Sequence[str]) -> List[str]:
    phrases: List[str] = []
    for size in (3, 2):
        for start in range(0, max(0, len(tokens) - size + 1)):
            phrases.append(" ".join(tokens[start : start + size]))
    return phrases


def _doc_score(doc: Dict[str, Any], query: str, query_tokens: Sequence[str]) -> float:
    doc_text = _normalize_text(doc.get("text") or "")
    title = _normalize_text(doc.get("title") or "")
    source_ref = _normalize_text(doc.get("source_ref") or "")
    doc_tokens = Counter(_tokens(doc_text))
    q_counts = Counter(query_tokens)

    score = 0.0
    for token, count in q_counts.items():
        if token in doc_tokens:
            score += min(float(doc_tokens[token]), 4.0) * min(float(count), 2.0)
        if token in title:
            score += 3.0
        if token in source_ref:
            score += 2.0

    normalized_query = _squash(_normalize_text(query))
    if normalized_query and normalized_query in doc_text:
        score += 10.0
    if normalized_query and normalized_query in title:
        score += 8.0

    for phrase in _query_phrases(query_tokens):
        if phrase and phrase in doc_text:
            score += 2.0
        if phrase and phrase in title:
            score += 3.0

    return round(score, 4)


def _best_sentences(doc: Dict[str, Any], query_tokens: Sequence[str], *, limit: int = 2) -> List[str]:
    text = str(doc.get("text") or "")
    raw_parts = [part.strip() for part in SENTENCE_SPLIT_RE.split(text) if part.strip()]
    if not raw_parts:
        raw_parts = [line.strip() for line in text.splitlines() if line.strip()]

    q = set(query_tokens)
    ranked: List[Tuple[float, int, str]] = []
    for index, sentence in enumerate(raw_parts):
        sentence_tokens = _tokens(sentence)
        if not sentence_tokens:
            continue
        overlap = len(q.intersection(sentence_tokens))
        heading_bonus = 1.5 if sentence.lstrip().startswith("#") else 0.0
        ranked.append((float(overlap) + heading_bonus, index, sentence))

    ranked.sort(key=lambda item: (-item[0], item[1]))
    selected = [sentence for score, _, sentence in ranked if score > 0][:limit]
    if selected:
        return [_trim(sentence.lstrip("# ").strip(), 260) for sentence in selected]
    return [_trim(raw_parts[0].lstrip("# ").strip(), 260)] if raw_parts else []


def _preview(doc: Dict[str, Any], query_tokens: Sequence[str]) -> str:
    return " ".join(_best_sentences(doc, query_tokens, limit=2))


def search_docs(index: Dict[str, Any], query: str, *, top_k: int = DEFAULT_TOP_K) -> Dict[str, Any]:
    """Search the docs index with deterministic lexical retrieval and reranking."""

    query_text = str(query or "").strip()
    query_tokens = _tokens(query_text)
    rows: List[Dict[str, Any]] = []

    for doc in index.get("docs") or []:
        if not isinstance(doc, dict):
            continue
        score = _doc_score(doc, query_text, query_tokens)
        if score <= 0.0:
            continue
        rows.append(
            {
                "source_ref": str(doc.get("source_ref") or ""),
                "title": str(doc.get("title") or ""),
                "score": score,
                "preview": _preview(doc, query_tokens),
            }
        )

    rows.sort(key=lambda item: (-float(item["score"]), item["source_ref"]))
    return {
        "apiVersion": API_VERSION,
        "kind": SEARCH_KIND,
        "ok": bool(rows),
        "query": query_text,
        "index_version": str(index.get("index_version") or INDEX_VERSION),
        "results": rows[: max(0, int(top_k))],
    }


def answer_docs_question(
    index: Dict[str, Any],
    query: str,
    *,
    top_k: int = DEFAULT_TOP_K,
    max_citations: int = DEFAULT_MAX_CITATIONS,
) -> Dict[str, Any]:
    """Return a grounded local-docs answer with citations, or a knowledge-gap notice."""

    search = search_docs(index, query, top_k=top_k)
    results = list(search.get("results") or [])
    cited = results[: max(0, int(max_citations))]
    if not cited:
        return {
            "apiVersion": API_VERSION,
            "kind": ANSWER_KIND,
            "ok": False,
            "mode": "knowledge_gap_notice",
            "grounded": False,
            "query": str(query or "").strip(),
            "answer": "No local documentation source matched this question strongly enough.",
            "index_version": str(index.get("index_version") or INDEX_VERSION),
            "retrieved_refs": [],
            "citations": [],
            "search": search,
        }

    fragments = []
    for offset, row in enumerate(cited, start=1):
        preview = _trim(str(row.get("preview") or ""), 320)
        fragments.append(f"{preview} [{offset}]")
    citations = [
        {
            "source_ref": str(row.get("source_ref") or ""),
            "title": str(row.get("title") or ""),
            "score": float(row.get("score") or 0.0),
        }
        for row in cited
    ]
    return {
        "apiVersion": API_VERSION,
        "kind": ANSWER_KIND,
        "ok": True,
        "mode": "docs_rag_answer",
        "grounded": True,
        "query": str(query or "").strip(),
        "answer": " ".join(fragments),
        "index_version": str(index.get("index_version") or INDEX_VERSION),
        "retrieved_refs": [str(row.get("source_ref") or "") for row in results],
        "citations": citations,
        "search": search,
    }


def answer_result_to_rag_eval_result(answer_result: Dict[str, Any], *, case_id: str) -> Dict[str, Any]:
    """Adapt a docs RAG answer artifact to production_ai_contracts RAG eval input."""

    return {
        "case_id": str(case_id or ""),
        "retrieved_refs": list(answer_result.get("retrieved_refs") or []),
        "citations": list(answer_result.get("citations") or []),
        "grounded": bool(answer_result.get("grounded")),
        "answer": str(answer_result.get("answer") or ""),
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build and query the local NoemaForge docs RAG index.")
    parser.add_argument("--root", default=".", help="Project root to index.")
    parser.add_argument("--query", default="", help="Question to answer from local docs.")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K, help="Number of retrieved docs.")
    parser.add_argument("--max-citations", type=int, default=DEFAULT_MAX_CITATIONS, help="Maximum citations in answer mode.")
    parser.add_argument("--max-chars-per-doc", type=int, default=DEFAULT_MAX_CHARS_PER_DOC, help="Per-document character cap.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    index = build_docs_index(args.root, max_chars_per_doc=args.max_chars_per_doc)
    if args.query:
        payload = answer_docs_question(index, args.query, top_k=args.top_k, max_citations=args.max_citations)
    else:
        payload = {
            "apiVersion": API_VERSION,
            "kind": "DocsRAGIndexSummary",
            "index_version": index["index_version"],
            "root": index["root"],
            "include_globs": index["include_globs"],
            "stats": index["stats"],
        }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
