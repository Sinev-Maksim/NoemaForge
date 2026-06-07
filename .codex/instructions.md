# NoemaForge — Codex instructions

You are reviewing NoemaForge, a local-first AI OS.
Read this file before starting any review.

## Repository context

- Integration branch: the PR's base branch — the active release line (e.g.
  `release/0.32.2-hardening` or `release/0.33.0-dev`). The review workflow supplies it; do
  not assume a fixed branch.
- Version target: the value in the version source of truth on the branch under review —
  `noemaforge/src/noemaforge_version.py` (`RUNTIME_VERSION`, which reads the canonical
  `VERSION` file). Do NOT assume a fixed version literal such as `0.32.2`.
- Version source of truth: `noemaforge/src/noemaforge_version.py`
- `RUNTIME_VERSION` assignment is only allowed in that file — never elsewhere

## Your role in this pipeline

You receive branches pushed by Claude Code (prefixed `claude/...`).
Your job: review the diff against the PR's base branch (the active release line), flag
issues, and suggest optimizations. Use read-only inspection only — do not modify files or
push commits during the review workflow run.

Workflow:
1. Fetch the base: `git fetch origin <base-branch>` (the workflow provides the base branch)
2. Review the diff: `git diff origin/<base-branch>...HEAD`
3. Report issues found (see gates below)
4. Suggest optimizations as inline comments or proposed code changes

## Review gates — FAIL if any of these:

- Python syntax error in any `.py` file
- `RUNTIME_VERSION =` assigned outside `noemaforge/src/noemaforge_version.py`
- `__pycache__` or `*.pyc`/`*.pyo` added to the git tree
- `return` inside a `finally` block without a comment explaining why
- Forbidden active-text strings present in active files — see
  `noemaforge/configs/docs-hygiene-policy.json` → `forbidden_active_text`
  (the legacy production host name, the stale-content marker, and the legacy
  public-docs path strings)
- Markdown placed outside `noemaforge/docs/**`, `helpers/`, or `prelaunch/`
  (root tooling files are allowlisted by the docs-hygiene policy)
- JSON parse error in any `.json` file
- YAML parse error in any `.yaml`/`.yml` file
- Any of the three canonical `VERSION` files (`VERSION`, `noemaforge/VERSION`,
  `docs/VERSION`) not equal to the version source of truth
  (`noemaforge_version.RUNTIME_VERSION`). Check against the SoT value on the branch under
  review — NOT against a fixed literal such as `0.32.2`. A version that legitimately
  advanced with the release line (e.g. `0.33.0` on `release/0.33.0-dev`) is correct.

## Display safety rule

The production target host runs Debian Trixie with GNOME/GDM and an RTX 3080 Ti.
Any command that starts model selection or heavy GPU work MUST pass
`--keep-display`. Never generate commands that could blank the display.

## Commit style

```text
fix(scope): short description

Types: fix, feat, refactor, test, docs, chore
Reference issue: Closes #N
```

## Do NOT

- Merge to `main` directly
- Create `CHANGELOG_*` or `RELEASE_NOTES_*` files
- Modify `VERSION` files (only the version-bump workflow does this)
- Run privileged GPU commands without `--keep-display`
