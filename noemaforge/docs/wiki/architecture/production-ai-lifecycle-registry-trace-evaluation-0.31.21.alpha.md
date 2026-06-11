# Production AI lifecycle integration for NoemaForge

> **Status: historical snapshot (0.31.21.alpha era).** Kept as release-evidence history; it is not maintained. For the current state start at the [wiki hub](../WIKI.md).

Version scope: runtime `0.32.1`, documentation reconciliation `0.32.1-docs-integrated`.  
Updated: 2026-05-18T20:33:59Z

## Purpose

This page integrates the production AI system patterns from the latest research packet into NoemaForge without treating them as isolated feature requests. The guiding lifecycle is:

```text
Idea / task
  -> contract
  -> registry entry
  -> baseline
  -> evaluation gate
  -> plan artifact
  -> safe rollout
  -> telemetry
  -> SR/SSR review
  -> promotion or rollback
  -> data-centric error loop
```

## P0 patterns now promoted into architecture

1. **Unified Registry** for model, prompt, retriever, reranker, tool-policy, pipeline, persona, task, epoch and eval-pack versions.
2. **Trace-first observability** with `trace_id` spanning Admin chat, jobs, pipelines, model selection, tools and artifacts.
3. **EvaluationGate** as the required quality boundary before promotion of code, prompt, model, RAG, pipeline, router or epoch changes.
4. **Intent Router Eval Pack** for deterministic Admin routing cases with per-route and per-abstention-action pass rates.
5. **Safe Rollout** for epoch/prompt/route changes: offline eval -> shadow -> canary -> promote -> rollback.
6. **Calibration and abstention** for ambiguous or high-risk intent: route, clarify, defer to Admin/SR/SSR, or block.
7. **Data-centric error loop**: every failure becomes an error class, regression case, task and evidence artifact.

## Executable Unified Registry validation

The registry is now checked as an executable local contract, not only as a seed JSON file. `noemaforge/src/unified_registry_runtime.py` validates:

- all required registry kinds are represented;
- every `refs` path resolves inside the local archive;
- every `eval_pack_refs` value points to an existing eval-pack registry entry;
- active stable refs can be listed for release evidence and audit cards.

CLI smoke command:

```bash
python noemaforge/src/unified_registry_runtime.py --project-root . --summary
```

## How is Admin intent routing evaluated?

Admin intent routing is evaluated by the Intent Router Eval Pack: each route fixture checks the selected route, interpreted intent and abstention action. The promotion gate requires overall pass rate, per-route metrics and per-abstention-action metrics so a route can improve without hiding a clarification, defer or block regression.

## P1 patterns

- Production RAG for docs/wiki/context with hybrid retrieval, reranking, citation coverage and groundedness eval.
- Model, Prompt, Pipeline, Epoch and Tool cards for release evidence.
- Trajectory-level agent evaluation for Dev Team, Model Evolution and SmartHome decisions.

## P2 patterns

- GraphRAG experiments after classic RAG is stable.
- MCP/A2A adapter governance as zero-trust extension boundaries, not autonomous execution rights.
- PEFT/LoRA lab readiness after registry/eval/rollback gates mature; training and production weight mutation remain disabled in the prelaunch archive.

## NoemaForge-specific invariant

All patterns preserve the current runtime safety invariant: one active heavy local LLM by default, explicit GPU policy, no hidden display-manager stop, and no privileged GUI action without an auditable job/request boundary.
