# Signed Manifests

NoemaForge tracks release integrity through **manifests + checksums**, with a path toward a fully
**signed, verifiable release contract**. Trust in a release should come from artifacts, not promises.

## Today

- `MANIFEST.json` (+ the package `noemaforge/docs/MANIFEST.json`) lists the active file set, and
  `SHA256SUMS` / `noemaforge/checksums/SHA256SUMS` pin content hashes. This evidence is **generated
  at pre-release only** (`publish-evidence.yml`) — it is not tracked, and there is no premerge
  evidence gate (owner directive 2026-06-14), which removes cross-PR checksum churn.
- `ci/regen_evidence.py` writes the evidence from the working tree and
  `manifest_checksum_exclusion_runtime.py --hash-source working-tree` verifies it (`ok=true`).
  `publish-evidence.yml` regenerates, verifies, and fails the workflow on any mismatch rather than
  publishing unverified evidence.
- Version source of truth is `noemaforge_version.py` reading `VERSION` (`RUNTIME_VERSION`).

## Target (0.33.0): release-manifest contract

A top-level, signed **release manifest** (schema: `noemaforge/schemas/release-manifest.schema.json`)
identifies the release, the contract epoch it ships, and the signed set of artifacts with hashes.
The intended flow (research milestone 4):

```text
noema release pack      # build the release bundle + manifest
noema release attest    # SBOM + provenance
noema release sign      # sign the manifest
noema release verify dist/release-manifest.json   # GO only if this passes
```

CI should refuse to publish a release whose `verify` step fails, and the release page should show
the manifest + verification instructions so anyone can independently confirm integrity.

## Why it matters

A verifiable release turns "trust us" into "verify it yourself": the artifact set, its hashes, the
epoch it ships, and its provenance are all checkable before install — and the same manifest is what
`noema upgrade` (0.33.0) verifies before applying an in-place upgrade.

## Related

- `../architecture/contract-epochs.md` — the epoch a release ships and pins.
- `../operations/release-verification.md` — operator verification steps (next doc PR).
