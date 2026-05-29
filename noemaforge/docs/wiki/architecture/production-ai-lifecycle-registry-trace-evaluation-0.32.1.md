# Production AI lifecycle: registry, trace and evaluation — 0.32.1

Version scope: runtime `0.32.1`, docs overlay `0.32.1-docs-integrated`.
Updated: 2026-05-29T00:00:00Z

## Purpose

Stub wiki page for the 0.32.1 production AI lifecycle, registry and trace evaluation integration.
See `production-ai-lifecycle-registry-trace-evaluation-0.31.21.alpha.md` for the predecessor content.

This page is referenced by `configs/graphrag-experiment-pack.json` as an offline ref anchor.
The canonical runtime contract is in `src/graphrag_experiment_runtime.py`.

## Lifecycle overview

```text
Idea / task
  -> contract (eval-pack entry in unified-registry.json)
  -> registry entry (kind: eval-pack, status: shadow/stable)
  -> baseline evaluation (EvaluationGate, ReleaseEvidence)
  -> rollout (shadow -> stable) with rollback plan
```

## Registry trace

Each eval-pack entry carries a `registry_key = f"{kind}:{id}:{version}"` and is referenced
by `eval_pack_refs` in pipeline and model entries.  Trace IDs link Admin chat, GUI jobs,
pipeline runs, model selection and tool calls to their originating eval-pack decision.

## Status

This page closes the open `docs/wiki/architecture/production-ai-lifecycle-registry-trace-evaluation-0.32.1.md`
ref required by `graphrag-experiment-pack-core`.
Detailed content lives in the 0.31.21.alpha predecessor and the live contracts.
