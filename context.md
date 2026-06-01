# NoemaForge — Operational Handoff Context

_Generated: 2026-06-01 by release-gate skill execution._
_This file is the operational handoff context, NOT canonical project docs._
_Canonical project context: noemaforge/docs/reference/PROJECT_CONTEXT.md_

---

## Current State

| Field | Value |
|-------|-------|
| Project | NoemaForge 0.32.2 hardening |
| Branch | `claude/task-50-server-epoch` |
| Base branch | `release/0.32.2-hardening` |
| Commits ahead of upstream | 34 |
| CURRENT_VERSION | 0.32.2 |
| TARGET (release) | 0.32.2 |
| Last released | 0.32.1 (2026-05-21) |

## Last 10 Commits (most recent first)

```
cd135bf docs(todo): twentieth analysis cycle — tasks 94-95 done, all Windows tasks closed
5b57adb fix(server): tasks_list lock + save_message conv lock (tasks 94-95)
1fcf971 fix(session-store): _append_event acquires _lock internally (task-93)
87cf603 docs(todo): nineteenth analysis cycle — tasks 89-92 done, task-93 proposed
5306b2b fix(server): _tasks_lock, per-job normalize, save() no double-event, norm_target init (tasks 89-92)
07ae1e4 docs(todo): mark tasks 87-88 done in eighteenth analysis cycle
2106cd9 fix(utils): _read_json stderr warning + normalize_job_progress helper (tasks 87-88)
d48d630 docs(todo): eighteenth analysis cycle — tasks 81-86 done, tasks 87-88 proposed
cd827fe fix(jobs): job_get lock+normalize, job_cancel normalize+conditional-write, save_message dedup, plugin_runner _safe_int (tasks 81-86)
14e7670 fix(utils): deduplicate _safe_int — lsp_facade/mcp_router import from orchestration_state (task-80)
```

## Uncommitted Changes (working tree)

Tracked files modified but not staged (mostly manifests/checksums updated externally):
- MANIFEST.json, MANIFEST.json.sha256, MANIFEST.sha256
- SHA256SUMS, SHA256SUMS.sha256
- docs/MANIFEST.json, docs/MANIFEST.json.sha256
- noemaforge/checksums/SHA256SUMS
- noemaforge/configs/docs-hygiene-policy.json
- noemaforge/docs/MANIFEST.json, noemaforge/docs/MANIFEST.json.sha256
- noemaforge/docs/backlog/ROADMAP_AND_TODO.md
- noemaforge/docs/history/CHANGELOG.md
- noemaforge/docs/quality/AUTONOMOUS_WORKFLOW_SAFETY_REVIEW_0.32.2.md
- noemaforge/docs/quality/CLAUDE_REVIEW_QUEUE_0.32.2.md
- noemaforge/docs/reference/PROJECT_CONTEXT.md
- noemaforge/docs/wiki/strict-markdown-placement-0.31.21.alpha.md
- noemaforge/release/release-v0.32.2.yaml
- noemaforge/src/docs_hygiene_runtime.py
- noemaforge/tests/test_docs_hygiene_performance.py
- noemaforge/tests/test_docs_hygiene_runtime.py
- prelaunch/evidence/ci-model-gates/release_evidence_0.32.2.json

Untracked:
- .coderabbit.yaml
- ".codex/Codex instructions.md"
- .cursor/
- .cursorignore
- docs/ROADMAP.md

## Hardening Sprint Summary (tasks 73-95)

All Windows-accessible hardening tasks complete (183 tests, all green). Key areas:
- Admin GUI job state machine: final-state guard, _jobs_lock, session_id clamp
- Concurrency: _tasks_lock, _conv_lock, _jobs_lock across all R-M-W paths
- Schema: normalize_job_record + normalize_job_progress throughout all endpoints
- Session: no double-event, _append_event self-locking
- Utils: _safe_int deduplicated (orchestration_state is canonical), _read_json stderr

## Known Blockers

1. SHA256SUMS regeneration — requires Linux target host after branch merges
2. bash -n for shell scripts — requires bash on Linux
3. Manual smoke tests — requires target host (GDM, GPU, live GUI)
4. PR #2 description — manual action via GitHub web UI
5. JobManager.prune_terminal() — blocked on tasks 10/11 merging
6. _run_preflight() exception reporting — blocked on tasks 10/11 merging
7. Executable-bit verification — requires tar extraction on Linux

## Active GitHub State

- Working branch: claude/task-50-server-epoch (34 commits ahead of upstream)
- Integration branch: release/0.32.2-hardening
- Release PR: #2 (release/0.32.2-hardening → main)

## Next Safe Actions

1. Commit all unstaged manifest/doc changes on task branch
2. Push claude/task-50-server-epoch to GitHub
3. Open PR: task branch → release/0.32.2-hardening
4. After all task PRs merge: regenerate SHA256SUMS on target host
5. Manual smoke tests on target host
6. Merge release branch to main, tag v0.32.2

## Windows PowerShell Notes

- Use `py -3` not `python3`
- Git credential extraction prohibited; GitHub via MCP only
- Archive: use `tar` (Win10/11) or 7-Zip; executable bits need manifest.txt workaround
- Bash commands not available (WSL not assumed); use PowerShell equivalents
