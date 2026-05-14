# === NoemaForge File Header ===
# File: noemaforge/tools/windows/apply_patches.ps1
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
<#
=== NoemaForge Autodoc File Header ===
File: tools/windows/apply_patches.ps1
Purpose: Provide the script 'apply_patches'.
Invoked by: Windows operator scripts, dot-sourcing, or direct PowerShell execution.
Inputs: Parameters and environment variables declared in the script.
Outputs: Console output, spawned processes, and filesystem changes as implemented below.
AutoDoc: refreshed 2026-04-09 (heuristic)
#>

param(
  [Parameter(Mandatory=$true)][string]$Root,
  [Parameter(Mandatory=$true)][string[]]$Zips
)

$ErrorActionPreference = "Stop"

if (!(Test-Path $Root)) {
  New-Item -ItemType Directory -Path $Root | Out-Null
}

foreach ($z in $Zips) {
  if (!(Test-Path $z)) {
    throw "Zip not found: $z"
  }
  Write-Host "Applying: $z"
  Expand-Archive -Path $z -DestinationPath $Root -Force
}

Write-Host "Done. Root: $Root"
