# Roadmap and TODO

This roadmap is intentionally short. The previous mixed historical TODO file was moved to `HISTORICAL_TODO_ARCHIVE.md` so current release gates remain readable. For the `0.32.0.alpha` release-gate pass, completed contract work stays recorded only where its gate has passed; target-machine and missing-tool checks remain open or blocked instead of being converted into success language.

## Canonical TODO Files

- `../TODO.md` - short active TODO mirror for operators.
- `CURRENT_0.32.1_TODO.md` - detailed active 0.32.1 gates and evidence requirements.
- `TODO_CROSSWALK.md` - old path/task mapping to current, obsolete, migrated or closed state.
- `HISTORICAL_TODO_ARCHIVE.md` - preserved historical 0.26-0.31 fragments.
- `../quality/TODO_STATUS_RECONCILIATION_0.32.1.md` - machine-readable status audit.

## Roadmap Priorities

### P0 - Target Safety

The next release line is dominated by target-machine safety: boot mode, display-manager preservation, storage health, journal writeability, abort behavior and rescue scripts. Real first-start validation stays blocked until storage and journal health are clean.

### P0 - Admin GUI Behavior

Admin chat must behave like a chat for conversational input, route explicit pipeline/model requests correctly, persist job state across refresh, and prevent duplicate model-selection or first-start processes.

### P0 - Runtime Service Safety

Gateway, main backend and ToolProxy checks remain target-open until service sockets, smoke results, token handling and logs are captured on the target machine without display side effects.

### P1 - Product Evidence

Telemetry, product metrics, docs RAG and grounded Admin help remain active P1 work. These gates must produce local evidence and should not claim creative/media quality without before/after metrics and tests.

### Roadmap Backlog

SmartHome privacy evaluation is closed at contract level by `smarthome-privacy-evaluation-gate-core`: device source labels, camera local-only policy, disabled cloud-upload defaults, automation audit trail and emergency all-automation pause now have local QA and bounded performance coverage. MCP/A2A adapter threat modeling is closed at contract level by `mcp-a2a-adapter-threat-model-core`: live adapters stay disabled by default, tool exposure is explicit-allowlist only, capability scopes are per-adapter and SR/SSR review is required. Epoch Card generation now has `epoch-card-target-readiness-core` to validate selected model, role map, staffing state, scorecards, rollback plan and approval evidence shape, but the TODO remains target-open until real model-selection evidence exists.

## Status Labels

- `target-open`: requires target-machine evidence.
- `blocked`: cannot proceed until the named precondition is resolved.
- `docs-open`: documentation restructuring remains active.
- `done-contract`: contract/documentation structure exists and local gates for that structure passed.
- `done-runtime`: runtime behavior exists and relevant runtime tests passed.
- `roadmap`: planned backlog work, not a current P0 gate.

`todo-status-label-audit-core` now enforces this vocabulary for active TODO files. Historical archives keep old checklist fragments as preserved context, while active TODO and roadmap files must avoid bare checked tasks and unlabeled open tasks.

## Current Release Readiness Constraint

NoemaForge must not claim release readiness until the detailed gates in `CURRENT_0.32.1_TODO.md` pass and `release-gate-environment-readiness-core` confirms that Python/pytest, semantic YAML parsing and bash syntax validation can run on the validation host. The `0.32.0.alpha` archive can still be rebuilt for inspection, but the release status remains blocked if those host tools are unavailable or if post-extraction manifest/checksum, executable-bit, Markdown, forbidden-text or completeness checks fail.

## Publication Workflow

GitHub main repository publication is a separate, reviewable operation after archive verification. The release tree should be committed from a clean extraction or an equivalent allowlisted source tree, with `trash/`, generated caches, previous archives and local extraction folders excluded. The commit or pull request should reference `noemaforge/docs/quality/VERIFICATION_AND_AUDIT.md`, the archive name, and the archive SHA256.

GitHub Wiki publication follows the canonical wiki tree under `noemaforge/docs/wiki`. Pages must be standalone prose articles; raw research documents, source dumps and link-only pages are not wiki upload inputs. Older versioned pages may remain active only while the stale-wiki cleanup gate tracks prose integration, canonical copy confirmation and project-trash quarantine.

## Documentation Completeness Discipline

Completeness is checked topic by topic rather than by file count. The quality report matrix covers TODO-driven autonomous improvement, release gates, Markdown hygiene, changelog uniqueness, deep research integration, repository/wiki publication, Windows PowerShell safety, MultiOS, trust-adaptive governance, Edge/TinyML/OTA, local-first constraints, clean distribution allowlists, trash quarantine, executable bits, manifest/checksum validation, QA/performance requirements, documentation completeness and known blockers. Any partial or missing topic stays as an explicit follow-up until the missing prose or evidence is added.

## Wiki Version Hygiene

`stale-wiki-version-audit-core` inventories older versioned wiki filenames and keeps the cleanup gate open. The safe migration order is: map each page to a canonical topic, merge unique prose into current standalone articles, preserve a crosswalk or redirect note, then move only obsolete source pages to project trash.

`stale-wiki-topic-crosswalk-core` now generates `../quality/STALE_WIKI_TOPIC_CROSSWALK_0.32.1.md`, which maps every inventoried versioned page to a proposed canonical topic and marks each row `needs-review`. This is executable progress, not completion: no wiki source page is moved until prose review and integration are done.

`stale-wiki-exact-duplicate-plan-core` narrows the first safe quarantine candidates by finding byte-equivalent duplicate pages within the crosswalk. The generated duplicate plan keeps `auto_move_allowed=false`, so actual trash moves require canonical-copy confirmation and explicit review.

`stale-wiki-canonical-copy-plan-core` now performs that explicit, bounded move step for exact duplicates only. Eight pulses have copied all twenty-four retained review sources into canonical wiki topic paths, verified each duplicate trash target under project trash, and moved twenty-four byte-equivalent duplicate source files out of the active wiki tree. The exact duplicate plan is now zero; the broader cleanup remains open because non-identical versioned pages still need prose review, integration and quarantine decisions.

`stale-wiki-prose-merge-plan-core` now starts the non-identical cleanup phase without moving files. It groups the remaining versioned wiki pages by canonical topic, records source hashes and word counts, flags missing canonical topics, and keeps every row in `needs-prose-review` with `move_sources_to_trash=false` until unique prose is merged.

`stale-wiki-single-source-prose-canonicalize-core` performs the narrow safe subset of that work. When a canonical topic is absent and exactly one versioned source exists, it copies the source into the canonical topic, verifies the canonical hash, and moves only the source file into project trash. Four bounded batches have canonicalized eleven topics and reduced the active prose queue to 28 groups and 40 source pages; multi-source and canonical-existing topics still require manual prose merge decisions.
