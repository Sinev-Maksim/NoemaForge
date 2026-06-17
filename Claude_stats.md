# Claude execution stats & model-routing calibration

Working telemetry for the Claude-driven development pipeline. One row per
delivered task/PR. Used to recalibrate the effort→model routing (legend in
[`noemaforge/docs/TODO.md`](noemaforge/docs/TODO.md)) when reality diverges
from the plan.

## Routing policy (v1, 2026-06-11)

| Tier | Executor | Typical shape |
|---|---|---|
| S | Haiku 4.5 subagent | mechanical change, ≤2 files, spec fits in one paragraph |
| M | Sonnet 4.6 subagent | localized feature/fix + its tests, single subsystem |
| L | Opus 4.8 / orchestrator | cross-file design, refactors, CI/architecture |
| XL | Fable 5 orchestrator | umbrella tracks decomposed into S/M/L slices |

Rules:

1. The orchestrator (Fable/Opus) decomposes, writes the task spec, reviews the
   subagent's diff, and owns the PR. Subagents execute.
2. **Auto-escalation:** two failed iterations (tests or review findings) at a
   tier escalate the task one tier up; log the miss here.
3. **De-escalation:** if an M/L task turns out mechanical in hindsight, note it
   so similar future tasks route lower.
4. Verification (gates, pristine-worktree checks) always runs at orchestrator
   level — never delegated below M.

## Token-economy rules (applies to every tier, including the orchestrator)

- Read narrow: `grep` with limits / targeted `Read` offsets instead of whole
  files; never re-read a file just edited.
