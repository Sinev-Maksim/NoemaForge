# Night Watch -> NoemaForge Seamless Integration Plan

**Status:** preparation / architecture candidate  
**Classification:** `UAT request findings resolution`  
**Development branch:** `night-watch`  
**Canonical NoemaForge execution contract:** `noemaforge.evolution-execution/v1`

## 1. Goal

Integrate the qualified Night Watch self-heal capabilities into NoemaForge without a flag day, without creating a second production control plane, and without weakening NoemaForge's existing approval, ToolProxy, review, evidence, or release boundaries.

The migration must preserve one external operator surface: **NoemaForge remains the system of record and authority boundary**. Night Watch is introduced behind canonical NF contracts and can be disabled or rolled back at every stage.

The required pattern is:

```text
NF request / trusted trigger
-> canonical EvolutionWorkItem
-> NF integration boundary
-> Night Watch capability (shadow/proposal/bounded execution)
-> canonical Evolution evidence/results
-> NF review/release gates
-> human authority
```

Night Watch MUST NOT become a parallel owner of:

- production task state;
- production GitHub merge/release authority;
- credentials;
- long-lived provider identity;
- canonical Evolution schemas;
- operator approval;
- production deployment.

## 2. Seamless-integration strategy: shadow -> proposal -> bounded execution -> native capability

The integration follows a strangler/canary migration while keeping **single-writer semantics**.

### Phase 0 — freeze the source capability

Prerequisites:

- exact Night Watch release identity is pinned;
- qualification evidence is preserved;
- current NF exact base is pinned;
- public integration docs contain no private/operator-only directives.

No code is imported from unrelated reference implementations. External/reference samples remain local-only and are treated as untrusted evidence.

### Phase 1 — read-only observation (already available)

Use `evolution_adapters/night_watch_readonly.py` as the first boundary.

Night Watch state is projected into canonical:

- `EvolutionRun`;
- `EvolutionWorkItem`;
- blocker/artifact observations.

Invariants:

- `mutating_operations=[]`;
- repeat import is byte-identical;
- observed state is unchanged;
- repository state is unchanged;
- untrusted Night Watch text never becomes an instruction;
- no lifecycle/Git/GitHub/provider/service action is exposed.

This phase establishes semantic mapping without execution coupling.

### Phase 2 — shadow qualification

Add an NF-owned `NightWatchShadowCoordinator` that accepts a canonical `EvolutionWorkItem` and creates an isolated, read-only/shadow Night Watch run against a disposable worktree/copy.

Both paths run:

```text
NF native validation path
Night Watch shadow validation path
```

but **only NF native state may mutate**.

The coordinator emits canonical `EvolutionEvent` / `EvolutionAgentResult` documents containing only normalized conclusions, evidence hashes and typed diagnostics.

Promotion criteria:

- same task identity;
- deterministic result identity;
- no repository/state mutation;
- no provider or heavy-resource invocation without an NF lease;
- disagreement is visible, never silently resolved;
- shadow failure cannot block the normal NF path unless it proves a hard integrity violation through an NF-recognized invariant.

### Phase 3 — proposal-only co-pilot

Night Watch may generate a candidate/proposal, but it cannot apply it.

The flow becomes:

```text
EvolutionWorkItem
-> isolated Night Watch analysis
-> proposal artifact
-> NF containment validation
-> NF-owned apply path (optional, separately authorized)
```

The proposal is translated into canonical `EvolutionMutationEvidence` with:

- exact base/head;
- changed-path set;
- patch SHA;
- task identity;
- producer identity;
- tests/evidence references;
- reference-source policy fields.

NF rejects proposals that:

- touch immutable tests/evidence;
- escape the allowed changed-path set;
- cannot bind to the exact base;
- contain unknown execution instructions instead of declarative patch/evidence;
- require hidden authority.

Night Watch still has no direct production writer role.

### Phase 4 — bounded executor in an isolated worktree

Only after Phase 3 parity is proven may NF grant a short-lived capability lease for mutation of one isolated candidate worktree.

Authority is explicitly bounded:

- one work item;
- one exact base;
- one allowed path set;
- one worktree;
- one provider role;
- one expiry;
- no merge/tag/release/deploy;
- immutable tests remain read-only;
- rollback identity is captured before mutation.

All writes go through the NF mutation/ToolProxy boundary. Night Watch cannot mint its own authority.

Any out-of-scope mutation triggers exact rollback and a typed control-plane failure. Rollback failure is a hard stop.

### Phase 5 — SSK2 repair pipeline under NF orchestration

Once bounded execution is stable, Night Watch's repair discipline becomes an NF orchestration policy rather than an external lifecycle owner.

Canonical cycle:

