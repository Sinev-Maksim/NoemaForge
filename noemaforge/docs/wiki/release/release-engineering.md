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
  (`@coderabbitai review`).
- **Every review comment must be responded to before merge — mandatory.**
  Each Codex finding and each CodeRabbit *inline* comment (read via
  `gh api repos/.../pulls/<n>/comments`, not just the summary) is either fixed
  on the branch or answered with a reasoned reply; a PR is not merge-ready
  while an unaddressed actionable comment remains. Recurring nits are folded
  into the canonical TODO with their source tag.
- The `## Optimizations` section of every Codex review is handled before the
  PR merges: each suggestion is applied on the branch or recorded in the
  canonical TODO with its `Codex #PR` tag (owner directive 2026-06-11).

## CI gates

| Workflow | Trigger | Gates |
|---|---|---|
| `premerge-quality.yml` | PRs | py_compile over src; version SoT consistency (`VERSION` files, `release.json`, no stray `RUNTIME_VERSION`); JSON/YAML parse; no tracked caches; shell `bash -n`; wiki integrity; docs hygiene. **No evidence gate** (pre-release only). |
| `acceptance.yml` | push/PR | artifact-driven AAT CI tier ([overview](../qa/acceptance-testing-aat.md)); checksum/signed-manifest cases are release-tier (skip on PR) |
| `publish-evidence.yml` | tag `v*` / dispatch | generates + verifies + attests release evidence into the signed bundle |
| `autonomous-pipeline.yml` | `claude/**`/`codex/**` push | lint+compile validation stages for the autonomous flow |
| `scorecard.yml` | nightly + main | OpenSSF Scorecard supply-chain posture |
| `p0-status-ledger.yml` | push | status ledger upkeep |
| `wiki-sync.yml` | push to `main` touching the wiki | publishes `noemaforge/docs/wiki/` to the GitHub Wiki |

## Release evidence (pre-release only)

The release contract is artifact-driven: `MANIFEST.json` (project) and
`noemaforge/docs/MANIFEST.json` (package) enumerate active files;
`SHA256SUMS` + sidecar `.sha256` files pin their hashes;
`manifest_checksum_exclusion_runtime.py --summary --hash-source git-index`
reports `ok=true` over the release tree.

Evidence lifecycle (owner directive 2026-06-14):

- Evidence is a **pre-release artifact only**. The manifests/checksums are
  **not tracked** (gitignored), **not generated, not checked and not merged**
  on dev / PR / release branches. There is no premerge evidence gate and no
  auto-refresh workflow — this removes the recurring cross-PR checksum churn
  entirely.
- `ci/regen_evidence.py` remains the single generator, but it runs **only at
  pre-release**: `publish-evidence.yml` (tag `v*` / dispatch) generates the
  evidence, verifies it, and assembles + attests the signed release bundle.
- The AAT `checksum_validation` and `signed_manifest_verification` cases are
  **release-tier**: they report `skip` on dev/PR trees (evidence absent) and
  run on release trees where the evidence has been generated.

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
