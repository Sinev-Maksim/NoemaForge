# NoemaForge — Operational Handoff Context

_Compressed working context (house-cleaning snapshot). NOT canonical project docs._
_Canonical project context: noemaforge/docs/reference/PROJECT_CONTEXT.md_
_Restore: read this file first to rebuild state. Rewritten at every 5-task / ~175k checkpoint._
_Refreshed: 2026-06-03 (after non-runtime Pattern-3 env-default migration, 2 commits → PR #29)._

## Snapshot

| Field | Value |
|-------|-------|
| Project | NoemaForge 0.32.2 hardening — local-first, privacy-first AI OS |
| Target host | BigBro-BOS: Debian Trixie, GNOME/GDM, RTX 3080 Ti |
| Version (SoT) | 0.32.2 — `noemaforge/src/noemaforge_version.py` |
| Current branch | `claude/platform-paths-migration` (PR #29) |
| Integration branch | `release/0.32.2-hardening` |
| Release PR | release→`main` (CLEAN/MERGEABLE) — do NOT mark merge-ready w/o BigBro-BOS target validation |

## Goal & guardrails (see memory: hardening-0.32.2-protocol)

Bring 0.32.2 hardening to a valid, verifiable state; NOT merge-ready without target validation. Roles: Claude=write/fix `claude/*`; Codex=review + some fix PRs (ChatGPT OAuth only, `CODEX_HOME=C:\Users\sinev\.codex`, never API key); CodeRabbit=PR lane; GH Actions on self-hosted `BIGBRO-WIN`; human=merge/target validation. Don't close Issue #1 (already CLOSED). Never claim BigBro-BOS validation unless actually run.

## Open PRs (all → release/0.32.2-hardening unless noted)

- **#29** `claude/platform-paths-migration` (MINE, green/CLEAN) — 8 commits: migrate tool fix + 2 path-migration groups (57 files, Pattern-2) + seclog cross-platform (guard fcntl, helpers, SEL_DIR→platform_paths) + **Pattern-3 env-default migration, 25 files** (61e86f5: 12 non-runtime; 7e5c4c0: 7 model/modelstore, modelstore→`data_root.parent/"modelstore"`; df5e674: 4 independent `*_runtime` state dirs; 13dc2fc: 2 firstboot/pipeline bootstrap + adds missing _pp import to firstboot_progress_runtime). **Non-socket, non-#26 Pattern-3 surface fully closed.** Only deferrals remain: `/run/noemaforge/*.sock` sockets + the 2 model-selection/evolution `*_runtime` files.
- **#27** `claude/pr23-coderabbit-fixes` (MINE, green/CLEAN, NOT merged) — event_log rotation, fixed orchestration_state test stub (ImportError), narrowed except, AGENTS.md allowlist.
- **#26** `codex/system-evolution-portability` (CODEX) — centralizes self-evolution paths; touches `code_evolution_loop.py`, `platform_paths.py`, `model_evolution_runtime.py`, `dev_team_runtime.py`, `runtime_observer_cards_runtime.py`, `startup_preflight.py`, `admin_gui_server.py`. **OVERLAPS my Task #3 Pattern-1 + Task #4 — avoid conflict.**
- **#28** `codex/fix-27-release-evidence-guard` (CODEX) — manifest checksum gate; **overlaps my PR #27 files** (AGENTS.md, docs-hygiene-policy, manifest-checksum-policy, event_log, tests). #27↔#28 will conflict at merge (human/Codex resolves).
- **#25** `coderabbitai/utg/...` → **main** — CodeRabbit-generated unit tests. Outside release queue.

## Task status

- **#1 DONE** — PR23 findings (all fixed; verified by running tests; landed PR #27).
- **#2 DONE** — Path migration redo (tool fixed, 57 files, PR #29).
- **#3 IN PROGRESS** — System independence. DONE: seclog fcntl guard + SEL_DIR (PR #29). Unix-only import audit: `fcntl` was the only module-level blocker (seclog; memsentinel imported it). DONE: **Pattern-3 env-get-with-hardcoded-default fully migrated except deferrals** (25 files, commits 61e86f5 / 7e5c4c0 / df5e674 / 13dc2fc). Independent `*_runtime` state dirs (code_qa, selftest, team_member, wiki_patch, firstboot_progress, pipeline) DONE. REMAINING: (a) **#26-domain `*_runtime`**: admin_runtime:52 + model_selection_runtime:39 (both `NOEMAFORGE_MODEL_SELECTION_STATE`/`MODEL_EVOLUTION_STATE` → should adopt `_pp.model_selection_state_dir`/`model_evolution_state_dir`; deferred until #26 merges). (b) **Socket defaults** `/run/noemaforge/*.sock` (gateway×3: model_scorecards:139, surgeon_auto:92, team_scorecards:79; gateway: noemaforge_llm_client:70; toolproxy: roles/role_entry:460; + non-env sock-dir literals in llm_backends_manager, prestart, bootdoctor) — deferred (Linux tmpfs, must sync w/ Go gateway, no Windows equiv → cross-component task). (c) **Non-env literals** (function-arg defaults, dict policy defaults, `or`-fallbacks, autodoc comments) — separate broader pass, lower priority. Verified final-state grep: only (a)+(b) socket/selection lines remain.
- **#4 PENDING** — Evolution/Code-evolution (`code_evolution_loop.py`) — **gated on Codex #26 (touches that file)**; coordinate before editing.

## Next resume step

1. Check PR #29 CI after the latest commits (`gh pr checks 29`); read any Codex/CodeRabbit comments and fix. Pattern-3 (non-socket/non-#26) is now fully closed.
2. Check if Codex #26/#28 merged (`gh pr list`). If #26 merged → rebase `claude/*` off updated release, then migrate the **2 #26-domain `*_runtime`** files (admin_runtime:52, model_selection_runtime:39) using `_pp.model_selection_state_dir`/`model_evolution_state_dir` per #26's convention; then Task #4.
3. If #26 still open → next non-conflicting batch is remaining-c (non-env literals: dict policy defaults / `or`-fallbacks / function-arg defaults) in NON-#26/#28 files. Higher-touch/nuanced — go file-by-file, verify each (note: function-level `_pp` usage is NOT caught by import-smoke alone; check `hasattr(mod,'_pp')` or that the import is module-level). compileall + import-smoke; commit small; push.
4. Socket defaults (remaining-b) need cross-component coordination (Go gateway) — leave for human/dedicated task; do NOT migrate unilaterally.
5. Optionally ask human whether to merge my #27/#29.

## Operative rules

- Never commit to `main`; `claude/*` branch → PR into `release/0.32.2-hardening`; logical chunks (not one giant commit).
- Commit msgs: English conventional `type(scope): ...` + trailer `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. PR/issue prose in **Russian**.
- Pre-commit self-check (Windows-safe): `py -3 -c "import compileall,sys; sys.exit(0 if compileall.compile_dir('noemaforge/src',quiet=1,force=True) else 1)"`, `git diff --check`, `git status --short`, + targeted unittests/import-smoke. Commit only if green.
- Version 0.32.2 everywhere; no hardcoded version literals outside the version module; no `RUNTIME_VERSION=` outside it.
- Display safety: model-selection / heavy-GPU commands MUST carry `--keep-display`.
- No `.pyc`/`__pycache__` in git (`$env:PYTHONPYCACHEPREFIX="$env:TEMP\nf_pyc"`). Markdown only under `noemaforge/docs/**`,`helpers/`,`prelaunch/` + allowlisted root tooling (CLAUDE.md, README.md, context.md, AGENTS.md).
- TODO.md + CLAUDE_REVIEW_QUEUE are Codex's lane — don't edit; use this file for resume.

## Environment notes (Windows dev host)

- PowerShell primary; `py -3`. Bash tool fails here (fork errors). `gh` CLI auth = Sinev-Maksim. github MCP NOT loaded. In PS, `"$n:"` needs `${n}`.
- CI "Quality gate" only `py_compile`s — does NOT run unit tests; run targeted unittests locally. Avoid monolithic pytest (pipeline_runtime hang).
- `manifest-checksum-exclusion` runtime test fails locally on a pre-existing ~947-file stale-manifest mismatch (Linux SHA256SUMS regen blocker; shadow-mode; Codex #28 addresses the gate).
- Broken original migration backup: `%TEMP%\nf-broken-migration-20260602-142728.patch` + git `stash@{0}` on `codex-fix-pr21-integration`.

## House-cleaning protocol

Every 5 solved tasks or ~175k tokens: rewrite this file (compressed), then `/clear` and restore from it. See memory `house-cleaning-context-protocol`.
