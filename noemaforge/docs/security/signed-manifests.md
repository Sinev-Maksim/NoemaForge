# Signed Manifests

NoemaForge tracks release integrity through **manifests + checksums**, with a path toward a fully
**signed, verifiable release contract**. Trust in a release should come from artifacts, not promises.

## Today (0.32.2)

- The repository ships `MANIFEST.json` (+ the package `noemaforge/docs/MANIFEST.json`) listing the
  active file set, and `SHA256SUMS` / `noemaforge/checksums/SHA256SUMS` pinning content hashes.
- A premerge **manifest/checksum evidence gate** verifies that the committed evidence matches the
  git-index (`manifest_checksum_exclusion_runtime.py --hash-source git-index`). A failure there is an
  evidence-consistency issue (regenerate), not a code defect — the gate now says so explicitly.
- Version source of truth is `noemaforge_version.py`; `VERSION` files are all `0.32.2`.

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
