# NoemaForge roadmap

Status date: **2026-07-24**.  
Shipped stable line: **0.32.2**.  
Active development line: `release/0.33.0-dev`.

This is the forward-looking project roadmap. Task-level tracking lives in the
canonical [`noemaforge/docs/TODO.md`](../noemaforge/docs/TODO.md). The focused
Loop → Harness integration plan is maintained in
[`noemaforge/docs/HARNESS_EVOLUTION_TODO.md`](../noemaforge/docs/HARNESS_EVOLUTION_TODO.md)
and umbrella issue [#304](https://github.com/Sinev-Maksim/NoemaForge/issues/304).
Historical backlog remains in
[`docs/backlog/ROADMAP_AND_TODO.md`](backlog/ROADMAP_AND_TODO.md).

## Product direction

NoemaForge remains a governed agent operating system, not a single unrestricted
universal agent and not a collection of bespoke pipelines.

```text
NF Controller
+ Personas and purpose/risk-aware Skills
+ ToolProxy policy and approvals
+ canonical Event/Evidence stores
+ Resource Broker
+ replaceable Harness Workers
```

The current prod-ready code-evolution loop is treated as the first proven Harness
adapter. NF will absorb its useful execution behaviour incrementally while the
current Bash implementation remains replaceable and local to its adapter boundary.

## Where we are

The 0.32.2 runtime was validated end-to-end on the production target host
(Debian 13 “Trixie”, GNOME/GDM, RTX 3080 Ti). The 0.33.0 line has since added a
large Admin GUI/UAT remediation set, stronger release evidence, platform-path
migration, Evolution execution contracts and continued automated closeout work.

Important current facts:

- Evolution execution contracts were merged through PR #272 and issue #266 was
  closed with exact-head evidence.
- Purpose/risk-aware Evolution skills remain tracked in issue #268.
- The read-only current-loop adapter remains tracked in issue #270.
- The loop proved it can implement a newly created architectural issue, but also
  created PR #272 while PR #267 already targeted the same issue. Canonical work
  ownership and duplicate-PR prevention are therefore a 0.33.0 prerequisite.
- Platform-independence work has begun, including `platform_paths` migrations, but
  full Linux/macOS/Windows parity and installation are still 0.33.1 goals.

## 0.33.0 — prod readiness plus the bounded Loop → NF bridge

Primary goal: a non-engineer operator can install, start, run a pipeline and
receive results through the Admin GUI without JSON reading or filesystem digging.
The release remains driven by the existing UAT defect register and target-host
validation requirements.

### Admin GUI and operator trust

- visible response for every command;
- readable model/epoch/persona state;
- progress, blockers and artifacts delivered in chat/UI;
- safe repeat-launch and stale-state guards;
- no hidden model/media/device autostart;
- target-host install, boot-mode and runtime evidence.

### Evolution/Harness bridge

0.33.0 does **not** add a new unrestricted execution runtime. It establishes
canonical truth and proves bounded observation:

- [#305](https://github.com/Sinev-Maksim/NoemaForge/issues/305) — one canonical
  owner and at most one active integration PR per logical work item;
- [#306](https://github.com/Sinev-Maksim/NoemaForge/issues/306) — compatible
  Evolution contract extension for Harness profiles, checkpoints, exact-head,
  idempotency, attempts and usage accounting;
- [#268](https://github.com/Sinev-Maksim/NoemaForge/issues/268) — purpose/risk-aware
  shared Skill Registry without Security super-role or persona exception tables;
- [#270](https://github.com/Sinev-Maksim/NoemaForge/issues/270) — strictly read-only
  adapter for the real v46/v3 current-loop state;
- [#307](https://github.com/Sinev-Maksim/NoemaForge/issues/307) — append-only
  Evolution Event Store and read-only `self_development` projection;
- [#308](https://github.com/Sinev-Maksim/NoemaForge/issues/308) — context-budget and
  bounded rollover contracts/telemetry;
- [#313](https://github.com/Sinev-Maksim/NoemaForge/issues/313) — operator-facing
  Evolution projection and one real-state observation dogfood.

0.33.0 keeps:

- explicit operator approval;
- one active heavy LLM by default;
- no automatic merge;
- no generic unrestricted host shell;
- no multiprocessing writers;
- no copied external reference code/runtime.

### Continuous Research Radar foundation

Issue [#310](https://github.com/Sinev-Maksim/NoemaForge/issues/310) adds the
contract and first read-only dry-run for a recurring discovery cycle. Candidates
are classified as:

- **Research** — findings, papers, architectures and experiments;
- **How-to** — reproducible procedures with verification;
- **Ready-to-use** — adoptable components subject to license/security/platform review;
- **Ready-to-re-code** — an external approach or technical technique used as a source
  of requirements and testable ideas. The NF implementation is created anew and
  independently, without transferring source code.

A coverage ledger records scanned and unscanned areas, freshness, failures,
licenses and provenance. The system must never claim exhaustive coverage without
that evidence.

### 0.33.0 acceptance for this new track

- duplicate work/PR fixtures cannot create a second mutation owner;
- repeated loop-state import creates no duplicate events, blockers or artifacts;
- NF restart reconstructs the same Evolution projection;
- the operator sees current work, blocker, exact-head status and next action;
- one observation dogfood performs zero writes to source loop state;
- one Research Radar dry-run emits evidence, dispositions and coverage blind spots.

## 0.33.1 — full system independence, installation and NF-native Harness runtime

NoemaForge runs consistently on Linux, macOS and Windows. This milestone combines
platform parity with the first native replaceable Harness execution plane.

### Platform and installation

- complete `PlatformPaths`, `ServiceManager`, `ProcessSupervisor`, `LockProvider`,
  `CredentialProvider`, `SandboxProvider` and device/backend discovery abstractions;
- eliminate import-time crashes from Unix-only modules;
- support platform-appropriate sockets/IPC and process groups/job objects;
- implement one idempotent installer flow:
  `probe → plan → preview → approve → apply → verify → rollback`;
- preserve user/machine state and support resume after partial installation;
- pass AAT and the full test matrix across Linux, macOS and Windows families.

### Native Harness Worker

Issue [#311](https://github.com/Sinev-Maksim/NoemaForge/issues/311) implements:

- a common Harness adapter API;
- typed file/search/edit/validation operations behind ToolProxy;
- constrained profile-specific shell rather than blanket Bash authority;
- isolated workspaces and one writer per worktree;
- provider/model adapters with local credentials, redaction-before-egress,
  rate/cost ceilings and explicit operator opt-in;
- one authoritative controller with leased workers;
- parallel read-only indexing/research/tests and bounded candidate generation;
- controller-owned commit, push, merge and release verdict.

Context lifecycle is governed by issue #308. Repeated no-progress collapse is
handled by the evidence-preserving strategy reset in
[#309](https://github.com/Sinev-Maksim/NoemaForge/issues/309), not by forgetting
all prior failures.

The current loop is replaced slice-by-slice only after equivalent exact-head
dogfood. It remains a compatibility fallback until explicitly retired.

### Recurring Research Radar runtime

0.33.1 enables budgeted scheduled source adapters after the 0.33.0 dry-run proves:

- stable candidate identity and deduplication;
- quarantine of malicious/untrusted content;
- license, provenance and supply-chain review;
- operator-controlled promotion to research experiment, how-to validation,
  Ready-to-use evaluation, independent implementation specification, skill proposal
  or benchmark.

## 0.33.2 — idempotent benchmarking and measured evolution

Issue [#312](https://github.com/Sinev-Maksim/NoemaForge/issues/312) reuses the same
Harness execution plane rather than creating another orchestrator.

### Execution model

```text
at-least-once shard attempts
→ immutable attempt artifacts
→ deterministic validation
→ atomic winner publication
→ exactly-once logical result
```

Logical identity includes benchmark/dataset/case versions, model/provider revision,
parameters, seed, HarnessProfile, prompt, skills, tools, NF commit, policy epoch,
backend, OS, drivers and hardware.

### Evaluation scope

- models of different sizes, architectures and providers under declared
  vendor-neutral selection rules;
- prompts, skills, ToolProxy schemas and provider adapters;
- context rollover thresholds and strategy-reset policies;
- correctness, tokens/cost, latency, retries, context use, unsafe attempts,
  resources, human intervention and variance;
- resumable shards and reuse of completed valid work;
- train/development/hidden-holdout/regression separation for prompt/skill
  auto-improvement;
- promotion of Research Radar candidates into bounded experiments with measured
  adoption value or regression.

## 0.33.3 — governed agent-OS maturation

After 0.33.0–0.33.2, NoemaForge matures the existing foundations rather than
starting another greenfield architecture:

- agent lifecycle and explicit handoff governance;
- independent fusion/judge/debate patterns where they add measurable value;
- advanced memory/retrieval quality and long-horizon planning;
- artifact lineage and workflow replay;
- dynamic cost/latency/quality-aware model routing;
- richer observability, decision auditing and failure classification;
- stable/LTS release channels and migration governance.

Functional separation remains mandatory where independence matters: mutation and
review, candidate and judge, privileged operation and release verdict. The roadmap
does not preserve multi-agent conversation for its own sake.

## Cross-cutting tracks

### Artifact-driven acceptance (AAT)

The AAT suite remains the release-facing verification layer for checksum,
telemetry privacy, capability tokens, ToolProxy isolation, signed manifests,
epoch immutability, installation, live models and GUI flows.

Harness and benchmarking work must emit artifacts that AAT can independently
validate; a model’s own success claim is never sufficient evidence.

### Purpose/risk-aware security

Security is an assurance/risk property of a concrete invocation, not a privileged
persona domain. Access is derived from persona purpose, task relevance,
capabilities, effective risk, environment policy, ToolProxy token and approval.

### Hardening for non-engineer operators

One-button install/run, plain-language errors, guided recovery, safe defaults and
GUI-first flows remain mandatory. Harness state must be understandable without
opening raw scheduler files.

### Documentation and project wiki

Keep README as the landing page, the canonical TODO as task-level tracking and
this roadmap as release sequencing. Focused design/TODO documents must link to
issues and be reconciled when work is completed or superseded.

### Review and research harvest

- actionable Codex/Copilot/CodeRabbit findings are resolved or recorded before merge;
- review-harvest sweeps prevent useful findings from rotting in threads;
- the Research Radar performs freshness and coverage sweeps under explicit budgets;
- repeated unchanged sources do not create duplicate candidates;
- failed and intentionally unscanned sources remain visible in coverage reports.

## Invariants that gate every milestone

- No production GitHub Release without explicit human GO and required target validation.
- `noema upgrade` never removes or overwrites user/machine state.
- `RUNTIME_VERSION` is assigned only in `noemaforge_version.py`.
- Heavy GPU/model operations preserve the display by default.
- Self-modification remains policy-gated, evidence-backed and explicitly approved.
- One logical work item cannot silently acquire competing mutation owners.
- Files are artifacts/checkpoints; canonical lifecycle is event-backed.
- Ready-to-re-code references inform requirements and testable ideas only; the NF
  implementation is created anew and independently, without transferring source code.
- Unknown values are represented as unknown, never as fabricated zero/success.
- Every final review and release decision is tied to the exact final HEAD.
