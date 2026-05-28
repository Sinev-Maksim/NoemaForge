# Prelaunch tools — 0.29.14

## Contents

This release includes extracted prelaunch helper tools under `prelaunch/tools/source/` and OS-specific wrappers under:

- `prelaunch/tools/trixie/`
- `prelaunch/tools/macos/`

## Imported source packs

| Source pack | Purpose |
|---|---|
| `library_windows_smart_launcher` | Safe/retry-oriented library download pipeline. |
| `unified_manifest_download_pack_20260408_hotfix3` | Manifest-driven model/dataset downloader. |

## Trixie target

The Trixie wrapper assumes Python 3 is available and runs tools from the local extracted source tree. It does not install system packages automatically.

## macOS target

The macOS wrapper uses `/usr/bin/env python3` and local paths. It is intended for dry-run/tool review first.

## Safety

These tools are included as prelaunch artifacts. Treat them as reviewable utilities, not as installed production services.
