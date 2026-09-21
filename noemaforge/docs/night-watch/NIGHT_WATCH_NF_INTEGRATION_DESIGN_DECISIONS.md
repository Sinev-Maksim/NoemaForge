# Night Watch -> NoemaForge Integration Design Decisions

**Status:** architecture corrected  
**Classification:** `UAT request findings resolution`

## Decision 1 — Night Watch is the code-evolution lane

Night Watch is not a sidecar to the code Evolution pipeline. It **is the code-evolution repair/qualification component** used by that pipeline.

```text
NoemaForge Evolution
├── code evolution  -> Night Watch
└── model evolution -> separate future design
```

## Decision 2 — model mutation is out of Night Watch scope

Night Watch has no model-mutation authority.

The future model-evolution branch must be designed separately. It may reuse generic NF contracts/infrastructure only after those semantics are explicitly defined.

## Decision 3 — NoemaForge owns global semantics

NF owns canonical work-item state, Controller/Event Store semantics, persona/Skill semantics, resource authorization and promotion authority.

Night Watch owns the internal state machine needed to execute one bounded **code** work item and emit candidate/evidence.

## Decision 4 — preserve the read-only adapter

`noemaforge/src/evolution_adapters/night_watch_readonly.py` stays read-only.

It remains useful for:

- observation;
- recovery;
- external inspection;
- UAT;
- zero-write projection.

It is not the production mutation path.

## Decision 5 — no permanent competing code-evolution implementation

Do not build:

`NF native code evolution + Night Watch shadow implementation`

as the target architecture.

Temporary shadow/comparison runs may be used for migration/UAT, but canonical code-work-item ownership must be singular.

## Decision 6 — canonical input/output

Input: canonical code `EvolutionWorkItem`.

Execution: Night Watch internal code-evolution state machine.

Output/projected state: canonical Evolution events/results/mutation evidence/review evidence/gate results as applicable.

If required semantics are missing, change/version the NF contract deliberately rather than inventing a Night Watch-local standard.

## Decision 7 — mutation boundary

Night Watch may perform bounded **code/repository mutation** in an isolated worktree when explicitly authorized by the code work item.

It may not merge, release, deploy to production, or mutate models.

## Decision 8 — target trust chain

```text
canonical code work item
-> Night Watch candidate
-> deterministic aggregate gates
-> local logically separate review
-> reproducer / regression / fault qualification
-> sealed exact-SHA evidence
-> remote independent review / CI
-> human/release authority
```

## Decision 9 — resource boundary

Night Watch consumes NF-granted provider/resource capability for code work.

It does not own global resource arbitration.

One-heavy-worker constraints can be satisfied through sequential persona/provider turns with durable typed context.

## Decision 10 — private context remains orthogonal

Private research/operator directives may improve design/research but do not alter the public code-evolution authority model and never grant model-mutation authority.
