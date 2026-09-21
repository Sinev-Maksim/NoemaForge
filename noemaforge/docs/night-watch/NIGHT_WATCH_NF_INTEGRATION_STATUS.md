# Night Watch -> NoemaForge Integration Status

**As of:** 2026-09-21  
**Classification:** `UAT request findings resolution`  
**Branch:** `night-watch`

```text
ARCHITECTURE_IDENTITY=CODE_EVOLUTION_LANE
NIGHT_WATCH_ROLE=CODE_REPAIR_AND_QUALIFICATION_HARNESS
READONLY_ADAPTER=OBSERVATION_BOUNDARY
CODE_MUTATION=BOUNDED_AND_WORK_ITEM_SCOPED
MODEL_MUTATION=OUT_OF_SCOPE
MODEL_EVOLUTION_ARCHITECTURE=DEFERRED_SEPARATE_BRANCH
GLOBAL_NF_CONTROL_PLANE=NOEMAFORGE
CODE_INTEGRATION_BINDING=NOT_IMPLEMENTED
```

## Corrected architecture

Night Watch is the code-oriented execution/state-machine component of NoemaForge Evolution.

It is not:

- a parallel NF coordinator;
- a permanent shadow adviser beside another canonical code-evolution engine;
- the model-evolution subsystem.

The Evolution pipeline is now explicitly decomposed conceptually into:

```text
Evolution
1. code evolution -> Night Watch
2. model evolution -> design separately later
```

## Existing foundations

Already available:

- canonical `noemaforge.evolution-execution/v1` contracts;
- proven read-only Night Watch adapter;
- qualified Night Watch self-heal runner;
- exact-base/worktree isolation;
- bounded code mutation and rollback rules;
- deterministic/product aggregate gates;
- local reviewer separation;
- fault/regression/extrapolation qualification;
- exact-SHA evidence/handoff;
- external independent-review boundary.

## Next integration slice

Design/implement the **binding between canonical code Evolution work items and the Night Watch runner**, including:

1. code-vs-model lane discrimination;
2. stable NF work-item -> Night Watch run identity;
3. exact-base/workspace materialization;
4. bounded authority/scope transfer;
5. resumable Night Watch execution;
6. canonical progress/evidence projection back to NF;
7. restart/idempotency proof;
8. explicit rejection/defer of model-evolution work items.

The previously drafted standalone shadow-coordinator target is superseded.

## Deferred second Evolution part

Model mutation/evolution will be designed separately and is not required to complete Night Watch integration into the code-evolution lane.
