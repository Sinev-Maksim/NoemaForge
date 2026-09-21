# Night Watch Development Rules

**Status:** canonical development policy for the Night Watch self-heal release line  
**Classification:** `UAT request findings resolution`  
**Current package family:** NoemaForge Night Watch / NoemaForge `0.33.0`  
**Canonical exact base:** `a3c172f5d60113876f0c103010de411fc30b8c38`

This document is the human-readable source for the engineering rules that must later be suitable for conversion into a reusable SKILL. Machine-readable copies of the enforceable rules live in `SELF_HEAL_POLICY.json`, `ENGINEERING_GUARDRAILS.json`, `PACKAGE_REQUIREMENTS.json`, `PRE_SEND_DRY_RUN_POLICY.json`, and `FAILURE_RESOLUTION_MATRIX.json`.

## 1. Primary objective: success first, evidence rich

Night Watch is **not** optimized for fail-fast. It is optimized for **success-first, max-evidence recovery**.

Canonical machine-policy identifier: `FAILURE_DISCOVERY_POLICY=SUCCESS_FIRST_MAX_EVIDENCE`.

For every run the preferred sequence is:

1. detect the failure;
2. classify it by ownership/plane;
3. attempt a safe automatic recovery;
4. if recovery is impossible, degrade only the affected capability;
5. continue every independent safe check/action that can still move the run toward success;
6. try alternate providers, runtimes, paths, storage roots, transports, or recovery paths where allowed;
7. accumulate all independent failures, blockers, degraded capabilities, and recovery outcomes;
8. stop only when success is no longer safely reachable or a hard integrity/safety boundary is crossed.

If a run cannot succeed, it should terminate with the **maximum useful evidence** that can be gathered without corrupting state. The next run should therefore start closer to success rather than merely discover the next error in a sequence.

### 1.1 Premature fail-fast is a defect

A recoverable or independent failure must not terminate the whole run merely because it occurred first. Examples:

- one provider is unavailable while another is usable;
- one evidence root is unwritable while a fallback exists;
- a provider process fails before materializing a candidate;
- an independent validation check fails while other safe checks can still run;
- direct mutation is unavailable but structured proposal transport is usable.

### 1.2 Hard-stop boundaries remain fail-closed

Immediate termination is correct only when continuation could corrupt state, invalidate evidence, or violate safety/separation-of-duties. Hard boundaries include at least:

- sealed package integrity cannot be established;
- exact pre-attempt candidate cannot be restored after untrusted mutation;
- cumulative handoff lineage/integrity cannot be proved;
- immutable tests/evidence would have to be weakened or changed;
- mutation scope/containment cannot be trusted;
- implementer would have to accept/review its own candidate;
- exact canonical base cannot be materialized safely;
- an atomic write/replace cannot be completed without risking corruption.

The required balance is therefore:

`recoverable failure -> recover/degrade/continue`  
`hard integrity loss -> fail closed immediately`

## 2. Failure ownership and plane separation

Every failure must be attributed before deciding what may change.

Supported planes:

- **sealed Night Watch package / self-harness**;
- **host/runtime/infrastructure**;
- **provider capability/transport/auth/network/quota**;
- **control plane / proposal protocol**;
- **PRODUCT (NoemaForge candidate)**;
- **review/acceptance**;
- **handoff/evidence continuity**.

A failure in one plane must not be “repaired” by mutating another plane.

In particular:

- a Night Watch harness defect must not be sent to the coding model as a PRODUCT task;
- provider/transport failures do not justify PRODUCT changes;
- proposal-format failures do not justify PRODUCT changes;
- immutable test failures may identify a PRODUCT regression, but tests themselves remain read-only evidence.

`PRODUCT_VALIDATION_BEGIN=PASS` marks entry into PRODUCT validation, but entry alone does **not** prove a PRODUCT defect. A PRODUCT repair task may be created only after the harness safely completes/aggregates its independent validations and emits `PRODUCT_VALIDATION_AGGREGATE=FAIL`. A crash after `BEGIN` but before the aggregate verdict remains `self_harness_preflight`. `PAYLOAD_COPY=PASS` is not a PRODUCT boundary.

