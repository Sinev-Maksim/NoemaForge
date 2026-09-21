# Night Watch -> NoemaForge Integration Plan

**Status:** architecture corrected / preparation  
**Classification:** `UAT request findings resolution`  
**Development branch:** `night-watch`  
**Canonical execution contract:** `noemaforge.evolution-execution/v1`

## 1. Architectural identity

**Night Watch is the code-evolution part of the NoemaForge Evolution pipeline.**

It is not a separate top-level NF subsystem, not a parallel coordinator, and not merely a shadow observer.

The target decomposition is:

```text
NoemaForge Evolution
├── Code evolution
│   └── Night Watch
│       ├── diagnose code/repository findings
│       ├── bounded code repair
│       ├── deterministic validation
│       ├── regression/fault testing
│       ├── implementer/reviewer orchestration
│       ├── candidate qualification
│       ├── evidence / exact-SHA handoff
│       └── preparation for independent acceptance
│
└── Model evolution / model mutation
    └── SEPARATE SECOND PART
        └── architecture to be designed separately
```

The model-mutation branch is intentionally outside the Night Watch design. Night Watch must not silently acquire model-mutation semantics while the second Evolution branch is still undefined.

## 2. Position inside NF

NoemaForge remains the higher-level system:

```text
persona intent
-> skill / execution plan
-> NF Controller / canonical Evolution work item
-> Evolution lane selection
   -> CODE task  => Night Watch
   -> MODEL task => future model-evolution branch
-> ToolProxy / capability / resource boundary
-> isolated execution workspace
-> artifacts + evidence
-> NF canonical state / Event Store projection
-> independent external gates
-> human/release authority
```

Night Watch therefore owns the **code candidate repair/qualification lifecycle inside one bounded Evolution work item**.

It does not own global NF lifecycle, Event Store, resource arbitration, persona semantics, Skill semantics, production approval, merge authority or release GO.

## 3. Historical read-only adapter

The existing `evolution_adapters/night_watch_readonly.py` is a proven trust/projection boundary, not the final integration architecture.

Its role remains valuable:

- inspect Night Watch state without mutation;
- project observations into `noemaforge.evolution-execution/v1`;
- prove zero-write/idempotent import;
- support diagnostics, UAT, recovery and external inspection.

But the production code-evolution lane is **not** defined as:

`NF native evolution + Night Watch shadow sidecar`.

Instead:

`Night Watch is the code-evolution harness/state machine used by the Evolution pipeline for code work items.`

## 4. Canonical code-evolution flow

For a code finding/work item:

```text
EvolutionWorkItem(kind=code)
-> Night Watch code-evolution state machine
-> classify finding / ownership plane
-> diagnostic/scout
-> implementer
-> candidate materialization
-> deterministic aggregate gates
-> local logically separate reviewer
-> reproduce root cause
   base FAIL
   candidate PASS
   negative control
-> root-cause extrapolation / regression synthesis
-> candidate qualification
-> exact-SHA evidence
-> independent remote review / CI
-> NF/human release boundary
```

Night Watch is allowed to perform bounded repository mutation inside the isolated code-evolution workspace when the canonical work item grants that authority.

The read-only paths remain genuinely read-only. Mutation is a distinct typed mode with scope, rollback and evidence.

## 5. Code-evolution responsibilities

Night Watch owns within the code lane:

- code/repository observation and diagnosis;
- typed product/control-plane classification;
- exact-base isolated worktree creation;
- scoped code mutation;
- immutable-test protection;
- implementer/fallback provider routing;
- logically separate local review;
- deterministic gates;
- reproducer and negative control;
- fault/regression testing;
- SUCCESS_FIRST_MAX_EVIDENCE behavior;
- stagnation/progress accounting;
- rollback after untrusted mutation;
- candidate qualification;
- evidence packaging;
- exact-SHA handoff;
- resumable/durable checkpoints.

## 6. Explicit non-responsibilities

Night Watch does not own:

- model mutation;
- model-training/fine-tuning/evolution semantics;
- global NF orchestration;
- Event Store semantics;
- global task scheduling;
- global Resource Broker policy;
- persona or Skill semantics;
- production credentials;
- production/GCP mutation authority;
- GitHub merge authority;
- final release GO.

The future model-evolution branch may share generic NF contracts and infrastructure, but must be designed independently rather than inferred from Night Watch.

## 7. Contract boundary

NoemaForge owns canonical semantics. Night Watch implements the code-evolution behavior behind them.

Principle:

```text
core contract owns semantics
Night Watch implements the code-evolution lane
```

Use existing `noemaforge.evolution-execution/v1` objects where they fit:

- `EvolutionRun`;
- `EvolutionWorkItem`;
- `EvolutionEvent`;
- `EvolutionAgentRequest`;
- `EvolutionAgentResult`;
- `EvolutionResourceLease`;
- `EvolutionMutationEvidence`;
- `EvolutionIndependentReviewEvidence`;
- `EvolutionReleaseGateResult`.

If code evolution needs new cross-system semantics, version/extend the NF contract deliberately. Do not make a Night Watch-local field a de facto NF standard.

## 8. Integration method

Integration is therefore not a strangler migration from "NF code evolution" to "Night Watch".

The correct method is:

1. preserve the proven read-only adapter as an observation/debug boundary;
2. bind canonical code `EvolutionWorkItem` creation to Night Watch execution;
3. move Night Watch run/attempt/result state into canonical NF projections/events without losing its internal resumable state;
4. route code implementation/review personas/providers through NF capability/resource rules;
5. return qualified candidate/evidence to the NF Evolution controller;
6. keep external independent review and human promotion outside Night Watch;
7. leave model evolution untouched until its separate architecture is designed.

## 9. State ownership

```text
Canonical Evolution work item / global state -> NF
Code-evolution execution state              -> Night Watch, projected to NF
Candidate repository/worktree               -> bounded Night Watch execution scope
Evidence/history                            -> Night Watch emits, NF records/projects
Global resource authority                   -> NF
Merge/release/deploy authority              -> external NF/human boundary
Model-evolution state                       -> future separate branch
```

Night Watch may keep rich local execution state needed for resumability, but ZIP/log/local files are not the global canonical state of NoemaForge.

## 10. First implementation target

The first real NF integration slice should connect **one canonical code Evolution work item to the existing qualified Night Watch runner**, rather than create a second shadow coordinator.

Required behavior:

1. accept/identify a code-evolution `EvolutionWorkItem`;
2. materialize exact base in an isolated workspace;
3. create/bind a Night Watch run identity;
4. execute Night Watch in the authority mode granted by that work item;
5. project state transitions/evidence back into canonical Evolution events/results;
6. preserve exact candidate/evidence hashes;
7. prove restart/resume idempotence;
8. prove unrelated NF state is unchanged;
9. keep merge/release/deploy outside the harness;
10. explicitly reject model-mutation work items as unsupported by Night Watch.

## 11. Separate future branch: model evolution

Model mutation/evolution is the **second part of the Evolution pipeline**.

For now:

```text
MODEL_EVOLUTION_ARCHITECTURE=DEFERRED
NIGHT_WATCH_MODEL_MUTATION_AUTHORITY=NONE
```

Do not infer its state machine, safety gates, mutation semantics, resource policy or acceptance criteria from the code-evolution harness. Those will be designed separately.
