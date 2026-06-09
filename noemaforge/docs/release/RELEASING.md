# Releasing NoemaForge

This page explains how a NoemaForge release is built, verified, and published — so the release
process is legible and a published GitHub Release can be independently trusted.

## Why Releases publish at GO (not before)

The repository already contains the release-engineering artifacts (`MANIFEST.json`, `SHA256SUMS`,
the manifest verifier, the release-manifest schema). A **GitHub Release is published only at the
human GO milestone**, which follows target-host validation — NoemaForge never advertises
production-readiness it has not validated. This is a deliberate trust choice: the substance ships
in the repo continuously; the *Release* is the audited, verifiable checkpoint.

## Release steps

```bash
# 1. Confirm the evidence chain is consistent (CI-equivalent, from the git index):
python noemaforge/src/manifest_checksum_exclusion_runtime.py --summary --hash-source git-index
#    -> ok=true, hash_mismatches=0

# 2. Build the signed release manifest (0.33.0+ tooling):
noema release pack --root <release-root> --version <X.Y.Z> --contract-epoch <epoch> \
                   --out dist/release-manifest.json

# 3. (Pending crypto-dep decision) sign the manifest:
#    noema release sign dist/release-manifest.json

# 4. Verify exactly what will be published — GO only if this passes:
noema release verify dist/release-manifest.json --root <release-root>
#    -> OVERALL: VERIFIED

# 5. Run the target-host P0 validation (Debian Trixie / GNOME-GDM / RTX 3080 Ti).
#    See docs/release/RELEASE_FINALIZATION_0.32.2.md for the gate list. (Human-operated.)

# 6. Human GO -> publish the GitHub Release for the tag, attaching:
#    - the release archive, MANIFEST.json + SHA256SUMS, and dist/release-manifest.json.
gh release create vX.Y.Z dist/release-manifest.json SHA256SUMS MANIFEST.json \
   --title "NoemaForge X.Y.Z" --notes-file <release-notes>
```

## Verifying a published release (anyone)

```bash
# Download the release assets, then:
noema release verify release-manifest.json --root <extracted-release>
# or, without the CLI:
python noemaforge/src/manifest_checksum_exclusion_runtime.py --summary --hash-source git-index
```

A release whose `verify` step fails must not be installed. `noema upgrade run` performs this
verification automatically before applying an in-place upgrade.

## Related

- [`../ci/PIPELINE.md`](../ci/PIPELINE.md) — the CI gates that protect every change.
- [`../operations/release-verification.md`](../operations/release-verification.md) — operator verification.
- [`../security/signed-manifests.md`](../security/signed-manifests.md) — the signed-manifest design.
