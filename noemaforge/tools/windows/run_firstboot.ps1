# === NoemaForge File Header ===
# File: noemaforge/tools/windows/run_firstboot.ps1
# Zone: release/package
# Version: 0.31.21.alpha
# Created: 2026-05-20
# Modified: 2026-05-20
# Purpose: Thin Windows wrapper over the cross-platform Python prep core firstboot staging command.
# Inputs: RepoRoot, LabRoot, AutoManifest, PythonExe and ModelProfile parameters.
# Outputs: JSON firstboot staging plan from noemaforge_prep_core.py.
# Side effects: Limited to requested lab/outbox paths.
# Tests: noemaforge/tests/test_cross_platform_prep_core_runtime.py
# Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
# === End NoemaForge File Header ===

param(
  [Alias("Root","BrainRoot")]
  [string]$RepoRoot = "",
  [string]$LabRoot = "",
  [switch]$AutoManifest,
  [string]$PythonExe = "",
  [ValidateSet("minimal","balanced","writer","research","gpu-heavy")]
  [string]$ModelProfile = "minimal",
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"

if (-not $RepoRoot -or $RepoRoot.Trim() -eq "") {
  $RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\.." )).Path
}
if (-not $LabRoot -or $LabRoot.Trim() -eq "") {
  $LabRoot = (Join-Path $RepoRoot "..\noemaforge-lab")
}
if (-not $PythonExe -or $PythonExe.Trim() -eq "") {
  if ($env:NOEMAFORGE_PYTHON) { $PythonExe = $env:NOEMAFORGE_PYTHON } else { $PythonExe = "py" }
}

$Core = Join-Path $RepoRoot "tools\prep\noemaforge_prep_core.py"
$Args = @($Core, "firstboot", "--repo-root", $RepoRoot, "--lab-root", $LabRoot, "--model-profile", $ModelProfile)
if ($AutoManifest) { $Args += "--auto-manifest" }
if ($DryRun) { $Args += "--dry-run" }

& $PythonExe @Args
exit $LASTEXITCODE
