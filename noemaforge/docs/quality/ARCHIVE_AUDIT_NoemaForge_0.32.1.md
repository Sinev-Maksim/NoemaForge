# NoemaForge 0.32.1 archive audit

## Scope

This audit checks the uploaded `noemaforge_0.32.0_release_gate_rechecked.tar.gz` package, repairs blocking installability and version-label issues, and rebuilds the installable package as `NoemaForge 0.32.1`.

## Blocking issues found

- The uploaded archive was named as a 0.32.0 release gate but unpacked into an old `0.31.13.alpha-patched1_docs-0.31.21-integrated` root directory.
- `setup.sh` printed `0.31.21.alpha` even though the active VERSION files said `0.32.0`.
- Non-dry-run install failed because the current installer had lost its executable bit after packaging.
- The root-level `README.md` and `context.md` required by the installer were missing.
- Current-version wiki files expected by `consistency-audit` were missing for `0.32.1`.
- Localized user-information files were not present under `docs/i18n/<locale>/` for the release gate.
- Historical top-level installers cluttered the active package root and made release ownership unclear.

## Repairs made

- Renamed active release to `0.32.1` across VERSION files, setup, installer, release metadata, active configs, runtime code and docs.
- Renamed the active installer/uninstaller to `install_noemaforge_0.32.1_mvp.sh` and `uninstall_noemaforge_0.32.1_mvp.sh`.
- Restored executable bits for setup, installer, helpers, CLI binaries and prep scripts.
- Added root `README.md` and `context.md`.
- Added current-version wiki pages required by the release consistency gate.
- Added localized user-information sets for `en`, `ru`, `uk`, `es`, `de`, `pt`, `it`, `zh-CN`, `ja`, `ko`.
- Added `noemaforge/TODO.md` as an installed release artifact.
- Added an `/opt/docs` mirror during install so consistency checks can resolve docs in rootfs and live layouts.
- Removed stale root-level historical installer/uninstaller clutter from the active package root.
- Removed generated `__pycache__` directories.
- Regenerated `MANIFEST.json`, docs manifest, `SHA256SUMS`, and checksum sidecars.

## Validation results

- Archive selftest: PASS.
- Rootfs test install: PASS.
- `noemaforge version`: PASS, returns `0.32.1`.
- `version-audit --json`: PASS, warnings=0.
- `consistency-audit --json`: PASS, 112 checks / 0 failures.
- Python syntax: PASS.
- Python shebang helper syntax: PASS.
- Bash syntax: PASS.
- JSON parse: PASS.
- YAML parse: PASS.
- Persona portrait references: PASS, missing=0.
- Admin GUI smoke: PASS for `/api/health`, `/api/gui/state`, persona portrait HEAD, conversational message, `public_mwp` route and `evolution` route.

## Notes

Historical documentation may still describe older release lineage where appropriate, but active runtime metadata and install paths are now aligned to `0.32.1`.
