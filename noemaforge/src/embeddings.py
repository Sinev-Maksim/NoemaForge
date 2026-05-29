#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/embeddings.py
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
# File: src/embeddings.py
# Purpose: Provide the module 'embeddings'.
# Invoked by / imported from:
#   - src/knowledge/embedding_worker.py
#   - src/memory_system.py
# Public API / entry functions:
#   - hash_embed
# Inputs:
#   - Imports: __future__, hashlib, re, typing
# Output formats / side effects:
#   - Returns Python values and/or performs in-memory orchestration.
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""embeddings.py (v0.17.0)

Deterministic, offline-first embedding helpers.

NoemaForge has two embedding worlds:
  1) "real" embeddings (LLM/SLM/tool-provided) — higher quality, higher cost.
  2) deterministic hashing embeddings — cheap, auditable, always available.

For the spine and early MVP, we rely on (2) for indexing and routing.

IMPORTANT:
Hash embeddings capture topical overlap, not logical agreement.
"""


import hashlib
import re
from typing import List


_token_re = re.compile(r"[\w\-]+", re.UNICODE)


# === NoemaForge Autodoc Function Header ===
# Function: hash_embed(text: str, dims: int)
# Purpose: Deterministic feature-hashing embedding.
# Inputs:
#   - text: str
#   - dims: int
# Called by:
#   - src/casebase.py
#   - src/knowledge/embedding_worker.py
#   - src/memory_system.py
# Calls:
#   - int, lower, sum, findall, hexdigest, sha256, encode
# Returns / emits: List[float]
# Key locals:
#   - dims, hi, hs, idx, norm, sign, t, tokens, vec
# === End NoemaForge Autodoc Function Header ===
def hash_embed(text: str, *, dims: int) -> List[float]:
    """Deterministic feature-hashing embedding.

    Returns an L2-normalized vector of length `dims`.
    """

    dims = int(dims)
    vec = [0.0] * dims
    if not text or dims <= 0:
        return vec

    tokens = [t.lower() for t in _token_re.findall(text.lower()) if t]
    if not tokens:
        return vec

    for t in tokens:
        hi = int(hashlib.sha256(("i:" + t).encode("utf-8")).hexdigest(), 16)
        idx = hi % dims
        hs = int(hashlib.sha256(("s:" + t).encode("utf-8")).hexdigest(), 16)
        sign = 1.0 if (hs % 2 == 0) else -1.0
        vec[idx] += sign

    norm = sum(x * x for x in vec) ** 0.5
    if norm > 0:
        vec = [x / norm for x in vec]
    return vec
