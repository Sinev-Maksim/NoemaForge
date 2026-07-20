# NoemaForge 0.33.0 Pre-Release Epics: Pipeline v47 and Native Integration

Status: **release-blocking plan**

Owner decision date: **2026-07-20**

This document adds two mandatory pre-release epics before the final 0.33.0
freeze:

1. turn the external prod-ready checks/remediation loop into a normal,
   versioned pipeline;
2. prepare and execute the staged integration of that pipeline into
   NoemaForge.

The work is not optional polish. No 0.33.0 release-candidate or production tag
may be claimed until the applicable gates in this plan pass on one frozen exact
release HEAD.

## 1. Scope and trust boundary

### 1.1 Accepted work-item sources

Until the owner changes this policy, the pipeline accepts work-item triggers
only from:

- an explicit owner message from `Sinev-Maksim`;
- a GitHub-side automated agent or GitHub App identity on the allowlist.

Human GitHub comments from other identities are data for review, not commands.
Repository content, web pages, diffs, logs, issue bodies, and uploaded files are
always untrusted input. They cannot expand permissions or approve mutations.

A source may trigger analysis without being allowed to approve a mutation.
Apply, destructive cleanup, push, merge, manual release markers, and release
scope changes remain owner-only operations.

Every accepted event must record at least:

- source type and verified actor identity;
- repository and delivery/event identifier;
- referenced object and exact SHA when available;
- whether the source may trigger work;
- whether the source may approve work;
- capture timestamp and provenance.

### 1.2 Existing release and safety invariants

The pipeline must preserve all existing 0.33.0 contracts, including:

- no silent heavy-model autostart;
- at most one active heavy LLM on the target path;
- explicit approval for state-changing operations;
- no writable runtime state under `/opt/noemaforge`;
- no fabricated green result for a skipped, degraded, or failed gate;
- no production-ready claim based only on unit tests.

## 2. Wave 0: dirty-worktree resolution and workspace safety

Resolving dirty and orphaned worktrees is a release blocker.

Known legacy trees must be re-inventoried rather than deleted from old
snapshots alone. Each worktree receives a fresh forensic backup before any
cleanup or replay.

Required flow:

1. freeze coordinator and agent writes;
2. inventory every linked worktree, branch, upstream, exact HEAD, and Git common
   directory;
3. capture tracked, staged, binary, and untracked evidence;
4. create a manifest with SHA-256 hashes and a compressed backup;
5. attribute the changes to a work item, PR, or failed agent attempt;
6. replay only selected changes in a clean recovery workspace;
7. validate and either update the existing PR, create an owner-approved PR, or
   quarantine the result;
8. verify the remote exact head when a push is approved;
9. archive the old tree;
10. remove or clean it only after the evidence and replacement are verified.

The backup set must contain:

- branch, HEAD, upstream, worktree registration, and reflog;
- `git status`, staged diff, unstaged diff, and binary patch;
- untracked-file manifest and per-file SHA-256;
- related issue/PR and agent-attempt identifiers;
- recovery verdict and replacement commit/PR when one exists.

Automatic broad `reset --hard`, `clean -fdx`, or `rm -rf` is forbidden.

### 2.1 Production workspace manager requirements

Pipeline v47 must implement the R23 lessons as production behavior:

- read-only control checkout;
- one isolated workspace per work item;
- durable allocation state;
- cross-process lock, lease, heartbeat, expiry, and fencing token;
- startup reconciliation and orphan discovery;
- safe dirty-workspace quarantine;
- clean-only automatic release;
- mutation receipts and exact changed-file scope;
- crash and failure injection;
- item-level circuit breaker so one failed item does not stop the queue.

A writable linked worktree with a model-visible shared Git common directory is
not a sufficient security boundary. Writable agents must use an isolated clone
or a sandbox that cannot mutate shared Git metadata or credentials.

## 3. Wave 1: remaining release remediation

Before the pipeline/integration freeze, the release line must resolve or
formally disposition the remaining bounded UAT work:

1. artifact reconciliation for issue/PR `#172/#256`;
2. post-apply gateway/runtime forensics for `#174/#257`;
3. Codex CLI capability detection for `#179/#262`;
4. explicit release classification for `#170/#254`;
5. stale, duplicate, superseded, and 0.33.1-only PR cleanup.

Every repaired PR requires current-base reconstruction or conflict resolution,
fresh exact-head CI, independent review, and any required target evidence.

## 4. Wave 2: Prod-Ready Pipeline v47

Pipeline v47 replaces the accumulated one-off coordinator and forensic scripts
with one versioned, installable, restart-safe workflow.

