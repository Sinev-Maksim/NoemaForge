<!--
=== NoemaForge File Header ===
File: noemaforge/docs/quality/AAT_SUITE.md
Zone: docs/quality
Version: 0.33.0
Purpose: Specify the artifact-driven acceptance suite (AAT) — its results bundle
  shape, the mandatory cases, and how to run it locally and in CI.
Notes: Documentation is English-only.
=== End NoemaForge File Header ===
-->

# NoemaForge Acceptance Suite (AAT)

The acceptance suite is **artifact-driven**: every case ends in a saved, re-verifiable
artifact. It proves the *evidence chain* (manifests, checksums, provenance, redaction,
epoch immutability), not merely that code executed. This complements the per-feature
UAT scenarios in `UAT_SCENARIOS_0.32.2.md`.

## Outputs bundle

Each run writes a self-describing bundle:

```
results/
  00-env/          environment capture (timestamp, platform, python, uname)
  10-integrity/    package/manifest/checksum integrity   → checksum_validation
  20-install/      install dry-run + preflight capture    (best-effort)
  30-safety/       no-hidden-autostart / warmup modes      (pending slice)
  40-toolproxy/    capability tokens / isolation           (pending slice)
  50-epochs/       contract-epoch immutability             (pending slice)
  60-telemetry/    redaction-before-persistence            (pending slice)
  70-release/      signed manifest / provenance verify     (pending slice)
  summary.json     aggregate verdict + per-case status
  junit.xml        CI-consumable test report
  manifest.sha256  sha256 of every produced artifact
```

`manifest.sha256` makes the bundle tamper-evident: re-hashing the artifacts and
diffing against it proves the published evidence was not altered after the run.

## Mandatory cases

| Case | Tier | Proves | Gating |
|------|------|--------|--------|
| `checksum_validation` | 10-integrity | MANIFEST/SHA256SUMS + `.sha256` sidecars match the tracked files (via the canonical git-index verifier) | **yes** |
| `install_dry_run` | 20-install | setup dry-run captured on a POSIX host | evidence-only |
| `no_hidden_autostart` | 30-safety | no unexpected LLM/media processes after boot | pending |
| `model_warmup_modes` | 30-safety | default startup stays safe/manual; heavy path only on explicit action | pending |
| `capability_tokens` | 40-toolproxy | minted token verifies; revoked / expired / tampered rejected (shipped `caps` store) | **yes** |
| `toolproxy_isolation` | 40-toolproxy | gateway is unix-socket only (no remote egress); `exec` is a bounded allowlist; enforcement on | **yes** |
| `contract_epoch_immutability` | 50-epochs | canonical artifact hash stable without an explicit revision | pending |
| `telemetry_privacy` | 60-telemetry | no raw secret/PII markers in stored artifacts (via the shipped `sense_privacy_runtime` filter) | **yes** |
| `signed_manifest_verification` | 70-release | policy mandates signed provenance (detached sig + key fingerprint, no plaintext keys); provenance record binds the manifest subject hash | **yes** |

`pending` cases reserve their tier and appear in `summary.json` as `pending` until
their implementation slice lands. The process exit code is non-zero **only** when an
implemented gating case fails, so the harness is safe to wire into CI immediately.

### LLM acceptance cases (later slice)

`grounded_summary`, `safe_refusal_boundary`, `toolproxy_event_explainer`,
`epoch_diff_interpreter`, `cost_ceiling_guard` — validated against schema, refusal
markers, redaction assertions, governance-note presence, and budget-stop behaviour.

## Running it

```bash
# Full bundle (Linux/macOS):
bash ci/run_acceptance.sh results

# Cross-platform (no shell needed):
python ci/acceptance_runner.py results

# Pytest layer:
python -m pytest ci/acceptance -q
```

> Integrity verification uses **git-index (canonical, LF) blob hashes**, matching how
> `SHA256SUMS` is generated, so results are platform-independent. The verifier
> enumerates the working tree, so run against a clean checkout (CI or a `git worktree`);
> a development tree with untracked artifacts reports extra files by design.

## CI

`.github/workflows/acceptance.yml` runs the harness, runs the pytest layer, uploads
`results/` as the `noemaforge-acceptance-results` workflow artifact (90-day retention),
and attests build provenance over the bundle digest. The split follows the two-level
model: **PR-level** integrity/schema/dry-run here; **nightly/manual** ToolProxy live
smoke, release-guard comparison, OpenSSF Scorecard, and cosign/attestation verification
in later slices.