- Batch mechanical edits through a script instead of many per-line edit calls.
- Delegate bulk scanning/searches to subagents (their intermediate context does
  not bill the orchestrator's window) — but don't spawn for one-liners.
- Evidence files never enter prompts (CI regenerates them; the Codex prompt
  filter strips them — PR #87).
- Review bots get lean diffs; evidence-only pushes skip model review entirely.
- Estimated token figures below are **self-estimates** (the model cannot see
  billing); treat trends, not absolutes.

## Stats

| Date | Task / PR | Tier | Model(s) | Wall time | Est. tokens | Review fixes | Notes |
|---|---|---|---|---|---|---|---|
| 2026-06-10 | #79 UAT reports + roadmap + TODO | L | Fable 5 | ~2.5h | ~160k | 0 | freeze-folder forensics dominated time |
| 2026-06-10 | #80 wiki canonicalization (141 pages, gate, publish) | L | Fable 5 | ~2h | ~150k | 0 | dump extraction scripted; 14 lost pages recovered |
| 2026-06-10 | #81 systemd canonical tree (B1) | M→L | Fable 5 | ~1h | ~60k | 0 | resolver analysis made config edits unnecessary |
| 2026-06-10 | #82 accepted-decisions TODO | S | Fable 5 | ~20m | ~25k | 0 | section later lost in #86 merge; restored in #88 |
| 2026-06-10 | #83 wiki-check portable sort hotfix | S | Fable 5 | ~30m | ~30k | 0 | platform-dependent Path sort; found via CI fail |
| 2026-06-11 | #84 Codex English prompt | S | Fable 5 | ~15m | ~15k | 0 | one-line prompt pin |
| 2026-06-11 | #85 hygiene prereqs + gate (A2) | M | Fable 5 | ~45m | ~50k | 0 | also fixed 3 registry refs; 5 red tests cleared |
| 2026-06-11 | GH English translation sweep (11 PR bodies + 7 comments) | S | Fable 5 | ~40m | ~45k | 0 | API edits; bot verdicts left untouched (audit trail) |
| 2026-06-11 | #86 release→main conflict resolution | L | Fable 5 | ~1h | ~70k | 0 | manual installer merge; forbidden-literal test fix |
| 2026-06-11 | #87 Codex sandbox + token diet + harvest | M | Fable 5 | ~1h | ~55k | 2 | back-swept reviews #5–#85 into TODO; two Codex FAIL rounds caught real isolation gaps (escalation rule fired: S retry → M approach change) |
| 2026-06-11 | #87 fix-up v1: token scoped away from codex exec | S | Fable 5 | ~20m | ~20k | — | job-level GITHUB_TOKEN removed; filter regex generalized |
| 2026-06-11 | #87 fix-up v2: enforced read-only + pre-flight digest | M | Fable 5 | ~40m | ~35k | — | approach change on 2nd Codex FAIL; filter → tested script |
| 2026-06-11 | A3 ledger queue-not-cancel (quickwins-t1) | S | Haiku 4.5 → Fable review | 53s agent | 23.8k | 1 | draft dropped the issues trigger (semantic loss); orchestrator restored it + queue strategy — root cause was event bursts, not duplicate triggers |
| 2026-06-11 | C3 caps.py timezone-aware timestamps (quickwins-t1) | S | Haiku 4.5 → Fable review | 95s agent | 31.0k | 0 | clean: Z-format preserved, naive-token back-compat, tests green; 55 remaining utcnow files left for repo-wide pass |
| 2026-06-13 | D-003 admin state glossary (#99) | M | Sonnet 4.6 → Fable review | ~5m agent | 48.8k | 1 | agent scope-crept into the shared has_explicit_control_request router (would break smalltalk-route contract); reverted + localized a verb-only guard; 0 regressions across 171 admin tests |
| 2026-06-11 | #88 evidence-in-CI (A1) | L | Fable 5 | ~50m | ~55k | 0 | regen-then-verify gate passed own PR first try |
| 2026-06-11 | model routing + this stats file | S | Fable 5 | ~30m | ~30k | 0 | 58 TODO items annotated by script |
| 2026-06-11 | C1 admin-gui route split (#94) | L | Opus 4.8 → Fable review | 17.5m agent | 168.8k | 0 | 61/61 endpoint parity; per-file suites identical; found pre-existing group-collection ImportError (reproduced on base) |
| 2026-06-11 | E pin actions + dependabot (#93) | S | Sonnet 4.6 → Fable review | 4.6m agent | 56.4k | 1 | SHAs all correct (3/3 spot-check), but main-based agent worktree would have rolled back #87/#88 workflow changes — re-applied as pure pin substitutions |
| 2026-06-11 | A3 ledger queue-not-cancel (#90) | S | Haiku 4.5 → Fable review | 53s agent | 23.8k | 1 | draft dropped the issues trigger; orchestrator restored it — real cause was event bursts |
| 2026-06-11 | C3 caps.py timezone-aware (#90) | S | Haiku 4.5 → Fable review | 95s agent | 31.0k | 0 | clean: Z-format kept, naive-token back-compat, tests green |
| 2026-06-11 | A1 follow-ups (#91, merge-race salvage) | S | Fable 5 | ~15m | ~12k | — | merge=ours + acceptance regen re-landed; evidence-refresh self-heal confirmed 2x |
| 2026-06-11 | C4 minimal pyproject.toml (#92) | S | Sonnet 4.6 → Fable review | 48s agent | 20.1k | 0 | clean: dynamic version from SoT, packages=[], dev/vector/gateway extras |
| 2026-06-11 | A5 CLAUDE.md rewrite (#92) | M | Fable 5 (orchestrator-context task) | ~15m | ~8k | — | full rewrite: A1 lifecycle, English-only, routing, canonical sources |

**Calibration note (2026-06-11):** every task so far ran on Fable 5 because the
routing policy did not exist yet — these rows are the baseline. From the next
task on, S/M tiers go to Haiku/Sonnet subagents; expect wall time to stay flat
and orchestrator-token usage per S/M task to drop roughly 3–5×. "Review fixes"
counts post-publication reviewer findings that required code changes (Codex
FAIL on #82 is excluded — the finding was a pre-existing tree violation, fixed
in #85).
| 2026-06-11 | A4 version-agnostic installer (#96) | M | Sonnet 4.6 -> Fable takeover | ~1h stall + 35m | ~45k (Fable) | 2 | agent stalled after a clean draft; escalation; resweep + Codex FAIL fix (dynamic version test) |
| 2026-06-14 | #100 evidence pre-release-only + working-tree release-gen | L | Fable 5 | ~4h | ~190k | 4 | owner directive: untrack evidence, no dev gate; 4 Codex FAIL rounds, each a real release-path bug: (1) git-index regen assumed committed files -> working-tree rewrite + bootstrap + templates; (2) templates hardcoded 0.32.2 + acceptance test git-index + latent unguarded MANIFEST read -> derive versions from release.json + working-tree + skip guards; (3) stale git-index docstring + qa-test verified real tree via git-index -> refresh + guard; (4) publish-evidence bundle dir polluted the verify walk + shipped only 5/8 evidence files -> verify-before-assemble (report to RUNNER_TEMP) + complete 8-file set; every round clean-worktree verified ok=true (neg-test confirmed the pollution bug) |
| 2026-06-16 | 0.33.3 strategic roadmap (validate + add) | L | Opus 4.8 | ~40m | ~70k | 0 | validated 9 proposed tracks against the codebase — most mature existing validation-contract runtimes (artifact_registry_table / memory_budgeted_retrieval / caps / sandbox / task_workflow / role_tournament), not greenfield; added 0.33.3 milestone to docs/ROADMAP.md + effort-annotated breakdown with per-item foundations to noemaforge/docs/TODO.md; hygiene+wiki gates green |
| 2026-06-17 | UAT one-button runner (noemaforge uat run) | M | Opus 4.8 | ~50m | ~90k | 0 | new src/uat_runtime.py: record events -> (launch GUI) -> run all pipelines saving artifacts -> stop recording -> evidence bundle (manifest/summary/events/per-pipeline run_dir); bin/noemaforge uat dispatch; integration test; ops doc. Validated headless: 90/90 pipelines, 2826 artifacts, session events |
