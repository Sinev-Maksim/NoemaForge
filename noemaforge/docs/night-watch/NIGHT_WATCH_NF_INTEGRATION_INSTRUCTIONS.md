# Night Watch / NoemaForge Code-Evolution Integration Instructions

**Status:** canonical public engineering instructions  
**Classification:** `UAT request findings resolution`

## 1. Core identity

Treat Night Watch as **the code-evolution execution/repair/qualification component of the NoemaForge Evolution pipeline**.

Do not design it as:

- a parallel top-level coordinator;
- a permanent shadow sidecar to another code-evolution implementation;
- a model-evolution engine.

Model mutation/evolution is a separate future Evolution branch.

## 2. Canonical routing rule

```text
Evolution work item
-> classify lane

code/repository repair or qualification
-> Night Watch

model mutation/evolution
-> NOT Night Watch
-> future separately designed branch
```

If lane classification is ambiguous, do not silently execute.

## 3. SSK2 work protocol

Use:

```text
Meaning
-> Specification
-> Code
-> Control contour 1: deterministic/formal
-> Control contour 2: scenario/acceptance
```

For each finding:

```text
finding
-> stable work-item identity
-> ownership/plane classification
-> diagnostic/scout
-> smallest safe implementation
-> candidate materialization
-> deterministic aggregate checks
-> scope-aware logically separate review
-> reproducer: base FAIL / candidate PASS
-> negative control
-> extrapolation / neighboring regressions
-> qualification evidence
-> checkpoint
```

## 4. Code-mutation authority

Night Watch may mutate **code** only when the canonical code Evolution work item grants a bounded mutation scope.

Before untrusted mutation:

- persist exact pre-attempt candidate/patch identity;
- bind exact base;
- define allowed paths;
- define immutable paths/tests/contracts;
- define rollback target.

After mutation:

- enforce changed-path containment;
- reject immutable-test/evidence edits;
- aggregate safe sibling checks;
- restore exact prior state after rejected/out-of-scope attempts;
- verify rollback SHA.

Rollback failure is a hard integrity stop.

## 5. Model-mutation exclusion

Night Watch MUST NOT:

- mutate model weights;
- fine-tune/train models;
- define model-evolution acceptance semantics;
- silently reinterpret model-selection work as code repair;
- acquire model-mutation authority through a generic provider/tool capability.

Generic model/provider calls used to reason about or implement code are not "model evolution". The excluded branch is mutation/evolution **of the models themselves**.

## 6. NF/Night Watch ownership boundary

NF owns:

- canonical Evolution work item;
- global Controller state;
- Event Store/projection semantics;
- persona/Skill semantics;
- global resource authorization;
- production approval;
- merge/release/deploy authority.

Night Watch owns for code work items:

- repair state machine;
- diagnosis;
- bounded code mutation;
- deterministic validation;
- local review orchestration;
- reproducer/fault/regression work;
- candidate qualification;
- evidence and exact-SHA handoff;
- durable resumable execution checkpoints.

## 7. Read-only adapter

Keep `night_watch_readonly.py` read-only.

It is an observation/projection/recovery tool and must not become the mutation entry point.

Code mutation belongs to the Night Watch code-evolution execution path under an explicit work-item capability.

## 8. Review and acceptance

Same-provider/local co-check is useful but not independent acceptance.

Required trust progression:

```text
Night Watch candidate
-> deterministic gates
-> local logically separate reviewer
-> sealed exact-SHA evidence
-> independent remote review / CI
-> human/release authority
```

Implementer cannot accept its own candidate.

## 9. SUCCESS_FIRST_MAX_EVIDENCE

Recover/degrade/continue on recoverable independent failures.

Fail closed only when integrity/safety/evidence validity is lost, including:

- exact rollback cannot be established;
- mutation scope is untrusted;
- exact base unavailable after bounded recovery;
- evidence lineage corrupt;
- immutable tests would have to be weakened;
- separation of duties cannot be preserved.

## 10. Resource behavior

Night Watch may request/use provider/resource leases for code-evolution work through NF policy.

It does not become the global Resource Broker.

Multiple logical roles may execute sequentially against shared typed context and durable checkpoints even when only one heavy LLM lease is active.

## 11. Repository durability

All useful non-secret intermediate code-evolution work is checkpointed to `night-watch`.

Incomplete checkpoints use:

`unstable, saved for context`

If understanding/rules/status changed, update canonical Markdown in the same iteration.

## 12. Private-context boundary

Private/operator-only directives remain outside GitHub.

They may inform research/design, but cannot:

- add authority;
- weaken tests/review/safety;
- become required to understand production correctness;
- leak into normal evidence/handoffs.

## 13. Current implementation instruction

Do not implement the previously proposed permanent `NightWatchShadowCoordinator` architecture.

Instead design the NF binding that dispatches **code Evolution work items into the Night Watch state machine** and projects Night Watch results/evidence back into canonical Evolution state.

Explicitly reject/defer model-evolution work items until the separate model-mutation architecture exists.
