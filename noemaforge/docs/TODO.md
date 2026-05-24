# TODO

This is the short active TODO mirror for the post-`0.32.0.alpha` gate cycle. Detailed active gates live in `backlog/CURRENT_0.32.1_TODO.md`; old task fragments live in `backlog/HISTORICAL_TODO_ARCHIVE.md`; path migrations live in `backlog/TODO_CROSSWALK.md`.

## P0 - Boot, Display And Storage Safety

- [ ] [target-open] Validate 0.32.1 install without display blackout.
- [ ] [target-open] Validate first-start dry-run with keep-display.
- [ ] [blocked] Validate real first-start keep-display only after storage and journal health are clean.
- [ ] [target-open] Add and validate journald/storage preflight before heavy model selection.
- [ ] [target-open] Validate safe-load rescue scripts on the target machine.

## P0 - Admin Chat And Routing

- [ ] [target-open] Verify Admin main chat behaves like a chat, not only router fallback.
- [ ] [target-open] Verify explicit pipeline commands switch modes correctly.
- [ ] [target-open] Verify Model Selection and Model Evolution stay distinct in chat.

## P0 - Stateful GUI Jobs

- [ ] [target-open] Verify Continue model selection is idempotent after refresh.
- [ ] [target-open] Verify Re-inventory Vault returns a privileged job or fallback command.
- [ ] [target-open] Verify active jobs are visible in GUI after page reload.

## P0 - Runtime Service Safety

- [ ] [target-open] Validate `noemaforge-llm-gateway` service.
- [ ] [target-open] Validate `noemaforge-llama@main` manual start/stop.
- [ ] [target-open] Validate ToolProxy capability issue/verify and `llm.chat` smoke.

## P1 - Telemetry And Product Metrics

- [ ] [target-open] Validate hardware telemetry on the primary target workstation.
- [ ] [target-open] Validate runtime telemetry.
- [ ] [target-open] Validate product metrics for Dev Team.

## P1 - Grounded Admin And Docs RAG

- [ ] [target-open] Build and test local docs/wiki RAG index.
- [ ] [target-open] Add retrieval eval for current docs.
- [ ] [target-open] Validate Admin help use cases.

## P1 - Documentation And TODO Hygiene

- [x] [done-contract] Create `backlog/CURRENT_0.32.1_TODO.md` with only active gates.
- [x] [done-contract] Move historical 0.26-0.31 TODO fragments into `backlog/HISTORICAL_TODO_ARCHIVE.md`.
- [x] [done-contract] Create `backlog/TODO_CROSSWALK.md` mapping old tasks to current gate, obsolete or closed.
- [ ] [docs-open] Rename or archive stale versioned wiki files so current docs are clearly 0.32.1.
  Progress: `stale-wiki-version-audit-core` inventories the versioned wiki pages and keeps this open until topic crosswalk, prose merge and trash quarantine are complete.
  Progress: `stale-wiki-topic-crosswalk-core` generated `quality/STALE_WIKI_TOPIC_CROSSWALK_0.32.1.md` with review-required mappings for all inventoried versioned wiki pages.
  Progress: `stale-wiki-exact-duplicate-plan-core` generated `quality/STALE_WIKI_EXACT_DUPLICATE_PLAN_0.32.1.md` for byte-equivalent duplicate groups; automatic moves remain disabled.
  Progress: `stale-wiki-canonical-copy-plan-core` copied all twenty-four exact duplicate groups into canonical topics across eight bounded batches and moved only the byte-equivalent duplicate sources into project trash; the gate remains open for non-identical versioned page review and prose merge work.
  Progress: `stale-wiki-prose-merge-plan-core` generated `quality/STALE_WIKI_PROSE_MERGE_PLAN_0.32.1.md` for the remaining 39 prose-review groups and 51 versioned sources; it does not authorize moves.
  Progress: `stale-wiki-single-source-prose-canonicalize-core` has canonicalized eleven missing single-source wiki topics across four bounded batches, hash-checked each canonical copy, and moved only those eleven source pages into project trash; the gate remains open for 28 prose-review groups and 40 versioned sources.
- [x] [done-contract] Replace ambiguous checked contract closures with explicit status labels across active docs. Closed by `todo-status-label-audit-core`.

## Backlog, Not P0

- [x] [done-contract] Add SmartHome local-first privacy evaluation gate. Closed by `smarthome-privacy-evaluation-gate-core`.
- [x] [done-contract] Add MCP/A2A adapter threat model before enabling live adapters. Closed by `mcp-a2a-adapter-threat-model-core`.
- [ ] [target-open] Generate current Epoch Card after successful target model selection.
  Progress: local evidence-shape contract added as `epoch-card-target-readiness-core`; target model-selection evidence is still required before this can close.

## Current Environment Blockers

- [ ] [blocked] Full release readiness still requires Python/pytest, semantic YAML parsing and a usable bash environment. `release-gate-environment-readiness-core` records this as local validation tooling blockers.
- [ ] [blocked] `0.32.0.alpha` cannot be marked release-ready until the rebuilt tarball is extracted and all release gates, including manifest/checksum validation and executable-bit preservation, pass on a prepared validation host.
