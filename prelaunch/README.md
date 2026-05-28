# NoemaForge Prelaunch Tools

Version: 0.32.1.

This folder contains manual prelaunch utilities extracted from the uploaded Windows packs and wrapped for Debian Trixie and macOS.

## Layout

- `tools/common/` — Python scripts shared across platforms.
- `tools/trixie/` — Debian Trixie wrappers.
- `tools/macos/` — macOS wrappers.
- `tools/windows_original/` — original Windows artifacts preserved for traceability when they remain readable active files; duplicated unreadable packs are quarantined under project trash after the canonical `tools/source/` copy is retained.

## Quick start: Trixie

```bash
cd prelaunch/tools/trixie
./run_unified_manifest_downloader_trixie.sh
./run_library_pipeline_trixie.sh
```

## Quick start: macOS

```bash
cd prelaunch/tools/macos
./run_unified_manifest_downloader_macos.sh
./run_library_pipeline_macos.sh
```

## Notes

- The wrappers create a local `.venv` by default.
- Set `NOEMAFORGE_PRELAUNCH_ROOT` to override the working root.
- Set `PYTHON_BIN` to force a Python executable.
- No runtime NoemaForge services are modified by these wrappers.