## 3. Attempts, stagnation, and recovery accounting

- Stable PRODUCT task stagnation limit: **2** attempts.
- Control-plane recovery retry limit: **4**.
- A PRODUCT attempt is charged only after a candidate has actually materialized.
- Provider quota/auth/network/transport/CLI failures before candidate materialization charge **0 PRODUCT attempts**.
- Out-of-scope mutation that is rolled back exactly charges **0 PRODUCT attempts**.
- Control-plane retries do not create PRODUCT task keys and do not consume PRODUCT stagnation budget.
- Infrastructure recovery is counted separately from PRODUCT attempts.

The point of these limits is not to fail quickly; it is to prevent repeated low-information attempts while allowing useful alternate recovery paths.

## 4. Provider roles and separation of duties

- Implementation provider preference is currently `codex_cli`, then `claude_cli`.
- Provider degradation is **role-scoped**, not pipeline-scoped.
- If one implementer is unavailable and the other is usable, implementation continues.
- Direct mutation failure downgrades to validated structured proposal transport when safe.
- Same-provider local co-check is useful evidence but **never independent acceptance**.
- The implementer must never accept its own candidate.
- If implementation is green but no distinct reviewer is available, terminal state is `IMPLEMENTATION_COMPLETE_INDEPENDENT_REVIEW_PENDING`, not false acceptance.

## 5. Mutation, containment, and rollback

Before any untrusted mutation, persist the exact pre-attempt candidate as a binary patch and SHA-256 identity.

If a provider:

- touches immutable tests;
- changes an out-of-scope path;
- partially mutates and crashes/exits non-zero;
- mutates during same-provider co-check;

Night Watch must restore the **exact** pre-attempt candidate, clean rogue untracked files, verify the restored patch SHA, and only then continue/fail over.

Rollback failure is a hard integrity boundary and must fail closed.

## 6. Tests are evidence, not repair targets

The entire `noemaforge/tests/**` tree is immutable during self-heal.

A proposal to edit tests is a typed control-plane rejection. It does not count as PRODUCT stagnation. New tests added by the canonical product/release process automatically inherit this protection; the protection must not depend on enumerating specific test filenames.

## 7. Exact base and worktree isolation

- Canonical exact base is pinned and must not silently drift.
- Source repository HEAD may advance; this is not itself a blocker.
- Night Watch creates an isolated worktree at the exact base.
- Missing exact base gets one bounded read-only fetch of the exact SHA, then a re-probe.
- If the exact base still cannot be materialized, stop with typed `EXACT_BASE_UNAVAILABLE` and zero PRODUCT attempts.
- Stale worktree metadata gets a bounded prune/retry.
- `safe.directory` adjustments are process-local only; never mutate global Git configuration.

## 8. Windows-first runtime compatibility

The release must remain compatible with Windows PowerShell 5.1 and ordinary Win32 filesystem semantics.

Mandatory constraints include:

- `.ps1`: UTF-8 BOM + CRLF;
- `.cmd`: ASCII + CRLF;
- no executable-source smart quotes (`U+2018/U+2019/U+201C/U+201D`);
- PowerShell AST is validated with target-host native parser before controller start;
- AST parser reads source content (`ParseInput`), not filesystem paths;
- package root derives from `$PSScriptRoot`, not a quoted trailing-backslash `%~dp0` argument;
- delayed expansion is forbidden in launchers so `!Projects` remains literal;
- WindowsApps `python.exe` path presence is not evidence of a working Python runtime;
- Python and Git candidates require execution canaries;
- `py.exe -3` executable+prefix remains bound as one runtime object;
- `.ps1`, `.cmd`, `.bat`, and native provider shims use explicit bridges;
- sealed paths must be valid under case-insensitive Win32 naming rules (no forbidden/reserved components, trailing dot/space, ADS colon, or casefold collisions);
- fault-injection physical fixtures themselves must be Win32-legal; impossible quote/newline Git records are tested in memory instead.

## 9. Evidence/storage/process resilience

