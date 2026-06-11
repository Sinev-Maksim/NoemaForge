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
| 2026-06-11 | #87 Codex sandbox + token diet + harvest | M | Fable 5 | ~1h | ~55k | 0 | back-swept reviews #5–#85 into TODO |
| 2026-06-11 | #88 evidence-in-CI (A1) | L | Fable 5 | ~50m | ~55k | 0 | regen-then-verify gate passed own PR first try |
| 2026-06-11 | model routing + this stats file | S | Fable 5 | ~30m | ~30k | 0 | 58 TODO items annotated by script |

**Calibration note (2026-06-11):** every task so far ran on Fable 5 because the
routing policy did not exist yet — these rows are the baseline. From the next
task on, S/M tiers go to Haiku/Sonnet subagents; expect wall time to stay flat
and orchestrator-token usage per S/M task to drop roughly 3–5×. "Review fixes"
counts post-publication reviewer findings that required code changes (Codex
FAIL on #82 is excluded — the finding was a pre-existing tree violation, fixed
in #85).
