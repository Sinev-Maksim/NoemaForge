# Release Verification

How to verify that a NoemaForge release is what it claims to be. Trust comes from artifacts, not
promises.

## Current — pre-release, working-tree based

The release evidence — `MANIFEST.json` / `noemaforge/docs/MANIFEST.json` (active-file manifests)
and `SHA256SUMS` / `.sha256` sidecars (content hashes) — is **generated at pre-release only**
(`publish-evidence.yml`); it is not tracked, and there is no premerge evidence gate (owner directive
2026-06-14). To generate and verify it locally on a clean checkout:

```bash
python ci/regen_evidence.py
python noemaforge/src/manifest_checksum_exclusion_runtime.py \
  --project-root . --summary --hash-source working-tree
# ok=true with 0 hash_mismatches = release evidence is consistent
```

`regen_evidence.py` writes the evidence from the working tree, and the verifier hashes the same
working-tree files, so the two are consistent by construction. A failure means the verification
itself is broken (publish-evidence fails the workflow rather than publishing it) — never a stale
committed checksum, since the evidence is regenerated every run.

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