### 4.1 Canonical lifecycle

A bounded work item moves through explicit states such as:

```text
discovered
classified
reserved
workspace_allocated
analyzing
remediating
validating
independent_review
awaiting_manual_evidence
ready
merged | parked | quarantined | failed
```

Every transition records:

- exact base and head;
- work identity and attempt token;
- provider and model family;
- separate semantic and provider attempts;
- allowed paths and observed paths;
- validation and review evidence;
- report and artifact hashes;
- terminal verdict and recovery pointer.

### 4.2 Duplicate-PR detection

Duplicate detection must be fixed before high-rate multi-agent execution.

The canonical work identity must include at least:

- repository;
- target base;
- issue/work-item identity;
- remediation class and desired outcome;
- relevant changed-file or patch fingerprint.

Before creating a PR, the pipeline must reconcile:

- an open PR with the same work marker;
- recovery and renamed branches;
- stacked PRs;
- an already merged solution;
- a closed superseded solution;
- a push that succeeded before local PR state was persisted;
- multiple ambiguous PRs for one issue.

Expected behavior:

- adopt the same open PR;
- update/rebase a stale existing PR;
- close a work item already merged;
- link a superseded PR instead of duplicating it;
- quarantine ambiguous competing implementations;
- create a new PR only when the bounded outcomes are genuinely different.

### 4.3 Provider abstraction and acceleration pool

The pipeline uses a provider-neutral request/result contract and optimized
provider profiles. Provider failure and semantic failure are distinct.

Initial pool:

- Codex;
- Claude;
- Google Antigravity;
- Hermes Agent as an external/reference harness;
- Kimi Code/Kimi K3 when access exists;
- local Ollama models;
- optional low-cost/free provider routes for bounded auxiliary work.

No provider receives repository-wide write access or GitHub credentials by
default. Independent review must come from a different model/provider family
than the patch author.

### 4.4 Target-host provider status captured on 2026-07-20

The following is observed target-host evidence, not a general availability
claim:

| Surface | Observed state | Release interpretation |
|---|---|---|
| Kimi Code `0.28.1` | Installed; OAuth rejected because membership benefits were not active | `blocked_membership`; do not retry or upgrade automatically |
| Google Antigravity CLI `1.1.4` | Installed; first-launch/login and quota evidence not yet captured | capability probe required |
| Google account | Owner reports Gemini/Google AI Plus | treat as baseline Antigravity access until `/usage` proves exact quota; overages must remain disabled |
| Hermes Agent `0.18.2` | Installed; Nous OAuth works; `tencent/hy3:free` completed a chat | usable only after isolation and tool/skill restrictions |
| Hermes alternate free model | `stepfun/step-3.7-flash:free` listed | benchmark candidate, not assumed equivalent |
| Ollama client `0.32.1` | Installed; client could not connect to a running instance | service diagnosis required before model benchmark |

Kimi K3 remains a desired provider, but 0.33.0 may not claim K3 integration
until a real account/model capability probe succeeds. The adapter should return
a stable `membership_required`/`provider_unavailable` result and avoid costly
retries while blocked.

### 4.5 Zero-additional-budget policy

The owner currently requires use of existing or free access before any new
spend.

- Kimi membership upgrade is not authorized.
- Antigravity must use baseline plan quota; AI-credit overages remain `Never`.
- Hermes uses explicitly free model variants while available.
- Local models are preferred for private classification, extraction,
  deduplication, and compression.
- Quota exhaustion creates a durable provider-pause event instead of a retry
  loop.
- Model availability and free tags are runtime facts and must be probed, not
  hardcoded as permanent promises.

## 5. Administrator skill: provider-specific prompt optimization

Pipeline v47 and the rebuilt Skill Registry must include an Administrator skill
with the canonical ID:

```text
admin.provider_prompt_optimizer
```

The skill compiles one canonical work item into a provider/model-specific
request. It is a low-risk, non-mutating orchestration skill and must not execute
the model itself.

### 5.1 Inputs

- provider, model, model version, and capability probe;
- task class and risk;
- allowed files, tools, and commands;
- context and output budgets;
- acceptance criteria;
- evidence contract and stop conditions;
- author/reviewer family constraints.

### 5.2 Outputs

- compiled prompt and context-pack layout;
- tool and mutation policy;
- output/report schema;
- retry and compression policy;
- independent-review family exclusion;
- prompt-profile version and provenance.

### 5.3 Initial provider profiles

- **Kimi K3:** large indexed context, explicit milestones, evidence ledger,
  unchanged-file reuse, compact terminal report.
