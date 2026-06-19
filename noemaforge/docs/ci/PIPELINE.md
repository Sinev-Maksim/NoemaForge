# CI & governance pipeline

NoemaForge's continuous-integration pipeline is intentionally small and legible: every change is
gated by read-only checks and an independent review, and release integrity is provable from the
repository. This page documents the actual workflow files under `.github/workflows/` so the
project's governance is visible, not implied.

## Workflows

### `premerge-quality.yml` — Quality gate (read-only)
Runs on every PR into the release lines and `main`. **No auto-commits, no auto-push.** Steps:

1. `py_compile` of `noemaforge/src/*.py`.
2. No forbidden `RUNTIME_VERSION =` assignment outside the version source of truth.
3. `VERSION` files equal the source-of-truth version (derived from `noemaforge_version.RUNTIME_VERSION`, not a hardcoded literal).
4. `docs/release.json` version fields consistent.
5. JSON parse of `noemaforge/configs/*.json`.
6. YAML parse of `noemaforge/configs/*.yaml`.
7. No tracked `__pycache__` / `*.pyc`.
8. **No premerge evidence gate** — the `MANIFEST.json` / `SHA256SUMS` evidence is generated and
   verified at pre-release only (`publish-evidence.yml`, working-tree hashes), not on PRs; it is
   untracked (owner directive 2026-06-14), which removes cross-PR checksum churn.
9. `bash -n` syntax check of `*.sh`.

### `autonomous-pipeline.yml` — per-push validation + independent review
Runs on push to `claude/**` / `codex/**`:

- **validate-claude-push** (ubuntu): compile, JSON/YAML parse, version checks, `__pycache__`
  guard — all scoped to the changed files, against the PR's auto-detected base branch.
- **codex-review** (self-hosted): an independent **Codex CLI review** of the diff against the
  PR's true base (resolved from the PR `base.ref`), posting one verdict comment per branch. When
  the reviewer is unavailable, the branch is marked ready and **CodeRabbit** review is requested as
  the fallback gate.

### `p0-status-ledger.yml` — append-only readiness ledger
Maintains a P0 readiness ledger so release-blocking status is tracked transparently.

### `qa-version-bump.yml` — gated version-bump automation
Performs the version bump only through the dedicated, gated workflow — never ad hoc.

### `publish-evidence.yml` — published acceptance evidence
On a release tag (`v*`) or manual dispatch, assembles the provenance chain (`MANIFEST.json` +
`SHA256SUMS` + sidecars), a machine-readable verification report, the capability catalog, and the
UAT acceptance scenarios into a single **`acceptance-evidence`** artifact — one-click downloadable
from the Actions run — and attaches a build-provenance attestation. This makes the evidence a
visible repository layer rather than something you must read the code to find.

### `semgrep.yml` — Semgrep CE code scanning
Runs Semgrep CE `1.166.0` on pull requests, release-line pushes, manual dispatches, and a weekly
schedule. The workflow checks out `semgrep/semgrep-rules` at commit
`d41fb34cf74466e2878af5f268ebf54466a04541`, scans the Python, JavaScript, TypeScript, and Go rule
directories with registry metrics disabled, and uploads `ERROR` findings to GitHub Code Scanning as
the `semgrep-ce` SARIF category. Findings are triaged in Code Scanning; promotion to an issue is a
manual decision that must include rationale, so CI cannot create duplicate or unreviewed issues.

### Dependency and CodeQL ownership
Dependabot checks the root `pyproject.toml` through the `pip` ecosystem and keeps SHA-pinned GitHub
Actions current on a weekly cadence. There is no `npm` entry because the repository has no Node
package manifest or lock file, and updates are never auto-merged.

GitHub CodeQL **default setup** is the authoritative CodeQL lane. The repository deliberately has
no advanced `.github/workflows/codeql.yml`: GitHub rejects advanced-setup SARIF uploads while
default setup is enabled. The connected repository API used for this change does not expose the
code-scanning alerts endpoint, so this documentation does not assert a current open-alert count.

## Review lanes

| Lane | Role |
|---|---|
| **Quality gate** | Mechanical correctness + evidence consistency (blocking). |
| **Codex CLI review** | Independent diff review against the deny-by-default + version + hygiene gates. |
| **CodeRabbit** | PR review lane; the fallback review gate when Codex is unavailable. |
| **Human** | Merge + target-host validation + the release GO decision. |

## Provenance & verification

The evidence chain (`MANIFEST.json`, `SHA256SUMS`, sidecars) is regenerated from the git index and
verified by `manifest_checksum_exclusion_runtime.py`. Releases additionally carry a signed
release-manifest (`noemaforge/schemas/release-manifest.schema.json`) verifiable with
`noema release verify`. See [`../release/RELEASING.md`](../release/RELEASING.md) and
[`../operations/release-verification.md`](../operations/release-verification.md).
