# === NoemaForge File Header ===
# File: noemaforge/tools/windows/make_checked.ps1
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
File: tools/windows/make_checked.ps1
Purpose: Provide the script 'make_checked'.
Invoked by: Windows operator scripts, dot-sourcing, or direct PowerShell execution.
Inputs: Parameters and environment variables declared in the script.
Outputs: Console output, spawned processes, and filesystem changes as implemented below.
AutoDoc: refreshed 2026-04-09 (heuristic)
#>

param(
  # Optional explicit brain root. Accepts either:
  #   - <root>\seed\noemaforge
  #   - <root>\noemaforge
  [string]$Root = "",
  # Output file. Default: <brain_root>\24.chexked
  [string]$Out = "",
  # Optional zip archive path to hash (e.g. noemaforge-flat-v0.24.0.zip)
  [string]$Zip = "",
  # Optional explicit python.exe path (if python is not on PATH)
  [string]$PythonExe = ""
)

$ErrorActionPreference = "Stop"

# === NoemaForge Autodoc Function Header ===
# Function: FindBrainRoot
# Purpose: Provide the PowerShell routine 'FindBrainRoot'.
# Inputs:
#   - $StartDir
# Called by:
#   - Wrapper scripts, direct PowerShell execution, or dot-sourced callers.
# Outputs: Console output and side effects implemented in the body below.
# === End NoemaForge Autodoc Function Header ===
function FindBrainRoot([string]$StartDir) {
  $d = Resolve-Path $StartDir -ErrorAction SilentlyContinue
  if (!$d) { return "" }

  for ($i = 0; $i -lt 10; $i++) {
    $cand = $d.Path

    $m1 = Join-Path $cand "manifest.yaml"
    $s1 = Join-Path $cand "checksums\SHA256SUMS"
    if ((Test-Path $m1) -and (Test-Path $s1)) {
      return $cand
    }

    $sb = Join-Path $cand "seed\noemaforge"
    $m2 = Join-Path $sb "manifest.yaml"
    $s2 = Join-Path $sb "checksums\SHA256SUMS"
    if ((Test-Path $m2) -and (Test-Path $s2)) {
      return (Resolve-Path $sb).Path
    }

    $parent = Split-Path -Parent $cand
    if (!$parent -or ($parent -eq $cand)) { break }
    $d = Resolve-Path $parent -ErrorAction SilentlyContinue
    if (!$d) { break }
  }
  return ""
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Brain = ""
if ($Root -and ($Root.Trim().Length -gt 0)) {
  $Brain = FindBrainRoot $Root
} else {
  $Brain = FindBrainRoot $ScriptDir
}

if (!$Brain -or ($Brain.Trim().Length -eq 0)) {
  throw "Could not locate Brain root from '$ScriptDir'. Pass -Root <path to noemaforge root>."
}

. (Join-Path $ScriptDir "lib_python.ps1")
$pyInfo = ResolveNoemaForgePython -BrainRoot $Brain -PythonExeParam $PythonExe -MinVersion "3.10"
if ($pyInfo.kind -eq "none") {
  throw "Python 3.10+ not found. Install Python or pass -PythonExe <path to python.exe> or set env:NOEMAFORGE_PYTHON."
}

$env:PYTHONDONTWRITEBYTECODE = "1"

if (!$Out -or ($Out.Trim().Length -eq 0)) {
  $Out = Join-Path $Brain "24.chexked"
}

$checker = Join-Path $Brain "tools\checker\noemaforge_checked.py"
if (!(Test-Path $checker)) {
  throw "noemaforge_checked.py not found: $checker"
}

Write-Host "Creating checked attestation:" -ForegroundColor Cyan
Write-Host "  BrainRoot: $Brain"
Write-Host "  Out:       $Out"
if ($Zip -and ($Zip.Trim().Length -gt 0)) {
  Write-Host "  Zip:       $Zip"
}
Write-Host ("  Python:    " + $pyInfo.exe + " " + ($pyInfo.args -join " ") + " (v" + $pyInfo.version + ")")

$args = @($checker, "--root", $Brain, "--out", $Out)
if ($Zip -and ($Zip.Trim().Length -gt 0)) {
  $args += @("--zip", $Zip)
}

& $pyInfo.exe @($pyInfo.args) @args

if ($LASTEXITCODE -eq 0) {
  Write-Host "OK: 24.chexked created." -ForegroundColor Green
} elseif ($LASTEXITCODE -eq 1) {
  Write-Host "WARN: created, but warnings were reported." -ForegroundColor Yellow
} else {
  Write-Host "FAIL: created, but failures were reported." -ForegroundColor Red
}

exit $LASTEXITCODE