- Evidence roots are write-probed before use.
- Preferred fallback order: `LOCALAPPDATA -> TEMP -> project runtime`.
- Require a reasonable free-space floor (currently 256 MiB).
- Evidence/run/staging paths use GUID suffixes to prevent collisions.
- Provider and helper processes are bounded by timeouts; hung process trees are terminated.
- AV/indexer transient locks receive bounded read/replace retries.
- Optional completion notification must never block terminal evidence.

## 10. Package closure and replace-in-place upgrades

The release verdict and runtime execution scope are defined only by the **sealed release closure**:

- `PACKAGE_REQUIREMENTS.json` defines required runtime/build members;
- `SHA256SUMS.json` defines their expected bytes.

Old diagnostic or obsolete files left beside the current release after overlay extraction:

- may be inventoried as hygiene evidence;
- must not be parsed/executed as part of the release;
- must not affect release PASS/FAIL.

A dirty-overlay negative control is mandatory before release.


### 10.1 Deployment must establish the sealed runtime, not assume overlay replacement

Validation isolation is insufficient if the operator can still execute stale bytes from an older overlay. Manual overwrite-in-place is therefore **not** an accepted deployment guarantee.

The supported release entrypoint must deploy from an immutable sealed archive and prove the target bytes before runtime:

1. verify the sealed archive and manifest before touching `current`;
2. reject duplicate/case-colliding/path-traversal archive entries;
3. move every unsealed leftover in `current` to `TO_REMOVE/batch-*/current-overlay` instead of deleting it;
4. deploy every sealed file with bounded retry for transient Windows locks;
5. verify every deployed SHA-256 against the sealed manifest;
6. verify every required runtime member again from the **target** directory;
7. reject surviving legacy diagnostic launchers/bootstrap files;
8. verify that the deployed `START_SELF_HEAL.cmd` identifies the expected release and points only to the canonical bootstrap;
9. write `CURRENT_RELEASE.json` only after target verification succeeds;
10. start Night Watch only after deployment returns PASS.

A unique versioned operator entrypoint (`START_HERE_vX_Y_Z.cmd`) is required so an obsolete shortcut/file with an old name cannot be mistaken for the new release. The installer itself may be extracted anywhere; extracting the release directly over `current` is no longer the required workflow.

This closes the class `sealed validator PASS -> stale launcher actually executes`. Deployment correctness is part of release qualification.

## 11. Cumulative handoff and history integrity

The fixed handoff is `NoemaForge-NightWatch-handoff.zip`.

Requirements:

- cumulative, incremental and content-addressed by SHA-256;
- packed object store (`OBJECTS.nwpack`) to remain Explorer-friendly;
- old runs/objects must never disappear;
- legacy id-less runs are preserved deterministically;
- repeated merge of the same terminal run must be byte-idempotent;
- corruption, duplicate ZIP members, object SHA mismatch, or lineage regression must fail closed while preserving the existing archive byte-for-byte;
- staging and final replace are isolated/atomic with bounded lock recovery.

## 12. Root-cause extrapolation before every release

Fixing the line that crashed is insufficient. Every real defect starts a new extrapolation cycle.

For each root cause perform at least these layers:

1. **Exact pattern** — direct duplicates of the faulty construct.
2. **Structural siblings** — analogous producers/consumers, lists, contracts, markers, variables, schemas.
3. **Lifecycle** — discover/materialize/validate/mutate/rollback/review/handoff/terminal variants.
4. **Ownership/plane** — confirm the failure is assigned to the correct repair surface.
5. **Failure inversion** — empty/missing/multiple/invalid/partial/non-zero/timeout variants.
6. **Platform** — WinPS 5.1, CRLF/BOM, Win32 paths, casefolding, `autocrlf`, shims, locks.
7. **Temporal/stateful** — repeat run, interrupted run, dirty overlay, stale worktree, existing handoff, failover after partial mutation.
8. **Self-test validity** — prove the test actually injected the intended fault and did not fail earlier for an unrelated reason.
9. **Regression synthesis** — exact regression + generalized invariant + negative control + neighboring failure simulation.