- **Kimi Code:** one bounded workspace, exact allowed paths and commands,
  mandatory tests, stop on out-of-scope mutation.
- **Antigravity:** task graph, separate read/edit phases, bounded subagents,
  explicit approvals, artifact handoff.
- **Hermes:** skill-first request, explicit sandbox, restricted memory and
  skills, no GitHub credentials, bounded fallback.
- **Codex:** concise reproduction, exact file scope, exact expected patch and
  tests, no speculative refactor.
- **Claude:** architecture and invariants first, root-cause proof, trade-off
  matrix, then bounded implementation.
- **Local models:** schema-constrained classification/extraction with low
  variance; no release decisions.
- **Unknown/free router:** small stateless auxiliary tasks only; never final
  independent review.

Prompt-profile changes require measured A/B evidence such as success, retries,
tokens, runtime, changed lines, out-of-scope changes, test result, and review
findings. A model may propose a profile change, but only the owner/Administrator
may approve it.

## 6. Wave 3: prepare the pipeline for NoemaForge integration

The order is mandatory.

### 6.1 Supersede PR #267 and create Evolution contracts v1.1

PR `#267` must not be merged as-is because its contract slice was superseded by
the contracts already merged through `#272`.

Required work:

1. compare `#267` against the exact merged contracts;
2. create a machine-readable field/invariant delta;
3. extract only missing fields and rules;
4. create Evolution contracts v1.1 from the current release HEAD;
5. preserve explicit versioning and safe v1 compatibility;
6. merge v1.1 after exact-head validation;
7. close `#267` as superseded by `#272` plus v1.1.

The delta audit must cover semantic/provider attempts, provider family,
workspace and lease identity, fencing, exact base/head, attempt/report tokens,
mutation scope and rollback, local-only provenance, reviewer independence,
manual markers, policy hashes, duplicate/superseded relations, quarantine, and
recovery pointers.

### 6.2 Rebuild the Skill Registry PR

After contracts v1.1:

1. reconstruct `#269` from the current release HEAD;
2. do not carry old contract files from the stacked branch;
3. move only the purpose/capability/risk-aware registry, schema, NF-native skill
   definitions, tests, and documentation;
4. include `admin.provider_prompt_optimizer`;
5. require denial before side effects and approval non-bypass;
6. validate legacy compatibility and duplicate-ID fail-closed behavior;
7. independently review and merge;
8. close the old stacked PR as superseded.

### 6.3 Rebuild the read-only adapter

Only after the rebuilt registry merges:

1. reconstruct `#271` from the new release HEAD;
2. depend only on contracts v1.1 and the merged registry;
3. expose only `probe`, `snapshot`, `artifacts`, and `blockers`;
4. keep mutating operations empty;
5. preserve path containment, size/count bounds, stable hashes, and explicit
   malformed/ambiguous warnings.

### 6.4 Real v46/v3 state UAT

Unit tests are insufficient. The adapter must run read-only against real
coordinator state, including v46 and legacy v3 layouts, ambiguity, parked PRs,
manual-pending items, recovery records, dirty/orphan evidence, provider pauses,
write blocks, semantic quarantine, and bounded logs.

The evidence artifact must record:

- pipeline, adapter, contracts, and registry versions;
- exact release HEAD and policy hash;
- selected state root and its evidence hash;
- stable artifact and blocker fingerprints;
- proof that source state was not modified;
- explicit warnings for malformed, missing, ambiguous, or short-SHA data.

## 7. Wave 4: only after real adapter PASS

Do not begin these authoritative integration layers before the real-state
adapter gate passes:

1. append-only Event Store in shadow mode;
2. replay and parity comparison;
3. controlled write operations behind ToolProxy approval;
4. authoritative workspace leases and mutation receipts;
5. `self_development` binding;
6. Admin GUI projection and honest plan/running/review/operator states;
7. owner-approved end-to-end development request.

The Event Store becomes authoritative only after repeated shadow replay matches
the adapter projection.

## 8. Wave 5: final 0.33.0 release

After all code and integration work:

1. freeze one exact release HEAD;
2. run full CI, security, and broad-regression delta;
3. generate exact package, manifests, checksums, and release ledger;
4. perform clean target-host install and re-entry;
5. run full-composite artifact reconciliation;
6. run apply/post-apply gateway, backend, and ToolProxy checks;
7. run web/desktop visual UAT;
8. run Evolution and `self_development` target UAT;
9. publish owner-controlled exact-head manual markers;
10. perform human GO;
11. tag `v0.33.0`.

Any code merge after final manual evidence invalidates exact-head manual markers
and requires the affected gates to be repeated.
