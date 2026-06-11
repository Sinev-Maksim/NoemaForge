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
