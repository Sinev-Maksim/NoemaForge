# === NoemaForge File Header ===
# File: noemaforge/bootstrap/make-seed.ps1
# Zone: release/package
# Version: 0.32.1
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
File: bootstrap/make-seed.ps1
Purpose: Provide the script 'make-seed'.
Invoked by: Windows operator scripts, dot-sourcing, or direct PowerShell execution.
Inputs: Parameters and environment variables declared in the script.
Outputs: Console output, spawned processes, and filesystem changes as implemented below.
AutoDoc: refreshed 2026-04-09 (heuristic)
#>

param(
  [Parameter(Mandatory=$true)][string]$TargetDriveLetter,
  [switch]$Force
)

$dst = "$TargetDriveLetter`:\seed\noemaforge"
$src = Join-Path $PSScriptRoot ".."
$src = (Resolve-Path $src).Path

if (-not (Test-Path "$TargetDriveLetter`:\")) {
  throw "Drive letter not found: $TargetDriveLetter"
}

if (Test-Path $dst) {
  if (-not $Force) { throw "Destination exists: $dst (use -Force)" }
  Remove-Item -Recurse -Force $dst
}

New-Item -ItemType Directory -Force -Path $dst | Out-Null
Copy-Item -Recurse -Force (Join-Path $src "*") $dst
Write-Host "Seed copied to $dst"