**Minimum root-cause extrapolation cycles before release: 3.**

If any cycle discovers a new defect, fix it and restart the cycle count from the new changed state. The final extrapolation cycle must discover **zero unresolved defects**.

## 13. Release freeze gate

A release is not ready because one happy-path test passed.

Before freeze, require at least:

- root-cause extrapolation cycles: `>= 3`;
- unresolved defects in final extrapolation cycle: `0`;
- clean full pre-send: `>= 3` consecutive PASS;
- fault-injection suite: `>= 5` consecutive PASS;
- dirty-overlay scenario: PASS;
- Windows-like Git configuration (`core.autocrlf=true`, quotepath/ignorecase): PASS;
- path matrix (`!`, spaces, Unicode): PASS;
- read-only sealed tree: PASS;
- real cumulative handoff replay: PASS;
- repeat handoff merge: byte-idempotent;
- final ZIP clean extraction: PASS;
- package ZIP integrity/duplicate/casefold/path checks: PASS;
- all mandatory checks: `SKIP_COUNT=0`.

After the release ZIP is frozen, **do not modify it**. Run the final validation suite only against a clean extraction of that exact immutable ZIP. If any test fails, discard the ZIP, fix in a new build tree, and restart the validation cycle.

## 13.1 Release qualification is not target-host startup work

Success-first also applies to the validator itself. Expensive stochastic/dynamic release qualification must **not** be re-executed recursively on every operator startup when it does not depend on that host. Otherwise the safety harness becomes a new availability failure (timeout, excessive latency, unnecessary filesystem churn).

Therefore validation is split into two scopes:

- **release qualification** — full fault-injection matrix, dirty-overlay negative controls, destructive/temporal handoff simulations, repeated extrapolation/stability cycles, immutable-ZIP replay; executed before release freeze;
- **target-host runtime preflight** — sealed SHA/closure integrity, native WinPS AST, encoding/path/runtime canaries, bounded static/self-harness checks and host-specific compatibility; executed on every Windows startup.

The host preflight must verify that it is running the exact sealed release and must never weaken a hard integrity check. It may rely on build-time qualification for simulations whose result is a property of the sealed bytes rather than of the current host. Target-host checks must remain bounded so the preflight itself cannot become the reason a healthy release fails to start.

A nested dirty-overlay test validates the **host-runtime preflight** on the dirty copy; it does not recursively rerun the complete release fault matrix. The parent release qualification already executes that matrix on the same sealed SHA.

## 14. Failure discovery during tests and runtime

Tests and runtime should maximize information per cycle.

For independent checks:

- record the first failure;
- continue all other safe independent checks;
- aggregate sibling failures;
- exercise safe fallback/recovery routes;
- report `blocking failures`, `recoverable failures`, `degraded capabilities`, and `recovery outcomes` separately.

The inner PRODUCT harness follows the same rule: `git diff --check`, syntax/schema, routing-contract tests, read-only adapter regression, evolution-execution regression, and changeset validation are collected into one `PRODUCT_VALIDATION_AGGREGATE` verdict instead of stopping at the first independent test failure.

Two anti-patterns are explicit release defects:

- `premature_fail_fast` — terminating on the first recoverable/independent failure;
- `silent_continue_after_integrity_loss` — continuing after a hard integrity boundary has been crossed.

## 15. Versioning, deliverables, and local UAT findings

- All creative reinterpretations/fixes derived from UAT are labeled **`UAT request findings resolution`**.
- Experimental/reinterpretation code remains isolated from release/production paths, but every materially useful intermediate state MUST be checkpointed to the dedicated `night-watch` GitHub branch. Incomplete checkpoints are explicitly marked `unstable, saved for context` and carry no merge/release/deploy authority.
- Fixed primary package filename: `NightWatch-Agent-Self-Heal.zip`.
- Fixed cumulative handoff filename: `NoemaForge-NightWatch-handoff.zip`.
- Avoid accumulating version-suffixed user-facing files unless needed as temporary internal validation artifacts.
- Every release must carry its own policy, guardrails, self-tests, validation evidence, and exact version marker.

