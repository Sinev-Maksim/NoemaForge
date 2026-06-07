# Release Verification

How to verify that a NoemaForge release is what it claims to be. Trust comes from artifacts, not
promises.

## 0.32.2 (current — git-index based)

The premerge **manifest/checksum evidence gate** verifies the file set + content hashes against the
committed `SHA256SUMS` / `MANIFEST.json` on every PR. To run it locally on a clean checkout:

```bash
python noemaforge/src/manifest_checksum_exclusion_runtime.py \
  --project-root . --summary --hash-source git-index
# ok=true with 0 hash_mismatches = release evidence is consistent
```

A failure here is evidence-consistency (the checksums need regeneration after a file change), not a
code defect — the gate now says so explicitly with a job-summary explanation.

## 0.33.0 target: signed release-manifest contract

The full verification flow uses the `release-manifest.schema.json`
(`noemaforge/schemas/release-manifest.schema.json`):

```bash
noema release pack      # build release bundle + manifest at dist/release-manifest.json
noema release attest    # add SBOM + provenance
noema release sign      # sign the manifest
noema release verify dist/release-manifest.json   # GO only if this passes
```

A release is **not published** until `verify` passes. The signed manifest pinned to the shipped
`contract_epoch` ties the release to its compatibility surface.

## Operator verification at install / upgrade time (0.33.0)

```bash
# Before applying an upgrade:
noema upgrade --verify-only   # confirm the incoming manifest is valid and signed
noema upgrade                 # apply only after verification passes
```

## Related

- `../schemas/release-manifest.schema.json` — the published release-manifest contract.
- `../security/signed-manifests.md` — design rationale.
- `../architecture/contract-epochs.md` — what the release epoch pins.
