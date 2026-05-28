#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/knowledge/embedding_worker.py
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
from __future__ import annotations


# === NoemaForge Autodoc File Header ===
# File: src/knowledge/embedding_worker.py
# Purpose: Implement the knowledge subsystem module 'embedding_worker'.
# Invoked by / imported from:
#   - src/knowledge_maintainer.py
# Public API / entry functions:
#   - load_embeddings_policy
#   - embed_passages
#   - embed_claims
#   - embed_concepts
# Inputs:
#   - Common path inputs: /var/lib/noemaforge/vstore
#   - Imports: __future__, os, time, json, typing, toolvault, embeddings, vstore
# Output formats / side effects:
#   - YAML files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""knowledge.embedding_worker (v0.17.0)

CPU-friendly embedding/indexing worker for the hypergraph.

This worker is intentionally boring:
  - loads embeddings-policy.yaml (epoch contract)
  - uses hashing embeddings by default (offline)
  - writes to VStore append-only segments
  - versioning key: (provider.model_id + chunking_version)

It can be run as part of the Knowledge Maintainer stream.
"""


import os
import time
import json
from typing import Any, Dict, Iterable, List, Optional, Tuple

from toolvault import load_yaml

from embeddings import hash_embed
from vstore import VStore, VStoreConfig

from .store import KnowledgeStore


# === NoemaForge Autodoc Function Header ===
# Function: _nowz()
# Purpose: Implement the routine ' nowz'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - src/audit_remediation.py
#   - src/noemaforge_core.py
#   - src/bundles.py
#   - src/caps.py
#   - src/casebase.py
#   - src/coordinator_fanout.py
#   - src/dream_cycle.py
#   - src/fixture_bundle.py
# Calls:
#   - strftime, gmtime
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _nowz() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# === NoemaForge Autodoc Function Header ===
# Function: load_embeddings_policy(epoch_dir: str)
# Purpose: Implement the routine 'load embeddings policy'.
# Inputs:
#   - epoch_dir: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - join, load_yaml, str, exists
# Returns / emits: Dict[str, Any]
# Key locals:
#   - p
# === End NoemaForge Autodoc Function Header ===
def load_embeddings_policy(epoch_dir: str) -> Dict[str, Any]:
    p = os.path.join(str(epoch_dir), "embeddings-policy.yaml")
    if not os.path.exists(p):
        return {"enabled": False}
    return load_yaml(p)


# === NoemaForge Autodoc Function Header ===
# Function: _vstore_cfg_from_epoch(epoch_dir: str)
# Purpose: Implement the routine ' vstore cfg from epoch'.
# Inputs:
#   - epoch_dir: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - join, str, int, VStoreConfig, exists, load_yaml, get
# Returns / emits: VStoreConfig
# Key locals:
#   - _, backend, base_dir, cfg, max_items, metric, p
# === End NoemaForge Autodoc Function Header ===
def _vstore_cfg_from_epoch(epoch_dir: str) -> VStoreConfig:
    p = os.path.join(str(epoch_dir), "vstore.yaml")
    cfg = load_yaml(p) if os.path.exists(p) else {}
    base_dir = str(cfg.get("base_dir") or "/var/lib/noemaforge/vstore")
    max_items = int(cfg.get("max_items_per_segment") or 50000)
    backend = str(cfg.get("backend") or "flat")
    metric = str(cfg.get("metric") or "cosine")
    # metric kept for future; currently VStore uses cosine.
    _ = metric
    return VStoreConfig(base_dir=base_dir, max_items_per_segment=max_items, backend=backend)


# === NoemaForge Autodoc Function Header ===
# Function: _provider(pol: Dict[str, Any], provider_id: str)
# Purpose: Implement the routine ' provider'.
# Inputs:
#   - pol: Dict[str, Any]
#   - provider_id: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - get, isinstance
# Returns / emits: Dict[str, Any]
# Key locals:
#   - ps
# === End NoemaForge Autodoc Function Header ===
def _provider(pol: Dict[str, Any], provider_id: str) -> Dict[str, Any]:
    ps = pol.get("providers") or {}
    return ps.get(provider_id) if isinstance(ps, dict) else {}


# === NoemaForge Autodoc Function Header ===
# Function: _layer(pol: Dict[str, Any], layer_id: str)
# Purpose: Implement the routine ' layer'.
# Inputs:
#   - pol: Dict[str, Any]
#   - layer_id: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - get, isinstance
# Returns / emits: Dict[str, Any]
# Key locals:
#   - ls
# === End NoemaForge Autodoc Function Header ===
def _layer(pol: Dict[str, Any], layer_id: str) -> Dict[str, Any]:
    ls = pol.get("layers") or {}
    return ls.get(layer_id) if isinstance(ls, dict) else {}


# === NoemaForge Autodoc Function Header ===
# Function: embed_passages(epoch_dir: str, store: KnowledgeStore, layer_id: str = 'kg_passages', limit: int = 500, stream_id: str = 'knowledge.vault', project_id: str = '')
# Purpose: Embed KG passages into VStore.
# Inputs:
#   - epoch_dir: str
#   - store: KnowledgeStore
#   - layer_id: str = 'kg_passages'
#   - limit: int = 500
#   - stream_id: str = 'knowledge.vault'
#   - project_id: str = ''
# Called by:
#   - src/knowledge_maintainer.py
# Calls:
#   - load_embeddings_policy, _layer, strip, _provider, int, _vstore_cfg_from_epoch, VStore, iter_passages, bool, str, entry_exists, append
# Returns / emits: Dict[str, Any]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - added, chunk_ver, dims, entry_id, errors, items, kind, lay, meta, model_id, p, pid
# === End NoemaForge Autodoc Function Header ===
def embed_passages(
    *,
    epoch_dir: str,
    store: KnowledgeStore,
    layer_id: str = "kg_passages",
    limit: int = 500,
    stream_id: str = "knowledge.vault",
    project_id: str = "",
) -> Dict[str, Any]:
    """Embed KG passages into VStore.

    Returns a report dict.
    """

    pol = load_embeddings_policy(epoch_dir)
    if not bool(pol.get("enabled", False)):
        return {"ok": False, "reason": "embeddings_disabled"}

    lay = _layer(pol, layer_id)
    if not lay:
        return {"ok": False, "reason": "missing_layer", "layer": layer_id}

    provider_id = str(lay.get("provider") or "").strip()
    prov = _provider(pol, provider_id)
    if not prov:
        return {"ok": False, "reason": "missing_provider", "provider": provider_id}

    kind = str(prov.get("kind") or "hashing").strip()
    model_id = str(prov.get("model_id") or "hash384-v1").strip()
    dims = int(prov.get("dims") or 384)
    chunk_ver = str(lay.get("chunking_version") or "").strip() or "kg_passage_v1"

    vstore_layer = str(lay.get("vstore_layer") or layer_id).strip()
    vcfg = _vstore_cfg_from_epoch(epoch_dir)
    vs = VStore(vstore_layer, cfg=vcfg)

    added = 0
    skipped = 0
    errors = 0

    items: List[Dict[str, Any]] = []
    for p in store.iter_passages(limit=int(limit)):
        pid = str(p.get("passage_id") or "")
        txt = str(p.get("text") or "")
        if not pid or not txt:
            skipped += 1
            continue

        entry_id = f"kg:passage:{pid}:{model_id}:{chunk_ver}"
        if vs.entry_exists(entry_id):
            skipped += 1
            continue

        try:
            if kind == "hashing":
                vec = hash_embed(txt, dims=dims)
            else:
                # unknown provider kind
                errors += 1
                continue
        except Exception:
            errors += 1
            continue

        meta = {
            "object_kind": "passage",
            "object_id": pid,
            "source_id": str(p.get("source_id") or ""),
            "realm": str(p.get("realm_override") or ""),
            "model_id": model_id,
            "chunking_version": chunk_ver,
            "created_at": _nowz(),
        }
        items.append(
            {
                "entry_id": entry_id,
                "vector": vec,
                "model_id": model_id,
                "dims": dims,
                "stream_id": stream_id,
                "project_id": project_id,
                "kind": str(lay.get("item_kind") or "kg.passage"),
                "meta": meta,
            }
        )

        if len(items) >= 64:
            rep = vs.upsert_many(items)
            if rep.get("ok"):
                added += int(rep.get("added") or 0)
            else:
                errors += len(items)
            items = []

    if items:
        rep = vs.upsert_many(items)
        if rep.get("ok"):
            added += int(rep.get("added") or 0)
        else:
            errors += len(items)

    return {
        "ok": True,
        "layer": layer_id,
        "vstore_layer": vstore_layer,
        "provider": provider_id,
        "model_id": model_id,
        "dims": dims,
        "chunking_version": chunk_ver,
        "added": added,
        "skipped": skipped,
        "errors": errors,
    }


# === NoemaForge Autodoc Function Header ===
# Function: embed_claims(epoch_dir: str, store: KnowledgeStore, layer_id: str = 'kg_claims', limit: int = 500, stream_id: str = 'knowledge.vault', project_id: str = '')
# Purpose: Embed KG claims into VStore.
# Inputs:
#   - epoch_dir: str
#   - store: KnowledgeStore
#   - layer_id: str = 'kg_claims'
#   - limit: int = 500
#   - stream_id: str = 'knowledge.vault'
#   - project_id: str = ''
# Called by:
#   - src/knowledge_maintainer.py
# Calls:
#   - load_embeddings_policy, _layer, strip, _provider, int, _vstore_cfg_from_epoch, VStore, iter_claims, bool, str, entry_exists, append
# Returns / emits: Dict[str, Any]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - added, c, chunk_ver, cid, dims, entry_id, errors, items, kind, lay, meta, model_id
# === End NoemaForge Autodoc Function Header ===
def embed_claims(
    *,
    epoch_dir: str,
    store: KnowledgeStore,
    layer_id: str = "kg_claims",
    limit: int = 500,
    stream_id: str = "knowledge.vault",
    project_id: str = "",
) -> Dict[str, Any]:
    """Embed KG claims into VStore."""

    pol = load_embeddings_policy(epoch_dir)
    if not bool(pol.get("enabled", False)):
        return {"ok": False, "reason": "embeddings_disabled"}

    lay = _layer(pol, layer_id)
    if not lay:
        return {"ok": False, "reason": "missing_layer", "layer": layer_id}

    provider_id = str(lay.get("provider") or "").strip()
    prov = _provider(pol, provider_id)
    if not prov:
        return {"ok": False, "reason": "missing_provider", "provider": provider_id}

    kind = str(prov.get("kind") or "hashing").strip()
    model_id = str(prov.get("model_id") or "hash384-v1").strip()
    dims = int(prov.get("dims") or 384)
    chunk_ver = str(lay.get("chunking_version") or "").strip() or "kg_claim_v1"

    vstore_layer = str(lay.get("vstore_layer") or layer_id).strip()
    vcfg = _vstore_cfg_from_epoch(epoch_dir)
    vs = VStore(vstore_layer, cfg=vcfg)

    added = 0
    skipped = 0
    errors = 0

    items: List[Dict[str, Any]] = []
    for c in store.iter_claims(limit=int(limit)):
        cid = str(c.get("claim_id") or "")
        txt = str(c.get("text_normalized") or "")
        if not cid or not txt.strip():
            skipped += 1
            continue

        entry_id = f"kg:claim:{cid}:{model_id}:{chunk_ver}"
        if vs.entry_exists(entry_id):
            skipped += 1
            continue

        try:
            if kind == "hashing":
                vec = hash_embed(txt, dims=dims)
            else:
                errors += 1
                continue
        except Exception:
            errors += 1
            continue

        meta = {
            "object_kind": "claim",
            "object_id": cid,
            "status": str(c.get("status") or ""),
            "confidence": float(c.get("confidence") or 0.0),
            "model_id": model_id,
            "chunking_version": chunk_ver,
            "created_at": _nowz(),
        }
        items.append(
            {
                "entry_id": entry_id,
                "vector": vec,
                "model_id": model_id,
                "dims": dims,
                "stream_id": stream_id,
                "project_id": project_id,
                "kind": str(lay.get("item_kind") or "kg.claim"),
                "meta": meta,
            }
        )

        if len(items) >= 64:
            rep = vs.upsert_many(items)
            if rep.get("ok"):
                added += int(rep.get("added") or 0)
            else:
                errors += len(items)
            items = []

    if items:
        rep = vs.upsert_many(items)
        if rep.get("ok"):
            added += int(rep.get("added") or 0)
        else:
            errors += len(items)

    return {
        "ok": True,
        "layer": layer_id,
        "vstore_layer": vstore_layer,
        "provider": provider_id,
        "model_id": model_id,
        "dims": dims,
        "chunking_version": chunk_ver,
        "added": added,
        "skipped": skipped,
        "errors": errors,
    }


# === NoemaForge Autodoc Function Header ===
# Function: embed_concepts(epoch_dir: str, store: KnowledgeStore, layer_id: str = 'kg_concepts', limit: int = 500, stream_id: str = 'knowledge.vault', project_id: str = '')
# Purpose: Embed KG concepts into VStore.
# Inputs:
#   - epoch_dir: str
#   - store: KnowledgeStore
#   - layer_id: str = 'kg_concepts'
#   - limit: int = 500
#   - stream_id: str = 'knowledge.vault'
#   - project_id: str = ''
# Called by:
#   - src/knowledge_maintainer.py
# Calls:
#   - load_embeddings_policy, _layer, strip, _provider, int, _vstore_cfg_from_epoch, VStore, iter_concepts, bool, str, join, entry_exists
# Returns / emits: Dict[str, Any]
# Key locals:
#   - added, c, chunk_ver, cid, dims, entry_id, errors, items, kind, labels, labels_list, lay
# === End NoemaForge Autodoc Function Header ===
def embed_concepts(
    *,
    epoch_dir: str,
    store: KnowledgeStore,
    layer_id: str = "kg_concepts",
    limit: int = 500,
    stream_id: str = "knowledge.vault",
    project_id: str = "",
) -> Dict[str, Any]:
    """Embed KG concepts into VStore."""

    pol = load_embeddings_policy(epoch_dir)
    if not bool(pol.get("enabled", False)):
        return {"ok": False, "reason": "embeddings_disabled"}

    lay = _layer(pol, layer_id)
    if not lay:
        return {"ok": False, "reason": "missing_layer", "layer": layer_id}

    provider_id = str(lay.get("provider") or "").strip()
    prov = _provider(pol, provider_id)
    if not prov:
        return {"ok": False, "reason": "missing_provider", "provider": provider_id}

    kind = str(prov.get("kind") or "hashing").strip()
    model_id = str(prov.get("model_id") or "hash384-v1").strip()
    dims = int(prov.get("dims") or 384)
    chunk_ver = str(lay.get("chunking_version") or "").strip() or "kg_concept_v1"

    vstore_layer = str(lay.get("vstore_layer") or layer_id).strip()
    vcfg = _vstore_cfg_from_epoch(epoch_dir)
    vs = VStore(vstore_layer, cfg=vcfg)

    added = 0
    skipped = 0
    errors = 0

    items: List[Dict[str, Any]] = []
    for c in store.iter_concepts(limit=int(limit)):
        cid = str(c.get("concept_id") or "")
        if not cid:
            skipped += 1
            continue

        # Build a stable text surface: labels + realm hints.
        try:
            labels = json.loads(str(c.get("labels_json") or "[]"))
        except Exception:
            labels = []
        labels_list = [str(x).strip() for x in (labels if isinstance(labels, list) else []) if str(x).strip()]
        txt = " | ".join(labels_list)
        if not txt.strip():
            skipped += 1
            continue

        entry_id = f"kg:concept:{cid}:{model_id}:{chunk_ver}"
        if vs.entry_exists(entry_id):
            skipped += 1
            continue

        try:
            if kind == "hashing":
                vec = hash_embed(txt, dims=dims)
            else:
                errors += 1
                continue
        except Exception:
            errors += 1
            continue

        meta = {
            "object_kind": "concept",
            "object_id": cid,
            "labels": labels_list[:16],
            "model_id": model_id,
            "chunking_version": chunk_ver,
            "created_at": _nowz(),
        }
        items.append(
            {
                "entry_id": entry_id,
                "vector": vec,
                "model_id": model_id,
                "dims": dims,
                "stream_id": stream_id,
                "project_id": project_id,
                "kind": str(lay.get("item_kind") or "kg.concept"),
                "meta": meta,
            }
        )

        if len(items) >= 64:
            rep = vs.upsert_many(items)
            if rep.get("ok"):
                added += int(rep.get("added") or 0)
            else:
                errors += len(items)
            items = []

    if items:
        rep = vs.upsert_many(items)
        if rep.get("ok"):
            added += int(rep.get("added") or 0)
        else:
            errors += len(items)

    return {
        "ok": True,
        "layer": layer_id,
        "vstore_layer": vstore_layer,
        "provider": provider_id,
        "model_id": model_id,
        "dims": dims,
        "chunking_version": chunk_ver,
        "added": added,
        "skipped": skipped,
        "errors": errors,
    }
