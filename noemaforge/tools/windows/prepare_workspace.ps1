# === NoemaForge File Header ===
# File: noemaforge/tools/windows/prepare_workspace.ps1
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
File: tools/windows/prepare_workspace.ps1
Purpose: Provide the script 'prepare_workspace'.
Invoked by: Windows operator scripts, dot-sourcing, or direct PowerShell execution.
Inputs: Parameters and environment variables declared in the script.
Outputs: Console output, spawned processes, and filesystem changes as implemented below.
AutoDoc: refreshed 2026-04-09 (heuristic)
#>

param(
  [string]$LabRoot = "C:\noemaforge-lab",
  [switch]$CreateExampleManifests
)

$ErrorActionPreference = "Stop"

# === NoemaForge Autodoc Function Header ===
# Function: EnsureDir
# Purpose: Provide the PowerShell routine 'EnsureDir'.
# Inputs:
#   - $p
# Called by:
#   - Wrapper scripts, direct PowerShell execution, or dot-sourced callers.
# Outputs: Console output and side effects implemented in the body below.
# === End NoemaForge Autodoc Function Header ===
function EnsureDir($p) {
  if (!(Test-Path $p)) { New-Item -ItemType Directory -Force -Path $p | Out-Null }
}

# Layout (Windows lab; later mapped into Linux mountpoints)
$Data = Join-Path $LabRoot "data"

$Library = Join-Path $Data "Library"
$Vault = Join-Path $Data "Vault"
$Workspace = Join-Path $Data "Workspace"
$Reports = Join-Path $Data "Reports"
$Indexes = Join-Path $Data "Indexes"

# Library
EnsureDir (Join-Path $Library "inbox")
EnsureDir (Join-Path $Library "sources")
EnsureDir (Join-Path $Library "manifests")
EnsureDir (Join-Path $Library "_queue")

# Vault
EnsureDir (Join-Path $Vault "inbox")
EnsureDir (Join-Path $Vault "_queue")
EnsureDir (Join-Path $Vault "models")
EnsureDir (Join-Path $Vault "models-gguf")
EnsureDir (Join-Path $Vault "adapters")
EnsureDir (Join-Path $Vault "bundles")
EnsureDir (Join-Path $Vault "manifests")

# Optional but recommended (P1+): datasets + offline mirrors
EnsureDir (Join-Path $Vault "datasets")
EnsureDir (Join-Path $Vault "datasets-tfds")
EnsureDir (Join-Path $Vault "download-mirror")
EnsureDir (Join-Path $Vault "hf-home")

# Workspace
EnsureDir (Join-Path $Workspace "inbox")
EnsureDir (Join-Path $Workspace "outbox")
EnsureDir (Join-Path $Workspace "quarantine")

# Common inbox subfolders (P1)
$in = Join-Path $Workspace "inbox"
EnsureDir (Join-Path $in "photos")
EnsureDir (Join-Path $in "bank")
EnsureDir (Join-Path $in "video")
EnsureDir (Join-Path $in "articles")
EnsureDir (Join-Path $in "work")
EnsureDir (Join-Path $in "home")
EnsureDir (Join-Path $in "3dprint")
EnsureDir (Join-Path $in "library")
EnsureDir (Join-Path $in "tg")
EnsureDir (Join-Path $in "tabs")
EnsureDir (Join-Path $in "selfdev")
EnsureDir (Join-Path $in "rss")
# Knowledge ingest queue (offline)
EnsureDir (Join-Path (Join-Path $in "library") "_queue")

# Reports/Indexes
EnsureDir $Reports
EnsureDir $Indexes

# Optional example manifests
if ($CreateExampleManifests) {
  $exLib = Join-Path $Library "manifests\EXAMPLE.source.json"
  if (!(Test-Path $exLib)) {
    @{
      apiVersion = "noemaforge.library/v1"
      kind = "LibraryManifest"
      source_id = "src_example"
      rel_path = "sources/EXAMPLE.pdf"
      title = "Example"
      source_kind = "pdf"
      language = ""
      tags = @("example")
      trust = "unknown"
      ingest = @{ status = "new" }
    } | ConvertTo-Json -Depth 8 | Out-File -FilePath $exLib -Encoding utf8
  }

  $exVault = Join-Path $Vault "manifests\EXAMPLE.model.json"
  if (!(Test-Path $exVault)) {
    @{
      apiVersion = "noemaforge.vault/v1"
      kind = "VaultArtifactManifest"
      artifact_id = "art_example"
      artifact_kind = "llm"
      rel_path = "models/EXAMPLE/model.gguf"
      sha256 = ""
      model_family = ""
      format = "gguf"
      trust = "unknown"
      intended_roles = @("pm")
      capabilities = @{}
    } | ConvertTo-Json -Depth 8 | Out-File -FilePath $exVault -Encoding utf8
  }
}

Write-Host "OK: Workspace prepared"
Write-Host "  LabRoot:   $LabRoot"
Write-Host "  Library:   $Library"
Write-Host "  Vault:     $Vault"
Write-Host "  Workspace: $Workspace"
Write-Host "  Reports:   $Reports"
Write-Host "  Indexes:   $Indexes"
