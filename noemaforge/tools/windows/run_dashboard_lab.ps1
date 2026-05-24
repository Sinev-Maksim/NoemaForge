# === NoemaForge File Header ===
# File: noemaforge/tools/windows/run_dashboard_lab.ps1
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
File: tools/windows/run_dashboard_lab.ps1
Purpose: Provide the script 'run_dashboard_lab'.
Invoked by: Windows operator scripts, dot-sourcing, or direct PowerShell execution.
Inputs: Parameters and environment variables declared in the script.
Outputs: Console output, spawned processes, and filesystem changes as implemented below.
AutoDoc: refreshed 2026-04-09 (heuristic)
#>

param(
  [string]$RepoRoot = "",
  [string]$LabRoot = "",
  [int]$Port = 8787,
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

$LabData = Join-Path $LabRoot "data"

# Resolve Python even if not present on PATH.
. (Join-Path $PSScriptRoot "lib_python.ps1")
$pyInfo = ResolveNoemaForgePython -BrainRoot $RepoRoot -PythonExeParam $PythonExe -MinVersion "3.10"
if ($pyInfo.kind -eq "none") {
  Write-Host "FAIL: Python 3.10+ not found. Install Python or set env:NOEMAFORGE_PYTHON / pass -PythonExe." -ForegroundColor Red
  exit 2
}

Write-Host "NoemaForge Dashboard (lab)" -ForegroundColor Cyan
Write-Host "  repo:       $RepoRoot"
Write-Host "  lab_root:   $LabRoot"
Write-Host "  state_root: $LabData"
Write-Host "  url:        http://127.0.0.1:$Port"
Write-Host ("  python:     " + $pyInfo.exe + " " + ($pyInfo.args -join " ") + " (v" + $pyInfo.version + ")")
Write-Host ""

$env:PYTHONDONTWRITEBYTECODE = "1"
& $pyInfo.exe @($pyInfo.args) (Join-Path $RepoRoot "src\brainui.py") serve --state-root $LabData --host 127.0.0.1 --port $Port
exit $LASTEXITCODE
