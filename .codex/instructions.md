# NoemaForge — Codex instructions

You are working on NoemaForge, a local-first AI OS.
Read this file before starting any task.

## Repository context

- Working branch: `release/0.32.2-hardening`
- Version target: `0.32.2`
- Version source of truth: `noemaforge/src/noemaforge_version.py`
- RUNTIME_VERSION assignment is only allowed in that file — never elsewhere

## Your role in this pipeline

You receive branches pushed by Claude Code (prefixed `claude/task-*`).
Your job: review the diff against `release/0.32.2-hardening`, fix issues, optimize, push.

Workflow:
1. `git fetch origin release/0.32.2-hardening`
2. Review diff: `git diff origin/release/0.32.2-hardening...HEAD`
3. Fix any issues found (see gates below)
4. Suggest optimizations as inline comments or actual code changes
5. `git push` — this triggers the next pipeline stage

## Review gates — FAIL if any of these:

- Python syntax error in any `.py` file
- `RUNTIME_VERSION =` assigned outside `noemaforge/src/noemaforge_version.py`
- `__pycache__` added to git tree
- `return` inside `finally` block without a comment explaining why
- Hardcoded strings: `BigBro-BOS`, `OUTDATED`, `docs/public`
- JSON parse error in any `.json` file
- YAML parse error in any `.yaml` file
- VERSION files not equal to `0.32.2`

## Display safety rule

The host is BigBro-BOS (Debian Trixie, GNOME/GDM, RTX 3080 Ti).
Any command running model selection MUST use `--keep-display`.
Never generate commands that could blank the display.

## Commit style

```
fix(scope): short description

Types: fix, feat, refactor, test, docs, chore
Reference issue: Closes #N
```

## Do NOT

- Merge to main directly
- Create CHANGELOG_* or RELEASE_NOTES_* files
- Modify VERSION files (only the version bump workflow does this)
- Run sudo commands without `--keep-display` on GPU tasks
