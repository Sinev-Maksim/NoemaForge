# Evolution execution contracts

Status: initial contract-first slice for `0.33.0`  
Classification: **UAT request findings resolution**

## Purpose

These contracts let NoemaForge own the lifecycle, audit trail, policy decisions,
evidence, and user-visible state of code evolution while the current prod-ready
loop remains a provisional execution adapter.

This slice does not launch models, mutate Git state, write to GitHub, operate
services, or enable multiprocessing. It only defines the canonical documents
that later adapters and the `self_development` pipeline must exchange.

## Ownership boundary

NoemaForge owns:

- run and work-item identity;
- state transitions and idempotency keys;
- persona and skill selection;
- approval and risk decisions;
- resource leases;
- artifact registration;
- mutation, review, and release-gate evidence;
- pause, resume, cancel, and final disposition.

An execution adapter may:

- observe an external runner;
- execute one explicitly approved operation;
- return immutable artifacts and measured usage;
- report blockers and provider/infrastructure failures.

An adapter must not silently change canonical state, expand its ToolProxy
capabilities, create manual evidence, or claim a different exact HEAD.

## Contracts

| Contract | Responsibility |
|---|---|
| `evolution_run.schema.json` | Mission-level lifecycle and provenance |
| `evolution_work_item.schema.json` | Bounded unit of work, scope, risk, skills, attempts |
| `evolution_event.schema.json` | Append-only, idempotent lifecycle observation |
| `agent_execution_request.schema.json` | Persona/skill/provider request with budgets and capabilities |
| `agent_execution_result.schema.json` | Immutable result, usage, failure classification |
| `resource_lease.schema.json` | Shared/exclusive resource ownership for future workers |
| `mutation_evidence.schema.json` | Exact-head mutation, tests, rollback, clean-room provenance |
| `review_evidence.schema.json` | Independent, non-stale review of one exact HEAD |
| `release_gate_result.schema.json` | Automated/manual release decision with evidence |

## Initial state model

```text
planned
  -> awaiting_approval
  -> ready
  -> running
  -> completed

Alternative controlled states:
blocked | paused | failed | cancelled | quarantined
```

The runtime implementation must later enforce allowed transitions
transactionally. The schema deliberately validates document shape rather than
pretending to provide transactional guarantees.

## Attempt accounting

Provider or infrastructure failures are distinct from semantic failures.

- `semantic_attempts_used` counts attempts where the proposed solution itself
  was evaluated and failed.
- `provider_attempts_used` records provider invocations, including rate limits
  and infrastructure failures.
- `AgentExecutionResult.failure.semantic_attempt_consumed` makes the decision
  explicit and auditable.

A provider reset or transient worker failure must not silently consume the
semantic retry budget.

## Review and exact-head rules

- mutation evidence identifies both `base_head` and `candidate_head`;
- review evidence is valid for exactly one `reviewed_head`;
- `reviewer_independent` must be true;
- stale review evidence is rejected;
- any later mutation invalidates prior review evidence at runtime;
- a manual release gate cannot pass without a real manual marker.

## Local reference boundary

External repositories, source excerpts, Design Canvas runtime, and experimental
reference adapters remain in the Local Reference Lab only.

Mutation evidence must state:

- classification is `UAT request findings resolution`;
- reference material is `none` or `local-only`;
- external source code was not imported;
- reference runtime was not shipped.

These fields are contract assertions and must later be backed by repository and
packaging gates.

## Next slices

1. Populate the Evolution Skill Registry from the current loop.
2. Add a read-only adapter that imports current-loop state and artifacts.
3. Add approved start/pause/resume/cancel operations through ToolProxy.
4. Bind the adapter to `self_development`.
5. Add the Admin GUI Evolution projection.
6. Introduce the recoverable controller/worker resource broker in `0.33.1`.
7. Reuse the execution plane for idempotent benchmarking in `0.33.2`.
