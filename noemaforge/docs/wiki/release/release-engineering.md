# Release engineering (current)

How a change travels from a `claude/*` or feature branch to a signed release,
and which gates it must pass. Maintained page; the workflows under
`.github/workflows/` are the source of truth for exact steps.

## Branch and review model

- `main` carries released states only; development happens on
  `release/<version>-dev` lines (currently `release/0.33.0-dev`), with one PR
  per complete feature from `claude/*`/`codex/*` branches.
- Review is shared by Codex, CodeRabbit and (when enabled repo-side) Copilot;
  PRs to non-default branches request CodeRabbit explicitly
  (`@coderabbitai review`). Actionable review comments are fixed before
  merge; recurring nits are folded into the canonical TODO.

## CI gates

| Workflow | Trigger | Gates |
|---|---|---|
| `premerge-quality.yml` | PRs | py_compile over src; version SoT consistency (`VERSION` files, `release.json`, no stray `RUNTIME_VERSION`); JSON/YAML parse; no tracked caches; shell `bash -n`; release manifest/checksum evidence (skipped for PRs into `main`); wiki integrity check |
| `acceptance.yml` | push/PR | artifact-driven AAT CI tier ([overview](../qa/acceptance-testing-aat.md)) |
| `autonomous-pipeline.yml` | `claude/**`/`codex/**` push | lint+compile validation stages for the autonomous flow |
| `scorecard.yml` | nightly + main | OpenSSF Scorecard supply-chain posture |
| `p0-status-ledger.yml` | push | status ledger upkeep |
| `publish-evidence.yml` | release events | published evidence bundle |
| `wiki-sync.yml` | push to `main` touching the wiki | publishes `noemaforge/docs/wiki/` to the GitHub Wiki |

## Release evidence

The release contract is artifact-driven: `MANIFEST.json` (project) and
`noemaforge/docs/MANIFEST.json` (package) enumerate active files;
`SHA256SUMS` + sidecar `.sha256` files pin their hashes;
`manifest_checksum_exclusion_runtime.py --summary --hash-source git-index`
must report `ok=true`. Verification runs against a **pristine worktree** —
local checkouts accumulate untracked files that pollute filesystem scans.

Accepted direction (2026-06-10, being implemented): on dev branches the
generated evidence files move out of git into a CI regenerate-and-verify
step, so parallel PRs stop conflicting on every base advance; committed,
signed evidence remains mandatory on release branches and tags.

## Provenance and hygiene

- `release-provenance-policy.json` mandates signed provenance for release
  archives (detached signature + fingerprint; no plaintext keys).
- The docs-hygiene gate (`docs_hygiene_runtime.py`) enforces Markdown
  placement, canonical files and forbidden active text.
- The wiki is part of the release evidence: pages follow the
  [Deep Research Integration Policy](../governance/deep-research-integration-policy.md),
  and the wiki integrity check keeps every page reachable from the hub.

## Hard rules

- No production GitHub Release without explicit human GO plus target-host
  validation evidence.
- Version literals live only in the SoT (`noemaforge_version.py` reading
  `VERSION`); `noema upgrade` never touches user or machine state.
- Heavy GPU / model-selection commands always preserve the display by
  default (`--keep-display` semantics).
