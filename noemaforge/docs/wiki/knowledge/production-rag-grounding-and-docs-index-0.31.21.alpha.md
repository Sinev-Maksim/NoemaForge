# Production RAG, grounding and documentation index

> **Status: historical snapshot (0.31.21.alpha era).** Kept as release-evidence history; it is not maintained. For the current state start at the [wiki hub](../WIKI.md).

Version scope: runtime `0.32.1`, documentation reconciliation `0.32.1-docs-integrated`.  
Updated: 2026-05-18T20:33:59Z

## Why this matters

Admin chat and usecase help should not rely only on canned responses. For project questions, Admin should retrieve and cite local NoemaForge documentation.

## Required RAG layers

1. Document engineering: chunking, section titles, source paths and version metadata.
2. Hybrid retrieval: keyword + embedding where available.
3. Reranking: local reranker if available, otherwise deterministic heuristic rerank.
4. Grounded answer generation with source paths.
5. RAG eval: retrieval hit rate, citation coverage, groundedness and helpfulness.

Executable RAG eval seed:

- `noemaforge/configs/rag-eval-suite.json` defines the first docs/wiki RAG eval cases.
- `noemaforge/configs/docs-rag-policy.json` defines the first local docs/wiki/context RAG policy.
- `noemaforge/src/docs_rag_runtime.py` builds a local Markdown index, retrieves docs, applies deterministic lexical reranking and emits extractive answers with citations.
- `production_ai_contracts.evaluate_rag_eval_cases(...)` computes retrieval hit rate, citation coverage, groundedness and answer helpfulness.
- `production_ai_contracts.rag_eval_report_to_gate_evidence(...)` converts the report into EvaluationGate-compatible checks.
- `noemaforge/contracts/docs_rag_policy.schema.json` defines the docs RAG policy shape.
- `noemaforge/contracts/rag_eval_suite.schema.json` defines the eval-pack shape.

## Executable docs RAG seed

The first production RAG runtime slice is deliberately local-first and deterministic. It does not require network access, embeddings, model downloads or an external vector database. That makes it safe for prelaunch gates and for archive rebuild validation.

Runtime behavior:

1. Indexes approved documentation sources from `docs/wiki/**`, `docs/architecture/**`, `docs/backlog/**`, `docs/quality/**`, `TODO.md` and `context.md`.
2. Extracts Markdown titles, section headings, token counts and bounded text bodies.
3. Scores candidates by token overlap, exact phrase matches and title/path boosts.
4. Reranks deterministically by score and source path.
5. Builds extractive grounded answers with numbered citations.
6. Emits a `knowledge_gap_notice` instead of inventing an answer when no local source matches.

CLI smoke command:

```bash
python noemaforge/src/docs_rag_runtime.py --root . --query "What does optimize model for Dev Team mean?" --top-k 3
```

Promotion path:

- Use `docs-rag-policy.json` as the retriever/reranker policy ref in the Unified Registry.
- Use `rag-eval-suite.json` plus `evaluate_rag_eval_cases(...)` to block promotion when retrieval, citations, groundedness or helpfulness regress.
- Keep future embedding and GraphRAG work behind the same EvaluationGate instead of replacing this baseline silently.

## GraphRAG experiment pack

GraphRAG is now represented as an experiment pack, not as the default retrieval
path:

- `noemaforge/configs/graphrag-experiment-pack.json`
- `noemaforge/contracts/graphrag_experiment_pack.schema.json`
- `noemaforge/src/graphrag_experiment_runtime.py`
- `noemaforge/tests/test_graphrag_experiment_runtime.py`

The seed pack uses a small local concept/source/control graph to check
multi-hop paths around classic RAG, EvaluationGate and release evidence. It
also converts its answers into the existing RAG eval contract, so GraphRAG
experiments must keep retrieval hit rate, citation coverage, groundedness and
helpfulness at least as strong as the classic baseline before promotion.

CLI smoke command:

```bash
python noemaforge/src/graphrag_experiment_runtime.py --project-root . --summary
```

The pack remains `disabled`/draft-local in the Unified Registry until a real
corpus graph, release evidence and rollback plan are reviewed.

## First target corpus

- `docs/wiki/**`
- `docs/architecture/**`
- `docs/backlog/**`
- `docs/quality/**`
- `TODO.md`
- `context.md`
- `noemaforge/configs/**` summaries
- file headers for public runtime modules

## Acceptance criteria

- “What does optimize model for Dev Team mean?” returns a grounded answer with local source references.
- Usecase explanations do not launch pipelines.
- RAG index version is recorded in the Unified Registry.
- RAG eval reports can block promotion when retrieval, citation, grounding or helpfulness thresholds are not met.
- GraphRAG experiments remain gated by classic RAG metrics plus graph path and multi-hop coverage.
