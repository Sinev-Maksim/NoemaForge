# Public MVP/MWP checklist — 0.30.0

## Done in this release

- [x] Root `setup.sh` front door with VM/host/docker-dev/macOS-dev modes.
- [x] Public-safe installer/uninstaller for 0.30.0.
- [x] Missing `lib/noemaforge-common.sh` restored for helper scripts.
- [x] CLI can run from installed `/opt/noemaforge` or unpacked archive with `NOEMAFORGE_ROOT`.
- [x] Model profiles: minimal, balanced, writer, research, gpu-heavy.
- [x] GGUF normalizer rejects non-head split shards.
- [x] Pipeline CLI accepts `--root`/`--state` before or after subcommands.
- [x] Pipeline artifact registry, summary, next-packet, doctor and export commands.
- [x] Minimal dashboard state includes artifact counts and next actions.
- [x] Safe forensics bundle command.

## Still intentionally deferred

- [ ] Real legacy live-validation host live validation of NVIDIA/GDM/LLM services.
- [ ] Full CPU/GPU evaluation matrix on the canonical model list.
- [x] ToolProxy capability token issuance UX.
- [x] Signed release provenance.

Signed release provenance is now guarded by the `release-provenance-core` contract pack for archive SHA256, manifest pinning, detached signatures, install transcript and verification summary evidence.
- [ ] Production-grade GUI installer.

