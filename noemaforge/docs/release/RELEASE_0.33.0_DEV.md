# NoemaForge 0.33.0 — Development Line

- **Version:** 0.33.0
- **Created:** 2026-06-07
- **Branch:** `release/0.33.0-dev` (development line; **not** a release yet)
- **Baseline:** branched from `release/0.32.2-hardening` @ `af30b54` (the fully integrated
  0.32.2 hardening tree).

## What this branch is

`release/0.33.0-dev` is the integration line for 0.33.0 feature work. It inherits the entire
0.32.2 hardening baseline (durable orchestration primitives, centralized `RUNTIME_VERSION`,
display-safe stop behavior, idempotent model-selection/vault actions, and the
architectural-legibility documentation layer) and opens development of the 0.33.0 roadmap.

0.32.2 finalization (target-host validation + human GO + merge to `main`) continues
independently on `release/0.32.2-hardening`; this branch does not block or replace it.

## Line-opening changes (this PR)

- **Version bump → 0.33.0**: `VERSION`, `noemaforge/VERSION`, `docs/VERSION`,
  `docs/release.json` (version/release/release_name/package/branch/title/summary), and the
  embedded fallback in `noemaforge/src/noemaforge_version.py`.
- **Version-agnostic premerge gate**: `.github/workflows/premerge-quality.yml` now derives the
  expected version from the source of truth (`noemaforge_version.RUNTIME_VERSION`) instead of a
  hardcoded literal, and triggers on `release/0.33.0-dev`. The same workflow therefore validates
  0.32.2 and 0.33.0 without further edits.
- Release evidence (`SHA256SUMS` / `MANIFEST.json`) regenerated for the new version surface.

## Security automation

- Weekly Dependabot coverage now includes both SHA-pinned GitHub Actions and the
  root `pyproject.toml` through the `pip` ecosystem, with grouped and bounded PRs.
- Semgrep CE `1.166.0` scans Python, JavaScript, TypeScript, and Go with rules
  pinned to `semgrep/semgrep-rules@d41fb34cf74466e2878af5f268ebf54466a04541`
  and publishes `ERROR` findings to the `semgrep-ce` Code Scanning category.
- GitHub CodeQL default setup remains the authoritative CodeQL lane; no advanced
  workflow is added because it would conflict with default setup SARIF handling.
  The current open-alert count was not independently available for this change.
- Semgrep baseline triage from run `27828184758` leaves four release-blocker
  audit tasks: frontend DOM/XSS (22), dynamic SQL construction (15), XML parser
  and input boundaries (5), and subprocess taint/allowlists (3). These 45
  findings are not confirmed vulnerabilities until audited in separate PRs.
  Baseline SARIF SHA-256 is
  `6db96262c017d13c9e7e8ae186d374321c26d89941f2ddd7e9f20e5e9c23a792` and the
  audit artifact is retained through 2026-06-26.

## 0.33.0 roadmap (development order)

The detailed roadmap lives in `noemaforge/docs/TODO.md` and the architecture notes. Planned
first increments, in order:

1. **`noema doctor`** — read-only readiness command (backend matrix, approved profiles, active
   epoch, policy status). Referenced throughout the 0.32.2 operator docs; stdlib-only,
   cross-platform, no GPU/display risk. **First feature.**
2. **`noema release verify` / `sign`** — implement the signed release-manifest contract
   (`noemaforge/schemas/release-manifest.schema.json`).
3. **`noema upgrade`** — GitHub-native in-place version upgrade with a fail-safe archive path,
   replace-by-extension, signed-manifest verification, dry-run, and preservation of
   user/machine-changed files (`context.md`, config, memory, sessions, tokens, data roots).
4. **ToolProxy policy engine** — enforce `noemaforge/policies/*.rego` + `noema policy test`.
5. **Knowledge projection** — generated epoch compatibility matrix and capability catalog.

Each ships as its own PR into `release/0.33.0-dev`.
