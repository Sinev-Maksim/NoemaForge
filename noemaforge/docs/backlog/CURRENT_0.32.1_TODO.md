# Current 0.32.1 TODO

This file is the detailed active gate list for 0.32.1. It intentionally contains only active gates and evidence requirements; historical fragments live in `HISTORICAL_TODO_ARCHIVE.md`.

## P0 - Boot, Display And Storage Safety

- [ ] [target-open] Validate 0.32.1 install without display blackout.
  Evidence:
  - `systemctl get-default = graphical.target`
  - display-manager/GDM active before and after install
  - no first-start path stops display-manager without explicit `--allow-display-stop`
  - Ctrl+C / abort path works

- [ ] [target-open] Validate first-start dry-run keep-display.
  Command:
  - `sudo noemaforge first-start --full_composite 4 --dry-run --keep-display ...`
  Evidence:
  - monitor remains active
  - no headless transition
  - no GDM stop
  - progress artifacts created

- [ ] [blocked] Validate real first-start keep-display only after storage/journald health is clean.
  Blocked by:
  - no `dmesg` I/O errors
  - writable `/var/log` or volatile journal configured
  - no kernel panic after reboot

- [ ] [target-open] Add and validate journald/storage preflight before heavy model selection.
  Required checks:
  - `df -h`
  - `df -i`
  - `touch /var/tmp/noemaforge-write-test`
  - journal write/rotate smoke
  - `dmesg` I/O error scan
  - rootfs read-write check

- [ ] [target-open] Validate safe-load rescue scripts on target machine.
  Evidence:
  - script path from shared disk
  - restore boot GUI result
  - journald volatile fallback result
  - NoemaForge services masked/stopped
  - successful reboot to GUI

## P0 - Admin Chat And Routing

- [ ] [target-open] Verify Admin main chat behaves like a chat, not only router fallback.
  Test messages:
  - `Привет, как живёшь?`
  - `Кто ты?`
  - `Что ты умеешь сейчас?`
  - `Отвечай на русском`
  Expected:
  - no public MWP launch
  - conversational reply
  - locale respected
  - backend message stored

- [ ] [target-open] Verify explicit pipeline commands switch modes correctly.
  Test messages:
  - `Запусти public_mwp по стандартному сценарию`
  - `Запусти evolution по стандартному сценарию`
  - `Оптимизируй модель для dev team`
  Expected:
  - correct route
  - persona switch line
  - artifact/run card
  - no duplicate process after refresh

- [ ] [target-open] Verify Model Selection and Model Evolution stay distinct in chat.
  Expected:
  - model-selection asks/uses `fast|normal|full|full_composite`
  - model-evolution creates baseline/mutation/candidate/scorecard/rollback

## P0 - Stateful GUI Jobs

- [ ] [target-open] Verify Continue model selection is idempotent after refresh.
  Expected:
  - active job restored
  - second click returns existing job
  - no duplicate first-start / tournament process

- [ ] [target-open] Verify Re-inventory Vault returns privileged job/fallback command.
  Expected:
  - not silent failure
  - clear `needs_privilege` status
  - fallback command visible
  - job state survives refresh

- [ ] [target-open] Verify active jobs are visible in GUI after page reload.
  Required:
  - `job_id`
  - status
  - progress
  - command
  - cancel/abort action

## P0 - Runtime Service Safety

- [ ] [target-open] Validate `noemaforge-llm-gateway` service.
  Evidence:
  - `/run/noemaforge/llm/gateway.sock`
  - no legacy runtime socket dependency
  - service status clean
  - journal clean

- [ ] [target-open] Validate `noemaforge-llama@main` manual start/stop.
  Evidence:
  - backend socket created
  - smoke result
  - stop removes socket
  - no display side effects

- [ ] [target-open] Validate ToolProxy capability issue/verify and `llm.chat` smoke.
  Evidence:
  - token issue
  - token verify
  - `llm.chat` local smoke
  - token redaction in archive

## P1 - Telemetry And Product Metrics

- [ ] [target-open] Validate hardware telemetry on the primary target workstation.
  Metrics:
  - CPU temperature
  - GPU temperature
  - GPU VRAM
  - GPU power draw
  - RAM / swap
  - disk usage
  - battery if present

