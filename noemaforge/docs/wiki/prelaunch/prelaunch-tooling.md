# Prelaunch Tooling

## Purpose

The `prelaunch/tools` folder collects tools that are useful before public release but should not be silently applied to the runtime.

## Folder layout

```text
prelaunch/tools/
  common/            # Python tools shared by platforms
  trixie/            # Debian Trixie launchers
  macos/             # macOS launchers
  windows_original/  # Readable original Windows packs retained for traceability
```

The canonical review copy of imported tool packs is `prelaunch/tools/source`. Windows-original files are not release inputs when they are duplicated by the source copy, and the docs hygiene gate now treats active files that cannot be stat/read-opened as failures. If a duplicate original pack becomes unreadable to the active scanner, its useful content must be represented by the source pack or docs prose, then the unreadable original is moved to project trash.

## Included common tools

- `unified_manifest_downloader.py`
- `download_targets_runtime_manifest.json`
- `library_pipeline_orchestrator.py`
- `oapen_bulk_download_safe.py`

## Trixie wrappers

- `run_unified_manifest_downloader_trixie.sh`
- `run_library_pipeline_trixie.sh`

## macOS wrappers

- `run_unified_manifest_downloader_macos.sh`
- `run_library_pipeline_macos.sh`

## Safety rule

These wrappers are prelaunch helpers. They should be run manually and reviewed before integration into installer flows.

## YAML Inventory Readability

`yaml-inventory-readability-core` adds a local fallback gate for active YAML files in prelaunch and package validation. The runtime inventories `.yaml` and `.yml` files under `noemaforge` and `prelaunch`, verifies that they can be read as UTF-8, rejects tab indentation and checks simple flow bracket balance without importing PyYAML or downloading dependencies.

The scope is deliberately narrow: it is a readability and YAML-lite syntax guard, not a full YAML semantic parser. Full YAML parsing should still be used when PyYAML is available in the target environment, but this gate means release hygiene can still catch unreadable YAML and obvious structural hazards in stripped-down local validation sessions. Closed by `yaml-inventory-readability-core`.

## Manifest And Checksum Exclusion

`manifest-checksum-exclusion-core` makes the release evidence boundary explicit for manifests and checksum lists. The validator compares the root package manifest, the NoemaForge docs manifest, manifest SHA sidecars, root SHA256 lists and package checksum list against the active tree while excluding project trash, Python caches, pytest caches, build outputs and other generated directories.

This protects the normal autonomous workflow: generated junk can be moved to project trash for later cleanup without becoming part of active release manifests, wiki uploads or checksum evidence. The gate also catches stale manifest file counts and hash mismatches after content changes. Closed by `manifest-checksum-exclusion-core`.

## Release Artifact Name Guard

`release-artifact-name-guard-core` protects the canonical release-history boundary. The only active release-history destination is `history/CHANGELOG.md`; new parallel release-note, extra changelog, verification-report and raw research/source report filenames are treated as active-tree hygiene failures rather than informal side artifacts.

The guard is intentionally filename-based and offline. It walks the active project tree, skips project trash and generated cache directories, and reports exact offending paths so useful content can be integrated into canonical docs before obsolete material is quarantined. Closed by `release-artifact-name-guard-core`.

## Post-Reboot Archive Gate

`post-reboot-validation-archive-readiness-core` keeps post-reboot validation as a target-machine evidence task in `blocked_until_target_post_reboot_archive_evidence`. The local prelaunch tooling contract requires an operator-reviewed evidence bundle before a wiki patch is treated as complete: post-reboot baseline, service health, live smoke transcripts, forensics and journal archives, SHA256 records, redaction manifest, wiki patch manifest and target evidence references.

The prelaunch rule is intentionally conservative. Local validation may check JSON, registry, docs and example structure, but it must not run target commands, start LLM services, read target journals, produce forensics bundles or apply wiki patch content without separate target-side evidence and review.
