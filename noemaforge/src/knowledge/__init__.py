"""
=== NoemaForge File Header ===
File: noemaforge/src/knowledge/__init__.py
Zone: release/package
Version: 0.32.1
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


# === NoemaForge Autodoc File Header ===
# File: src/knowledge/__init__.py
# Purpose: Implement the knowledge subsystem module '__init__'.
# Invoked by / imported from:
#   - No inbound Python import detected; treat as library leaf or direct entrypoint.
# Inputs:
#   - Imports: policy, store, retrieval
# Output formats / side effects:
#   - Returns Python values and/or performs in-memory orchestration.
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""NoemaForge Knowledge Hypergraph (Stage D).

This package provides an offline-first canonical store (SQLite) for the
hypergraph knowledge base described in our design discussions, plus optional
vector indexing via VStore.

Important: this is infrastructure code. It is not a UI.
"""

from .error_learning import ErrorLearningStore


def _unavailable(name, exc):
    def _raise(*args, **kwargs):
        raise RuntimeError(f"knowledge export unavailable:{name}:{exc}") from exc
    return _raise


try:
    from .policy import load_knowledge_policy
except Exception as exc:  # pragma: no cover
    load_knowledge_policy = _unavailable("load_knowledge_policy", exc)

try:
    from .store import KnowledgeStore
except Exception as exc:  # pragma: no cover
    KnowledgeStore = _unavailable("KnowledgeStore", exc)

try:
    from .retrieval import search_keyword, search_semantic
except Exception as exc:  # pragma: no cover
    search_keyword = _unavailable("search_keyword", exc)
    search_semantic = _unavailable("search_semantic", exc)

try:
    from .prep_store import PrepStore
except Exception as exc:  # pragma: no cover
    PrepStore = _unavailable("PrepStore", exc)

try:
    from .prep_pipeline import analyze_book_path, analyze_next_queue_entry, load_prep_processing_config
except Exception as exc:  # pragma: no cover
    analyze_book_path = _unavailable("analyze_book_path", exc)
    analyze_next_queue_entry = _unavailable("analyze_next_queue_entry", exc)
    load_prep_processing_config = _unavailable("load_prep_processing_config", exc)

try:
    from .extraction_pipeline import extract_book, extract_next_book, load_extraction_config
except Exception as exc:  # pragma: no cover
    extract_book = _unavailable("extract_book", exc)
    extract_next_book = _unavailable("extract_next_book", exc)
    load_extraction_config = _unavailable("load_extraction_config", exc)

try:
    from .grounded_administrator import answer_query as grounded_answer_query
except Exception as exc:  # pragma: no cover
    grounded_answer_query = _unavailable("grounded_answer_query", exc)

try:
    from .synthetic_book import write_synthetic_book
except Exception as exc:  # pragma: no cover
    write_synthetic_book = _unavailable("write_synthetic_book", exc)

try:
    from .eval_runtime import evaluate_extraction_against_gold, evaluate_grounded_queries
except Exception as exc:  # pragma: no cover
    evaluate_extraction_against_gold = _unavailable("evaluate_extraction_against_gold", exc)
    evaluate_grounded_queries = _unavailable("evaluate_grounded_queries", exc)

__all__ = [
    "load_knowledge_policy",
    "KnowledgeStore",
    "search_keyword",
    "search_semantic",
    "PrepStore",
    "analyze_book_path",
    "analyze_next_queue_entry",
    "load_prep_processing_config",
    "extract_book",
    "extract_next_book",
    "load_extraction_config",
    "grounded_answer_query",
    "ErrorLearningStore",
    "write_synthetic_book",
    "evaluate_extraction_against_gold",
    "evaluate_grounded_queries",
]