- [ ] [target-open] Validate runtime telemetry.
  Metrics:
  - active model
  - active persona
  - CPU/GPU policy
  - backend device
  - RAM/VRAM current and peak
  - latency if available

- [ ] [target-open] Validate product metrics for Dev Team.
  Required:
  - `metrics_before.json`
  - `metrics_after.json`
  - diff/patch
  - tests before/after
  - no fake quality claim for creative media

## P1 - Grounded Admin And Docs RAG

- [ ] [target-open] Build and test local docs/wiki RAG index.
  Expected:
  - answers cite local docs/wiki paths
  - use-case help uses docs, not canned fallback
  - missing knowledge is reported explicitly

- [ ] [target-open] Add retrieval eval for current docs.
  Metrics:
  - retrieval hit rate
  - citation coverage
  - groundedness
  - answer helpfulness

- [ ] [target-open] Validate Admin help use cases.
  Examples:
  - `что значит оптимизируй модель для dev team?`
  - `что такое эпоха?`
  - `что значит full_composite?`

## P1 - Documentation And TODO Hygiene

- [x] [done-contract] Create `CURRENT_0.32.1_TODO.md` with only active gates.
- [x] [done-contract] Move historical 0.26-0.31 TODO fragments into `HISTORICAL_TODO_ARCHIVE.md`.
- [x] [done-contract] Create `TODO_CROSSWALK.md` mapping old tasks to current gate / obsolete / closed.
- [ ] [docs-open] Rename or archive stale versioned wiki files so current docs are clearly 0.32.1.
  Progress:
  - `stale-wiki-version-audit-core` inventories stale versioned wiki filenames and blocks completion until each page has a canonical topic crosswalk, unique prose is merged, and obsolete source files are moved to project trash.
  - `stale-wiki-topic-crosswalk-core` generated the first canonical topic crosswalk for 75 inventoried pages; the task remains open until review, prose merge, redirect/crosswalk preservation and quarantine are complete.
  - `stale-wiki-exact-duplicate-plan-core` identified 24 exact duplicate groups and 24 duplicate sources that are candidates for review-before-trash; no files were moved automatically.
  - `stale-wiki-canonical-copy-plan-core` processed all exact-duplicate batches: twenty-four canonical topic pages were created from retained review sources, and twenty-four byte-equivalent duplicate sources were moved to project trash after target-path verification. The exact duplicate plan is now zero; remaining versioned wiki pages are non-identical and still require prose review.
  - `stale-wiki-prose-merge-plan-core` generated the non-identical prose merge plan for 39 remaining canonical topics and 51 versioned source pages, with `move_sources_to_trash=false` until unique prose is reviewed and integrated.
  - `stale-wiki-single-source-prose-canonicalize-core` completed four bounded single-source prose batches: eleven missing canonical wiki topics were created from their only source, byte-for-byte hashes were verified, and the eleven versioned source pages were moved into project trash. The gate remains open for 28 prose-review groups and 40 versioned sources.
- [x] [done-contract] Replace ambiguous checked contract closures with status labels: `done-contract`, `done-runtime`, `target-open`, `roadmap`. Closed by `todo-status-label-audit-core`.

## Backlog, Not P0

- [x] [done-contract] Add SmartHome local-first privacy evaluation gate. Closed by `smarthome-privacy-evaluation-gate-core`.
  Scope:
  - device source trusted/simulated/unverified
  - camera local-only policy
  - no cloud upload by default
  - automation audit trail
  - emergency all-automation pause

- [x] [done-contract] Add MCP/A2A adapter threat model before enabling live adapters. Closed by `mcp-a2a-adapter-threat-model-core`.
  Required:
  - zero-trust adapter manifest
  - deny-by-default tool exposure
  - per-adapter capability scopes
  - SR/SSR review

- [ ] [target-open] Generate current Epoch Card after successful target model selection.
  Progress:
  - `epoch-card-target-readiness-core` now defines the required evidence shape and blocks card generation without target model-selection evidence.
  Include:
  - selected model
  - role map
  - staffing state
  - scorecards
  - rollback plan
  - approval evidence

Status note: `[roadmap]` remains a valid label for planned backlog work, but the current non-P0 roadmap items in this section have either been closed at contract level or require target evidence.
