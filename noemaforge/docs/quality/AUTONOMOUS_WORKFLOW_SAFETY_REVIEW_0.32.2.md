# Autonomous Workflow Safety Review — NoemaForge 0.32.2

<!-- === NoemaForge File Header ===
File: noemaforge/docs/quality/AUTONOMOUS_WORKFLOW_SAFETY_REVIEW_0.32.2.md
Zone: release/quality
Version: 0.32.2
Created: 2026-05-28
Modified: 2026-05-28
Purpose: Record safety review findings for the autonomous pipeline CI workflows
  added during 0.32.2 development. Documents risks, mitigations and operator actions required.
=== End NoemaForge File Header === -->

## Scope

Files reviewed:

| File | Status |
|---|---|
| `.github/workflows/autonomous-pipeline.yml` | Reviewed 2026-05-28 |
| `.github/workflows/autonomous-pipeline-v2.yml` | Reviewed 2026-05-28 |
| `.github/workflows/qa-version-bump.yml` | Reviewed 2026-05-28 |
| `.codex/instructions.md` | Not yet committed — untracked |
| `CLAUDE.md` | Reviewed 2026-05-28 (no risks) |

---

## CLAUDE.md — PASS

`CLAUDE.md` contains project conventions for Claude Code. No autonomous network access, no auto-push, no secret handling. Compliant.

---

## `qa-version-bump.yml` — NEEDS OPERATOR ACTION

### Description
Triggered by `workflow_dispatch` (manual) or `workflow_call` (from batch-counter). Runs all gate checks, bumps `0.32.2.x` patch counter, commits, pushes directly to `release/0.32.2-hardening`, and creates a Git tag.

### Risks

| ID | Severity | Finding |
|---|---|---|
| QVB-1 | **HIGH** | `git push origin release/0.32.2-hardening` directly — bypasses PR review for the release branch. |
| QVB-2 | **MEDIUM** | Automatic Git tag creation (`refs/tags/v0.32.2.x`) — tags published without human sign-off. |
| QVB-3 | **LOW** | Auto-creates GitHub issues on failure — benign but noisy if misconfigured. |
| QVB-4 | **LOW** | No explicit `permissions:` block — inherits repository default (write). Recommend `contents: write` explicitly scoped. |

### Required operator actions
- [ ] **QVB-1**: Change the push step to open a PR against `release/0.32.2-hardening` instead of pushing directly. Use `gh pr create` or `actions/github-script` to open the PR and require human merge.
- [ ] **QVB-2**: Gate tag creation on explicit `workflow_dispatch` input (`create_tag: true`) or a manual approval step rather than auto-tagging on every bump.
- [ ] **QVB-4**: Add `permissions: { contents: write, pull-requests: write }` to narrow token scope.

---

## `autonomous-pipeline.yml` — NEEDS OPERATOR ACTION

