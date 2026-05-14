# === NoemaForge File Header ===
# File: prelaunch/tools/windows_original/unified_manifest_download_pack_20260408_hotfix3/run_unified_manifest_downloader.ps1
# Zone: release/package
# Version: 0.31.13.alpha
# Created: 2026-05-14
# Modified: 2026-05-14
# Purpose: Provide NoemaForge release functionality for the packaged local runtime.
# Inputs: Command-line arguments, environment variables, package files and local NoemaForge runtime state as applicable.
# Outputs: Structured command output, files, service state or UI state as documented by the caller.
# Side effects: Limited to the documented NoemaForge paths, runtime state directories or systemd units used by this file.
# Tests: Syntax validation plus the release setup selftest, consistency-audit and targeted smoke checks.
# Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
# === End NoemaForge File Header ===
$ErrorActionPreference = "Stop"

if (-not $env:HF_HOME) { $env:HF_HOME = "E:\hf-home" }
if (-not $env:HF_HUB_CACHE) { $env:HF_HUB_CACHE = Join-Path $env:HF_HOME "hub" }
if (-not $env:HF_XET_CACHE) { $env:HF_XET_CACHE = Join-Path $env:HF_HOME "xet" }
if (-not $env:HF_HUB_DISABLE_XET) { $env:HF_HUB_DISABLE_XET = "1" }
if (-not $env:HF_HUB_DISABLE_SYMLINKS_WARNING) { $env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1" }
if (-not $env:VAULT_ROOT) { $env:VAULT_ROOT = "E:\noemaforge-lab\data\Vault" }

python "$PSScriptRoot\unified_manifest_downloader.py" `
  --manifest "$PSScriptRoot\download_targets_runtime_manifest.json" `
  --target-root "$env:VAULT_ROOT\download-mirror" `
  --cache-dir "$env:HF_HUB_CACHE" `
  --tfds-data-dir "$env:VAULT_ROOT\datasets-tfds" `
  --web-download-root "$env:VAULT_ROOT\datasets-web" `
  @args