```text
finding
-> work item
-> minimal implementation
-> local deterministic check
-> scope-aware review
-> reproducer: base FAIL / candidate PASS / negative control
-> cost estimate
-> budget route
-> external/heavy gate when required
-> formal result
-> next iteration
```

The older "two control contours" remain explicit:

1. **formal/deterministic contour** — schemas, syntax, unit/regression tests, containment, hashes, static invariants;
2. **scenario/acceptance contour** — reproducer, negative control, real behavior, independent review, operator acceptance.

Review failure short-circuits expensive downstream work. Changes invalidate only the affected review scope.

### Phase 6 — native NF capability and standalone fallback

After sufficient parity, factor stable Night Watch semantics into NF-native modules/contracts.

The standalone Night Watch package remains only as:

- qualification oracle;
- recovery/fallback tool;
- target-host diagnostic harness;
- regression reference for migration.

At this point NF owns runtime state and lifecycle; Night Watch no longer needs to be a permanent parallel runtime.

## 3. Canonical contract mapping

Night Watch output must map into existing `noemaforge.evolution-execution/v1` objects rather than introduce a second schema family.

| Night Watch concept | NF canonical object |
|---|---|
| run/session | `EvolutionRun` |
| task/finding | `EvolutionWorkItem` |
| diagnostic/status transition | `EvolutionEvent` |
| model/provider request | `EvolutionAgentRequest` |
| provider result | `EvolutionAgentResult` |
| heavy model/GPU/provider exclusivity | `EvolutionResourceLease` |
| patch/candidate proof | `EvolutionMutationEvidence` |
| independent review | `EvolutionIndependentReviewEvidence` |
| qualification/manual gate | `EvolutionReleaseGateResult` |

No Night Watch-specific field is added to a canonical object unless the NF contract is deliberately versioned.

## 4. State ownership: single writer, dual observer

During migration there must never be two authoritative writers for the same state.

```text
Canonical task/run state       -> NF only
Production repository mutation -> NF-authorized path only
GitHub merge/release            -> NF/human gate only
Night Watch internal evidence   -> Night Watch local state
Cross-system mapping            -> immutable IDs + SHA-256 refs
```

Avoid dual-write synchronization. Prefer append-only evidence exchange and deterministic projection.

## 5. Integration boundary

Introduce an NF-owned boundary with three explicit modes:

```text
observe
shadow
propose
```

Later, only after approval and qualification:

```text
execute_bounded
```

The boundary owns:

- canonical input validation;
- exact-base binding;
- capability/lease validation;
- state-root selection;
- environment sanitization;
- timeout/resource bounds;
- output normalization;
- evidence hashing;
- mutation containment;
- rollback verification.

Night Watch owns its internal reasoning/repair loop but not NF authority.

## 6. Private operator context

The integration may support an **operator-private local instruction overlay**, but:

- it lives outside the repository;
- it is not required to understand production correctness;
- it cannot weaken safety, review, approval, evidence, or release gates;
- it is never copied into Git history, GitHub issues/PRs, normal handoff archives or telemetry;
- only the minimum role that needs the private context receives it;
- declassified outputs must stand on their own without the private material.

Production behavior must remain reproducible from public/canonical contracts plus explicit operator approvals.

## 7. Rollout switches

Every phase requires a reversible config state. Recommended states:

```text
off
observe
shadow
proposal
bounded_execution
native
```

Transitions are monotonic only after qualification evidence. Rollback to a safer state is always allowed.

No automatic transition to `bounded_execution` or `native`.

## 8. Acceptance gates per phase

Each phase must prove:

- exact-base identity;
- canonical contract validation;
- deterministic replay/idempotence where applicable;
- zero unexpected changed paths;
- no hidden Git/GitHub/provider/service side effects;
- immutable test/evidence preservation;
- bounded process/runtime behavior;
- explicit resource lease for heavy work;
- structured typed failure ownership;
- evidence completeness;
- rollback/recovery;
- independent review when acceptance authority is claimed.

## 9. First implementation slice

The first code slice after this design should be deliberately small:

1. add a canonical integration policy/config with modes `off|observe|shadow|proposal`;
2. add an NF-owned coordinator wrapping the existing read-only adapter;
3. accept one `EvolutionWorkItem`;
4. emit normalized `EvolutionEvent` + `EvolutionAgentResult`;
5. prove zero-write and byte-idempotent replay;
6. add disagreement/evidence reporting;
7. do **not** enable mutation in this slice.

Only after this slice passes may proposal transport be introduced.

## 10. Non-goals of the first integration release

Not included initially:

- direct merge/release/deploy;
- automatic policy activation;
- autonomous production GitHub writes;
- secret/private instruction persistence;
- replacement of NF canonical contracts;
- copying a foreign/reference runtime into NF;
- multiple simultaneous heavy LLM workers;
- hidden provider execution;
- changing immutable tests to satisfy the integration.

