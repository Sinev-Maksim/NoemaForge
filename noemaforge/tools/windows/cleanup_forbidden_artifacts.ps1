# === NoemaForge File Header ===
# File: noemaforge/tools/windows/cleanup_forbidden_artifacts.ps1
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
File: tools/windows/cleanup_forbidden_artifacts.ps1
Purpose: Provide the script 'cleanup_forbidden_artifacts'.
Invoked by: Windows operator scripts, dot-sourcing, or direct PowerShell execution.
Inputs: Parameters and environment variables declared in the script.
Outputs: Console output, spawned processes, and filesystem changes as implemented below.
AutoDoc: refreshed 2026-04-09 (heuristic)
#>

param(
  [string]$Root = ""
)

$ErrorActionPreference = "Continue"

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

  for ($i = 0; $i -lt 8; $i++) {
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

if ($Root -eq "") {
  $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
  $Brain = FindBrainRoot $ScriptDir
} else {
  $Brain = FindBrainRoot $Root
}

if (!$Brain -or ($Brain.Trim().Length -eq 0)) {
  throw "Could not locate Brain root. Provide -Root <path to noemaforge root>."
}

Write-Host "Cleaning forbidden artifacts under: $Brain"

$pyc = Get-ChildItem -Path $Brain -Recurse -Force -File -Filter "*.pyc" -ErrorAction SilentlyContinue
$cacheDirs = Get-ChildItem -Path $Brain -Recurse -Force -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue

$deletedPyc = 0
foreach ($f in $pyc) {
  try { Remove-Item -Force $f.FullName; $deletedPyc += 1 } catch { }
}

$deletedDirs = 0
foreach ($d in $cacheDirs) {
  try { Remove-Item -Recurse -Force $d.FullName; $deletedDirs += 1 } catch { }
}

Write-Host "Done. Deleted *.pyc: $deletedPyc; deleted __pycache__ dirs: $deletedDirs"
