# NoemaForge prelaunch tools

Version: 0.29.14

This folder contains reviewable utility packs and wrappers. They are not installed automatically.

## Layout

- `source/` — extracted original tool packs.
- `trixie/` — Debian Trixie wrappers.
- `macos/` — macOS wrappers.

## Imported packs

1. `library_windows_smart_launcher` — retry/safe launcher for library acquisition workflows.
2. `unified_manifest_download_pack_20260408_hotfix3` — manifest-based downloader for models/datasets.

## Rule

Prelaunch tools must be idempotent, reviewable, and safe by default. They should not enable timers, daemons, or heavy LLM services without explicit user action.
