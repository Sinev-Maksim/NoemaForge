# Harness Evolution and Research Harvest TODO

Status date: **2026-07-24**  
Umbrella: [#304](https://github.com/Sinev-Maksim/NoemaForge/issues/304)  
Classification: **UAT request findings resolution**

## Decision

NoemaForge will absorb the current code-evolution loop as functionality without
making its Bash implementation the permanent product architecture.

```text
NF Controller
+ Personas and purpose/risk-aware Skills
+ ToolProxy policy and approvals
+ canonical Event/Evidence stores
+ Resource Broker
+ replaceable Harness Workers
```

The current loop is the first production-proven Harness adapter. Files remain
artifacts/checkpoints; canonical truth belongs to NF events and projections.

## Rules that apply to every slice

- One logical work item has one canonical owner and at most one active integration PR.
- Persona names never grant blanket tool access.
- Security is evaluated from purpose, task scope, invocation risk, environment,
  capability tokens and approval.
- External source/examples remain local-only unless a compatible dependency is
  explicitly approved as Ready-to-use.
- Ready-to-re-code candidates produce clean-room requirements/tests, not copied code.
- Unknown token, cost, resource or exact-head values remain explicitly unknown.
- Provider retries and semantic attempts are accounted separately.
- Mutation invalidates earlier review; final review must match the exact final HEAD.
- No automatic merge, manual-evidence fabrication or hidden scope widening.

## 0.33.0 — bridge, canonical truth and bounded observation

### P0 ownership and contract foundation

- [ ] [#305](https://github.com/Sinev-Maksim/NoemaForge/issues/305) — enforce
  canonical work ownership and prevent duplicate PRs. _(L)_
- [ ] [#306](https://github.com/Sinev-Maksim/NoemaForge/issues/306) — extend
  Evolution contracts for Harness lifecycle, idempotency, checkpoints, exact HEAD,
  attempts and usage accounting. _(L)_
- [ ] Reconcile draft PR #267 as superseded by merged PR #272; migrate only missing
  contract semantics through #306 and do not create a second schema vocabulary. _(M)_

### Skills and current-loop observation

- [ ] [#268](https://github.com/Sinev-Maksim/NoemaForge/issues/268) — rebase and
  land the purpose/risk-aware Evolution Skill Registry without the obsolete #267
  contract stack. _(L)_
- [ ] [#270](https://github.com/Sinev-Maksim/NoemaForge/issues/270) — rebase and
  land the strictly read-only current-loop adapter against canonical contracts. _(L)_
- [ ] [#307](https://github.com/Sinev-Maksim/NoemaForge/issues/307) — add the
  append-only Evolution Event Store and read-only `self_development` projection. _(L)_
- [ ] [#313](https://github.com/Sinev-Maksim/NoemaForge/issues/313) — add the
  operator-facing Evolution projection and one real-state observation dogfood. _(L)_

### Context lifecycle contract

- [ ] [#308](https://github.com/Sinev-Maksim/NoemaForge/issues/308) — add
  `HarnessProfile`, context budgets, structured iteration checkpoints and bounded
  Ralph-style rollover policy. Runtime control remains deferred. _(L)_
- [ ] Record context utilization as known/estimated/unknown and benchmark the
  rollover thresholds later; do not encode “30–40%” as a universal truth. _(M)_

### Continuous Research Radar

- [ ] [#310](https://github.com/Sinev-Maksim/NoemaForge/issues/310) — define the
  recurring Research/How-to/Ready-to-use/Ready-to-re-code harvest cycle. _(XL)_
- [ ] Add a source coverage ledger with freshness, cursor/version, failures,
  license/provenance confidence, blind spots and explicit unscanned areas. _(M)_
- [ ] Add stable candidate identity and deduplication across repeated scans and
  upstream versions. _(M)_
- [ ] Run one read-only bounded harvest and archive the coverage/evidence report. _(M)_
- [ ] Verify that malicious `SKILL.md`/README content remains quarantined and cannot
  request tools, permissions, execution or promotion. _(M)_

### 0.33.0 completion gate for this track

- [ ] No duplicate logical work or integration PR is produced in race/restart tests.
- [ ] NF imports real loop state twice without duplicate events, blockers or artifacts.
- [ ] Operator sees current work, blocker, exact-head status and required next action
  without reading raw scheduler files.
- [ ] One bounded observation dogfood completes with zero source-state writes.
- [ ] One Research Radar dry-run emits candidate dispositions and coverage blind spots.
- [ ] No controlled Harness execution or multiprocessing is enabled by default.

## 0.33.1 — multiplatform NF-native Harness runtime and installation

- [ ] [#311](https://github.com/Sinev-Maksim/NoemaForge/issues/311) — implement the
  platform-neutral NF-native Harness Worker runtime. _(XL)_
- [ ] [#309](https://github.com/Sinev-Maksim/NoemaForge/issues/309) — implement
  evidence-preserving strategy reset for repeated no-progress loops. _(L)_
- [ ] Complete PlatformPaths, ServiceManager, ProcessSupervisor, LockProvider,
  CredentialProvider, SandboxProvider and DeviceDiscovery parity for Linux/macOS/Windows. _(XL)_
- [ ] Implement one authoritative controller with leased workers; parallelize read-only
  discovery/indexing/tests while preserving one writer per worktree/integration branch. _(XL)_
- [ ] Reuse the Harness execution plane for the unified installer flow:
  `probe → plan → preview → approve → apply → verify → rollback`. _(XL)_
- [ ] Add provider adapters behind ToolProxy with local credentials,
  redaction-before-egress, cost/rate limits and explicit opt-in. _(L)_
- [ ] Replace legacy loop slices one at a time after equivalent exact-head dogfood;
  retain the current-loop adapter as fallback until explicit retirement. _(XL)_
- [ ] Enable scheduled Research Radar adapters only after budgets, source policy,
  quarantine and operator disposition are verified. _(L)_

### 0.33.1 completion gate

- [ ] Full test/AAT matrix passes on Linux, macOS and Windows families.
- [ ] A worker crash resumes from a valid checkpoint without duplicate publication.
- [ ] Two read-only workers may run concurrently; conflicting writers are denied.
- [ ] Cancellation terminates the complete process group/job and preserves canonical state.
- [ ] Current-loop and NF-native adapters produce equivalent canonical outputs for a
  bounded fixture task.
- [ ] Installer is idempotent, resumable and rollback-aware on supported platforms.

## 0.33.2 — idempotent benchmarking and measured evolution

- [ ] [#312](https://github.com/Sinev-Maksim/NoemaForge/issues/312) — implement
  idempotent benchmarking on the Harness execution plane. _(XL)_
- [ ] Define deterministic identities for benchmark run, shard, case and attempt.
- [ ] Support at-least-once attempts with immutable evidence and exactly-once logical
  result publication.
- [ ] Reuse completed valid shards after restart; invalidate only the affected cache
  scope when model/prompt/skill/tool/policy/environment changes.
- [ ] Evaluate models of different sizes, architectures and providers using declared,
  vendor-neutral selection rules.
- [ ] Measure correctness, tokens/cost, latency, tool calls, retries, context rollover,
  unsafe attempts, resource use, human intervention and variance.
- [ ] Evaluate context thresholds and strategy-reset policy against no-rollover and
  ordinary-rollover baselines.
- [ ] Promote Research Radar candidates into bounded experiments and record whether
  adoption produced measurable value or regression.
- [ ] Keep prompt/skill auto-improvement separated into train, development, hidden
  holdout and regression sets.

## Recurring Research Radar operating policy

Initial default proposal; all cadence and budgets remain configurable:

| Pass | Default cadence when enabled | Purpose |
|---|---:|---|
| Freshness scan | daily | releases, changed docs, watched repositories and registries |
| Focused roadmap scan | weekly | active issues, release goals and capability gaps |
| Coverage/backfill review | monthly | blind spots, failed sources, stale watches and old candidates |
| Operator-triggered | on demand | named issue, technology, model, provider or platform |

Every pass follows:

```text
coverage plan
→ bounded discovery
→ deduplication / claim clustering
→ evidence packet
→ relevance and novelty assessment
→ license/security/provenance review
→ disposition
```

Allowed dispositions:

- `no_action`;
- `watch`;
- `research_experiment`;
- `how_to_validation`;
- `ready_to_use_evaluation`;
- `skill_proposal_quarantine`;
- `clean_room_recode_spec`;
- `benchmark_candidate`;
- `roadmap_or_issue_candidate`;
- `rejected` with reason.

A scan is never reported as exhaustive unless its coverage ledger proves the declared
source/query scope was completed. Failed and intentionally unscanned areas are part of
the result, not hidden operational detail.

## Sequencing

```text
#305 ownership gate
  → #306 contracts v1.1
  → #268 Skill Registry
  → #270 read-only adapter
  → #307 Event Store / self_development
  → #313 operator projection + observation dogfood

#306 + #307
  → #308 context rollover
  → #309 strategy reset
  → #311 NF-native Harness runtime
  → #312 idempotent benchmarking

#268 + Research_Packet + SkillProposal quarantine
  → #310 recurring Research Radar
  → #311 scheduled Harness evaluation
  → #312 measured adoption/regression
```

## Definition of done for the umbrella

The umbrella [#304](https://github.com/Sinev-Maksim/NoemaForge/issues/304) is complete
only when the current loop is a replaceable adapter, NF owns canonical lifecycle and
evidence, context/reset behaviour is policy-driven, research harvesting is recurring
and auditable, and the same execution plane supports multiplatform installation and
idempotent benchmarking.