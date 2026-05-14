# === NoemaForge File Header ===
# File: noemaforge/tools/windows/run_firstboot.ps1
# Zone: release/package
# Version: 0.31.13.alpha
# Created: 2026-05-14
# Modified: 2026-05-14
# Purpose: Coordinate first-start model inventory, tournament, staffing and epoch safety checks.
# Inputs: Command-line arguments, environment variables, package files and local NoemaForge runtime state as applicable.
# Outputs: Structured command output, files, service state or UI state as documented by the caller.
# Side effects: Limited to the documented NoemaForge paths, runtime state directories or systemd units used by this file.
# Tests: Syntax validation plus the release setup selftest, consistency-audit and targeted smoke checks.
# Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
# === End NoemaForge File Header ===
<#
=== NoemaForge Autodoc File Header ===
File: tools/windows/run_firstboot.ps1
Purpose: Provide the script 'run_firstboot'.
Invoked by: Windows operator scripts, dot-sourcing, or direct PowerShell execution.
Inputs: Parameters and environment variables declared in the script.
Outputs: Console output, spawned processes, and filesystem changes as implemented below.
AutoDoc: refreshed 2026-04-09 (heuristic)
#>

param(
  [Alias("Root","BrainRoot")]
  [string]$RepoRoot = "",
  [string]$LabRoot = "",
  [switch]$AutoManifest,
  # Optional explicit python.exe path (if python is not on PATH)
  [string]$PythonExe = ""
)

$ErrorActionPreference = "Stop"

if (-not $RepoRoot -or $RepoRoot.Trim() -eq "") {
  $RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\.." )).Path
}

if (-not $LabRoot -or $LabRoot.Trim() -eq "") {
  # Default LabRoot as a sibling folder (keeps the repo clean): <repo>\..\noemaforge-lab
  $lr = Resolve-Path (Join-Path $RepoRoot "..\noemaforge-lab") -ErrorAction SilentlyContinue
  if ($lr) {
    $LabRoot = $lr.Path
  } else {
    $LabRoot = (Join-Path $RepoRoot "..\noemaforge-lab")
  }
}

Write-Host "NoemaForge FIRSTBOOT (Windows)" -ForegroundColor Cyan
Write-Host "  brain_root: $RepoRoot"
Write-Host "  lab_root:   $LabRoot"
if ($PythonExe -and $PythonExe.Trim().Length -gt 0) {
  Write-Host "  python:     $PythonExe" -ForegroundColor Yellow
}
Write-Host ""

# Best-effort cleanup (does not fail the run)
try {
  & powershell -ExecutionPolicy Bypass -File (Join-Path $RepoRoot "tools\windows\cleanup_forbidden_artifacts.ps1") -Root $RepoRoot | Out-Null
} catch {}

Write-Host "Step 1/3: verify_seed" -ForegroundColor Cyan
& powershell -ExecutionPolicy Bypass -File (Join-Path $RepoRoot "tools\windows\verify_seed.ps1") -Root $RepoRoot

Write-Host "Step 2/3: noemaforge_check (deep)" -ForegroundColor Cyan
$checkArgs = @("-Root", $RepoRoot, "-Deep")
if ($PythonExe -and $PythonExe.Trim().Length -gt 0) { $checkArgs += @("-PythonExe", $PythonExe) }
& powershell -ExecutionPolicy Bypass -File (Join-Path $RepoRoot "tools\windows\noemaforge_check.ps1") @checkArgs

Write-Host "Step 3/3: noemaforge_lab (prep + scans)" -ForegroundColor Cyan
$labArgs = @("-SeedRoot", $RepoRoot, "-LabRoot", $LabRoot)
if ($AutoManifest) { $labArgs += "-AutoManifest" }
if ($PythonExe -and $PythonExe.Trim().Length -gt 0) { $labArgs += @("-PythonExe", $PythonExe) }
& powershell -ExecutionPolicy Bypass -File (Join-Path $RepoRoot "tools\windows\noemaforge_lab.ps1") @labArgs

Write-Host "OK: Firstboot prep complete." -ForegroundColor Green
