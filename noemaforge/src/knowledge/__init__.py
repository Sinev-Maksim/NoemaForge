"""
=== NoemaForge File Header ===
File: noemaforge/src/knowledge/__init__.py
Zone: release/package
Version: 0.31.13.alpha
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

from .policy import load_knowledge_policy
from .store import KnowledgeStore
from .retrieval import search_keyword, search_semantic
from .prep_store import PrepStore
from .prep_pipeline import analyze_book_path, analyze_next_queue_entry, load_prep_processing_config
from .extraction_pipeline import extract_book, extract_next_book, load_extraction_config
from .grounded_administrator import answer_query as grounded_answer_query
from .error_learning import ErrorLearningStore
from .synthetic_book import write_synthetic_book
from .eval_runtime import evaluate_extraction_against_gold, evaluate_grounded_queries

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
