# AI OS Memory Architecture: Embeddings, Vector DBs, and Routing

## Core distinction

Embeddings are numerical representations of meaning. They turn text, images, or other objects into vectors where semantically similar objects are close together.

Vector databases are infrastructure for storing, indexing, filtering, and retrieving those vectors efficiently.

Therefore:

```text
Embeddings = meaning as geometry.
Vector DBs = scalable infrastructure for geometry.
AI OS memory = cognitive architecture built on top of retrieval, metadata, graph, events, and governance.
```

## When embeddings alone are enough

Use embeddings plus simple search for small, local, temporary, or experimental workloads:

- hundreds to tens of thousands of items;
- prototypes and offline analysis;
- working context and scratch memory;
- cases where brute force, NumPy, sklearn cosine similarity, or FAISS Flat is enough.

## When vector DBs become necessary

Use a vector DB when the system needs:

- millions of vectors;
- low-latency retrieval;
- persistence and concurrent users;
- metadata filtering;
- hybrid search;
- operational scaling.

Typical examples: enterprise RAG, agent memory, multimodal vaults, large document repositories, and code search.

## Vector search families

| Family | Method | Strength | Weakness | Best use |
|---|---|---|---|---|
| Flat / exact | Compare with every vector | Exact recall | Expensive at scale | Evaluation, tiny datasets |
| HNSW | Graph navigation | Fast, strong recall | RAM-heavy, update complexity | Local/personal memory, moderate vaults |
| IVF | Cluster partitions | Scalable, storage-efficient | Requires tuning, lower recall | Large vaults |
| PQ | Compressed vectors | Huge memory savings | Accuracy loss | Very large indexes |
| Hybrid | Vector + keyword/BM25 | Better precision, exact identifiers | More complex ranking | Enterprise docs, code, regulated search |

## NoemaForge memory layers

### Layer A — Working set

Purpose: current conversation, temporary reasoning, active context.

Recommended implementation: in-memory cache, brute force, FAISS Flat.

### Layer B — Personal memory

Purpose: preferences, decisions, user history, projects, long-term context.

Required metadata:

- `project_id`
- `confidentiality`
- `timestamp`
- `memory_type`
- `embedding_model_id`
- `chunking_version`
- `index_version`

Recommended implementation: local HNSW plus hybrid search.

### Layer C — Knowledge vault

Purpose: documents, PDFs, code, wiki, large corpora.

Recommended implementation: HNSW for moderate scale; IVF/PQ for massive scale; hybrid retrieval for exact references.

### Layer D — World model / observations

Purpose: logs, telemetry, events, calendar, external observations.

Vector search is insufficient here. This layer needs event stores, graph databases, time-series systems, OLAP/log systems, and lightweight vector retrieval.

## Retrieval flow

A single user query should not blindly search one memory. It should be routed:

```text
query
  → intent router
  → working memory
  → personal memory
  → knowledge vault
  → graph/events
  → reranker
  → synthesis
```

## Two-stage retrieval

1. Candidate generation: ANN retrieval with HNSW/IVF.
2. Precision stage: reranking by cross-encoder, LLM scorer, rules, or metadata policy.

This reduces semantic garbage while preserving scalability.

## Spine vs Brain

### Spine zone

Reliable, deterministic, local, offline-capable, versioned. Prefer slightly weaker but always working.

Recommended: stable local embeddings, local HNSW, strict versioning.

### Brain zone

Experimental, adaptive, agentic, externally integrated. Prefer safe experiments with rollback.

Recommended: managed vector DB experiments, new embeddings, dynamic retrieval, IVF/PQ experiments.

## Failure modes to avoid

- Treating vector search as causality or exact knowledge.
- Using one universal memory model.
- Changing embedding models without versioning.
- Ignoring metadata filters and access control.
- Skipping hybrid search for identifiers, code, and regulated documentation.
