# Night Watch -> NoemaForge Integration Design Decisions

**Status:** architecture preparation  
**Classification:** `UAT request findings resolution`

## Decision 1 — NoemaForge owns the boundary

The integration component is NF-owned. Night Watch is never allowed to become a second production control plane.

Selected module shape for the first slice:

```text
noemaforge/src/evolution_adapters/night_watch_integration.py
noemaforge/configs/night-watch-integration-policy.json
noemaforge/tests/test_night_watch_integration.py
noemaforge/tools/uat/run-night-watch-integration-shadow.sh
noemaforge/docs/architecture/night-watch-nf-integration.md
```

The existing:

`noemaforge/src/evolution_adapters/night_watch_readonly.py`

remains the observation primitive and is not converted into a mutating adapter.

## Decision 2 — first slice supports only off/observe/shadow/proposal

Initial policy enum:

```text
off
observe
shadow
proposal
```

`bounded_execution` and `native` are documented future states but are intentionally not accepted by the first implementation.

If configuration requests an unsupported higher-authority state, validation fails closed.

## Decision 3 — canonical input is EvolutionWorkItem

The coordinator accepts an already validated `EvolutionWorkItem` using:

`apiVersion = noemaforge.evolution-execution/v1`

Night Watch-specific task structures are not accepted at the public boundary.

The coordinator must validate:

- work item ID;
- run ID;
- status;
- provenance;
- operator-approval requirement;
- ToolProxy requirement;
- allowed/forbidden actions.

## Decision 4 — canonical output is event/result evidence

The first slice returns:

- one or more `EvolutionEvent` documents;
- one `EvolutionAgentResult` document;
- adapter-local diagnostic metadata outside canonical objects.

It does not create a new canonical contract family.

Shadow disagreement is represented as a typed event/result diagnostic rather than silently overwriting the NF-native verdict.

## Decision 5 — deterministic integration identity

The integration result identity is derived from:

```text
integration policy version
+ canonical work item bytes
+ exact NF base/head
+ Night Watch source fingerprint
+ selected state-root identity
+ normalized shadow inputs
```

No wall-clock timestamp participates in deterministic comparison identity.

Timestamps may appear in execution/evidence metadata, but not in the stable comparison fingerprint.

## Decision 6 — single writer

In `observe` and `shadow`:

- repository writes = forbidden;
- Night Watch state writes = forbidden;
- production NF task writes = forbidden by the adapter;
- provider invocation = forbidden unless separately introduced by a later explicit lease design;
- GitHub mutation = forbidden.

In `proposal`:

- proposal/evidence may be written only to the NF-approved evidence/state root;
- repository application remains outside the adapter;
- GitHub mutation remains forbidden.

## Decision 7 — state/evidence layout

Recommended NF-owned external state layout:

```text
<NoemaForge data root>/
  evolution/
    night-watch/
      runs/
        <integration_run_id>/
          input/
          observation/
          shadow/
          proposal/
          evidence/
          terminal.json
```

The tree must not be inside:

- the source repository;
- the observed Night Watch state root;
- an immutable release tree.

All externalized paths in evidence are normalized; containment checks use native filesystem semantics.

## Decision 8 — disagreement contract

Shadow comparison reports:

```text
agreement
nf_only_finding
night_watch_only_finding
severity_mismatch
ownership_mismatch
evidence_gap
non_comparable
```

A disagreement is evidence, not authority.

Only these classes may become immediate blockers in shadow mode:

- integrity cannot be established;
- exact base mismatch;
- observed-state containment failure;
- evidence lineage corruption.

Ordinary semantic disagreement is recorded and the NF-native path remains authoritative.

## Decision 9 — private operator overlay is outside the repository

The public integration boundary may receive a boolean/private-overlay-presence marker or a local opaque reference if a future operator workflow requires it, but public code must never serialize private content.

Private overlay content:

- cannot add authority;
- cannot alter canonical contracts;
- cannot disable tests;
- cannot change release gates;
- cannot appear in GitHub/public evidence.

The first implementation slice does not need private content at runtime.

## Decision 10 — promotion evidence

Promotion from one mode to the next requires a machine-readable evidence package containing:

- exact policy SHA;
- exact source head;
- test result;
- before/after repository fingerprint;
- before/after observed-state fingerprint;
- deterministic replay result;
- disagreement corpus summary;
- no-secret-leak result;
- independent review result where applicable.

No configuration flip is accepted solely because documentation says a phase is ready.
