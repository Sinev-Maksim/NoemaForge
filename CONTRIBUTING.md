# Contributing to NoemaForge

Thank you for your interest in contributing.

## How to contribute

- **Bug reports / feature requests:** open a GitHub issue.
- **Code contributions:** fork the repository, create a branch off `release/0.32.2-hardening`
  (or the current release branch), and open a pull request targeting that branch — **never
  directly to `main`**.
- **Documentation:** docs live under `noemaforge/docs/` (allowed subfolders) and the root
  `README.md`. Markdown outside those locations is not permitted.

## Branch / PR conventions

- Branch names: `claude/task-N-slug` (automated), `fix/...`, `feat/...`, `docs/...`.
- Target: always `release/0.32.2-hardening` (or the current release branch), not `main`.
- Commit messages: English, conventional format `type(scope): short description`.
- One PR = one complete feature or fix.

## Quality gate

Every PR must pass the **Premerge quality gate** (`premerge-quality.yml`):
`py_compile`, no `RUNTIME_VERSION=` outside the version module, `VERSION` files = 0.32.2, JSON/YAML
parse, no tracked `__pycache__`, and the manifest/checksum evidence gate. If the checksum gate
fails, regenerate `SHA256SUMS` / `MANIFEST.json` with the regen script and push again — it is a
consistency check, not a code defect.

## Security issues

Do **not** open a public issue for a security vulnerability. See [`SECURITY.md`](SECURITY.md).

## Code style

- Python: follow existing style; no new external dependencies without discussion.
- Shell: POSIX-compatible where possible; add `bash -n` self-check.
- All code comments and Git-facing text in **English**.
- Version strings: use `RUNTIME_VERSION` from `noemaforge_version.py` — do not hardcode.
- Display safety: any command that starts model selection or heavy GPU work must carry
  `--keep-display`.