## 16. Rule precedence

When rules conflict, use this precedence:

1. integrity / safety / separation-of-duties;
2. preservation of exact candidate and immutable evidence;
3. success-first recovery and continuation;
4. max-evidence collection;
5. PRODUCT correctness;
6. efficiency/token/process cost;
7. convenience.

Success-first never permits unsafe continuation; fail-closed never justifies throwing away safe diagnostic/recovery opportunities.

### Post-fix validation must also aggregate

The success-first/max-evidence rule applies both before and after a model repair. `Invoke-Gates` may fail immediately on a **hard integrity boundary** such as an out-of-scope/forbidden changed path. After containment is proven, independent PRODUCT checks (`git diff --check`, syntax/schema, routing contract, read-only adapter regression, evolution-execution regression) MUST all run and their sibling failures MUST be aggregated before another model cycle is started. A first semantic failure is not a valid reason for premature termination.

Release regression: `post_fix_gate_max_evidence_aggregation` / `NW-FI-075`.

## 17. Repository-canonical context

`CHAT_IS_TRANSPORT_NOT_STORAGE=TRUE`  
`REPOSITORY_MD_IS_CANONICAL=TRUE`

All non-secret development knowledge required to continue or reproduce Night Watch work MUST be persisted in repository Markdown. Chat history, assistant memory, transient agent context, issue comments, and terminal scrollback may transport information, but MUST NOT be the sole storage location for:

- architecture and trust boundaries;
- development and release rules;
- current status and pending gates;
- accepted/rejected design decisions;
- recovery/resume instructions;
- failure lessons and regression rationale;
- operator procedures needed to reproduce a result.

If losing the chat would impair development, the information belongs in canonical `.md` documentation.

Repository evidence and canonical contracts take precedence over chat summaries when they disagree. Contradictions are recorded explicitly; old rules are marked superseded rather than silently coexisting.

### 17.1 Secret-context exclusion

Secret/internal directives and hidden goals are deliberately excluded from normal repository documentation, Git history, GitHub issues, generated evidence, and handoff archives.

Production behavior, correctness contracts, release gates, and safety boundaries MUST remain understandable without secret context. An agent receives secret context only when that execution actually requires it.

## 18. Intermediate-result remote persistence

`INTERMEDIATE_RESULT_REMOTE_PERSISTENCE=MANDATORY`  
`NIGHT_WATCH_DEVELOPMENT_BRANCH=night-watch`  
`UNSTABLE_CONTEXT_MARKER="unstable, saved for context"`

Any materially useful intermediate result MUST be persisted to GitHub even when incomplete, failing validation, not release-qualified, or expected to be replaced.

A checkpoint is required when at least one of these is true:

- a meaningful patch or document update exists;
- a finding was closed or materially narrowed;
- architecture/controller/release semantics changed;
- a working partial state would be expensive to reconstruct;
- the next iteration may destroy or invalidate useful current work;
- the run is stopping because of stagnation, provider/control-plane failure, timeout, or operator interruption;
- newly learned context/rules would otherwise exist only in chat or local files.

Incomplete checkpoints:

- go only to the dedicated `night-watch` development branch;
- use a commit message containing `unstable, saved for context`;
- preserve enough code, evidence, and Markdown context to resume;
- MUST NOT be represented as production-ready, independently reviewed, release-qualified, safe to merge, or safe to deploy;
- MUST NOT automatically trigger merge, tag, release, deployment, or production mutation.

Remote persistence is a durability/recovery boundary, not a promotion boundary.

## 19. Context-persistence gate

A meaningful development iteration is NOT complete until all applicable layers are persisted:

1. code/artifacts;
2. relevant evidence;
3. canonical Markdown for any new rule, decision, constraint, or lesson;
4. current status when a trust boundary or qualification state changed;
5. explicit supersession when an earlier rule is no longer valid.

The three layers move together:

`code + evidence + canonical context`

A result that exists only in chat is `NOT_PERSISTED`. A WIP code checkpoint whose changed reasoning/status is missing from canonical Markdown is also incomplete.