### Description
Triggers on `push` to `claude/**` and `codex/**` branches. Stage 1: lint/compile on `ubuntu-latest`. Stage 2: Codex CLI review on `self-hosted, Windows` runner (the operator's own target workstation or dev machine). Stage 3: batch-counter that auto-triggers `qa-version-bump.yml`.

### Risks

| ID | Severity | Finding |
|---|---|---|
| AP-1 | **HIGH** | Self-hosted Windows runner reads `C:\Users\sinev\.codex\auth.json` — the operator's personal ChatGPT OAuth token. If a malicious branch is pushed to `claude/**`, Stage 2 runs on the operator's machine with access to home directory credentials. |
| AP-2 | **HIGH** | Stage 3 batch-counter auto-triggers `qa-version-bump.yml` which pushes directly to `release/0.32.2-hardening` — no human approval in the chain. |
| AP-3 | **MEDIUM** | No explicit `permissions:` at workflow level — jobs inherit repo-level write access. |
| AP-4 | **MEDIUM** | Batch-counter logic counts all commits on all `codex/**` branches in the last 24 hours, not just the current batch. A burst of commits from any codex branch can unexpectedly trigger the version bump. |
| AP-5 | **LOW** | `github-actions[bot]` git config is set in `qa-version-bump.yml` — acceptable but the committer identity should be documented for audit trail. |

### Required operator actions
- [ ] **AP-1**: Add a branch protection rule on `claude/**` that only allows pushes from trusted collaborators. Consider adding a manual approval gate before Stage 2 runs, or restrict the self-hosted runner to only run after a `workflow_dispatch` approval. Do not expose `auth.json` to arbitrary pushes.
- [ ] **AP-2**: Break the auto-trigger chain: make `batch-counter` open a GitHub issue or PR comment instead of calling `workflow_dispatch` on `qa-version-bump.yml` automatically. Require a human to approve the version bump.
- [ ] **AP-3**: Add `permissions: { contents: read, pull-requests: write }` to the workflow and `contents: write` only to the commit/push job.
- [ ] **AP-4**: Replace the 24-hour window count with a dedicated counter file (e.g., `.github/batch-counter.json`) that is reset explicitly, not inferred from time windows.

---

## `autonomous-pipeline-v2.yml` — NEEDS OPERATOR ACTION

### Description
Triggers on `push` to `claude/**` branches. Runs on `self-hosted, linux, codex` runner (target workstation). Stage 2 runs `codex exec --approval-mode auto-edit` which allows Codex to modify files on the runner.

### Risks

| ID | Severity | Finding |
|---|---|---|
| APV2-1 | **CRITICAL** | `codex exec --approval-mode auto-edit` allows Codex to edit files on the self-hosted Linux runner without human review. A malicious prompt or injected content in the diff could cause Codex to modify arbitrary files on the target workstation. |
| APV2-2 | **HIGH** | Same batch-counter → `qa-version-bump.yml` auto-trigger chain as `autonomous-pipeline.yml`. |
| APV2-3 | **HIGH** | No permissions block — inherits write access. |
| APV2-4 | **MEDIUM** | Review output written to `/tmp/codex_review.md` and `/tmp/codex_run.log` — tmp files not cleaned up between runs. On a shared self-hosted runner this could leak review content across runs. |

### Required operator actions
- [ ] **APV2-1 CRITICAL**: Change `--approval-mode auto-edit` to `--approval-mode suggest` (read-only suggestions only) or remove the `--approval-mode` flag entirely so Codex requires explicit approval for any file modification. **This is the highest-priority fix.**
- [ ] **APV2-2**: Same as AP-2 above — break the auto-trigger chain.
- [ ] **APV2-3**: Add explicit `permissions:` blocks.
- [ ] **APV2-4**: Add a cleanup step: `rm -f /tmp/codex_review.md /tmp/codex_run.log`.

---

## `.github/workflows/premerge-quality.yml` — NEW (PASS)

Added 2026-05-28 in claude/task-15-frontend-event-polling. This workflow:
- Triggers only on `pull_request` events (read-only trigger)
- Has `permissions: { contents: read, pull-requests: read }` (minimal)
- Runs no auto-commits, no auto-push, no auto-tags
- All steps are read-only quality checks

No risks identified.

---

## Summary

| File | Risk level | Blocking? |
|---|---|---|
| `CLAUDE.md` | None | No |
| `premerge-quality.yml` | None | No |
| `qa-version-bump.yml` | HIGH | Recommend fix before enabling workflow |
| `autonomous-pipeline.yml` | HIGH (self-hosted credential exposure) | Recommend fix before enabling |
| `autonomous-pipeline-v2.yml` | **CRITICAL** (`auto-edit` on self-hosted) | **Fix before any use** |

### Recommended immediate actions (operator)

1. `autonomous-pipeline-v2.yml` line 99: change `--approval-mode auto-edit` to `--approval-mode suggest`.
2. `qa-version-bump.yml`: change the push step to open a PR instead of direct push.
3. `autonomous-pipeline.yml` + `autonomous-pipeline-v2.yml`: break the auto-trigger chain for version bumps.
4. Add `permissions:` blocks to all three workflows.

These workflows are currently **untracked** (not committed to the branch) as of 2026-05-28. The fixes above should be applied before they are committed and enabled.
