# NoemaForge consolidated MVP kernel and shell roadmap

> **Status: historical snapshot (0.31.13.alpha-patched1 era).** Kept as release-evidence history; it is not maintained. For the current state start at the [wiki hub](../WIKI.md).

Status: candidate roadmap/backlog material for future versions.  
Release package: `0.32.1`.  
Runtime impact: none for this package; this document does not add hard dependencies or install-time requirements.

## Executive synthesis

NoemaForge is converging toward an **agent operating environment** rather than a chatbot product. The near-term public path should therefore center on a narrow, stable kernel and safe contribution surfaces, not on shipping the full idea backlog at once.

The stable kernel direction is:

- four default roles in the base install: `Admin`, `Surgeon`, `Scary`, `Evolver/Darwin`;
- optional roles as inactive `RolePack`s, not active core roles;
- one active heavy worker NN now, with future growth toward three worker slots;
- Admin and Scary as logically always-on lightweight supervisors, not permanently resident heavy models;
- crash-safe sleep/wake transactions for every worker role switch;
- shell-first visual interface through `NoemaShell Lite`;
- guarded Evolve lab with quarantine and promotion gates;
- metadata-first HFBridge;
- quarantine-first `git_exchange` for community packs.

## Decision ledger

| Topic | Consolidated position |
|---|---|
| Default roles | Keep exactly four in the base install: Admin, Surgeon, Scary, Evolver/Darwin |
| Optional roles | Install as inactive role packs, not active core |
| Worker NN policy | One active worker NN now; grow to three later |
| Always-on roles | Admin and Scary stay logically always-on as lightweight supervisory layers |
| Visual layer | Primary shell mode and desktop alternative, not cosmetic UI |
| Community extension | Add `git_exchange` early, but quarantine-first |
| Role sequence artifact | Standardize as `RoleFlow` / `orchestration_graph` |
| Evolve boundary | Mutation only in lab; promotion only through Scary -> Surgeon -> Admin |

## Runtime kernel implications

Current practical invariant:

```text
only one heavy worker NN active at a time
```

Therefore every role switch must act as a durable transaction:

```text
flush state -> persist deltas -> record baton/context -> unload/sleep -> wake/load next role -> resume
```

Admin and Scary should stay present as policies, deterministic checks, persisted state, and optionally small-model assistance. They should not consume the single heavy worker slot unless explicitly invoked.

## Role boundary for Evolve

The safe improvement loop is:

```text
Admin -> Surgeon -> Scary -> Evolver/Darwin -> Surgeon -> Scary -> Admin -> SR/SSR observation
```

Responsibilities:

- `Admin`: rights owner and final approver.
- `Surgeon`: frames experiments, captures baselines, validates candidate evidence, drafts promotion dossiers.
- `Scary`: hidden gates, sandbox constraints, risk intervention, promotion veto.
- `Evolver/Darwin`: mutational executor inside the lab only.
- `SR/SSR`: value/cost observation and governance signals; not direct mutation.

Invariant:

```text
No mutation or model promotion may bypass Scary -> Surgeon -> Admin.
```

## NoemaShell Lite target

NoemaShell Lite is the product shell for the public MVP/MWP path. It should expose:

- session launch;
- active role and worker slot status;
- persona/role switching;
- approvals and interrupts;
- artifact cards;
- daemon/resource budget profiles;
- safe mode and recovery entry;
- model-selection and epoch-change confirmations.

Platform direction:

| Platform | MVP direction |
|---|---|
| Linux | First-class shell/resource-saving mode with reversible service profiles |
| Windows | Fullscreen primary app mode by default; true shell mode only on supported editions later |
| macOS | Login-primary app mode with launchd-managed helpers; no Finder replacement in MVP |

Safe daemon rule:

```text
Use whitelisted, reversible service profiles. Do not perform destructive daemon surgery.
```

## Contribution units

Community and optional extensions should be packaged as:

| Pack | Purpose |
|---|---|
| `RolePack` | Role definition, prompt profile, tools, permissions, critic pairing |
| `RoleFlow` | Role order, branching, guards, batons, approvals, rollback edges |
| `KnowledgeGraphPack` | Hypergraph fragments, ontologies, citations, merge hints |
| `EvalPack` | Tests, scorecards, rubrics, dataset manifests |
| `ModelDeltaPack` | Adapter deltas / mutation lineage; quarantine-only at first |
| `ArtifactPack` | Templates, examples, docs, demos |

`RoleFlow` formal schema name:

```text
orchestration_graph
```

Preferred filenames:

```text
roleflow.graph.yaml
roleflow.json
```

## git_exchange MVP

`git_exchange` should become the standard community transport for NoemaForge packs, but with quarantine-first import.

Pipeline:

```text
signed repo/bundle/LFS-backed pack
  -> Scary import prefilter
  -> signature/provenance/license/privacy/risk/size checks
  -> quarantine registry
  -> sandbox eval / Evolve lab
  -> Surgeon dossier
  -> Admin activation or rejection
```

Priority order for community packs:

1. `RolePack`
2. `RoleFlow`
3. `EvalPack`
4. `KnowledgeGraphPack`
5. `ArtifactPack`
6. `ModelDeltaPack` only in quarantine/lab until promotion rules mature

## HFBridge target

HFBridge should stay metadata-first and read-mostly in MVP:

- map local installed capabilities to roles;
- discover candidate eval tasks and datasets;
- recommend assets under hardware, cost, license, privacy, and provenance limits;
- never auto-import arbitrary data or weights into active runtime.

## Release hygiene rule

Clean public distribution should be assembled by allowlist buckets:

| Bucket | Purpose |
|---|---|
| core distribution | runtime, installer, schemas, policies, docs |
| dev/test pack | tests, synthetic fixtures, debug tools |
| history pack | old reports and migration records |
| drop/quarantine | local experiments, downloaded assets, unapproved packs |

Do not ship optional HF assets, raw community packs, model weights, local experiments, or stale personal-path reports as part of the core seed.

## Phased roadmap

```text
FIRST MVP SLICE
  schemas
    -> release hygiene
    -> ActiveNNManager
    -> NoemaShell Lite
    -> git_exchange v0
    -> sample Coder/Tester pack
    -> HFBridge metadata/eval mode

COMMUNITY PHASE
  public pack docs
    -> signed bundles
    -> quarantine imports
    -> community EvalPacks
    -> KnowledgeGraphPacks
    -> broader optional RolePacks

SCALE PHASE
  3 worker slots
    -> true parallel creator/critic teams
    -> deeper OS integration
    -> richer research/workbench UI
    -> advanced evolution labs
```

## Acceptance criteria for turning this roadmap into implementation

- `ActiveNNManager` has explicit one-worker invariant and durable baton/state snapshots.
- Role switches are recoverable after crash/restart.
- `RoleFlow` schema exists and validates.
- `git_exchange` imports go through quarantine and Scary verdict before activation.
- NoemaShell Lite can show active worker, queued approvals, artifacts, and recovery controls.
- Evolve promotion always produces a candidate dossier, rollback plan, Scary verdict, Surgeon recommendation, and Admin approval record.


## Source report preservation

The original consolidated architecture report is preserved at `docs/source_reports/deep-research-report-6-consolidated-architecture.md`.
